"""简单翻译：屏幕读取 → 内容翻译 → 翻译内容显示。"""

from .display import ConsoleDisplay, Display, TkOverlayDisplay
from .models import ScreenRegion, TextBox, TranslationResult
from .pipeline import Pipeline
from .screen_reader import (
    DemoScreenReader,
    RapidOcrScreenReader,
    ScreenReader,
    TesseractScreenReader,
)
from .translator import DemoTranslator, OpenAiTranslator, Translator, ZhtransTranslator

__version__ = "0.1.0"

__all__ = [
    "Pipeline",
    "ScreenRegion",
    "TextBox",
    "TranslationResult",
    "ScreenReader",
    "DemoScreenReader",
    "TesseractScreenReader",
    "RapidOcrScreenReader",
    "Translator",
    "DemoTranslator",
    "OpenAiTranslator",
    "ZhtransTranslator",
    "Display",
    "ConsoleDisplay",
    "TkOverlayDisplay",
]
