"""High-level offline translation pipeline.

English input -> local spelling/grammar repair -> MTranServer batch translation
-> Chinese output plus a machine-readable correction report.

The local layer never translates: MTranServer is the only translation backend.
This keeps quality and latency predictable.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from .grammar import correct as correct_english
from .lexicon import Lexicon
from .mtran import MTranClient, MTranError
from .tokenizer import Segment, split_sentences, tokenize

VERSION = "1.0.0"
WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?")


class TranslationEngine:
    def __init__(
        self,
        client: Optional[MTranClient] = None,
        lexicon: Optional[Lexicon] = None,
        *,
        server: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
        auto_start: bool = True,
        batch_size: int = 32,
        cache: bool = True,
    ) -> None:
        self.client = client or MTranClient(
            base_url=server, token=token, timeout=timeout, auto_start=auto_start
        )
        self.lexicon = lexicon or Lexicon()
        self.batch_size = max(1, int(batch_size))
        self.cache_enabled = cache

    # ------------------------------------------------------------------ public
    def translate(
        self,
        text: str,
        *,
        correct: bool = True,
        source: str = "en",
        target: str = "zh-Hans",
        analyze: bool = True,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        if text is None:
            raise TypeError("text must be a string")
        text = str(text)
        segments = split_sentences(text)

        processed: List[Dict[str, Any]] = []
        for index, seg in enumerate(segments):
            processed.append(
                self._process_segment(index, seg, correct=correct, analyze=analyze)
            )
        _attach_separators(processed, segments)

        to_translate = [
            item["corrected"] if item["corrected"].strip() else item["source"]
            for item in processed
        ]
        translations: List[str] = []
        if to_translate:
            try:
                translations = self.client.translate_batch(
                    to_translate,
                    source=source,
                    target=target,
                    batch_size=self.batch_size,
                )
            except MTranError:
                raise
            except Exception as exc:  # pragma: no cover - defensive boundary
                raise MTranError(f"translation failed: {exc}") from exc
        else:
            translations = []

        for item, translated in zip(processed, translations):
            item["translation"] = translated.strip()

        corrected_text = _join(processed, "corrected", chinese=False)
        translation_text = _join(processed, "translation", chinese=True)
        issues: List[Dict[str, Any]] = []
        for item in processed:
            for issue in item["issues"]:
                record = dict(issue)
                record["segment"] = item["index"]
                record["sentence"] = item["source"]
                issues.append(record)
        unknown = sorted({word for item in processed for word in item["unknown"]})
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

        return {
            "source": text,
            "corrected": corrected_text,
            "translation": translation_text,
            "segments": [
                {
                    "index": item["index"],
                    "source": item["source"],
                    "corrected": item["corrected"],
                    "translation": item["translation"],
                    "issues": item["issues"],
                    "unknown": item["unknown"],
                }
                for item in processed
            ],
            "issues": issues,
            "unknown": unknown,
            "stats": {
                "engine": "zhtrans",
                "version": VERSION,
                "backend": "MTranServer",
                "server": self.client.base_url,
                "characters": len(text),
                "words": sum(len(WORD_RE.findall(seg.text)) for seg in segments),
                "sentences": len(segments),
                "issues": len(issues),
                "elapsed_ms": elapsed_ms,
            },
        }

    def translate_text(
        self,
        text: str,
        *,
        correct: bool = True,
        source: str = "en",
        target: str = "zh-Hans",
    ) -> str:
        return self.translate(text, correct=correct, source=source, target=target)["translation"]

    def translate_file(
        self,
        path: Union[str, Path],
        *,
        encoding: str = "utf-8",
        correct: bool = True,
        source: str = "en",
        target: str = "zh-Hans",
    ) -> Dict[str, Any]:
        data = Path(path).read_text(encoding=encoding)
        return self.translate(data, correct=correct, source=source, target=target)

    def close(self) -> None:
        self.client.close()

    def _process_segment(
        self, index: int, seg: Segment, *, correct: bool, analyze: bool
    ) -> Dict[str, Any]:
        tokens = tokenize(seg.text)
        if correct:
            corrected, issues, unknown = correct_english(
                tokens,
                self.lexicon,
                seg.text,
                spelling=True,
                grammar=True,
            )
        else:
            corrected = seg.text.strip()
            issues = []
            unknown = []
        if not analyze:
            issues = []
            unknown = []
        return {
            "index": index,
            "source": seg.text,
            "corrected": corrected.strip(),
            "translation": "",
            "issues": [issue.to_dict() for issue in issues],
            "unknown": unknown,
        }


def _join(processed: Sequence[Dict[str, Any]], field: str, *, chinese: bool) -> str:
    if not processed:
        return ""
    # The separators are recovered from the original source via a fresh split
    # when the engine is created.  Here we use a simple rule: paragraph/newline
    # boundaries are preserved, while ordinary sentence spaces disappear in
    # Chinese and become a single space in corrected English.
    out: List[str] = []
    for i, item in enumerate(processed):
        if i:
            sep = processed[i - 1].get("_sep", "")
            if sep:
                if "\n" in sep:
                    out.append("\n\n" if sep.count("\n") >= 2 else "\n")
                elif not chinese:
                    out.append(" ")
        out.append(item.get(field, ""))
    return "".join(out).strip()


def _attach_separators(processed: Sequence[Dict[str, Any]], segments: Sequence[Segment]) -> None:
    for item, seg in zip(processed, segments):
        item["_sep"] = seg.sep


def translate(
    text: str,
    *,
    server: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 30.0,
    correct: bool = True,
    source: str = "en",
    target: str = "zh-Hans",
    auto_start: bool = True,
) -> Dict[str, Any]:
    """Convenience function for one-off use.

    For repeated calls, construct :class:`TranslationEngine` yourself so the
    lexicon and HTTP connection are reused.
    """
    client = MTranClient(
        base_url=server, token=token, timeout=timeout, auto_start=auto_start
    )
    engine = TranslationEngine(client=client)
    try:
        return engine.translate(text, correct=correct, source=source, target=target)
    finally:
        engine.close()


_default_engine: Optional[TranslationEngine] = None
_default_lock = threading.Lock()


def default_engine() -> TranslationEngine:
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            _default_engine = TranslationEngine()
        return _default_engine


def close_default() -> None:
    global _default_engine
    with _default_lock:
        if _default_engine is not None:
            _default_engine.close()
            _default_engine = None
