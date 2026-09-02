# -*- coding=utf8 -*-
"""滑动方向探测：试 4 种方向（左右上下），找出能让岗位标题变化的那种"""
from __future__ import annotations
import os, subprocess, sys, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import cv2, numpy as np
from ocr_helper import ENGINE
import config as cfg

ADB = r"E:\AutoPlayGame\AirtestIDE-win-1.2.17\AirtestIDE\airtest\core\android\static\adb\windows\adb.exe"

def adb(*a, binary=False):
    r = subprocess.run([ADB]+list(a), capture_output=True, timeout=30)
    return r.stdout if binary else r.stdout.decode("utf-8","ignore")

def pick_serial():
    out = adb("devices")
    for l in out.splitlines():
        if "\tdevice" in l: return l.split("\t")[0]
    return None

def grab(serial):
    raw = adb("-s", serial, "exec-out", "screencap", "-p", binary=True)
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

def tap(s, nx, ny, w, h):
    adb("-s", s, "shell", "input", "tap", str(max(1, min(int(round(w*nx)), w-1))), str(max(1, min(int(round(h*ny)), h-1))))

def swipe(s, x1, y1, x2, y2, w, h, dur=0.5):
    def c(v, lim): return max(1, min(int(round(v)), lim-1))
    adb("-s", s, "shell", "input", "swipe", str(c(x1,w)), str(c(y1,h)), str(c(x2,w)), str(c(y2,h)), str(int(dur*1000)))

def title_of(img):
    return " | ".join(ENGINE.texts(img, cfg.ROI_JOB_TITLE)) or "(空)"

def main():
    s = pick_serial()
    if not s: return print("[error] 无设备")
    img0 = grab(s)
    H, W = img0.shape[:2]
    print("设备 %s  屏 %dx%d" % (s, W, H))
    base_title = title_of(img0)
    print("当前岗位: %s\n" % base_title)

    cy = int(H * 0.5)  # 屏中央
    cy_top = int(H * 0.25)
    cy_bot = int(H * 0.75)
    cx_left = int(W * 0.2)
    cx_right = int(W * 0.8)

    # 4 个候选方向，每个测一次
    candidates = [
        ("左滑 45%  (详情页横向切换)",   (cx_right, cy, cx_left, cy)),
        ("右滑 45%  (回上一个?)",        (cx_left, cy, cx_right, cy)),
        ("上滑 50%  (推荐列表向上滚)",   (cx_left, cy_bot, cx_left, cy_top)),
        ("下滑 50%  (推荐列表向下滚)",   (cx_left, cy_top, cx_left, cy_bot)),
        ("上滑 80%  (大手势翻页)",       (cx_left, cy_bot, cx_left, int(H*0.1))),
    ]

    for name, (x1, y1, x2, y2) in candidates:
        # 滑之前确保回到当前岗位
        img_b = grab(s)
        tb = title_of(img_b)
        swipe(s, x1, y1, x2, y2, W, H, 0.5)
        time.sleep(1.5)
        img_a = grab(s)
        ta = title_of(img_a)
        changed = (tb != ta)
        mark = "[切换成功]" if changed else "[未变化]"
        print("%-35s %s" % (name, mark))
        print("    滑前: %s" % tb)
        print("    滑后: %s" % ta)
        # 切走之后，滑回来（用反向 / 重抓后判断）
        if changed:
            # 多数情况用反向滑回去
            rx1, ry1, rx2, ry2 = x2, y2, x1, y1
            swipe(s, rx1, ry1, rx2, ry2, W, H, 0.5)
            time.sleep(1.5)
            img_r = grab(s)
            tr = title_of(img_r)
            print("    反向回去: %s" % tr)
        print()

    print("=" * 60)
    print("结论：找打标 [切换成功] 的方向，那就是岗位切换手势。")
    print("把它填回 config.py 的 SWIPE_START_POS 和 SWIPE_DX/DY。")

if __name__ == "__main__":
    main()
