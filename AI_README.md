# AI 导读（给 AI / 自动化工具）

本文件是给 AI 阅读本仓库用的精简地图。先读本文件，通常即可定位到需要改动的文件，避免通读全部源码。

## 一句话概括

一个 Python 屏幕取词翻译工具，流程为：**截屏 OCR（屏幕读取）→ 翻译（内容翻译）→ 显示（翻译内容显示）**。三部分通过接口解耦，可独立替换。

## 最少阅读路径

1. 本文件（结构 + 接口 + 陷阱）。
2. `simple_translation/models.py`（数据结构）。
3. `simple_translation/pipeline.py`（三部分如何串起来）。
4. 只打开你需要改的那一个模块（见下方文件地图）。

## 文件地图

| 文件 | 职责 | 关键符号 |
| --- | --- | --- |
| `main.py` | CLI/UI 入口 | `main()` |
| `simple_translation/factory.py` | 根据配置创建后端 | `build_reader()`, `build_translator()`, `build_display()` |
| `simple_translation/ui.py` | 简洁图形界面 | `TranslationApp`, `run_ui()` |
| `simple_translation/hotkey.py` | Windows 全局快捷键 | `GlobalHotkey`, `parse_hotkey()` |
| `run_ui.cmd` | Windows 双击启动 UI | `python main.py --ui` |
| `simple_translation/models.py` | 数据模型 | `ScreenRegion`, `TextBox`, `TranslationResult` |
| `simple_translation/config.py` | 配置加载 | `AppConfig`, `load_config()`, `save_default_config()` |
| `simple_translation/screen_reader.py` | 第一部分：截屏 + OCR + 帧差分 | `ScreenReader`, `TesseractScreenReader`, `RapidOcrScreenReader`, `DemoScreenReader` |
| `simple_translation/translator.py` | 第二部分：翻译 | `Translator`, `ZhtransTranslator`, `DemoTranslator`, `OpenAiTranslator` |
| `zhtrans/` | 随仓库附带的离线英译中引擎（纯标准库） | `zhtrans.translate_text`, `TranslationEngine`, `MTranClient` |
| `simple_translation/display.py` | 第三部分：显示 | `Display`, `ConsoleDisplay`, `TkOverlayDisplay` |
| `simple_translation/pipeline.py` | 串联流程 | `Pipeline.run_once()`, `Pipeline.run()` |
| `config.json` | 默认配置 | 见“配置”一节 |
| `requirements.txt` | 依赖 | tesserocr / pytesseract / mss / Pillow / openai |

## 核心接口

### 屏幕读取

```python
class ScreenReader(ABC):
    def read(self) -> str: ...                      # 纯文本
    def read_boxes(self) -> list[TextBox]: ...      # 句子级文本框（默认实现将 read() 包成无坐标框）
```

`TesseractScreenReader` 关键构造参数（均有默认值）：

```python
TesseractScreenReader(
    region: ScreenRegion | None = None,
    lang: str = "eng",
    psm: int | None = None,          # 映射到 tesserocr PSM，None => AUTO
    min_conf: float = 0.0,           # 过滤低置信度词
    max_side: int | None = None,     # >该值时先缩小再 OCR，坐标自动映射回原图
    workers: int = 0,                # 0=大图自动并行，1=单次，>1=横向条带并行
    diff: bool = True,               # 帧差分：只重扫变化区域
    diff_threshold: int = 24,        # 缩略图灰度差阈值（0-255）
)
```

额外方法：`read_words() -> list[TextBox]`（词级框）。

### 翻译

```python
class Translator(ABC):
    def translate(self, text: str, source: str = "auto", target: str = "zh") -> str: ...
```

- `DemoTranslator`：不调外部服务，返回 `[source -> target] 原文`。
- `ZhtransTranslator(server=None, token=None, timeout=30.0, correct=True, auto_start=True)`：默认翻译后端，调用随仓库的 `zhtrans`（本地 MTranServer，离线英译中）。`target="zh"` 会自动映射为 `zh-Hans`。
- `OpenAiTranslator(api_key=None, model=None, base_url=None)`：读环境变量 `OPENAI_API_KEY`、`OPENAI_TRANSLATE_MODEL`、`OPENAI_BASE_URL`。

