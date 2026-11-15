"""数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScreenRegion:
    """屏幕上的矩形区域，单位均为像素。

    left/top 为左上角坐标，width/height 为宽高；为 None 时表示整块屏幕。
    """

    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_list(cls, value: Optional[list[int]]) -> Optional["ScreenRegion"]:
        if not value:
            return None
        left, top, width, height = value
        return cls(left=left, top=top, width=width, height=height)


@dataclass
class TranslationResult:
    """一次翻译的结果。"""

    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
