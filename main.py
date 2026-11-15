"""简单翻译入口：屏幕读取 → 内容翻译 → 翻译内容显示。"""

from __future__ import annotations

import argparse

from simple_translation.config import load_config
from simple_translation.factory import build_display, build_reader, build_translator
from simple_translation.models import ScreenRegion
from simple_translation.pipeline import Pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="简单翻译：屏幕读取 → 内容翻译 → 翻译内容显示")
    parser.add_argument("--config", help="配置文件路径，默认读取项目下的 config.json")
    parser.add_argument("--ui", action="store_true", help="启动图形界面")
    parser.add_argument("--demo", action="store_true", help="使用演示后端（不访问屏幕、不调用外部服务）")
    parser.add_argument("--reader", choices=["demo", "tesseract", "rapidocr"], help="覆盖读取后端")
    parser.add_argument("--translator", choices=["demo", "zhtrans", "openai"], help="覆盖翻译后端")
    parser.add_argument("--display", choices=["console", "overlay"], help="覆盖显示后端")
    parser.add_argument("--source", help="源语言，默认 auto")
    parser.add_argument("--target", help="目标语言，默认 zh")
    parser.add_argument("--interval", type=float, help="循环读取间隔（秒）")
    parser.add_argument("--once", action="store_true", help="只执行一次后退出")
    args = parser.parse_args(argv)

    if args.ui:
        from simple_translation.ui import run_ui

        return run_ui(args.config, demo=args.demo)

    config = load_config(args.config)

    reader_kind = "demo" if args.demo else (args.reader or config.reader)
    translator_kind = "demo" if args.demo else (args.translator or config.translator)

    reader = build_reader(
        reader_kind,
        ScreenRegion.from_list(config.region),
        config.max_side,
        config.workers,
        config.diff,
    )
    translator = build_translator(translator_kind, config.openai_model)
    display = build_display(args.display or config.display)

    source = args.source or config.source_lang
    target = args.target or config.target_lang
    interval = args.interval if args.interval is not None else config.interval

    pipeline = Pipeline(reader, translator, display, source_lang=source, target_lang=target)
    pipeline.run(interval=interval, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
