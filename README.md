# BOSS直聘自动打招呼

> 基于 **OCR 视觉判定 + 归一化坐标驱动 + adb 原生指令** 的 Android 自动化脚本。
> 自动筛查岗位、过滤关键词、发起沟通、切换下一个岗位。

---

## 🚀 项目简介

本项目是一套面向 BOSS直聘 岗位详情页的自动化工具：通过 ONNX 版 PP-OCRv5 识别屏幕文本判断当前状态（岗位是否值得沟通、是否已沟通过、点击是否生效），再用归一化坐标经 adb 完成点击与滑动，实现"筛岗位 → 打招呼 → 切下一个"的无人值守循环。

核心设计思路是 **视觉判定与操作执行解耦**：OCR 只负责"看"，坐标只负责"动"，adb 只负责"执行"。因此脚本不依赖任何 App 内部接口，也不受 UI 树可读性的限制。

---

## ✨ 功能特性

- **关键词黑名单过滤** —— 子串匹配岗位标题与公司名，命中即跳过（如"硬件""机械""车载"）
- **已沟通岗位自动跳过** —— 识别底部按钮文案「继续沟通」，避免重复打招呼
- **全归一化坐标** —— 所有点位以 0~1 比例表示，天然适配任意分辨率机型
- **OCR 驱动的状态校验** —— 点击后轮询确认页面流转，不靠 `sleep` 盲等
- **ROI 区域裁剪** —— 只在关键区域跑 OCR，速度提升约 6 倍（整页 0.51s → 按钮区 0.08s）
- **反风控节奏控制** —— 步间随机延时 1.5~4s，每 20 个岗位长休息 60s
- **异常自保护** —— 连续失败 3 次自动停机，跳过/异常自动截图留证
- **双通道运行** —— 纯 adb 版可与 AirtestIDE 投屏共存；airtest 版适合在 IDE 内直接运行

---

## 🛠️ 技术栈

| 层级 | 技术 / 工具 | 用途说明 |
|---|---|---|
| 运行时 | Python 3.12（3.8+ 即可） | 脚本执行环境 |
| 设备通信 | Android Debug Bridge (adb) | 抓屏、点击、滑动的底层通道 |
| 自动化框架 | Airtest 1.4.3 | **仅 `auto_greeting.py` / `calibrate.py` 使用**，其余脚本为纯 adb |
| 图像处理 | OpenCV 4.6 + NumPy 1.26 | 截图编解码、ROI 裁剪、中文路径兼容 |
| 文字识别 | onnxocr-ppocrv5 0.0.22 | PP-OCRv5 的 ONNX 版本，轻量中文场景 |
| 推理后端 | ONNX Runtime 1.29 | CPU 推理，模型内置在包内，无需额外下载 |
| 配置管理 | config.py 单一参数中心 | 坐标、ROI、关键词、超时、反风控集中管理 |
| 构建工具 | 无 | 纯脚本项目，无需编译 |
| 数据库 | 无 | 无持久化，靠截图留证 |

---

## 📋 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows / macOS / Linux |
| Python | 3.8 ~ 3.12（**不支持 3.6**；3.13+ 部分轮子不全） |
| Android 设备 | 已开启 USB 调试，Android 7.0+ |
| adb | 需可用（AirtestIDE 自带，或系统 PATH 中） |
| 磁盘空间 | 约 500 MB（含依赖与模型） |

---

## 📦 安装

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. 安装依赖
pip install -r requirements.txt
```

> ⚠️ **onnxruntime 是 extra 依赖**，只装 `onnxocr-ppocrv5` 会在 import 阶段失败。
> `requirements.txt` 中已用 `onnxocr-ppocrv5[onnx]` 语法处理，请勿手动删掉 `[onnx]`。

---

## 🚀 快速开始

### 1. 连接设备

```bash
adb devices          # 确认设备在线
```

### 2. 校准区域（首次使用必做）

手机停在 **岗位详情页**，运行零侵入校准工具：

```bash
python calibrate_adb.py
```

输出示例：

```
  y= 10.2%~ 13.5%  x= 3.1%~48.0%  0.97  高级软件工程师
  y= 65.9%~ 68.0%  x= 3.1%~60.2%  0.99  某某科技有限公司
  y= 93.8%~ 97.2%  x=28.0%~70.0%  0.98  立即沟通
