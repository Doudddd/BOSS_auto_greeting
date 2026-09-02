# -*- encoding=utf8 -*-
"""BOSS直聘 自动打招呼

前置条件：手机已停在 BOSS直聘「岗位详情页」（用户手动打开）。
          脚本只做两件事：① 判断该岗位是否值得打招呼 ② 切换下一个岗位。

用法：
    AirtestIDE 直接运行（默认 30 轮）
    命令行：python auto_greeting.py --rounds 50

依赖：airtest、onnxocr-ppocrv5（装在与 AirtestIDE 关联的 Python 环境中）
"""
__author__ = "BOSS-Auto-Greeting"

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from airtest.core.api import *            # noqa: F401,F403  touch/swipe/sleep/G/log
from airtest.cli.parser import cli_setup

import config as cfg
from ocr_helper import ENGINE


# ==================== 全局状态 ====================
STATS = {"success": 0, "skip": 0, "fail": 0}
REASONS = {"skip": {}, "fail": {}}
_consecutive_fail = 0
_log_dir = ""


# ==================== 基础工具 ====================
def _init():
    """连接设备并确定日志目录"""
    global _log_dir
    if not cli_setup():
        auto_setup(__file__, logdir=True, devices=[cfg.DEVICE_URI])
    try:
        import airtest.core.settings as settings
        _log_dir = getattr(settings, "LOG_DIR", "") or ""
    except Exception:
        _log_dir = ""
    if not _log_dir:
        _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")


def get_resolution():
    from airtest.core.api import G
    return G.DEVICE.get_current_resolution()


def shot():
    """截当前屏，返回 ndarray (H, W, 3) RGB"""
    from airtest.core.api import G
    return G.DEVICE.snapshot(quality=99)


def to_px(norm_pos, w, h):
    """归一化坐标 -> 像素坐标，并做边界钳制（防止算到屏幕外）"""
    x = int(round(w * norm_pos[0]))
    y = int(round(h * norm_pos[1]))
    return max(1, min(x, w - 1)), max(1, min(y, h - 1))


def save_shot(screen, tag):
    """保存截图到 log/shots/"""
    if screen is None:
        return None
    try:
        import cv2
        d = os.path.join(_log_dir, "shots")
        if not os.path.isdir(d):
            os.makedirs(d)
        name = "%s_%s.png" % (tag, time.strftime("%H%M%S"))
        p = os.path.join(d, name)
        img = screen[:, :, ::-1] if screen.ndim == 3 else screen  # RGB -> BGR
        # 用 imencode + tofile：Windows 下 cv2.imwrite 不支持中文路径
        ok, buf = cv2.imencode(".png", img)
        if ok:
            buf.tofile(p)
        return p if ok else None
    except Exception as e:
        print("  [warn] 截图保存失败: %s" % e)
        return None


# ==================== 动作 ====================
def do_swipe_next(w, h):
    """左滑切换到下一个岗位"""
    sx, sy = to_px(cfg.SWIPE_START_POS, w, h)
    ex = sx + int(round(w * cfg.SWIPE_DX))
    ey = sy + int(round(h * cfg.SWIPE_DY))
    ex, ey = max(1, min(ex, w - 1)), max(1, min(ey, h - 1))
    swipe((sx, sy), (ex, ey), duration=cfg.SWIPE_DURATION, steps=cfg.SWIPE_STEPS)


def wait_leave_detail(timeout):
    """点击后：等底部「立即沟通」消失 = 已跳出岗位详情页"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = shot()
        if s is not None and not ENGINE.has(s, cfg.TEXT_READY, cfg.ROI_BUTTON):
            return True
        sleep(cfg.POLL_INTERVAL)
    return False


def wait_back_detail(timeout):
    """返回后：等按钮区重新出现「立即沟通」或「继续沟通」= 已回到详情页"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = shot()
        if s is not None:
            texts = ENGINE.texts(s, cfg.ROI_BUTTON)
            if any((cfg.TEXT_READY in t) or (cfg.TEXT_ALREADY in t) for t in texts):
                return True
        sleep(cfg.POLL_INTERVAL)
    return False


def match_blacklist(screen):
    """返回命中的黑名单关键词；未命中返回 None"""
    if cfg.FILTER_SCOPE == "full_page":
        rois = [None]
    else:
        rois = [cfg.ROI_JOB_TITLE, cfg.ROI_COMPANY]

    texts = []
    for roi in rois:
        texts.extend(ENGINE.texts(screen, roi))

    # 整页模式下先做白名单豁免，避免误伤
    if cfg.FILTER_SCOPE == "full_page":
        joined = "\n".join(texts)
        for w in cfg.WHITE_KEYWORDS:
            if w in joined:
                return None

    for kw in cfg.BLACK_KEYWORDS:
        for t in texts:
            if kw in t:
                return kw
    return None


