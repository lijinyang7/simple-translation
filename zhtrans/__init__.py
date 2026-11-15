"""zhtrans: offline English -> Chinese CLI/library powered by MTranServer.

Quick use::

    import zhtrans

    result = zhtrans.translate("I has a apple.")
    print(result["translation"])
    print(result["issues"])

For repeated calls, keep a :class:`TranslationEngine`::

    engine = zhtrans.TranslationEngine()
    print(engine.translate_text("Hello, world!"))
    engine.close()
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .engine import (
    VERSION,
    TranslationEngine,
    close_default,
    default_engine,
    translate as _translate,
)
from .mtran import MTranClient, MTranError, MTranUnavailable

__all__ = [
    "VERSION",
    "TranslationEngine",
    "MTranClient",
    "MTranError",
    "MTranUnavailable",
    "translate",
    "translate_text",
    "correct",
    "check_server",
    "close_default",
]

__version__ = VERSION


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
    """Translate one text and return the full result dictionary."""
    return _translate(
        text,
        server=server,
        token=token,
        timeout=timeout,
        correct=correct,
        source=source,
        target=target,
        auto_start=auto_start,
    )


def translate_text(
    text: str,
    *,
    server: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 30.0,
    correct: bool = True,
    source: str = "en",
    target: str = "zh-Hans",
    auto_start: bool = True,
) -> str:
    """Translate one text and return only the Chinese string."""
    return translate(
        text,
        server=server,
        token=token,
        timeout=timeout,
        correct=correct,
        source=source,
        target=target,
        auto_start=auto_start,
    )["translation"]


def correct(text: str) -> Dict[str, Any]:
    """Run only the local spelling/grammar layer (no server needed)."""
    from .grammar import correct as _correct
    from .lexicon import Lexicon
    from .tokenizer import split_sentences, tokenize

    lex = Lexicon()
    segments = []
    issues = []
    unknown = set()
    corrected_parts = []
    source_segments = split_sentences(text)
    for index, seg in enumerate(source_segments):
        fixed, seg_issues, seg_unknown = _correct(tokenize(seg.text), lex, seg.text)
        segments.append(
            {
                "index": index,
                "source": seg.text,
                "corrected": fixed,
                "issues": [i.to_dict() for i in seg_issues],
                "unknown": seg_unknown,
            }
        )
        issues.extend(
            dict(i.to_dict(), segment=index, sentence=seg.text) for i in seg_issues
        )
        unknown.update(seg_unknown)
        if corrected_parts and "\n" in source_segments[index - 1].sep:
            corrected_parts.append(
                "\n\n" if source_segments[index - 1].sep.count("\n") >= 2 else "\n"
            )
        elif corrected_parts:
            corrected_parts.append(" ")
        corrected_parts.append(fixed)
    return {
        "source": text,
        "corrected": "".join(corrected_parts).strip(),
        "segments": segments,
        "issues": issues,
        "unknown": sorted(unknown),
    }


def check_server(
    server: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 5.0,
    auto_start: bool = True,
) -> bool:
    """Return True if /languages answers successfully (may start bundle)."""
    client = MTranClient(
        base_url=server, token=token, timeout=timeout, auto_start=auto_start
    )
    try:
        return client.ping()
    finally:
        client.close()
