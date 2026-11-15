"""根据配置创建读取、翻译、显示后端。"""

from __future__ import annotations

from typing import Optional

from .display import ConsoleDisplay, Display, TkCoverDisplay, TkOverlayDisplay
from .models import ScreenRegion
from .screen_reader import (
    DemoScreenReader,
    RapidOcrScreenReader,
    ScreenReader,
    TesseractScreenReader,
)
from .translator import DemoTranslator, OpenAiTranslator, Translator, ZhtransTranslator


def build_reader(
    kind: str,
    region: Optional[ScreenRegion] = None,
    max_side: Optional[int] = None,
    workers: int = 0,
    diff: bool = True,
) -> ScreenReader:
    if kind == "demo":
        return DemoScreenReader()
    if kind == "tesseract":
        return TesseractScreenReader(
            region=region,
            max_side=max_side,
            workers=workers,
            diff=diff,
        )
    if kind == "rapidocr":
        return RapidOcrScreenReader(region=region)
    raise ValueError(f"未知的读取后端：{kind}")


def build_translator(kind: str, model: str = "gpt-4o-mini") -> Translator:
    if kind == "demo":
        return DemoTranslator()
    if kind == "zhtrans":
        return ZhtransTranslator()
    if kind == "openai":
        return OpenAiTranslator(model=model)
    raise ValueError(f"未知的翻译后端：{kind}")


def build_display(kind: str) -> Display:
    if kind == "console":
        return ConsoleDisplay()
    if kind == "overlay":
        return TkOverlayDisplay()
    if kind == "cover":
        return TkCoverDisplay()
    raise ValueError(f"未知的显示后端：{kind}")
