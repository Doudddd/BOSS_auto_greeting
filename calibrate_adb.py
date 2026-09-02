# -*- encoding=utf8 -*-
"""零侵入校准工具（adb 版）

与 calibrate.py 的区别：
  calibrate.py    走 airtest 连接，会启动 minicap/minitouch，可能打断 AirtestIDE 投屏
  calibrate_adb.py 只用 adb exec-out screencap 取帧，不占用任何连接，可在 IDE 运行时安全使用

用途：把手机停在 BOSS直聘「岗位详情页」，运行本脚本。
      输出屏幕上每一条文字的纵向/横向百分比范围，照着填回 config.py 的 ROI。
"""
__author__ = "BOSS-Auto-Greeting"

import os
import subprocess
import sys
import time

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

import cv2
import numpy as np

from ocr_helper import ENGINE
import config as cfg

ADB = r"E:\AutoPlayGame\AirtestIDE-win-1.2.17\AirtestIDE\airtest\core\android\static\adb\windows\adb.exe"


def pick_serial():
    """自动挑一个在线设备；多设备时返回第一个"""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return sys.argv[1]
    try:
        out = subprocess.run([ADB, "devices"], capture_output=True, timeout=20)
        lines = out.stdout.decode("utf-8", "ignore").splitlines()
        serials = [l.split("\t")[0] for l in lines if "\tdevice" in l]
        return serials[0] if serials else None
    except Exception:
        return None


def grab(serial):
    """二进制安全抓屏，避免 Windows shell 换行符破坏 PNG"""
    r = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"],
                       capture_output=True, timeout=30)
    if not r.stdout:
        raise RuntimeError("adb 无输出: %s" % r.stderr.decode("utf-8", "ignore")[:200])
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("PNG 解码失败，收到 %d 字节" % len(r.stdout))
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def main():
    serial = pick_serial()
    if not serial:
        print("[error] 没找到在线设备。请先用 adb 或 AirtestIDE 连上手机。")
        return

    print("=" * 78)
    print("零侵入校准 | 设备 %s" % serial)
    print("=" * 78)

    screen = grab(serial)
    H, W = screen.shape[:2]
    print("抓屏成功: %dx%d" % (W, H))

    ok, buf = cv2.imencode(".png", screen[:, :, ::-1])
    if ok:
        p = os.path.join(D, "log", "calibrate_latest.png")
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            buf.tofile(p)
            print("原图已存: %s" % p)
        except Exception as e:
            print("[warn] 原图保存失败: %s" % e)

    print("\nOCR 识别中 ...")
    t0 = time.time()
    dets = ENGINE.dump(screen)
    print("耗时 %.2fs，识别 %d 条\n" % (time.time() - t0, len(dets)))

    print("-" * 78)
    print("  %-20s %-20s %-6s %s" % ("纵向范围", "横向范围", "置信度", "文本"))
    print("-" * 78)
    dets.sort(key=lambda d: d.bbox[1])
    for d in dets:
        x, y, bw, bh = d.bbox
        y1, y2 = y / H * 100.0, (y + bh) / H * 100.0
        x1, x2 = x / W * 100.0, (x + bw) / W * 100.0
        flag = "" if d.conf >= cfg.OCR_CONF_MIN else "   <-低于阈值会被丢弃"
        print("  y=%5.1f%%~%5.1f%%     x=%5.1f%%~%5.1f%%    %.2f  %s%s"
              % (y1, y2, x1, x2, d.conf, d.text, flag))
    print("-" * 78)

    print("\n【当前配置 vs 实测】（【空】表示该区域没框中内容，需要调整）")
    for name, roi in (("ROI_BUTTON", cfg.ROI_BUTTON),
                      ("ROI_JOB_TITLE", cfg.ROI_JOB_TITLE),
                      ("ROI_COMPANY", cfg.ROI_COMPANY)):
        got = ENGINE.texts(screen, roi)
        print("  %-14s y=%5.1f%%~%5.1f%%  ->  %s"
              % (name, roi[1] * 100, roi[3] * 100, got if got else "【空】"))

    print("\n【按钮态判定】")
    got_ready = ENGINE.has(screen, cfg.TEXT_READY, cfg.ROI_BUTTON)
    got_done = ENGINE.has(screen, cfg.TEXT_ALREADY, cfg.ROI_BUTTON)
    print("  「%s」: %s" % (cfg.TEXT_READY, got_ready))
    print("  「%s」: %s" % (cfg.TEXT_ALREADY, got_done))
    if not got_ready and not got_done:
        print("\n  [提示] 当前屏幕没有招呼按钮 —— 确认手机停在 BOSS直聘「岗位详情页」了吗？")

    f = ENGINE.find(screen, cfg.TEXT_READY, cfg.ROI_BUTTON)
    if f:
        print("\n  「%s」实测中心归一化坐标: (%.4f, %.4f)   当前配置: %s"
              % (cfg.TEXT_READY, f.center_norm[0], f.center_norm[1], cfg.BTN_COMMUNICATE_POS))
        print("  若偏差大，把这个值填回 config.py 的 BTN_COMMUNICATE_POS")


if __name__ == "__main__":
    main()
