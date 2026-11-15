"""简单翻译入口：屏幕读取 → 内容翻译 → 翻译内容显示。"""

from __future__ import annotations

import argparse

from simple_translation.config import load_config
from simple_translation.display import ConsoleDisplay, Display, TkOverlayDisplay
from simple_translation.models import ScreenRegion
from simple_translation.pipeline import Pipeline
from simple_translation.screen_reader import (
    DemoScreenReader,
    RapidOcrScreenReader,
    ScreenReader,
    TesseractScreenReader,
)
from simple_translation.translator import DemoTranslator, OpenAiTranslator, Translator


def build_reader(kind: str, region: ScreenRegion | None) -> ScreenReader:
    if kind == "demo":
        return DemoScreenReader()
    if kind == "tesseract":
        return TesseractScreenReader(region=region)
    if kind == "rapidocr":
        return RapidOcrScreenReader(region=region)
    raise ValueError(f"未知的读取后端：{kind}")


def build_translator(kind: str, model: str) -> Translator:
    if kind == "demo":
        return DemoTranslator()
    if kind == "openai":
        return OpenAiTranslator(model=model)
    raise ValueError(f"未知的翻译后端：{kind}")


def build_display(kind: str) -> Display:
    if kind == "console":
        return ConsoleDisplay()
    if kind == "overlay":
        return TkOverlayDisplay()
    raise ValueError(f"未知的显示后端：{kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="简单翻译：屏幕读取 → 内容翻译 → 翻译内容显示")
    parser.add_argument("--config", help="配置文件路径，默认读取项目下的 config.json")
    parser.add_argument("--demo", action="store_true", help="使用演示后端（不访问屏幕、不调用外部服务）")
    parser.add_argument("--reader", choices=["demo", "tesseract", "rapidocr"], help="覆盖读取后端")
    parser.add_argument("--translator", choices=["demo", "openai"], help="覆盖翻译后端")
    parser.add_argument("--display", choices=["console", "overlay"], help="覆盖显示后端")
    parser.add_argument("--source", help="源语言，默认 auto")
    parser.add_argument("--target", help="目标语言，默认 zh")
    parser.add_argument("--interval", type=float, help="循环读取间隔（秒）")
    parser.add_argument("--once", action="store_true", help="只执行一次后退出")
    args = parser.parse_args(argv)

    config = load_config(args.config)

    if args.demo:
        reader = DemoScreenReader()
        translator = DemoTranslator()
        display = build_display(args.display or config.display)
    else:
        region = ScreenRegion.from_list(config.region)
        reader = build_reader(args.reader or config.reader, region)
        translator = build_translator(args.translator or config.translator, config.openai_model)
        display = build_display(args.display or config.display)

    source = args.source or config.source_lang
    target = args.target or config.target_lang
    interval = args.interval if args.interval is not None else config.interval

    pipeline = Pipeline(reader, translator, display, source_lang=source, target_lang=target)
    pipeline.run(interval=interval, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
