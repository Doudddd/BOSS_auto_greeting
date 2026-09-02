# -*- coding=utf8 -*-
"""单轮真机测试：检测 1 个岗位 -> 沟通/跳过 -> 返回 -> 左滑切换下一个

只跑一个岗位，用来验证整条链路是否通。

为什么不用 airtest 连接：
    airtest 连接会起 minicap/minitouch，可能打断正在投屏的 AirtestIDE。
    本脚本全程走 adb（exec-out screencap / input tap / input swipe），
    零占用，IDE 投屏可以一直开着。

用法：
    python test_one.py              # 完整跑一轮（会真的点「立即沟通」）
    python test_one.py --dry-run    # 只检测不操作，用来确认判定是否正确
    python test_one.py --serial XXX # 指定设备
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ocr_helper import ENGINE  # noqa: E402
import config as cfg  # noqa: E402

ADB = r"E:\AutoPlayGame\AirtestIDE-win-1.2.17\AirtestIDE\airtest\core\android\static\adb\windows\adb.exe"
LOGDIR = os.path.join(D, "log")


# ==================== adb 封装 ====================
def adb(*args, binary=False, timeout=30):
    r = subprocess.run([ADB] + list(args), capture_output=True, timeout=timeout)
    return r.stdout if binary else r.stdout.decode("utf-8", "ignore")


def pick_serial(argv):
    for a in argv[1:]:
        if not a.startswith("-") and len(a) > 3:
            return a
    out = adb("devices")
    serials = [l.split("\t")[0] for l in out.splitlines() if "\tdevice" in l]
    return serials[0] if serials else None


def grab(serial):
    """二进制安全抓屏（重定向到文件会被 Windows 换行符转换破坏 PNG）"""
    raw = adb("-s", serial, "exec-out", "screencap", "-p", binary=True)
    if not raw:
        raise RuntimeError("adb 无输出")
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("PNG 解码失败，收到 %d 字节" % len(raw))
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def size(serial):
    out = adb("-s", serial, "shell", "wm size")
    for tok in out.replace("Physical size:", "").split():
        if "x" in tok:
            w, h = tok.split("x")
            return int(w), int(h)
    img = grab(serial)
    return img.shape[1], img.shape[0]


def tap(serial, nx, ny, w, h):
    x = max(1, min(int(round(w * nx)), w - 1))
    y = max(1, min(int(round(h * ny)), h - 1))
    adb("-s", serial, "shell", "input", "tap", str(x), str(y))
    return x, y


def swipe(serial, nx, ny, dx, dy, w, h, duration=0.5):
    x1 = max(1, min(int(round(w * nx)), w - 1))
    y1 = max(1, min(int(round(h * ny)), h - 1))
    x2 = max(1, min(int(round(w * (nx + dx))), w - 1))
    y2 = max(1, min(int(round(h * (ny + dy))), h - 1))
    ms = int(duration * 1000)
    adb("-s", serial, "shell", "input", "swipe",
        str(x1), str(y1), str(x2), str(y2), str(ms))
    return (x1, y1), (x2, y2)


def save(img, tag):
    os.makedirs(LOGDIR, exist_ok=True)
    p = os.path.join(LOGDIR, "test_one_%s_%s.png" % (tag, time.strftime("%H%M%S")))
    ok, buf = cv2.imencode(".png", img[:, :, ::-1])
    if ok:
        buf.tofile(p)  # imwrite 不支持中文路径，必须用 imencode + tofile
    return p


def shot(serial, tag):
    """抓屏并存档，返回图像"""
    img = grab(serial)
    p = save(img, tag)
    return img, p


# ==================== 业务判定 ====================
def read_job(img):
    """读取岗位标题 + 公司名文本"""
    title = ENGINE.texts(img, cfg.ROI_JOB_TITLE)
    company = ENGINE.texts(img, cfg.ROI_COMPANY)
    return title, company


def match_blacklist(texts):
    """子串匹配黑名单，返回命中的关键词"""
    for kw in cfg.BLACK_KEYWORDS:
        for t in texts:
            if kw in t:
                return kw
    return None


def hit_white(texts):
    for kw in cfg.WHITE_KEYWORDS:
        for t in texts:
            if kw in t:
                return kw
    return None


def btn_state(img):
    """返回 'done'(继续沟通=已沟通过) / 'ready'(立即沟通) / None"""
    if ENGINE.has(img, cfg.TEXT_ALREADY, cfg.ROI_BUTTON):
        return "done"
    if ENGINE.has(img, cfg.TEXT_READY, cfg.ROI_BUTTON):
        return "ready"
    return None


# ==================== 主流程 ====================
def main():
    argv = sys.argv
    dry = "--dry-run" in argv

    serial = pick_serial(argv)
    if not serial:
        print("[error] 没找到在线设备。请先用 adb 或 AirtestIDE 连上手机。")
        return 1

    W, H = size(serial)
    print("=" * 78)
    print("单轮测试 | 设备 %s | 屏幕 %dx%d | %s"
          % (serial, W, H, "检测模式(不操作)" if dry else "执行模式"))
    print("=" * 78)

    # ---------- 阶段 1：检测当前岗位 ----------
    print("\n[阶段1] 读取当前岗位")
    img, p = shot(serial, "before")
    print("  截图: %s" % p)

    t0 = time.time()
    title, company = read_job(img)
    state = btn_state(img)
    print("  OCR 耗时 %.2fs" % (time.time() - t0))
    print("  岗位标题区: %s" % (title if title else "【空 —— ROI 没对准!】"))
    print("  公司名区  : %s" % (company if company else "【空 —— ROI 没对准!】"))
    print("  按钮态    : %s" % {"ready": "立即沟通(可沟通)",
                              "done": "继续沟通(已沟通过)",
                              None: "【未识别到按钮 —— 确认在岗位详情页?】"}[state])

    if state is None:
        print("\n[中止] 底部没找到招呼按钮，请确认手机停在 BOSS直聘「岗位详情页」。")
        return 2

    # ---------- 阶段 2：黑名单判定 ----------
    print("\n[阶段2] 黑名单过滤（模式: %s）" % cfg.FILTER_SCOPE)
    if cfg.FILTER_SCOPE == "full_page":
        pool = ENGINE.texts(img)
    else:
        pool = title + company

    kw = match_blacklist(pool)
    wk = hit_white(pool) if cfg.FILTER_SCOPE == "full_page" else None
    print("  待检文本: %s" % pool)
    print("  命中黑名单: %s" % (kw if kw else "无"))
    if wk:
        print("  命中白名单: %s -> 豁免" % wk)

    skip = bool(kw) and not (wk and cfg.FILTER_SCOPE == "full_page")

    if state == "done":
        print("\n[决策] 该岗位已沟通过 -> 跳过")
        skip = True
    elif skip:
        print("\n[决策] 命中黑名单「%s」-> 跳过" % kw)
    else:
        print("\n[决策] 未命中黑名单 -> 执行「立即沟通」")

    if dry:
        print("\n[dry-run] 检测到此为止，未执行任何点击/滑动。")
        print("  确认判定无误后，去掉 --dry-run 再跑一次。")
        return 0

    # ---------- 阶段 3：沟通 or 跳过 ----------
    if skip:
        if cfg.SAVE_SKIP_SHOT:
            print("  跳过截图: %s" % save(img, "skip"))
    else:
        x, y = tap(serial, cfg.BTN_COMMUNICATE_POS[0], cfg.BTN_COMMUNICATE_POS[1], W, H)
        print("\n[阶段3] 点击「立即沟通」 像素(%d, %d)" % (x, y))

        # 轮询等待离开详情页：底部「立即沟通」消失
        left = False
        t0 = time.time()
        while time.time() - t0 < cfg.TIMEOUT_LEAVE_DETAIL:
            time.sleep(cfg.POLL_INTERVAL)
            cur = grab(serial)
            if btn_state(cur) is None:
                left = True
                break
        print("  离开详情页: %s (耗时 %.1fs)" % ("是" if left else "否", time.time() - t0))
        if not left:
            print("  [warn] 未检测到页面变化，可能没点中。截图: %s"
                  % save(grab(serial), "nochange"))

        time.sleep(cfg.STAY_IN_CHAT)
        chat_shot = save(grab(serial), "chat")
        print("  聊天页截图: %s" % chat_shot)

        # 返回
        bx, by = tap(serial, cfg.BTN_BACK_POS[0], cfg.BTN_BACK_POS[1], W, H)
        print("  点击返回 像素(%d, %d)" % (bx, by))

        back = False
        t0 = time.time()
        while time.time() - t0 < cfg.TIMEOUT_BACK_DETAIL:
            time.sleep(cfg.POLL_INTERVAL)
            cur = grab(serial)
            # 回到详情页 = 出现「立即沟通」或「继续沟通」任一
            if btn_state(cur) is not None:
                back = True
                break
        print("  回到详情页: %s (耗时 %.1fs, 按钮态=%s)"
              % ("是" if back else "否", time.time() - t0,
                 btn_state(grab(serial)) if not back else "ok"))
        if not back:
            cur = grab(serial)
            print("  [warn] 未确认回到详情页，按钮态=%s。截图: %s"
                  % (btn_state(cur), save(cur, "noback")))

    # ---------- 阶段 4：左滑切换下一个岗位 ----------
    print("\n[阶段4] 左滑切换下一个岗位")
    before = grab(serial)
    b_title, _ = read_job(before)

    p1, p2 = swipe(serial, cfg.SWIPE_START_POS[0], cfg.SWIPE_START_POS[1],
                   cfg.SWIPE_DX, cfg.SWIPE_DY, W, H, cfg.SWIPE_DURATION)
    dx_px = p2[0] - p1[0]
    print("  滑动 %s -> %s (横向 %d px = %.1f%% 屏宽)"
          % (p1, p2, dx_px, abs(dx_px) / float(W) * 100))

    time.sleep(cfg.SETTLE_AFTER_SWIPE)
    after, ap = shot(serial, "after")
    a_title, a_company = read_job(after)
    print("  滑动后岗位标题区: %s" % (a_title if a_title else "【空 —— ROI 没对准!】"))
    print("  滑动后公司名区  : %s" % (a_company if a_company else "【空 —— ROI 没对准!】"))

    same = (b_title == a_title)
    print("\n  切换结果: %s" % ("【未变化 —— 滑动距离不够，需要加大 SWIPE_DX 或右移 SWIPE_START_POS】"
                            if same else "成功切到下一个岗位"))
    if same:
        print("  建议把 config.py 的 SWIPE_START_POS 起点右移到 (0.8, 0.5) + SWIPE_DX=-0.6 再试"
              % cfg.SWIPE_DX)

    # ---------- 汇总 ----------
    print("\n" + "=" * 78)
    print("测试结束")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
