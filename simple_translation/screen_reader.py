"""第一部分：屏幕读取。

负责截取屏幕（或指定区域）并通过 OCR 识别出其中的文字。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import ScreenRegion, TextBox


_SENTENCE_ENDERS = (".", "!", "?")
_PSM_NAMES = {
    3: "AUTO",
    6: "SINGLE_BLOCK",
    7: "SINGLE_LINE",
    11: "SPARSE_TEXT",
    12: "SPARSE_TEXT_OSD",
    13: "RAW_LINE",
}


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

    def read_lines(self) -> list[TextBox]:
        """返回行级文本框；默认退化为句子级。"""
        return self.read_boxes()


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


def _capture_screen_with_origin(region: Optional[ScreenRegion] = None):
    """用 mss 截取屏幕，返回 (PIL.Image, (left, top))。"""
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
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return image, (int(monitor.get("left", 0)), int(monitor.get("top", 0)))


def _capture_screen(region: Optional[ScreenRegion] = None):
    """用 mss 截取屏幕，返回 PIL.Image。"""
    image, _origin = _capture_screen_with_origin(region)
    return image


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


def _find_tessdata() -> Optional[str]:
    """查找 Tesseract 语言包目录，供 tesserocr 使用。"""
    import os
    from pathlib import Path

    env_path = os.environ.get("TESSDATA_PREFIX")
    if env_path and Path(env_path).is_dir():
        return env_path

    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tessdata"
    if default.is_dir():
        return str(default)
    return None


def _resolve_psm(psm_module, psm: Optional[int]):
    if psm is None:
        return psm_module.AUTO
    name = _PSM_NAMES.get(psm)
    if name and hasattr(psm_module, name):
        return getattr(psm_module, name)
    return psm_module.AUTO


def _rescale(item: dict, scale: float) -> dict:
    """把识别坐标从缩放图映射回原图坐标。"""
    if scale == 1.0:
        return item
    factor = 1.0 / scale
    return {
        **item,
        "left": round(item["left"] * factor),
        "top": round(item["top"] * factor),
        "width": round(item["width"] * factor),
        "height": round(item["height"] * factor),
    }


def _sample_box_colors(image, left: int, top: int, width: int, height: int):
    """从原图文本框附近取主色作为背景色，并按亮度选黑/白文字。"""
    if image is None:
        return None, None
    from collections import Counter

    pad = 3
    x0 = max(0, left - pad)
    y0 = max(0, top - pad)
    x1 = min(image.width, left + width + pad)
    y1 = min(image.height, top + height + pad)
    if x1 <= x0 or y1 <= y0:
        return None, None

    pixels = list(image.crop((x0, y0, x1, y1)).convert("RGB").getdata())
    if not pixels:
        return None, None
    counter = Counter((r // 16, g // 16, b // 16) for r, g, b in pixels)
    dominant = counter.most_common(1)[0][0]
    matching = [p for p in pixels if (p[0] // 16, p[1] // 16, p[2] // 16) == dominant]
    background = tuple(
        sum(pixel[i] for pixel in matching) // len(matching) for i in range(3)
    )
    luminance = 0.299 * background[0] + 0.587 * background[1] + 0.114 * background[2]
    foreground = (0, 0, 0) if luminance > 140 else (255, 255, 255)
    return background, foreground


class TesseractScreenReader(ScreenReader):
    """基于 Tesseract 的英文读取器。

    优先使用进程内的 tesserocr，不可用时回退到 pytesseract。

    max_side：截图最长边超过该值时先等比缩小再识别，坐标自动映射回原图。
    workers：并行 worker 数，0 表示大图自动并行。
    diff：启用帧差分缓存。循环读取时只对屏幕变化区域重新 OCR，静态区域
    复用上一次结果，可显著降低整屏稳态耗时。
    """

    def __init__(
        self,
        region: Optional[ScreenRegion] = None,
        lang: str = "eng",
        psm: Optional[int] = None,
        min_conf: float = 0.0,
        max_side: Optional[int] = None,
        workers: int = 0,
        diff: bool = True,
        diff_threshold: int = 24,
    ):
        self.region = region
        self.lang = lang
        self.psm = psm
        self.min_conf = min_conf
        self.max_side = max_side
        self.workers = workers
        self.diff = diff
        self.diff_threshold = diff_threshold
        self._tess_api = None
        self._api_local = None
        self._prev_thumb = None
        self._cache_words = []
        self._cache_lines = []
        self.last_origin = (0, 0)
        self._last_image = None

    # ---- 截图 / 缩放 ----
    def _resize_for_ocr(self, image):
        from PIL import Image

        scale = 1.0
        if self.max_side and max(image.size) > self.max_side:
            scale = self.max_side / max(image.size)
            new_size = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            image = image.resize(new_size, Image.LANCZOS)
        return image, scale

    # ---- tesserocr ----
    def _make_tesserocr_api(self):
        from tesserocr import PyTessBaseAPI, PSM

        return PyTessBaseAPI(
            lang=self.lang,
            path=_find_tessdata(),
            psm=_resolve_psm(PSM, self.psm),
        )

    def _tesserocr(self):
        if self._tess_api is None:
            try:
                self._tess_api = self._make_tesserocr_api()
            except ImportError:
                return None
        return self._tess_api

    def _worker_api(self):
        if self._api_local is None:
            import threading

            self._api_local = threading.local()
        api = getattr(self._api_local, "api", None)
        if api is None:
            api = self._make_tesserocr_api()
            self._api_local.api = api
        return api

    def _effective_workers(self, image) -> int:
        if self.workers and self.workers > 1:
            return self.workers
        if self.workers == 0 and image.width * image.height > 800_000:
            import os

            return min(os.cpu_count() or 4, 8)
        return 1

    @staticmethod
    def _tesserocr_words(api, top_offset: int = 0) -> list[dict]:
        from tesserocr import RIL

        iterator = api.GetIterator()
        words = []
        while True:
            text = ""
            try:
                text = iterator.GetUTF8Text(RIL.WORD).strip()
            except RuntimeError:
                pass
            if text:
                left, top, right, bottom = iterator.BoundingBox(RIL.WORD)
                words.append(
                    {
                        "text": text,
                        "left": left,
                        "top": top_offset + top,
                        "width": right - left,
                        "height": bottom - top,
                        "confidence": iterator.Confidence(RIL.WORD),
                    }
                )
            try:
                has_next = iterator.Next(RIL.WORD)
            except RuntimeError:
                has_next = False
            if not has_next:
                break
        return words

    @staticmethod
    def _tesserocr_lines(api, top_offset: int = 0) -> list[dict]:
        from tesserocr import RIL

        iterator = api.GetIterator()
        lines = []
        while True:
            text = ""
            try:
                text = iterator.GetUTF8Text(RIL.TEXTLINE).strip()
            except RuntimeError:
                pass
            if text:
                left, top, right, bottom = iterator.BoundingBox(RIL.TEXTLINE)
                lines.append(
                    {
                        "text": text,
                        "left": left,
                        "top": top_offset + top,
                        "width": right - left,
                        "height": bottom - top,
                        "confidence": iterator.Confidence(RIL.TEXTLINE),
                    }
                )
            try:
                has_next = iterator.Next(RIL.TEXTLINE)
            except RuntimeError:
                has_next = False
            if not has_next:
                break
        return lines

    # ---- pytesseract（回退） ----
    def _tesseract_config(self) -> str:
        return f"--psm {self.psm}" if self.psm else ""

    def _ocr_data(self, image=None) -> dict:
        pytesseract = _pytesseract()
        from pytesseract import Output

        if image is None:
            image = _capture_screen(self.region)
        return pytesseract.image_to_data(
            image,
            lang=self.lang,
            output_type=Output.DICT,
            config=self._tesseract_config(),
        )

    # ---- OCR（单次 / 并行） ----
    def _ocr_strip(self, strip, top_offset: int):
        api = self._worker_api()
        api.SetImage(strip)
        api.Recognize()
        return (
            self._tesserocr_words(api, top_offset),
            self._tesserocr_lines(api, top_offset),
        )

    def _ocr_image_single(self, image, scale):
        api = self._tesserocr()
        if api is None:
            words = _words_from_data(self._ocr_data(image), self.min_conf)
            lines = _words_to_lines(words)
        else:
            api.SetImage(image)
            api.Recognize()
            words = [w for w in self._tesserocr_words(api) if w["confidence"] >= self.min_conf]
            lines = self._tesserocr_lines(api)
        return [_rescale(w, scale) for w in words], [_rescale(line, scale) for line in lines]

    def _ocr_image_parallel(self, image, scale, workers):
        from concurrent.futures import ThreadPoolExecutor

        height = image.height
        bounds = [(i * height // workers, (i + 1) * height // workers) for i in range(workers)]
        words = []
        lines = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self._ocr_strip,
                    image.crop((0, top, image.width, bottom)),
                    top,
                )
                for top, bottom in bounds
            ]
            for future in futures:
                strip_words, strip_lines = future.result()
                words.extend(strip_words)
                lines.extend(strip_lines)
        return [_rescale(w, scale) for w in words], [_rescale(line, scale) for line in lines]

    def _ocr_image(self, image, scale, offset_x: int = 0, offset_y: int = 0):
        workers = self._effective_workers(image)
        if workers > 1 and self._tesserocr() is not None:
            words, lines = self._ocr_image_parallel(image, scale, workers)
        else:
            words, lines = self._ocr_image_single(image, scale)
        if offset_x or offset_y:
            for item in words + lines:
                item["left"] += offset_x
                item["top"] += offset_y
        return words, lines

    def _ocr_region(self, image, x: int, y: int, w: int, h: int):
        crop = image.crop((x, y, x + w, y + h))
        resized, scale = self._resize_for_ocr(crop)
        return self._ocr_image(resized, scale, offset_x=x, offset_y=y)

    # ---- 帧差分 ----
    @staticmethod
    def _thumbnail(image, target_width: int = 160):
        from PIL import Image

        factor = target_width / image.width
        size = (target_width, max(1, round(image.height * factor)))
        return image.convert("L").resize(size, Image.BILINEAR)

    @staticmethod
    def _mask_components(mask):
        height = len(mask)
        width = len(mask[0]) if height else 0
        visited = [[False] * width for _ in range(height)]
        components = []
        for y in range(height):
            for x in range(width):
                if not mask[y][x] or visited[y][x]:
                    continue
                stack = [(y, x)]
                visited[y][x] = True
                min_x = max_x = x
                min_y = max_y = y
                while stack:
                    cy, cx = stack.pop()
                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < height and 0 <= nx < width and mask[ny][nx] and not visited[ny][nx]:
                            visited[ny][nx] = True
                            stack.append((ny, nx))
                components.append((min_x, min_y, max_x, max_y))
        return components

    @staticmethod
    def _merge_regions(regions):
        merged = []
        for region in sorted(regions):
            if not merged:
                merged.append(region)
                continue
            mx, my, mw, mh = merged[-1]
            x, y, w, h = region
            gap = 24
            if x <= mx + mw + gap and mx <= x + w + gap and y <= my + mh + gap and my <= y + h + gap:
                nx = min(mx, x)
                ny = min(my, y)
                merged[-1] = (nx, ny, max(mx + mw, x + w) - nx, max(my + mh, y + h) - ny)
            else:
                merged.append(region)
        return merged

    def _changed_regions(self, thumb, full_size):
        from PIL import ImageChops

        if self._prev_thumb is None or self._prev_thumb.size != thumb.size:
            return "FULL"

        diff = ImageChops.difference(thumb, self._prev_thumb)
        width, height = thumb.size
        pixels = list(diff.getdata())
        mask = [
            [pixels[y * width + x] > self.diff_threshold for x in range(width)]
            for y in range(height)
        ]
        changed = sum(row.count(True) for row in mask)
        if changed == 0:
            return []
        if changed / (width * height) > 0.5:
            return "FULL"

        components = self._mask_components(mask)
        fw, fh = full_size
        scale_x = fw / width
        scale_y = fh / height
        pad_x = max(4, round(8 * scale_x))
        pad_y = max(4, round(8 * scale_y))
        regions = []
        for x0, y0, x1, y1 in components:
            left = max(0, round(x0 * scale_x) - pad_x)
            top = max(0, round(y0 * scale_y) - pad_y)
            right = min(fw, round((x1 + 1) * scale_x) + pad_x)
            bottom = min(fh, round((y1 + 1) * scale_y) + pad_y)
            regions.append((left, top, right - left, bottom - top))

        regions = self._merge_regions(regions)
        if regions and sum(r[2] * r[3] for r in regions) / (fw * fh) > 0.6:
            return "FULL"
        return regions

    @staticmethod
    def _intersects_any(item, regions):
        x, y, w, h = item["left"], item["top"], item["width"], item["height"]
        for rx, ry, rw, rh in regions:
            if x < rx + rw and rx < x + w and y < ry + rh and ry < y + h:
                return True
        return False

    # ---- 对外读取（含差分缓存） ----
    def _read_full(self):
        image, origin = _capture_screen_with_origin(self.region)
        self.last_origin = origin
        self._last_image = image

        if not self.diff:
            resized, scale = self._resize_for_ocr(image)
            words, lines = self._ocr_image(resized, scale)
            words.sort(key=lambda w: (w["top"], w["left"]))
            lines.sort(key=lambda line: (line["top"], line["left"]))
            return words, lines

        thumb = self._thumbnail(image)
        if self._prev_thumb is None:
            resized, scale = self._resize_for_ocr(image)
            words, lines = self._ocr_image(resized, scale)
        else:
            regions = self._changed_regions(thumb, image.size)
            if not regions:
                words, lines = self._cache_words, self._cache_lines
            elif regions == "FULL":
                resized, scale = self._resize_for_ocr(image)
                words, lines = self._ocr_image(resized, scale)
            else:
                new_words = []
                new_lines = []
                for x, y, w, h in regions:
                    region_words, region_lines = self._ocr_region(image, x, y, w, h)
                    new_words.extend(region_words)
                    new_lines.extend(region_lines)
                words = [w for w in self._cache_words if not self._intersects_any(w, regions)] + new_words
                lines = [line for line in self._cache_lines if not self._intersects_any(line, regions)] + new_lines

        words.sort(key=lambda w: (w["top"], w["left"]))
        lines.sort(key=lambda line: (line["top"], line["left"]))
        self._prev_thumb = thumb
        self._cache_words = words
        self._cache_lines = lines
        return words, lines

    def read(self) -> str:
        _, lines = self._read_full()
        return "\n".join(line["text"] for line in lines)

    def read_words(self) -> list[TextBox]:
        words, _ = self._read_full()
        return [
            TextBox(
                text=w["text"],
                left=w["left"],
                top=w["top"],
                width=w["width"],
                height=w["height"],
                confidence=round(w["confidence"], 2),
            )
            for w in words
        ]

    def read_boxes(self) -> list[TextBox]:
        _, lines = self._read_full()
        return _merge_lines_into_sentences(lines)

    def read_lines(self) -> list[TextBox]:
        """返回行级文本框，用于按原文位置覆盖显示。"""
        _, lines = self._read_full()
        boxes = []
        for line in lines:
            background, foreground = _sample_box_colors(
                self._last_image,
                line["left"],
                line["top"],
                line["width"],
                line["height"],
            )
            boxes.append(
                TextBox(
                    text=line["text"],
                    left=line["left"],
                    top=line["top"],
                    width=line["width"],
                    height=line["height"],
                    confidence=round(line["confidence"], 2),
                    background=background,
                    foreground=foreground,
                )
            )
        return boxes


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


def _words_from_data(data: dict, min_conf: float = 0.0) -> list[dict]:
    """把 pytesseract 的 image_to_data 输出转成词列表。"""
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
    return words


def _words_to_lines(words: list[dict]) -> list[dict]:
    """把带 key 的词列表按行合并成统一结构的行列表。"""
    if not words:
        return []

    words = sorted(words, key=lambda item: item["key"])
    grouped = []
    current_line_key = None
    for word in words:
        line_key = word["key"][:3]
        if line_key != current_line_key:
            grouped.append({"text": word["text"], "words": [word]})
            current_line_key = line_key
        else:
            grouped[-1]["text"] += " " + word["text"]
            grouped[-1]["words"].append(word)

    lines = []
    for line in grouped:
        line_words = line["words"]
        left = min(word["left"] for word in line_words)
        top = min(word["top"] for word in line_words)
        right = max(word["left"] + word["width"] for word in line_words)
        bottom = max(word["top"] + word["height"] for word in line_words)
        lines.append(
            {
                "text": line["text"],
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
                "confidence": sum(word["confidence"] for word in line_words) / len(line_words),
            }
        )
    return lines


def _merge_lines_into_sentences(lines: list[dict]) -> list[TextBox]:
    """把行列表按句尾标点合并成句子文本框。"""
    sentences = []
    for line in lines:
        text = line["text"]
        if sentences and not sentences[-1]["ended"]:
            sentences[-1]["text"] += " " + text
            sentences[-1]["lines"].append(line)
        else:
            sentences.append({"text": text, "lines": [line], "ended": False})
        if text.endswith(_SENTENCE_ENDERS):
            sentences[-1]["ended"] = True

    boxes = []
    for sentence in sentences:
        line_items = sentence["lines"]
        left = min(item["left"] for item in line_items)
        top = min(item["top"] for item in line_items)
        right = max(item["left"] + item["width"] for item in line_items)
        bottom = max(item["top"] + item["height"] for item in line_items)
        confidence = round(
            sum(item["confidence"] for item in line_items) / len(line_items), 2
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


def _group_sentences(data: dict, min_conf: float = 0.0) -> list[TextBox]:
    """把 pytesseract 的 image_to_data 输出按句子分组成文本框。"""
    words = _words_from_data(data, min_conf)
    lines = _words_to_lines(words)
    return _merge_lines_into_sentences(lines)
