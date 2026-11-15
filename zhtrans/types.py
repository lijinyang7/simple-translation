"""Small, dependency-free value objects shared by the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple


@dataclass
class Token:
    """A surface token with its original character span.

    ``text`` is mutable because spelling/grammar repair edits the token in
    place while the original ``start``/``end`` offsets stay valid.
    """

    text: str
    start: int
    end: int
    kind: str = "word"          # word | number | punct
    lower: str = ""
    lemma: str = ""
    pos: str = ""
    zh: str = ""
    cls: str = ""
    form: str = "base"          # base | 3sg | past | pp | ing | pl | comp | sup | adv
    flags: Tuple[str, ...] = ()
    known: bool = True
    deleted: bool = False
    prefix: str = ""

    def refresh(self, lexicon: Any) -> "Token":
        self.lower = self.text.lower().replace("\u2019", "'")
        info = lexicon.analyze(self.text)
        self.lemma = info.lemma
        self.pos = info.pos
        self.zh = info.zh
        self.cls = info.cls
        self.form = info.form
        self.flags = info.flags
        self.known = info.known
        return self


@dataclass
class Unit:
    """A translation unit: one word, one phrase, or one punctuation mark."""

    text: str
    lemma: str
    pos: str
    zh: str
    cls: str = ""
    form: str = "base"
    flags: Tuple[str, ...] = ()
    kind: str = "word"          # word | phrase | punct
    known: bool = True

    @property
    def lower(self) -> str:
        return self.text.lower().replace("\u2019", "'")


@dataclass
class Issue:
    kind: str                   # spelling | grammar | punctuation | unknown
    severity: str               # error | warning | info
    message: str
    original: str = ""
    suggestion: str = ""
    start: int = 0
    end: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.kind,
            "severity": self.severity,
            "message": self.message,
            "original": self.original,
            "suggestion": self.suggestion,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class FormInfo:
    lemma: str
    pos: str
    zh: str
    cls: str
    form: str
    flags: Tuple[str, ...]
    known: bool = True


def match_case(source: str, replacement: str) -> str:
    """Carry the obvious casing of *source* over to *replacement*."""
    if not replacement:
        return replacement
    if source.isupper() and len(source) > 1:
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def join_zh(parts: Sequence[str]) -> str:
    """Join Chinese fragments without introducing accidental spaces."""
    return "".join(p for p in parts if p)
