"""第一部分：屏幕读取。

负责截取屏幕（或指定区域）并通过 OCR 识别出其中的文字。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ScreenRegion


class ScreenReader(ABC):
    """屏幕读取器接口。"""

    @abstractmethod
    def read(self) -> str:
        """读取当前屏幕上的文字，返回识别结果。"""


class DemoScreenReader(ScreenReader):
    """演示用读取器：轮流返回预设文本，不访问真实屏幕。"""

    def __init__(self, samples: Optional[List[str]] = None):
        self._samples = samples or [
            "Hello, welcome to the game.",
            "Press Start to continue.",
        ]
        self._index = 0

    def read(self) -> str:
        text = self._samples[self._index % len(self._samples)]
        self._index += 1
        return text


def _capture_screen(region: Optional[ScreenRegion] = None):
    """用 mss 截取屏幕，返回 PIL.Image。"""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        if region is None:
            monitor = sct.monitors[0]  # 所有显示器拼接成的虚拟屏
        else:
            monitor = {
                "left": region.left,
                "top": region.top,
                "width": region.width,
                "height": region.height,
            }
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


class TesseractScreenReader(ScreenReader):
    """基于 Tesseract-OCR 的读取器（需安装 Tesseract 并加入 PATH）。"""

    def __init__(self, region: Optional[ScreenRegion] = None, lang: str = "eng+chi_sim"):
        self.region = region
        self.lang = lang

    def read(self) -> str:
        import pytesseract

        image = _capture_screen(self.region)
        return pytesseract.image_to_string(image, lang=self.lang).strip()


class RapidOcrScreenReader(ScreenReader):
    """基于 RapidOCR（onnxruntime）的读取器，纯 pip 安装、离线可用。"""

    def __init__(self, region: Optional[ScreenRegion] = None):
        self.region = region
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def read(self) -> str:
        import numpy as np

        image = _capture_screen(self.region)
        result, _ = self._get_engine()(np.array(image))
        if not result:
            return ""
        return "\n".join(item[1] for item in result)