# ==================== 单轮处理 ====================
def process_one(n, w, h):
    """返回 (结果类型, 说明)；结果类型 ∈ success / skip / fail"""
    screen = shot()
    if screen is None:
        return "fail", "截图失败"

    btn_texts = ENGINE.texts(screen, cfg.ROI_BUTTON)
    already = any(cfg.TEXT_ALREADY in t for t in btn_texts)
    ready = any(cfg.TEXT_READY in t for t in btn_texts)

    # ① 按钮态判定：都不在 -> 页面不对；已沟通 -> 跳过
    if not already and not ready:
        if cfg.SAVE_FAIL_SHOT:
            save_shot(screen, "fail_nobtn_%03d" % n)
        return "fail", "按钮区未识别到[%s/%s]，实际识别: %s" % (
            cfg.TEXT_READY, cfg.TEXT_ALREADY, btn_texts or "空")

    if already:
        if cfg.SAVE_SKIP_SHOT:
            save_shot(screen, "skip_done_%03d" % n)
        return "skip", "已沟通过（继续沟通）"

    # ② 黑名单过滤
    hit = match_blacklist(screen)
    if hit:
        if cfg.SAVE_SKIP_SHOT:
            save_shot(screen, "skip_kw_%03d" % n)
        return "skip", "命中黑名单[%s]" % hit

    # ③ 点击「立即沟通」
    touch(to_px(cfg.BTN_COMMUNICATE_POS, w, h))
    if not wait_leave_detail(cfg.TIMEOUT_LEAVE_DETAIL):
        if cfg.SAVE_FAIL_SHOT:
            save_shot(shot(), "fail_noclick_%03d" % n)
        return "fail", "点击后未离开详情页"

    # ④ 停留等招呼语发出，然后返回
    sleep(cfg.STAY_IN_CHAT + random.uniform(0, 0.8))
    touch(to_px(cfg.BTN_BACK_POS, w, h))
    if not wait_back_detail(cfg.TIMEOUT_BACK_DETAIL):
        if cfg.SAVE_FAIL_SHOT:
            save_shot(shot(), "fail_noback_%03d" % n)
        return "fail", "返回后未回到详情页"

    return "success", ""


# ==================== 主流程 ====================
def parse_rounds():
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a.startswith("--rounds="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                pass
        if a in ("--rounds", "-n") and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
    return cfg.DEFAULT_ROUNDS


def print_summary():
    total = STATS["success"] + STATS["skip"] + STATS["fail"]
    print("")
    print("=" * 56)
    print("运行结束 | 共 %d 个岗位 -> 成功 %d / 跳过 %d / 失败 %d" % (
        total, STATS["success"], STATS["skip"], STATS["fail"]))
    for kind, label in (("skip", "跳过原因"), ("fail", "失败原因")):
        if REASONS[kind]:
            print("  %s：" % label)
            for reason, cnt in sorted(REASONS[kind].items(), key=lambda kv: -kv[1]):
                print("    x%-3d %s" % (cnt, reason))
    print("=" * 56)


def main():
    _init()

    rounds = parse_rounds()
    global _consecutive_fail

    w, h = get_resolution()
    print("=" * 56)
    print("BOSS直聘 自动打招呼")
    print("  轮次=%d  过滤范围=%s  黑名单=%s" % (
        rounds, cfg.FILTER_SCOPE, "/".join(cfg.BLACK_KEYWORDS)))
    print("  分辨率=%dx%d  招呼按钮=%s  返回=%s" % (
        w, h, to_px(cfg.BTN_COMMUNICATE_POS, w, h), to_px(cfg.BTN_BACK_POS, w, h)))
    print("=" * 56)

    print("[info] 正在初始化 OCR 引擎（首次会下载模型，请耐心）...")
    t0 = time.time()
    ENGINE.detect(shot(), cfg.ROI_BUTTON)
    print("[info] OCR 就绪，耗时 %.1fs" % (time.time() - t0))

    for i in range(rounds):
        n = i + 1
        print("\n----- [%d/%d] 第 %d 个岗位 -----" % (n, rounds, n))

        try:
            kind, reason = process_one(n, w, h)
        except Exception as e:
            kind, reason = "fail", "异常: %r" % e

        STATS[kind] += 1
        if reason:
            REASONS[kind][reason] = REASONS[kind].get(reason, 0) + 1
        print("  -> %s  %s" % (kind.upper(), reason))

        if kind == "fail":
            _consecutive_fail += 1
            if _consecutive_fail >= cfg.MAX_CONSECUTIVE_FAIL:
                print("\n[stop] 连续失败 %d 次，停止运行。请检查手机当前页面。" % _consecutive_fail)
                break
        else:
            _consecutive_fail = 0

        if n >= rounds:
            break

        # 切换到下一个岗位
        do_swipe_next(w, h)
        sleep(cfg.SETTLE_AFTER_SWIPE)

        # 反风控：每 N 个长休息一次，否则随机延时
        if n % cfg.LONG_REST_EVERY == 0:
            print("  [rest] 已处理 %d 个，长休息 %ds ..." % (n, cfg.LONG_REST_SEC))
            sleep(cfg.LONG_REST_SEC)
        else:
            sleep(random.uniform(cfg.DELAY_MIN, cfg.DELAY_MAX))

    print_summary()


if __name__ == "__main__":
    main()

