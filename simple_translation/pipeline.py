"""把屏幕读取、内容翻译、翻译显示三部分串起来的处理流程。"""

from __future__ import annotations

import time

from .display import Display
from .screen_reader import ScreenReader
from .translator import Translator


class Pipeline:
    """依次执行：读取屏幕 → 翻译 → 显示。"""

    def __init__(
        self,
        reader: ScreenReader,
        translator: Translator,
        display: Display,
        source_lang: str = "auto",
        target_lang: str = "zh",
    ):
        self.reader = reader
        self.translator = translator
        self.display = display
        self.source_lang = source_lang
        self.target_lang = target_lang

    def run_once(self) -> str:
        text = self.reader.read()
        if not text or not text.strip():
            self.display.clear()
            return ""
        translated = self.translator.translate(text, self.source_lang, self.target_lang)
        self.display.show_pair(text, translated)
        return translated

    def run_boxes_once(self):
        """按行级文本框翻译，并交给显示后端原位覆盖。"""
        boxes = self.reader.read_lines()
        boxes = [box for box in boxes if box.text.strip()]
        if not boxes:
            self.display.clear()
            return []
        items = [
            (box, self.translator.translate(box.text, self.source_lang, self.target_lang))
            for box in boxes
        ]
        origin = getattr(self.reader, "last_origin", (0, 0))
        self.display.show_boxes(items, origin)
        return items

    def _step_once(self):
        if getattr(self.display, "prefers_boxes", False):
            return self.run_boxes_once()
        return self.run_once()

    def run(self, interval: float = 2.0, once: bool = False) -> None:
        if once:
            self._step_once()
            self.display.wait()
            self.display.close()
            return

        try:
            while True:
                self._step_once()
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.display.close()
