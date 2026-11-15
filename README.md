# 简单翻译

一个“屏幕取词翻译”工具：读取屏幕上的文字，翻译成目标语言，再把译文悬浮显示出来。整体用 Python 实现，三部分解耦，方便分别替换后端。

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

## 三部分后端

屏幕读取支持三种后端（`config.json` 的 `reader` 字段）：

- `demo`：演示用，返回预设文本，默认。
- `tesseract`：Tesseract-OCR，英文识别 + 句子级文本框。
- `rapidocr`：RapidOCR（onnxruntime），纯 pip 安装、离线可用，推荐。

### 句子框定（Tesseract）

`TesseractScreenReader.read_boxes()` 会调用 Tesseract 的 `image_to_data` 拿到词级坐标，再按行合并、按句尾标点（`. ! ?`）切分成句子，返回 `TextBox` 列表：

```python
from simple_translation.screen_reader import TesseractScreenReader

reader = TesseractScreenReader(lang="eng", psm=None, min_conf=0.0)
for box in reader.read_boxes():
    print(box.text, box.bbox, box.confidence)  # bbox=(left, top, right, bottom)
```

`lang` 默认 `eng`；`psm` 可传 Tesseract 页面分割模式（例如稀疏文本用 `11`）；`min_conf` 用于过滤低置信度词。`read()` 仍返回不带坐标的纯文本。

翻译支持两种后端（`translator` 字段）：

- `demo`：演示用，不调用外部服务，默认。
- `openai`：OpenAI 兼容接口，需提供 `OPENAI_API_KEY` 环境变量。

显示支持两种后端（`display` 字段）：

- `console`：终端打印，默认。
- `overlay`：tkinter 置顶半透明悬浮窗。

## 配置文件

`config.json` 字段说明：

| 字段 | 含义 | 默认值 |
| --- | --- | --- |
| `source_lang` | 源语言，`auto` 表示自动 | `auto` |
| `target_lang` | 目标语言 | `zh` |
| `reader` | 屏幕读取后端 | `demo` |
| `translator` | 翻译后端 | `demo` |
| `display` | 显示后端 | `console` |
| `interval` | 循环读取间隔（秒） | `2.0` |
| `region` | 截图区域 `[left, top, width, height]`，`null` 为全屏 | `null` |
| `openai_model` | OpenAI 翻译用的模型名 | `gpt-4o-mini` |

## 安装真实后端依赖

```bash
python -m pip install -r requirements.txt
```

若要使用 RapidOCR（推荐）或 OpenAI 翻译，取消 `requirements.txt` 中对应行的注释后再安装。API 密钥请放在环境变量里（例如 `OPENAI_API_KEY`），不要提交到仓库。
