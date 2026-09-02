# -*- encoding=utf8 -*-
"""ROI 校准工具

用途：把手机停在 BOSS直聘「岗位详情页」，运行本脚本。
      它会截一张屏、跑一次全屏 OCR，然后按屏幕从上到下的顺序列出
      每一条文字及其归一化坐标，你照着结果把 config.py 里的
      ROI_JOB_TITLE / ROI_COMPANY / ROI_BUTTON 改成真实值。

输出示例：
    [0.312] y=10.2%~13.5%  x= 3.1%~48.0%  conf=0.97  高级软件工程师
                                                       ^ 这就是岗位标题区
"""
__author__ = "BOSS-Auto-Greeting"

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from airtest.core.api import *            # noqa: F401,F403
from airtest.cli.parser import cli_setup

import config as cfg
from ocr_helper import ENGINE, OCREngine, Detection  # noqa: F401


def main():
    if not cli_setup():
        auto_setup(__file__, logdir=True, devices=[cfg.DEVICE_URI])

    from airtest.core.api import G

    w, h = G.DEVICE.get_current_resolution()
    print("=" * 74)
    print("ROI 校准 | 分辨率 %dx%d" % (w, h))
    print("=" * 74)

    print("[1/3] 截屏 ...")
    screen = G.DEVICE.snapshot(quality=99)
    if screen is None:
        print("[error] 截图失败，手机画面没投过来？")
        return

    # 落盘一张，方便对照
    try:
        import cv2
        import airtest.core.settings as settings
        logdir = getattr(settings, "LOG_DIR", "") or os.path.dirname(os.path.abspath(__file__))
        d = os.path.join(logdir, "shots")
        if not os.path.isdir(d):
            os.makedirs(d)
        p = os.path.join(d, "calibrate_%s.png" % time.strftime("%H%M%S"))
        # 用 imencode + tofile：Windows 下 cv2.imwrite 不支持中文路径
        ok, buf = cv2.imencode(".png", screen[:, :, ::-1])
        if ok:
            buf.tofile(p)
            print("      原图已存: %s" % p)
        else:
            print("      [warn] 原图编码失败")
    except Exception as e:
        print("      [warn] 原图保存失败: %s" % e)

    print("[2/3] OCR 识别中（首次会下载模型，慢）...")
    t0 = time.time()
    dets = ENGINE.dump(screen)          # conf_min=0，保留全部结果
    print("      耗时 %.1fs，识别到 %d 条" % (time.time() - t0, len(dets)))

    print("[3/3] 结果（按屏幕从上到下排序）：")
    print("-" * 74)
    print("  %-18s %-18s %-6s %s" % ("纵向范围", "横向范围", "置信度", "文本"))
    print("-" * 74)

    H, W = screen.shape[:2]
    dets.sort(key=lambda d: d.bbox[1])
    for d in dets:
        x, y, bw, bh = d.bbox
        y1, y2 = y / H * 100.0, (y + bh) / H * 100.0
        x1, x2 = x / W * 100.0, (x + bw) / W * 100.0
        flag = "" if d.conf >= cfg.OCR_CONF_MIN else "  (低于阈值，会被丢弃)"
        print("  y=%5.1f%%~%5.1f%%  x=%5.1f%%~%5.1f%%  %.2f  %s%s" % (
            y1, y2, x1, x2, d.conf, d.text, flag))
    print("-" * 74)

    print("\n对照 config.py 当前配置：")
    for name, roi in (("ROI_BUTTON", cfg.ROI_BUTTON),
                      ("ROI_JOB_TITLE", cfg.ROI_JOB_TITLE),
                      ("ROI_COMPANY", cfg.ROI_COMPANY)):
        print("  %-14s y=%5.1f%%~%5.1f%%  x=%5.1f%%~%5.1f%%" % (
            name, roi[1] * 100, roi[3] * 100, roi[0] * 100, roi[2] * 100))

    # 顺带验证一下当前的按钮区能不能识别到关键文案
    print("\n按钮区(ROI_BUTTON)实测识别：%s" % (ENGINE.texts(screen, cfg.ROI_BUTTON) or "空 —— 需要调整!"))
    print("标题区(ROI_JOB_TITLE)实测：%s" % (ENGINE.texts(screen, cfg.ROI_JOB_TITLE) or "空 —— 需要调整!"))
    print("公司区(ROI_COMPANY)实测：%s" % (ENGINE.texts(screen, cfg.ROI_COMPANY) or "空 —— 需要调整!"))
    print("\n把上面三行的实际范围填回 config.py 即可。")


if __name__ == "__main__":
    main()