### 显示

```python
class Display(ABC):
    def show(self, text: str) -> None: ...
    def show_pair(self, original: str, translation: str) -> None: ...  # 默认把两者拼给 show()
    def show_boxes(self, items, origin=(0, 0)) -> None: ...            # items=[(TextBox, 译文)]
    def clear(self) -> None: ...
    def wait(self) -> None: ...   # 有窗口的后端阻塞到窗口关闭
    def close(self) -> None: ...
```

- `ConsoleDisplay`：终端同时打印原文与译文。
- `TkOverlayDisplay(title="简单翻译", font=None, corner="top-right", alpha=0.92, max_chars=800, width=640)`：tkinter 无边框、置顶、半透明双语窗口，可拖动、点 `×` 关闭。
- `TkCoverDisplay`：按原文行框位置创建覆盖窗，把译文直接盖在原文上；`prefers_boxes=True`，`Pipeline.run()` 会自动走 `run_boxes_once()`。
- `CoverOverlayManager`：覆盖窗管理器，UI 和 `TkCoverDisplay` 共用；`show(items, origin)` / `clear()` / `close()`。

### 流程

```python
Pipeline(reader, translator, display, source_lang="auto", target_lang="zh")
Pipeline.run_once() -> str                      # 读取 → 翻译 → 显示，返回译文
Pipeline.run(interval=2.0, once=False) -> None  # 循环；Ctrl+C 退出
```

## 数据流

```
main.main()
  → load_config() → build_reader/translator/display()
  → Pipeline.run(interval, once)
      → reader.read()            # 屏幕读取（TesseractScreenReader 内部含差分缓存）
      → translator.translate()   # 内容翻译
      → display.show_boxes(items, origin)         # 原位覆盖（或 show_pair 整体显示）
```

## 数据结构

```python
ScreenRegion(left, top, width, height)          # 像素；from_list([l, t, w, h])
TextBox(text, left, top, width, height, confidence=None)
  .right  = left + width
  .bottom = top + height
  .bbox   = (left, top, right, bottom)          # 注意是 l/t/r/b，不是 l/t/w/h
TranslationResult(source_text, translated_text, source_lang, target_lang)
```

## 配置（`config.json` / `AppConfig`）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `source_lang` | `"auto"` | 源语言 |
| `target_lang` | `"zh"` | 目标语言 |
| `reader` | `"tesseract"` | `demo` / `tesseract` / `rapidocr` |
| `translator` | `"zhtrans"` | `zhtrans` / `demo` / `openai` |
| `display` | `"console"` | `console` / `overlay` |
| `interval` | `2.0` | 循环间隔（秒） |
| `region` | `null` | 截图区域 `[left, top, width, height]`，`null` 为全屏 |
| `max_side` | `null` | OCR 前最长边上限，用于控制耗时 |
| `workers` | `0` | 并行 worker 数；`0` 表示大图自动 |
| `diff` | `true` | 帧差分：只对变化区域重新 OCR |
| `hotkey` | `"F8"` | 全局快捷键，开始/结束翻译 |
| `openai_model` | `"gpt-4o-mini"` | OpenAI 翻译模型名 |

## CLI

```bash
python main.py --demo --once
python main.py --demo
python main.py --demo --display overlay
python main.py --reader tesseract --translator openai --display overlay
```

参数：`--config`、`--ui`、`--demo`、`--reader {demo,tesseract,rapidocr}`、`--translator {demo,zhtrans,openai}`、`--display {console,overlay}`、`--source`、`--target`、`--interval`、`--once`。

## 实现要点与陷阱

