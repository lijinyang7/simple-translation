"""Sentence splitting and a compact English tokenizer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .types import Token

WORD_RE = re.compile(
    r"[A-Za-z]+(?:['\u2019\-][A-Za-z]+)*"
    r"|\d+(?:[.,]\d+)*"
    r"|\.\.\.|--"
    r"|[^\sA-Za-z\d]"
)

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "u.s", "u.k", "no", "fig", "al", "inc", "ltd", "co",
    "dept", "est", "approx", "jan", "feb", "mar", "apr", "jun", "jul",
    "aug", "sep", "sept", "oct", "nov", "dec",
}


@dataclass
class Segment:
    text: str
    start: int
    end: int
    sep: str = ""


def split_sentences(text: str) -> List[Segment]:
    """Split prose into sentences, preserving the whitespace after each one."""
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    n = len(text)
    segments: List[Segment] = []
    start = 0
    i = 0

    def emit(end: int) -> int:
        nonlocal start
        piece = text[start:end]
        stripped = piece.strip()
        if not stripped:
            return end
        lead = len(piece) - len(piece.lstrip())
        real_start = start + lead
        real_end = real_start + len(stripped)
        k = end
        while k < n and text[k].isspace():
            k += 1
        segments.append(Segment(stripped, real_start, real_end, text[end:k]))
        start = k
        return k

    while i < n:
        ch = text[i]
        if ch == "\n":
            # A line break is a safe sentence boundary when the line has text.
            if text[start:i].strip():
                k = i + 1
                while k < n and text[k].isspace():
                    k += 1
                emit(i)
                i = start
                continue
            i += 1
            continue

        if ch in ".!?":
            if ch == "." and 0 < i < n - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
                i += 1
                continue
            j = i + 1
            while j < n and text[j] in "\"'\u201d\u2019)]}":
                j += 1
            if j < n and not text[j].isspace():
                i += 1
                continue
            token = _last_token(text, start, i)
            if ch == "." and _is_abbreviation(token, i, n, text):
                i += 1
                continue
            if text[start:j].strip():
                k = j
                while k < n and text[k].isspace():
                    k += 1
                segments.append(Segment(text[start:j].strip(), start, j, text[j:k]))
                start = k
                i = k
                continue
        i += 1

    if text[start:].strip():
        piece = text[start:]
        stripped = piece.strip()
        lead = len(piece) - len(piece.lstrip())
        segments.append(Segment(stripped, start + lead, start + lead + len(stripped), ""))
    return segments


def _last_token(text: str, start: int, dot: int) -> str:
    j = dot - 1
    while j >= start and (text[j].isalnum() or text[j] in ".'"):
        j -= 1
    return text[j + 1:dot].lower().strip(".")


def _is_abbreviation(token: str, dot: int, n: int, text: str) -> bool:
    if token in _ABBREVIATIONS:
        return True
    # Single initials such as "J. K. Rowling" and dotted acronyms.
    if len(token) == 1 and token.isalpha():
        return True
    if "." in token:
        return True
    # A number followed by a dot and a space at end of line is usually a list.
    return False


def tokenize(sentence: str) -> List[Token]:
    tokens: List[Token] = []
    for match in WORD_RE.finditer(sentence):
        raw = match.group(0)
        start, end = match.span()
        if raw[0].isdigit():
            kind = "number"
        elif raw[0].isalpha():
            kind = "word"
        else:
            kind = "punct"
        tokens.append(
            Token(
                text=raw,
                start=start,
                end=end,
                kind=kind,
                lower=raw.lower().replace("\u2019", "'"),
            )
        )
    return tokens
