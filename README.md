# 简单翻译

一个“屏幕取词翻译”工具：读取屏幕上的文字，翻译成目标语言，再把译文悬浮显示出来。整体用 Python 实现，三部分解耦，方便分别替换后端。

> 给 AI / 自动化工具看的精简导读（推荐先读）：[AI_README.md](AI_README.md)

## 整体流程

屏幕读取（OCR）→ 内容翻译 → 翻译内容显示

## 目录结构

```
.
├── main.py                    # 入口：解析参数、组装三部分并运行
├── config.json                # 默认配置
├── requirements.txt           # 依赖清单
└── simple_translation/
    ├── screen_reader.py       # 第一部分：屏幕读取（截图 + OCR）
    ├── translator.py          # 第二部分：内容翻译
    ├── display.py             # 第三部分：翻译内容显示
    ├── pipeline.py            # 串联三部分的处理流程
    ├── models.py              # 数据模型
    └── config.py              # 配置加载
```

## 下载

Windows x64 完整便携包（源码 + UI + zhtrans + Node/模型）：[v1.0.0](https://github.com/lijinyang7/simple-translation/releases/tag/v1.0.0)

## 快速开始

先跑一次演示（不访问屏幕、不调用外部服务）：

```bash
python main.py --demo --once
```

循环演示（按 `Ctrl+C` 退出）：

```bash
python main.py --demo
```

悬浮窗演示（tkinter 置顶半透明窗口）：

```bash
python main.py --demo --display overlay
```

启动图形界面：

```bash
python main.py --ui
```

也可以直接双击项目根目录的 `run_ui.cmd`。

界面启动后会注册全局快捷键 **F8**，在任意窗口下按下即可开始或结束连续翻译；可在 `config.json` 的 `hotkey` 字段改成其他组合键（如 `Ctrl+Alt+T`）。

## 三部分后端

屏幕读取支持三种后端（`config.json` 的 `reader` 字段）：

- `demo`：演示用，返回预设文本。
- `tesseract`：默认。Tesseract-OCR，英文识别 + 句子级文本框。
- `rapidocr`：RapidOCR（onnxruntime），纯 pip 安装、离线可用，推荐。

屏幕读取默认在后台按 `capture_fps`（默认 5 帧/秒）持续捕获；内部使用帧差分，只有画面变化时才重新 OCR，上层始终读取最新结果。可用 `continuous: false` 关闭后台捕获，退回按需截图。

### 句子框定（Tesseract）

`TesseractScreenReader.read_boxes()` 会调用 Tesseract 的 `image_to_data` 拿到词级坐标，再按行合并、按句尾标点（`. ! ?`）切分成句子，返回 `TextBox` 列表：

```python
from simple_translation.screen_reader import TesseractScreenReader

reader = TesseractScreenReader(lang="eng", psm=None, min_conf=0.0)
for box in reader.read_boxes():
    print(box.text, box.bbox, box.confidence)  # bbox=(left, top, right, bottom)
```

`lang` 默认 `eng`；`psm` 可传 Tesseract 页面分割模式（例如稀疏文本用 `11`）；`min_conf` 用于过滤低置信度词。`read()` 仍返回不带坐标的纯文本。

框词优化：默认使用 `psm=6`（单块文本，速度更快）；大图并行分条时会向上下扩展重叠区域，并按“中心点归属”只保留该条核心区的框，避免切词和重复框。句子框在没有句尾标点时也会按行距或每 4 行切分，不再合并成整屏一个大框。实测 444 词的双栏整屏召回 444/444，真实截图 53 词全部唯一。

### 性能

识别优先走进程内的 `tesserocr`（无子进程启动开销），不可用时自动回退到 `pytesseract`。实测 519×391 的截图单次 OCR 约 113ms，比 pytesseract 的约 269ms 快一倍以上。对于整屏/大图，可设置 `max_side`：当截图最长边超过该值时先等比缩小再识别，坐标会自动映射回原图。例如 `max_side=260` 时同一张图约 60ms（词数从 53 略降到 51）。注意缩得太小会降低小字识别率，实际使用中更推荐配合 `region` 只截取关心的区域。

整块 2560×1440 屏幕单次识别约 1.1–1.6s。设置 `workers` 后会把屏幕切成横向条带并行识别（`0` 为自动按 CPU 核数，也可手动设 `8` 等），实测约 0.45s、约 240 个词，且保持原分辨率、不损失小字。若还要压到 200ms 以内，只能再组合 `max_side` 缩小（如 `max_side=1536`），代价是小字识别率明显下降；真实使用仍推荐用 `region` 限定关注区域。

循环运行时建议开启帧差分（`diff: true`，默认开启）：每帧只对与上一帧不同的区域重新 OCR，静态区域直接复用上一次结果。实测整屏首帧约 0.78s，画面静止后连续帧降到约 42ms；只有局部变化时仅重扫变化区域。

翻译支持三种后端（`translator` 字段）：

- `zhtrans`：默认。随仓库附带的离线英译中引擎（本地 MTranServer），无需联网。
- `demo`：演示用，不调用外部服务。
- `openai`：OpenAI 兼容接口，需提供 `OPENAI_API_KEY` 环境变量。

### zhtrans 离线翻译运行时

翻译引擎 `zhtrans` 的 Python 代码已随仓库附带（`zhtrans/`，纯标准库），实际翻译由本地 MTranServer 完成。Node 运行时与英译中模型约 380MB，放在 `vendor/`，该目录不入库。

- 若 `vendor/` 存在，首次翻译会自动启动本地服务（首次约 15 秒加载模型，之后很快）。
- 也可以设置环境变量 `ZHTRANS_VENDOR` 指向已有的 `vendor` 目录。
- 无需联网，也不需要单独安装 Node。

#### 安装运行时

新克隆项目后 `vendor/` 是空的，运行一次：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_runtime.ps1
```

脚本会从 GitHub Release 下载运行时（约 163MB），校验 SHA256 后解压到 `vendor/`。也可以直接从本地已有的 translate 目录复制：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_runtime.ps1 -FromPath 'C:\path\to\translate\vendor'
```

运行时已发布为 Release 附件：[runtime-v1.0.0](https://github.com/lijinyang7/simple-translation/releases/tag/runtime-v1.0.0)。发布新版本时先重新打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\package_runtime.ps1 -UpdateMetadata
```

然后把 `dist/simple-translation-runtime-win64.zip` 上传为 Release 附件，并把下载地址写入 `runtime.json` 的 `url`。

显示支持三种后端（`display` 字段）：

- `console`：终端打印原文与译文，默认。
- `overlay`：整体双语悬浮窗（原文 + 译文）。
- `cover`：按原文行位置用译文覆盖原文；屏幕右上角有 `×` 关闭。

图形界面默认使用“原位覆盖”，不再整体显示原文/译文。使用 `--once --display cover` 时覆盖层会保持，直到点击右上角 `×` 或按 `Ctrl+C`。

## 配置文件

`config.json` 字段说明：

| 字段 | 含义 | 默认值 |
| --- | --- | --- |
| `source_lang` | 源语言，`auto` 表示自动 | `auto` |
| `target_lang` | 目标语言 | `zh` |
| `reader` | 屏幕读取后端 | `tesseract` |
| `translator` | 翻译后端 | `zhtrans` |
| `display` | 显示后端 | `console` |
| `interval` | 循环读取间隔（秒） | `2.0` |
| `region` | 截图区域 `[left, top, width, height]`，`null` 为全屏 | `null` |
| `max_side` | OCR 前最长边上限，控制单帧耗时 | `null` |
| `workers` | 并行 worker 数，`0` 表示大图自动并行 | `0` |
| `diff` | 帧差分：只对变化区域重新 OCR | `true` |
| `continuous` | 后台持续捕获屏幕 | `true` |
| `capture_fps` | 持续捕获帧率 | `5.0` |
| `hotkey` | 全局快捷键：开始/结束翻译 | `F8` |
| `openai_model` | OpenAI 翻译用的模型名 | `gpt-4o-mini` |

## 安装真实后端依赖

```bash
python -m pip install -r requirements.txt
```

若要使用 RapidOCR（推荐）或 OpenAI 翻译，取消 `requirements.txt` 中对应行的注释后再安装。API 密钥请放在环境变量里（例如 `OPENAI_API_KEY`），不要提交到仓库。