- OCR 后端优先 `tesserocr`（进程内），不可用时回退 `pytesseract`（子进程）。不要把两者混在同一个 `PyTessBaseAPI` 上。
- `tesserocr` 的 `BoundingBox` 返回 `(left, top, right, bottom)`，代码中已换算成 `width/height`。
- `TesseractScreenReader.read()` / `read_words()` / `read_boxes()` 都经过 `_read_full()`，共享同一帧差分缓存；不要假设三者是三次独立识别。
- 帧差分状态是**实例级**的：一个 `TesseractScreenReader` 只对应一个连续屏幕流。切换屏幕/区域或需要强制全量识别时，新建实例或设置 `diff=False`。
- 差分流程：160px 灰度缩略图 → 阈值 24 → 连通区域 + 边距/合并 → 只对变化区域 OCR；变化超过 50% 或合并区域超过 60% 时回退全屏 OCR。
- `workers > 1` 使用线程池 + 每线程独立 tesserocr API（`threading.local`）；`PyTessBaseAPI` 不能跨线程共享。
- 句子分组规则：把连续行合并，直到某行以 `.` `!` `?` 结尾。界面文字通常没有句尾标点，因此可能合并成一个很大的框——这是已知行为，不是 bug。
- `RapidOcrScreenReader` 是独立后端，只实现 `read()`；在部分机器上比 Tesseract 慢，默认不启用。
- `zhtrans/` 是随仓库附带的纯标准库英译中引擎；真正翻译由本地 MTranServer 完成。
- `GlobalHotkey` 用 Windows `RegisterHotKey` 注册系统级热键；回调只向 UI 队列投递事件，Tk 操作始终留在主线程。UI 收到后切换开始/停止，默认 `F8`。
- `vendor/`（Node 运行时 + 英译中模型，约 380MB）不入库；默认找项目根目录下的 `vendor/`，也可用 `ZHTRANS_VENDOR` 环境变量指向已有目录。
- 首次 `ZhtransTranslator.translate()` 会启动本地服务并加载模型（约 15s），之后复用连接/词典/缓存，通常 8–200ms。
- Windows 下 `tesserocr` 需要 tessdata：代码会依次查 `TESSDATA_PREFIX`、`%ProgramFiles%\Tesseract-OCR\tessdata`。
- `read()` 返回的是行文本用换行拼接的结果，来源于差分后的缓存行。

## 扩展方式

- 新增读取后端：实现 `ScreenReader.read()`（需要框时再实现 `read_boxes()` / `read_words()`），在 `main.build_reader()` 注册。
- 新增翻译后端：实现 `Translator.translate()`，在 `main.build_translator()` 注册。
- 新增显示后端：实现 `Display.show/clear/close`，在 `main.build_display()` 注册。

## 验证命令

```bash
python -m compileall -q simple_translation main.py
python main.py --demo --once
python -c "from simple_translation.screen_reader import TesseractScreenReader; print('ok')"
```

## 运行时安装

- `vendor/` 不入库（Node + MTranServer + 模型，约 380MB）。
- `setup_runtime.ps1` 读取 `runtime.json` 的 `url` 下载 zip，校验 SHA256 后解压到 `vendor/`；也支持 `-FromPath <dir>` 从本地复制。
- `tools/package_runtime.ps1 -UpdateMetadata` 打包本地 `vendor/` 为 `dist/simple-translation-runtime-win64.zip`，并更新 `runtime.json` 的 `archive`/`sha256`/`size`。
- 当前运行时 Release：`https://github.com/lijinyang7/simple-translation/releases/tag/runtime-v1.0.0`。
- 首次翻译会启动本地服务并加载模型（约 15–30s），之后连接与缓存复用。

## 性能参考（本机实测）

| 场景 | 耗时 |
| --- | --- |
| 519×391 截图单次 OCR | ~110 ms |
| 2560×1440 整屏单次 | ~1.1–1.6 s |
| 整屏 + `workers` 并行 | ~0.45 s |
| 整屏 + 帧差分（画面静止） | ~42 ms |
| zhtrans 单句（热启动） | ~8–200 ms |

## 已知限制

- 全屏原分辨率用 Tesseract 很难稳定 <200ms；需要用小区域 `region`、`max_side` 缩小（损失小字）或等待更快后端。
- 帧差分假定屏幕连续；首次读取会全量识别，之后只重扫变化区域。
- OpenAI 翻译需要网络与 `OPENAI_API_KEY`。