```

把对应行的百分比填回 `config.py` 的 `ROI_JOB_TITLE` / `ROI_COMPANY` / `ROI_BUTTON`。

> `calibrate_adb.py` 走 `adb exec-out screencap` 取帧，不启动 minicap/minitouch，
> **AirtestIDE 正在投屏时也能安全运行**，不会打断连接。

### 3. 正式运行

```bash
python auto_greeting.py              # 默认 30 轮
python auto_greeting.py --rounds 50  # 指定 50 轮
```

在 AirtestIDE 中点运行时，轮次取 `config.py` 的 `DEFAULT_ROUNDS`。

---

## ⚙️ 配置说明

所有可调参数集中在 `config.py`，主脚本无需改动。

| 参数 | 说明 |
|---|---|
| `DEFAULT_ROUNDS` | 默认处理轮次（命令行 `--rounds` 可覆盖） |
| `BTN_COMMUNICATE_POS` / `BTN_BACK_POS` | 「立即沟通」与返回按钮的归一化坐标 |
| `SWIPE_START_POS` / `SWIPE_DX` | 滑动起点与横向位移（负=左滑） |
| `ROI_JOB_TITLE` / `ROI_COMPANY` / `ROI_BUTTON` | 三个 OCR 检测区域 |
| `FILTER_SCOPE` | `title_company`（推荐，误伤少）/ `full_page`（需配白名单） |
| `BLACK_KEYWORDS` | 黑名单关键词列表，**子串匹配** |
| `WHITE_KEYWORDS` | 白名单豁免（仅 `full_page` 模式生效） |
| `OCR_CONF_MIN` | OCR 置信度阈值，低于此值的结果丢弃（默认 0.6） |
| `DELAY_MIN` / `DELAY_MAX` / `LONG_REST_*` | 反风控节奏控制 |
| `MAX_CONSECUTIVE_FAIL` | 连续失败多少次后自动停机（默认 3） |

### 默认校准值（1080×2408 实测）

```python
BTN_COMMUNICATE_POS = (0.50, 0.954)
BTN_BACK_POS        = (0.09, 0.08)
SWIPE_START_POS     = (0.80, 0.50)
SWIPE_DX            = -0.60          # 实测需 ≥60% 屏宽才能触发切岗位
ROI_BUTTON          = (0.00, 0.925, 1.00, 1.00)
ROI_JOB_TITLE       = (0.04, 0.105, 0.75, 0.20)
ROI_COMPANY         = (0.04, 0.645, 0.97, 0.72)
```

**换机型或 App 改版后，请重新运行 `calibrate_adb.py` 校准。**

---

## 📁 目录结构

```
BOSS_Zhi_Pin_Greeting/
├── config.py                    # 参数中心（唯一需要修改的文件）
├── ocr_helper.py                # OCR 适配层：ROI 裁剪、置信度过滤、子串匹配
├── auto_greeting.py             # 主循环脚本（airtest 版）
├── test_one.py                  # 单轮测试（纯 adb 版，支持 --dry-run）
├── probe_swipe.py               # 滑动手势探测工具（找有效切换距离）
├── calibrate_adb.py             # 区域校准（纯 adb，零侵入，推荐）
├── calibrate.py                 # 区域校准（airtest 版）
├── requirements.txt             # 依赖清单
├── 使用说明.md                   # 详细使用文档
└── LICENSE                      # MIT
```

### 脚本选型

| 脚本 | 设备连接方式 | 可与 AirtestIDE 投屏共存 |
|---|---|---|
| `auto_greeting.py` | airtest（minicap/minitouch） | ❌ 会抢占设备 |
| `calibrate.py` | airtest | ❌ 会抢占设备 |
| `test_one.py` | 纯 adb | ✅ |
| `probe_swipe.py` | 纯 adb | ✅ |
| `calibrate_adb.py` | 纯 adb | ✅ |

> airtest 连接时会独占输入通道，与 IDE 投屏使用同一套机制，同时运行会互相踢。

---

## 🔧 常见问题

| 现象 | 原因与处理 |
|---|---|
| `ModuleNotFoundError: onnxocr` | 未安装或装在了别的 Python 环境；确认解释器路径 |
| OCR 报缺少 onnxruntime | 需 `pip install "onnxocr-ppocrv5[onnx]"` |
| 滑动后仍是同一个岗位 | 位移太小，加大 `SWIPE_DX`（实测需 ≥0.60） |
| 提示「按钮区未识别到」 | 页面不是岗位详情页，或 `ROI_BUTTON` 未覆盖按钮，重跑校准 |
| 中文路径下截图保存失败 | 已用 `cv2.imencode + tofile` 规避；若仍失败检查目录权限 |
| OCR 识别慢 | 确认 `OCR_USE_CLS = False`（开启会多加载方向分类模型） |
| Windows 下 `adb screencap > a.png` 图片损坏 | 不要用 shell 重定向，需 `subprocess(capture_output=True)` 捕获二进制流 |

---

## ⚠️ 免责声明

- 本项目仅供**学习 Android 自动化与 OCR 技术**使用，不得用于任何商业用途或大规模批量操作。
- 使用自动化工具操作第三方平台**可能违反其用户协议**，存在账号限制或封禁风险；请自行评估并承担全部后果。
- 请合理控制运行频率，避免对目标服务造成异常负载。
- 作者不对因使用本项目导致的任何直接或间接损失负责。

---

## 📄 许可证

本项目采用 [MIT License](./LICENSE) 开源协议。
