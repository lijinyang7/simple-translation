"""第一部分：屏幕读取。

负责截取屏幕（或指定区域）并通过 OCR 识别出其中的文字。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ScreenRegion, TextBox


_SENTENCE_ENDERS = (".", "!", "?")


class ScreenReader(ABC):
    """屏幕读取器接口。"""

    @abstractmethod
    def read(self) -> str:
        """读取当前屏幕上的文字，返回识别结果。"""

    def read_boxes(self) -> list[TextBox]:
        """读取屏幕文字，并返回带位置框的句子列表。

        默认实现基于 read() 生成一个无坐标的文本框；需要真实坐标时子类应覆写。
        """
        text = self.read().strip()
        if not text:
            return []
        return [TextBox(text=text, left=0, top=0, width=0, height=0)]


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

    mss_cls = getattr(mss, "MSS", mss.mss)
    with mss_cls() as sct:
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


def _pytesseract():
    """导入 pytesseract，并在 Windows 下自动回退到默认安装路径。"""
    import os
    import shutil
    from pathlib import Path

    import pytesseract

    if shutil.which("tesseract") is None:
        default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
        if default.exists():
            pytesseract.pytesseract.tesseract_cmd = str(default)
    return pytesseract


class TesseractScreenReader(ScreenReader):
    """基于 Tesseract-OCR 的英文读取器（需安装 Tesseract 并加入 PATH）。

    read() 返回纯文本；read_boxes() 返回按句子分组的文本框，每个框带有
    (left, top, width, height) 坐标和平均置信度，可用于后续高亮或局部翻译。
    """

    def __init__(
        self,
        region: Optional[ScreenRegion] = None,
        lang: str = "eng",
        psm: Optional[int] = None,
        min_conf: float = 0.0,
    ):
        self.region = region
        self.lang = lang
        self.psm = psm
        self.min_conf = min_conf

    def _tesseract_config(self) -> str:
        return f"--psm {self.psm}" if self.psm else ""

    def _ocr_data(self) -> dict:
        pytesseract = _pytesseract()
        from pytesseract import Output

        image = _capture_screen(self.region)
        return pytesseract.image_to_data(
            image,
            lang=self.lang,
            output_type=Output.DICT,
            config=self._tesseract_config(),
        )

    def read(self) -> str:
        pytesseract = _pytesseract()

        image = _capture_screen(self.region)
        return pytesseract.image_to_string(
            image, lang=self.lang, config=self._tesseract_config()
        ).strip()

    def read_boxes(self) -> list[TextBox]:
        return _group_sentences(self._ocr_data(), self.min_conf)


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


def _group_sentences(data: dict, min_conf: float = 0.0) -> list[TextBox]:
    """把 Tesseract 的 image_to_data 输出按句子分组成文本框。"""
    words = []
    texts = data.get("text") or []
    for index in range(len(texts)):
        text = (texts[index] or "").strip()
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError, KeyError):
            confidence = -1.0
        if not text or confidence < min_conf:
            continue
        words.append(
            {
                "text": text,
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
                "confidence": confidence,
                "key": (
                    int(data["block_num"][index]),
                    int(data["par_num"][index]),
                    int(data["line_num"][index]),
                    int(data["word_num"][index]),
                ),
            }
        )

    if not words:
        return []

    words.sort(key=lambda item: item["key"])

    # 第一步：同一行的单词合并成一行
    lines = []
    current_line_key = None
    for word in words:
        line_key = word["key"][:3]
        if line_key != current_line_key:
            lines.append({"key": line_key, "text": word["text"], "words": [word]})
            current_line_key = line_key
        else:
            lines[-1]["text"] += " " + word["text"]
            lines[-1]["words"].append(word)

    # 第二步：把连续的行合并成句子（以上一行是否以 .!? 结尾作为边界）
    sentences = []
    for line in lines:
        text = line["text"]
        if sentences and not sentences[-1]["ended"]:
            sentences[-1]["text"] += " " + text
            sentences[-1]["words"].extend(line["words"])
        else:
            sentences.append({"text": text, "words": list(line["words"]), "ended": False})
        if text.endswith(_SENTENCE_ENDERS):
            sentences[-1]["ended"] = True

    boxes = []
    for sentence in sentences:
        sentence_words = sentence["words"]
        left = min(word["left"] for word in sentence_words)
        top = min(word["top"] for word in sentence_words)
        right = max(word["left"] + word["width"] for word in sentence_words)
        bottom = max(word["top"] + word["height"] for word in sentence_words)
        confidence = round(
            sum(word["confidence"] for word in sentence_words) / len(sentence_words), 2
        )
        boxes.append(
            TextBox(
                text=sentence["text"].strip(),
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
                confidence=confidence,
            )
        )
    return boxes
