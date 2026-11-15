"""Deterministic spelling and grammar repair.

The rules are intentionally conservative: a rule only rewrites text when the
pattern is strong enough to be useful for learner/typo-heavy input.  Every
change is recorded as an :class:`Issue` with the original character span.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from .lexicon import Lexicon
from .types import Issue, Token, match_case

PRONOUNS = {
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
}

SINGULAR_3 = {"he", "she", "it"}
PLURAL_SUBJECTS = {"you", "we", "they"}

AUX_CONTRACTIONS = {
    "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "haven't", "hasn't", "hadn't", "can't", "couldn't", "won't", "wouldn't",
    "shouldn't", "mustn't", "needn't", "ain't",
}

PAST_MARKERS = {
    "yesterday", "ago", "formerly", "previously",
}
TIME_NOUNS = {
    "week", "month", "year", "night", "morning", "afternoon", "evening",
    "summer", "winter", "spring", "autumn", "fall", "decade", "century",
}

IRREGULAR_CONFUSIONS = {
    "alot": "a lot",
    "alright": "all right",
    "aswell": "as well",
    "infact": "in fact",
    "incase": "in case",
    "everyday": "every day",
}

VOWEL_EXCEPTIONS = {
    "hour", "honest", "honor", "honour", "heir", "herb",
}
CONSONANT_EXCEPTIONS = {
    "university", "universal", "union", "unique", "uniform", "unit",
    "united", "use", "used", "useful", "user", "usual", "usually",
    "european", "one", "once", "ubiquitous",
}

ARTICLE_VERBS = {
    "have", "has", "had", "want", "wants", "wanted", "need", "needs",
    "buy", "buys", "bought", "see", "sees", "saw", "eat", "eats", "ate",
    "read", "reads", "find", "finds", "found", "like", "likes", "liked",
    "make", "makes", "made", "get", "gets", "got",
}


def _words(tokens: Sequence[Token]) -> List[int]:
    return [i for i, t in enumerate(tokens) if t.kind == "word" and not t.deleted]


def _next_word(tokens: Sequence[Token], index: int) -> Optional[int]:
    for j in range(index + 1, len(tokens)):
        if tokens[j].kind == "word" and not tokens[j].deleted:
            return j
        if tokens[j].kind == "punct" and tokens[j].text not in "-'\u2019":
            return None
    return None


def _prev_word(tokens: Sequence[Token], index: int) -> Optional[int]:
    for j in range(index - 1, -1, -1):
        if tokens[j].kind == "word" and not tokens[j].deleted:
            return j
        if tokens[j].kind == "punct":
            return None
    return None


def _is_plural(tok: Token) -> bool:
    if tok.form == "pl":
        return True
    return tok.lemma in {"people", "children", "men", "women", "data", "police"}


def _needs_an(word: str) -> bool:
    w = word.lower()
    if w in VOWEL_EXCEPTIONS:
        return True
    if w in CONSONANT_EXCEPTIONS:
        return False
    if not w:
        return False
    if w[0].isdigit():
        return w.startswith(("8", "11", "18"))
    return w[0] in "aeiou"


def _record(
    issues: List[Issue],
    kind: str,
    severity: str,
    message: str,
    tok: Optional[Token] = None,
    original: str = "",
    suggestion: str = "",
    start: int = 0,
    end: int = 0,
) -> None:
    if tok is not None:
        start, end = tok.start, tok.end
        if not original:
            original = tok.text
    issues.append(Issue(kind, severity, message, original, suggestion, start, end))


def _set(tok: Token, new_text: str, issues: List[Issue], kind: str, message: str, severity: str = "error") -> None:
    if not new_text or new_text == tok.text:
        return
    old = tok.text
    shown = match_case(old, new_text)
    tok.text = shown
    _record(issues, kind, severity, message.format(old=old, new=shown), tok, original=old, suggestion=shown)


def correct(
    tokens: List[Token],
    lexicon: Lexicon,
    sentence: str,
    spelling: bool = True,
    grammar: bool = True,
) -> Tuple[str, List[Issue], List[str]]:
    issues: List[Issue] = []
    unknown: List[str] = []

    for tok in tokens:
        tok.refresh(lexicon)
        tok.deleted = False
        tok.prefix = ""

    if spelling:
        _spell(tokens, lexicon, issues, unknown, sentence)
        for tok in tokens:
            tok.refresh(lexicon)

    if grammar:
        _grammar(tokens, lexicon, issues, sentence)
        for tok in tokens:
            tok.refresh(lexicon)

    corrected, appended = _rebuild(sentence, tokens)
    corrected = _normalize_spacing(corrected)
    if appended:
        corrected = _append_terminal(corrected, appended)
        issues.append(
            Issue("punctuation", "warning", f"句末缺少标点，已补上 {appended}",
                  "", appended, len(sentence), len(sentence))
        )
    return corrected, issues, sorted(set(unknown))


def _spell(tokens: List[Token], lex: Lexicon, issues: List[Issue], unknown: List[str], sentence: str) -> None:
    for idx, tok in enumerate(tokens):
        if tok.kind != "word" or tok.deleted:
            continue
        low = tok.text.lower().replace("\u2019", "'")
        if "'" in low and low not in lex.misspellings:
            continue
        if lex.is_known(low):
            continue
        # Mid-sentence capitalised words are likely names; do not churn them.
        if idx > 0 and tok.text[:1].isupper() and not tok.text.isupper():
            continue
        if tok.text.isupper() and len(tok.text) > 1:
            continue
        candidate = lex.correction(low)
        if candidate is None:
            if low.isalpha():
                unknown.append(low)
            continue
        old = tok.text
        tok.text = match_case(old, candidate)
        _record(
            issues,
            "spelling",
            "error",
            f"拼写错误：{old} → {tok.text}",
            tok,
            original=old,
            suggestion=tok.text,
        )


def _is_verb(tok: Token, lex: Lexicon) -> bool:
    return (
        tok.pos in ("V", "AUX", "MODAL")
        or tok.lower in AUX_CONTRACTIONS
        or lex.has_pos(tok.lemma, "V")
    )


def _grammar(tokens: List[Token], lex: Lexicon, issues: List[Issue], sentence: str) -> None:
    def is_verb(tok: Token) -> bool:
        return _is_verb(tok, lex)

    # 1. Lone lowercase i.
    for tok in tokens:
        if tok.kind == "word" and tok.text == "i":
            _set(tok, "I", issues, "grammar", "人称代词 I 应大写")

    # 2. Capitalise the first word.
    first = _next_word(tokens, -1)
    if first is not None:
        tok = tokens[first]
        if tok.text and tok.text[0].islower() and not any(c.isupper() for c in tok.text[1:]):
            _set(tok, tok.text[0].upper() + tok.text[1:], issues, "grammar", "句首字母应大写")

    # 3. a / an.
    for i, tok in enumerate(tokens):
        if tok.kind != "word" or tok.deleted or tok.lower not in ("a", "an"):
            continue
        nxt = _next_word(tokens, i)
        if nxt is None:
            continue
        target = "an" if _needs_an(tokens[nxt].text) else "a"
        if tok.lower != target:
            _set(tok, target, issues, "grammar", f"冠词错误：{tok.text} → {target}")

    # 4. Repeated words.
    for i in range(1, len(tokens)):
        prev = _prev_word(tokens, i)
        tok = tokens[i]
        if prev is None or tok.kind != "word" or tok.deleted:
            continue
        if tok.lower == tokens[prev].lower and tok.lower not in {"had", "that", "very"}:
            old = tok.text
            tok.deleted = True
            _record(issues, "grammar", "warning", f"重复用词：{old} {old}", tok, original=old)

    # 4b. Shift present verbs after a past-time marker before agreement runs,
    # so "Yesterday he go" is repaired once to "went", not "goes" then "went".
    _tense_shift(tokens, lex, issues)
    for tok in tokens:
        tok.refresh(lex)

    # 5. Subject-verb agreement for the common pronoun cases.
    for i, tok in enumerate(tokens):
        if tok.kind != "word" or tok.deleted:
            continue
        if not is_verb(tok):
            continue
        subj_idx = _subject_pronoun(tokens, i)
        if subj_idx is None:
            continue
        subj = tokens[subj_idx].lower
        _agree(tok, subj, lex, issues)

    # 6. there is/are and there have.
    _there_be(tokens, lex, issues)

    # 7. one of the ... are -> is.
    lows = [t.lower for t in tokens]
    for i in range(len(tokens) - 2):
        if lows[i] == "one" and lows[i + 1] == "of":
            for j in range(i + 2, min(len(tokens), i + 12)):
                if tokens[j].lower in ("are", "were"):
                    _set(tokens[j], "is" if tokens[j].lower == "are" else "was",
                         issues, "grammar", "one of 后接复数名词时谓语用单数")
                    break

    # 8. Base form after do/modal/to; past participle after have.
    for i, tok in enumerate(tokens):
        if tok.kind != "word" or tok.deleted:
            continue
        low = tok.lower
        nxt = _next_word(tokens, i)
        if nxt is None:
            continue
        nt = tokens[nxt]
        if not is_verb(nt) or nt.deleted:
            continue
        if low in ("do", "does", "did", "don't", "doesn't", "didn't") or tok.pos == "MODAL" or low == "to":
            if nt.form in ("past", "3sg", "ing") and low != "to":
                _set(nt, lex.conjugate(nt.lemma, "base"), issues, "grammar", "助动词/情态动词后应用动词原形")
            elif nt.form in ("past", "3sg") and low == "to":
                _set(nt, lex.conjugate(nt.lemma, "base"), issues, "grammar", "不定式 to 后应用动词原形")
        elif low in ("have", "has", "had"):
            if nt.form == "past":
                pp = lex.conjugate(nt.lemma, "pp")
                if pp != nt.text.lower():
                    _set(nt, pp, issues, "grammar", "完成时中应使用过去分词")

    # 8b. could of -> could have (phonetic confusion).
    for i, tok in enumerate(tokens):
        if tok.lower not in ("could", "would", "should", "must", "might") or tok.deleted:
            continue
        nxt = _next_word(tokens, i)
        if nxt is not None and tokens[nxt].lower == "of":
            _set(tokens[nxt], "have", issues, "grammar", "情态动词后应是 have，不是 of")

    # 9. I am agree -> I agree.
    for i, tok in enumerate(tokens):
        if tok.lower in ("am", "is", "are", "was", "were"):
            nxt = _next_word(tokens, i)
            if nxt is not None and tokens[nxt].lemma == "agree":
                tok.deleted = True
                _record(issues, "grammar", "error", "be 动词不能直接接 agree，应说 I agree", tok,
                        original=tok.text)

    # 10. be + base verb -> progressive.
    for i, tok in enumerate(tokens):
        if tok.lower not in ("am", "is", "are", "was", "were", "be", "been") or tok.deleted:
            continue
        nxt = _next_word(tokens, i)
        if nxt is None or tokens[nxt].deleted:
            continue
        nt = tokens[nxt]
        if is_verb(nt) and nt.form == "base" and nt.lemma not in ("be", "have", "do"):
            _set(nt, lex.conjugate(nt.lemma, "ing"), issues, "grammar", "be 动词后应使用现在分词或形容词")

    # 11. more better / most best.
    for i, tok in enumerate(tokens):
        if tok.lower in ("more", "most") and not tok.deleted:
            nxt = _next_word(tokens, i)
            if nxt is not None and tokens[nxt].form in ("comp", "sup"):
                tok.deleted = True
                _record(issues, "grammar", "warning", f"比较级重复：{tok.text} {tokens[nxt].text}", tok,
                        original=tok.text)

    # 12. Missing article before a singular countable noun.
    for i, tok in enumerate(tokens):
        if tok.lower not in ARTICLE_VERBS or tok.deleted:
            continue
        nxt = _next_word(tokens, i)
        if nxt is None or tokens[nxt].deleted:
            continue
        nt = tokens[nxt]
        if (
            nt.pos == "N"
            and nt.form == "base"
            and nt.cls
            and "mass" not in nt.flags
            and "no_article" not in nt.flags
            and nt.lemma not in ("home", "school", "work", "church")
        ):
            article = "an" if _needs_an(nt.text) else "a"
            nt.prefix = article + " "
            _record(issues, "grammar", "warning", f"可数名词前可能缺少冠词：{article} {nt.text}", nt,
                    original=nt.text, suggestion=f"{article} {nt.text}")

    # 13b. "He is doctor" -> "He is a doctor".
    for i, tok in enumerate(tokens):
        if tok.lower not in ("am", "is", "are", "was", "were") or tok.deleted:
            continue
        nxt = _next_word(tokens, i)
        if nxt is None:
            continue
        nt = tokens[nxt]
        if (
            nt.pos == "N"
            and nt.form == "base"
            and "human" in nt.flags
            and "no_article" not in nt.flags
        ):
            article = "an" if _needs_an(nt.text) else "a"
            nt.prefix = article + " "
            _record(issues, "grammar", "warning", f"职业名词前缺少冠词：{article} {nt.text}", nt,
                    original=nt.text, suggestion=f"{article} {nt.text}")

    # 14. Final punctuation is reported by the caller after rebuilding.
    stripped = sentence.rstrip()
    if stripped and stripped[-1] not in ".!?":
        # The actual appended character is computed during rebuild.
        pass


def _subject_pronoun(tokens: Sequence[Token], index: int) -> Optional[int]:
    j = index - 1
    while j >= 0:
        tok = tokens[j]
        if tok.kind == "punct":
            return None
        if tok.deleted:
            j -= 1
            continue
        if tok.kind != "word":
            j -= 1
            continue
        low = tok.lower
        if low in PRONOUNS:
            k = j - 1
            while k >= 0 and tokens[k].kind != "word":
                if tokens[k].kind == "punct" and tokens[k].text in (",", ";"):
                    return None
                k -= 1
            if k >= 0 and tokens[k].lower in ("and", "or"):
                return None
            return j
        if low in AUX_CONTRACTIONS:
            j -= 1
            continue
        if tok.pos == "ADV" or low in ("not", "never", "also", "just", "still", "already"):
            j -= 1
            continue
        return None
    return None


def _agree(tok: Token, subj: str, lex: Lexicon, issues: List[Issue]) -> None:
    low = tok.lower
    if subj in SINGULAR_3:
        if low == "are":
            _set(tok, "is", issues, "grammar", "主谓一致：第三人称单数用 is")
        elif low == "were":
            _set(tok, "was", issues, "grammar", "主谓一致：第三人称单数用 was")
        elif low == "have":
            _set(tok, "has", issues, "grammar", "主谓一致：第三人称单数用 has")
        elif low == "do":
            _set(tok, "does", issues, "grammar", "主谓一致：第三人称单数用 does")
        elif low == "don't":
            _set(tok, "doesn't", issues, "grammar", "主谓一致：第三人称单数用 doesn't")
        elif low == "haven't":
            _set(tok, "hasn't", issues, "grammar", "主谓一致：第三人称单数用 hasn't")
        elif low == "aren't":
            _set(tok, "isn't", issues, "grammar", "主谓一致：第三人称单数用 isn't")
        elif low == "weren't":
            _set(tok, "wasn't", issues, "grammar", "主谓一致：第三人称单数用 wasn't")
        elif lex.has_pos(tok.lemma, "V") and tok.form == "base":
            _set(tok, lex.conjugate(tok.lemma, "3sg"), issues, "grammar", "主谓一致：第三人称单数动词加 -s")
    elif subj == "i":
        if low == "is" or low == "are":
            _set(tok, "am", issues, "grammar", "主谓一致：I 用 am")
        elif low == "were":
            _set(tok, "was", issues, "grammar", "主谓一致：I 用 was")
        elif low == "has":
            _set(tok, "have", issues, "grammar", "主谓一致：I 用 have")
        elif low == "does":
            _set(tok, "do", issues, "grammar", "主谓一致：I 用 do")
        elif low == "doesn't":
            _set(tok, "don't", issues, "grammar", "主谓一致：I 用 don't")
        elif low == "hasn't":
            _set(tok, "haven't", issues, "grammar", "主谓一致：I 用 haven't")
        elif lex.has_pos(tok.lemma, "V") and tok.form in ("3sg", "pl"):
            _set(tok, lex.conjugate(tok.lemma, "base"), issues, "grammar", "主谓一致：I 后用动词原形")
    elif subj in PLURAL_SUBJECTS:
        if low == "is":
            _set(tok, "are", issues, "grammar", "主谓一致：复数主语用 are")
        elif low == "was":
            _set(tok, "were", issues, "grammar", "主谓一致：复数主语用 were")
        elif low == "has":
            _set(tok, "have", issues, "grammar", "主谓一致：复数主语用 have")
        elif low == "does":
            _set(tok, "do", issues, "grammar", "主谓一致：复数主语用 do")
        elif low == "doesn't":
            _set(tok, "don't", issues, "grammar", "主谓一致：复数主语用 don't")
        elif low == "hasn't":
            _set(tok, "haven't", issues, "grammar", "主谓一致：复数主语用 haven't")
        elif low == "isn't":
            _set(tok, "aren't", issues, "grammar", "主谓一致：复数主语用 aren't")
        elif low == "wasn't":
            _set(tok, "weren't", issues, "grammar", "主谓一致：复数主语用 weren't")
        elif lex.has_pos(tok.lemma, "V") and tok.form in ("3sg", "pl"):
            _set(tok, lex.conjugate(tok.lemma, "base"), issues, "grammar", "主谓一致：复数主语后用动词原形")


def _there_be(tokens: List[Token], lex: Lexicon, issues: List[Issue]) -> None:
    for i, tok in enumerate(tokens):
        if tok.lower != "there" or tok.deleted:
            continue
        be_idx = None
        for j in range(i + 1, min(len(tokens), i + 4)):
            if tokens[j].lower in ("is", "are", "was", "were", "have", "has", "had"):
                be_idx = j
                break
        if be_idx is None:
            continue
        noun = None
        for j in range(be_idx + 1, min(len(tokens), be_idx + 8)):
            if tokens[j].pos == "N" and not tokens[j].deleted:
                noun = tokens[j]
                break
        if noun is None:
            continue
        plural = _is_plural(noun)
        be = tokens[be_idx]
        low = be.lower
        target: Optional[str] = None
        if low in ("have", "has", "had"):
            target = "are" if plural else "is"
            _set(be, target, issues, "grammar", "There be 句型不能直接用 have，应按名词单复数用 is/are")
            continue
        if plural:
            target = {"is": "are", "was": "were"}.get(low)
        else:
            target = {"are": "is", "were": "was"}.get(low)
        if target:
            _set(be, target, issues, "grammar", "There be 句型应与后面的名词保持数一致")


def _tense_shift(tokens: List[Token], lex: Lexicon, issues: List[Issue]) -> None:
    words = [t.lower for t in tokens if t.kind == "word" and not t.deleted]
    has_past_marker = any(w in PAST_MARKERS for w in words)
    if not has_past_marker:
        for i in range(len(words) - 1):
            if words[i] == "last" and words[i + 1] in TIME_NOUNS:
                has_past_marker = True
                break
    if not has_past_marker:
        return
    if any(w in ("will", "would", "can", "could", "may", "might", "must", "should") for w in words):
        return
    for i, tok in enumerate(tokens):
        if tok.kind != "word" or tok.deleted or not _is_verb(tok, lex):
            continue
        if tok.form not in ("base", "3sg"):
            continue
        if tok.lemma in ("be", "have", "do"):
            continue
        prev = _prev_word(tokens, i)
        if prev is not None and tokens[prev].lower in (
            "to", "do", "does", "did", "will", "would", "can", "could",
            "may", "might", "must", "should", "am", "is", "are", "was", "were",
        ):
            continue
        _set(tok, lex.conjugate(tok.lemma, "past"), issues, "grammar", "过去时间状语提示应使用过去式")


def _rebuild(sentence: str, tokens: Sequence[Token]) -> Tuple[str, str]:
    out: List[str] = []
    last = 0
    for tok in tokens:
        gap = sentence[last:tok.start]
        if tok.deleted:
            if gap.strip():
                out.append(gap)
            last = tok.end
            continue
        out.append(gap)
        out.append(tok.prefix)
        out.append(tok.text)
        last = tok.end
    out.append(sentence[last:])
    text = "".join(out)

    # If the sentence ends in a comma/semicolon, replace it with a full stop.
    stripped = text.rstrip()
    appended = ""
    if stripped and stripped[-1] not in ".!?":
        if stripped[-1] in ",;:":
            text = stripped[:-1].rstrip()
        appended = "?" if _question_like(tokens) else "."
    return text, appended


def _question_like(tokens: Sequence[Token]) -> bool:
    words = [t.lower for t in tokens if t.kind == "word" and not t.deleted]
    if not words:
        return False
    wh = {"what", "where", "when", "why", "how", "who", "whom", "whose", "which"}
    aux = {"am", "is", "are", "was", "were", "do", "does", "did", "have", "has", "had",
           "can", "could", "will", "would", "should", "may", "might", "must"}
    return words[0] in wh or words[0] in aux


def _append_terminal(text: str, punct: str) -> str:
    text = text.rstrip().rstrip(",;:")
    text = text.rstrip()
    if not text:
        return punct
    if text[-1] in "\"'\u201d\u2019)]}":
        return text[:-1].rstrip() + punct + text[-1]
    return text + punct


def _normalize_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


