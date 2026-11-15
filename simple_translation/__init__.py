"""简单翻译：屏幕读取 → 内容翻译 → 翻译内容显示。"""

from .display import ConsoleDisplay, Display, TkOverlayDisplay
from .pipeline import Pipeline
from .screen_reader import (
    DemoScreenReader,
    RapidOcrScreenReader,
    ScreenReader,
    ScreenRegion,
    TesseractScreenReader,
)
from .translator import DemoTranslator, OpenAiTranslator, Translator

__version__ = "0.1.0"

__all__ = [
    "Pipeline",
    "ScreenRegion",
    "ScreenReader",
    "DemoScreenReader",
    "TesseractScreenReader",
    "RapidOcrScreenReader",
    "Translator",
    "DemoTranslator",
    "OpenAiTranslator",
    "Display",
    "ConsoleDisplay",
    "TkOverlayDisplay",
]
