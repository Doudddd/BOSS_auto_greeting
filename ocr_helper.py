# -*- encoding=utf8 -*-
"""OCR 适配层 —— 封装 onnxocr-ppocrv5

对外只暴露 OCREngine 一个类：
    detect(img, roi)        -> [Detection, ...]  识别指定区域
    texts(img, roi)         -> [str, ...]        只要文本
    find(img, kw, roi)      -> Detection | None  子串查找第一个命中
    has(img, kw, roi)       -> bool              是否存在
    dump(img, roi)          -> [Detection, ...]  校准用，不过滤

归一化 ROI：(x1, y1, x2, y2)，取值 0~1。

注意：onnxocr-ppocrv5 的真实入口是 onnxocr.onnx_paddleocr.ONNXPaddleOcr，
      不是 PaddleOCR；onnxruntime 是该包的 extra 依赖，需单独安装
      （pip install "onnxocr-ppocrv5[onnx]"），否则 import 阶段就会失败。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from config import OCR_CONF_MIN, OCR_LANG, OCR_USE_CLS  # noqa: E402


class Detection(object):
    """一条 OCR 识别结果"""

    __slots__ = ("text", "conf", "bbox", "center", "center_norm")

    def __init__(self, text, conf, bbox, center, center_norm):
        self.text = text
        self.conf = float(conf)
        self.bbox = bbox                  # (x, y, w, h) 像素
        self.center = center              # (cx, cy) 像素
        self.center_norm = center_norm    # (cx/W, cy/H) 归一化

    def __repr__(self):
        return "<OCR %r conf=%.2f center_norm=(%.3f, %.3f)>" % (
            self.text, self.conf, self.center_norm[0], self.center_norm[1]
        )


class OCREngine(object):
    """OCR 引擎（懒加载，首次调用时才初始化模型）"""

    def __init__(self, lang=None, conf_min=None, use_cls=None):
        self.lang = lang or OCR_LANG
        self.conf_min = OCR_CONF_MIN if conf_min is None else conf_min
        self.use_cls = OCR_USE_CLS if use_cls is None else use_cls
        self._ocr = None

    # ---------------- 引擎 ----------------
    def _ensure_engine(self):
        if self._ocr is not None:
            return
        try:
            from onnxocr.onnx_paddleocr import ONNXPaddleOcr
        except ImportError as e:
            raise ImportError(
                "OCR 引擎不可用。请在本项目使用的 Python 环境中执行：\n"
                '    pip install "onnxocr-ppocrv5[onnx]"\n'
                "（onnxruntime 是 extra 依赖，不会随主包自动安装）\n"
                "原始错误: %s" % e
            )

        # onnxocr 默认打 INFO 日志，会刷屏，压到 WARNING
        import logging
        logger = logging.getLogger("onnxocr")
        logger.setLevel(logging.WARNING)

        # 注意：该实现没有 lang / use_gpu 参数，传了也不生效
        self._ocr = ONNXPaddleOcr(logger=logger, use_angle_cls=self.use_cls)

    # ---------------- 工具 ----------------
    @staticmethod
    def _crop(img, roi):
        """按归一化 ROI 裁剪，返回 (裁剪图, (offset_x, offset_y))"""
        if roi is None:
            return img, (0, 0)
        h, w = img.shape[:2]
        x1 = int(round(w * roi[0]))
        y1 = int(round(h * roi[1]))
        x2 = int(round(w * roi[2]))
        y2 = int(round(h * roi[3]))
        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        if x2 <= x1 or y2 <= y1:
            return img, (0, 0)
        return img[y1:y2, x1:x2], (x1, y1)

    @staticmethod
    def _unwrap(raw):
        """兼容返回结构 [[det, det, ...]]（onnxocr 实际返回）与 [det, ...]"""
        if not raw:
            return []
        try:
            probe = raw[0][0][0]
            is_flat = np.isscalar(probe) or isinstance(probe, (int, float, np.number))
        except (IndexError, TypeError, KeyError):
            return []
        return list(raw) if is_flat else list(raw[0])

    # ---------------- 核心 ----------------
    def detect(self, img, roi=None, conf_min=None):
        """识别图像（可选 ROI 裁剪），返回按置信度过滤后的 Detection 列表"""
        self._ensure_engine()
        crop, (ox, oy) = self._crop(img, roi)
        if crop is None or crop.size == 0:
            return []

        raw = self._ocr.ocr(crop, cls=self.use_cls)
        H, W = img.shape[:2]
        limit = self.conf_min if conf_min is None else conf_min

        out = []
        for line in self._unwrap(raw):
            try:
                box = line[0]
                text, conf = line[1]
            except (IndexError, TypeError, ValueError):
                continue
            conf = float(conf)
            if conf < limit:
                continue
            xs = [float(p[0]) + ox for p in box]
            ys = [float(p[1]) + oy for p in box]
            x, y = min(xs), min(ys)
            bw, bh = max(xs) - x, max(ys) - y
            cx, cy = x + bw / 2.0, y + bh / 2.0
            out.append(Detection(
                text=str(text), conf=conf,
                bbox=(x, y, bw, bh),
                center=(cx, cy),
                center_norm=(cx / W if W else 0.0, cy / H if H else 0.0),
            ))
        return out

    # ---------------- 便捷方法 ----------------
    def texts(self, img, roi=None):
        return [d.text for d in self.detect(img, roi)]

    def find(self, img, keyword, roi=None, substring=True):
        """子串（或全等）查找，返回第一个命中的 Detection"""
        for d in self.detect(img, roi):
            if (keyword in d.text) if substring else (keyword == d.text):
                return d
        return None

    def has(self, img, keyword, roi=None, substring=True):
        return self.find(img, keyword, roi, substring) is not None

    def dump(self, img, roi=None):
        """校准用：返回全部识别结果（含低置信度，conf_min=0）"""
        return self.detect(img, roi, conf_min=0.0)


ENGINE = OCREngine()
