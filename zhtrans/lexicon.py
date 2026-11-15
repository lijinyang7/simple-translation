"""Offline lexicon, morphology, phrase table and spelling helpers.

Everything in this module is deterministic and stdlib-only.  The data lives
in ``zhtrans/data`` as tab-separated UTF-8 files so it can be extended without
touching Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .types import FormInfo

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Sense:
    pos: str
    zh: str
    cls: str = ""
    flags: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Phrase:
    text: str
    zh: str
    pos: str
    flags: Tuple[str, ...] = ()


# Word contractions are expanded for translation, while the original surface
# form is retained for the correction report and output.
CONTRACTIONS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "i'm": (("i", "PRON", "我"), ("am", "AUX", "是")),
    "i've": (("i", "PRON", "我"), ("have", "AUX", "有")),
    "i'll": (("i", "PRON", "我"), ("will", "MODAL", "会")),
    "i'd": (("i", "PRON", "我"), ("would", "MODAL", "会")),
    "you're": (("you", "PRON", "你"), ("are", "AUX", "是")),
    "you've": (("you", "PRON", "你"), ("have", "AUX", "有")),
    "you'll": (("you", "PRON", "你"), ("will", "MODAL", "会")),
    "you'd": (("you", "PRON", "你"), ("would", "MODAL", "会")),
    "he's": (("he", "PRON", "他"), ("is", "AUX", "是")),
    "he've": (("he", "PRON", "他"), ("have", "AUX", "有")),
    "he'll": (("he", "PRON", "他"), ("will", "MODAL", "会")),
    "he'd": (("he", "PRON", "他"), ("would", "MODAL", "会")),
    "she's": (("she", "PRON", "她"), ("is", "AUX", "是")),
    "she'll": (("she", "PRON", "她"), ("will", "MODAL", "会")),
    "she'd": (("she", "PRON", "她"), ("would", "MODAL", "会")),
    "it's": (("it", "PRON", "它"), ("is", "AUX", "是")),
    "it'll": (("it", "PRON", "它"), ("will", "MODAL", "会")),
    "we're": (("we", "PRON", "我们"), ("are", "AUX", "是")),
    "we've": (("we", "PRON", "我们"), ("have", "AUX", "有")),
    "we'll": (("we", "PRON", "我们"), ("will", "MODAL", "会")),
    "we'd": (("we", "PRON", "我们"), ("would", "MODAL", "会")),
    "they're": (("they", "PRON", "他们"), ("are", "AUX", "是")),
    "they've": (("they", "PRON", "他们"), ("have", "AUX", "有")),
    "they'll": (("they", "PRON", "他们"), ("will", "MODAL", "会")),
    "they'd": (("they", "PRON", "他们"), ("would", "MODAL", "会")),
    "there's": (("there", "PRON", "那里"), ("is", "AUX", "是")),
    "that's": (("that", "PRON", "那"), ("is", "AUX", "是")),
    "what's": (("what", "PRON", "什么"), ("is", "AUX", "是")),
    "who's": (("who", "PRON", "谁"), ("is", "AUX", "是")),
    "where's": (("where", "ADV", "哪里"), ("is", "AUX", "是")),
    "when's": (("when", "ADV", "什么时候"), ("is", "AUX", "是")),
    "how's": (("how", "ADV", "怎么"), ("is", "AUX", "是")),
    "let's": (("let", "V", "让"), ("us", "PRON", "我们")),
    "don't": (("do", "AUX", ""), ("not", "ADV", "不")),
    "doesn't": (("does", "AUX", ""), ("not", "ADV", "不")),
    "didn't": (("did", "AUX", ""), ("not", "ADV", "不")),
    "isn't": (("is", "AUX", "是"), ("not", "ADV", "不")),
    "aren't": (("are", "AUX", "是"), ("not", "ADV", "不")),
    "wasn't": (("was", "AUX", "是"), ("not", "ADV", "不")),
    "weren't": (("were", "AUX", "是"), ("not", "ADV", "不")),
    "haven't": (("have", "AUX", "有"), ("not", "ADV", "不")),
    "hasn't": (("has", "AUX", "有"), ("not", "ADV", "不")),
    "hadn't": (("had", "AUX", "有"), ("not", "ADV", "不")),
    "can't": (("can", "MODAL", "能"), ("not", "ADV", "不")),
    "cannot": (("can", "MODAL", "能"), ("not", "ADV", "不")),
    "couldn't": (("could", "MODAL", "能"), ("not", "ADV", "不")),
    "won't": (("will", "MODAL", "会"), ("not", "ADV", "不")),
    "wouldn't": (("would", "MODAL", "会"), ("not", "ADV", "不")),
    "shouldn't": (("should", "MODAL", "应该"), ("not", "ADV", "不")),
    "mustn't": (("must", "MODAL", "必须"), ("not", "ADV", "不")),
    "needn't": (("need", "MODAL", "需要"), ("not", "ADV", "不")),
    "ain't": (("is", "AUX", "是"), ("not", "ADV", "不")),
    "gonna": (("going", "V", "去"), ("to", "PART", "到")),
    "wanna": (("want", "V", "想要"), ("to", "PART", "到")),
    "gotta": (("got", "V", "得到"), ("to", "PART", "到")),
}

IRREGULAR_NOUNS = {
    "child": "children",
    "man": "men",
    "woman": "women",
    "person": "people",
    "foot": "feet",
    "tooth": "teeth",
    "mouse": "mice",
    "goose": "geese",
    "ox": "oxen",
    "leaf": "leaves",
    "life": "lives",
    "knife": "knives",
    "wife": "wives",
    "wolf": "wolves",
    "half": "halves",
    "shelf": "shelves",
    "thief": "thieves",
}

IRREGULAR_ADJECTIVES = {
    "good": ("better", "best"),
    "bad": ("worse", "worst"),
    "many": ("more", "most"),
    "much": ("more", "most"),
    "little": ("less", "least"),
    "far": ("farther", "farthest"),
    "old": ("elder", "eldest"),
}

DOUBLING_VERBS = {
    "admit", "begin", "chat", "commit", "control", "drop", "fit", "get",
    "hit", "jog", "let", "plan", "prefer", "put", "quit", "refer", "run",
    "set", "shop", "sit", "slip", "stop", "swim", "travel", "win",
}


class Lexicon:
    """Loaded once and shared by all sentences."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)
        self.senses: Dict[str, List[Sense]] = {}
        self.forms: Dict[str, "FormInfo"] = {}
        self.base_words: set[str] = set()
        self.known_only: set[str] = set()
        self.known: set[str] = set()
        self.phrase_trie: Dict[str, Dict] = {}
        self.phrases: Dict[Tuple[str, ...], Phrase] = {}
        self.misspellings: Dict[str, str] = {}
        self.irregular_verbs: Dict[str, Tuple[str, str]] = {}
        self._spell_buckets: Dict[str, List[str]] = {}

        self._load_lexicon_files()
        self._load_irregular_verbs()
        self._build_forms()
        self._load_phrases()
        self._load_misspellings()
        self._build_spell_index()

    # ------------------------------------------------------------------ load
    def _lexicon_files(self) -> List[Path]:
        files = sorted(self.data_dir.glob("lexicon*.tsv"))
        if not files:
            raise FileNotFoundError(f"no lexicon*.tsv found under {self.data_dir}")
        return files

    def _load_lexicon_files(self) -> None:
        for path in self._lexicon_files():
            with path.open("r", encoding="utf-8-sig") as fh:
                for line_no, raw in enumerate(fh, 1):
                    line = raw.rstrip("\r\n")
                    if not line or line.startswith("#"):
                        continue
                    cols = line.split("\t")
                    if len(cols) < 3:
                        raise ValueError(f"{path.name}:{line_no}: expected 3+ columns")
                    word = cols[0].strip().lower()
                    pos = cols[1].strip().upper()
                    zh = cols[2].strip()
                    if zh == "-":
                        zh = ""
                    cls = cols[3].strip() if len(cols) > 3 else ""
                    flags = tuple(x for x in (cols[4].strip().split(",") if len(cols) > 4 else []) if x)
                    if not word or not pos:
                        continue
                    sense = Sense(pos, zh, cls, flags)
                    self.senses.setdefault(word, []).append(sense)

        for word, senses in self.senses.items():
            self.base_words.add(word)
            self.known.add(word)
            primary = senses[0]
            self.forms.setdefault(
                word,
                FormInfo(word, primary.pos, primary.zh, primary.cls, "base", primary.flags),
            )

    def _load_irregular_verbs(self) -> None:
        path = self.data_dir / "irregular_verbs.tsv"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split("\t")
                if len(cols) < 3:
                    continue
                base = cols[0].strip().lower()
                past = cols[1].strip().lower()
                pp = cols[2].strip().lower()
                self.irregular_verbs[base] = (past, pp)

    def _build_forms(self) -> None:
        # Base forms are already registered.  Generated forms never override a
        # real dictionary headword (e.g. "left" as adjective beats "leave" past).
        for word, senses in list(self.senses.items()):
            for sense in senses:
                if sense.pos in ("V", "AUX"):
                    if word == "be":
                        for surface, form in (
                            ("am", "base"), ("is", "base"), ("are", "base"),
                            ("was", "past"), ("were", "past"),
                            ("been", "pp"), ("being", "ing"),
                        ):
                            self._add_generated(surface, word, sense.pos, sense, form)
                        continue
                    for form, surface in self._verb_forms(word).items():
                        self._add_generated(surface, word, sense.pos, sense, form)
                elif sense.pos == "N":
                    plural = self._plural(word)
                    if plural:
                        self._add_generated(plural, word, "N", sense, "pl")
                elif sense.pos == "ADJ":
                    comp, sup = self._adjective_forms(word)
                    self._add_generated(comp, word, "ADJ", sense, "comp")
                    self._add_generated(sup, word, "ADJ", sense, "sup")
                elif sense.pos == "ADV" and word.endswith("ly"):
                    pass

        # Adverb derivation from adjectives: beautiful -> beautifully.
        for word, senses in list(self.senses.items()):
            adj = next((s for s in senses if s.pos == "ADJ"), None)
            if adj is None:
                continue
            adv = self._adverb(word)
            if adv and adv not in self.forms:
                self._add_generated(adv, word, "ADV", Sense("ADV", adj.zh + "地", "", ("derived",)), "adv")

        self.known.update(self.forms)

    def _add_generated(self, surface: str, lemma: str, pos: str, sense: Sense, form: str) -> None:
        if not surface or surface == lemma:
            return
        if surface in self.forms:
            self.known.add(surface)
            return
        self.forms[surface] = FormInfo(lemma, pos, sense.zh, sense.cls, form, sense.flags)
        self.known.add(surface)

    @staticmethod
    def _plural(word: str) -> str:
        if word in IRREGULAR_NOUNS:
            return IRREGULAR_NOUNS[word]
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ies"
        if word.endswith("fe"):
            return word[:-2] + "ves"
        if word.endswith("f"):
            return word[:-1] + "ves"
        return word + "s"

    @staticmethod
    def _third_person(word: str) -> str:
        if word in ("be", "have", "do"):
            return {"be": "is", "have": "has", "do": "does"}[word]
        if word.endswith(("s", "x", "z", "ch", "sh", "o")):
            return word + "es"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ies"
        return word + "s"

    @staticmethod
    def _past(word: str) -> str:
        if word in DOUBLING_VERBS and len(word) >= 3:
            return word + word[-1] + "ed"
        if word.endswith("e"):
            return word + "d"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ied"
        return word + "ed"

    @staticmethod
    def _ing(word: str) -> str:
        if word in ("be", "see", "free"):
            return word + "ing"
        if word.endswith("ie"):
            return word[:-2] + "ying"
        if word.endswith("e") and not word.endswith("ee"):
            return word[:-1] + "ing"
        if word in DOUBLING_VERBS:
            return word + word[-1] + "ing"
        return word + "ing"

    def _verb_forms(self, word: str) -> Dict[str, str]:
        forms: Dict[str, str] = {}
        if word == "be":
            for surface in ("am", "is", "are", "was", "were", "been", "being"):
                forms["base" if surface in ("am", "is", "are") else "pp" if surface == "been" else "ing" if surface == "being" else "past"] = surface
            return forms
        if word == "have":
            return {"3sg": "has", "past": "had", "pp": "had", "ing": "having"}
        if word == "do":
            return {"3sg": "does", "past": "did", "pp": "done", "ing": "doing"}
        past, pp = self.irregular_verbs.get(word, (self._past(word), self._past(word)))
        forms["3sg"] = self._third_person(word)
        forms["past"] = past
        forms["pp"] = pp
        forms["ing"] = self._ing(word)
        return forms

    @staticmethod
    def _adjective_forms(word: str) -> Tuple[str, str]:
        if word in IRREGULAR_ADJECTIVES:
            return IRREGULAR_ADJECTIVES[word]
        if word.endswith("e"):
            return word + "r", word + "st"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ier", word[:-1] + "iest"
        if _is_cvc(word):
            return word + word[-1] + "er", word + word[-1] + "est"
        return word + "er", word + "est"

    @staticmethod
    def _adverb(word: str) -> str:
        if word in ("true", "due", "whole"):
            return {"true": "truly", "due": "duly", "whole": "wholly"}[word]
        if word == "public":
            return "publicly"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ily"
        if word.endswith("le"):
            return word[:-1] + "y"
        if word.endswith("ic"):
            return word + "ally"
        if word.endswith("ll"):
            return word + "y"
        return word + "ly"

    def _load_phrases(self) -> None:
        for path in sorted(self.data_dir.glob("phrases*.tsv")):
            with path.open("r", encoding="utf-8-sig") as fh:
                for line_no, raw in enumerate(fh, 1):
                    line = raw.rstrip("\r\n")
                    if not line or line.startswith("#"):
                        continue
                    cols = line.split("\t")
                    if len(cols) < 3:
                        raise ValueError(f"{path.name}:{line_no}: expected 3+ columns")
                    english = cols[0].strip()
                    zh = cols[1].strip()
                    pos = cols[2].strip().upper()
                    flags = tuple(x for x in (cols[3].strip().split(",") if len(cols) > 3 else []) if x)
                    words = tuple(w.lower() for w in english.split())
                    if len(words) < 2:
                        continue
                    phrase = Phrase(english, zh, pos, flags)
                    self.phrases[words] = phrase
                    node = self.phrase_trie
                    for word in words:
                        node = node.setdefault(word, {})
                    node["$"] = phrase
                    for word in words:
                        self.known_only.add(word)
                        self.known.add(word)

    def _load_misspellings(self) -> None:
        path = self.data_dir / "misspellings.tsv"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8-sig") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split("\t")
                if len(cols) >= 2:
                    self.misspellings[cols[0].strip().lower()] = cols[1].strip().lower()

    def _build_spell_index(self) -> None:
        for word in self.base_words:
            if len(word) < 2 or not word.isalpha():
                continue
            self._spell_buckets.setdefault(word[:1], []).append(word)

    # --------------------------------------------------------------- analysis
    def analyze(self, text: str) -> FormInfo:
        low = text.lower().replace("\u2019", "'")
        info = self.forms.get(low)
        if info is not None:
            return info
        if low in self.known_only:
            return FormInfo(low, "", low, "", "base", ("unknown",), True)
        return FormInfo(low, "", low, "", "base", ("unknown",), False)

    def is_known(self, text: str) -> bool:
        low = text.lower().replace("\u2019", "'")
        return low in self.known or low in self.base_words

    def has_pos(self, text: str, pos: str) -> bool:
        low = text.lower()
        if any(s.pos == pos for s in self.senses.get(low, ())):
            return True
        info = self.forms.get(low)
        return bool(info and info.pos == pos)

    def conjugate(self, lemma: str, form: str) -> str:
        lemma = lemma.lower()
        if form == "base":
            return lemma
        if form == "pl":
            return self._plural(lemma)
        if form == "3sg":
            return self._third_person(lemma)
        if form == "past":
            if lemma in self.irregular_verbs:
                return self.irregular_verbs[lemma][0]
            return self._past(lemma)
        if form == "pp":
            if lemma in self.irregular_verbs:
                return self.irregular_verbs[lemma][1]
            return self._past(lemma)
        if form == "ing":
            return self._ing(lemma)
        if form in ("comp", "sup"):
            comp, sup = self._adjective_forms(lemma)
            return comp if form == "comp" else sup
        return lemma

    def senses_of(self, lemma: str) -> Sequence[Sense]:
        return self.senses.get(lemma.lower(), ())

    def phrase_at(self, units: Sequence, index: int) -> Tuple[int, Optional[Phrase]]:
        """Return (number_of_units, phrase) for the longest phrase at index."""
        node = self.phrase_trie
        best_len = 0
        best: Optional[Phrase] = None
        j = index
        while j < len(units):
            lemma = units[j].lemma.lower()
            if lemma not in node:
                break
            node = node[lemma]
            j += 1
            hit = node.get("$")
            if hit is not None:
                best_len = j - index
                best = hit
        return best_len, best

    # -------------------------------------------------------------- spelling
    def correction(self, word: str) -> Optional[str]:
        """High-precision spelling candidate for an unknown lowercase word."""
        low = word.lower()
        if low in self.misspellings:
            return self.misspellings[low]
        if len(low) < 4 or not low.isalpha():
            return None
        best: List[Tuple[int, str]] = []
        best_dist = 2
        for cand in self._spell_buckets.get(low[:1], ()):
            if len(cand) < 4 or abs(len(cand) - len(low)) > 1:
                continue
            d = _damerau(low, cand, best_dist)
            if d < best_dist:
                best_dist = d
                best = [(d, cand)]
            elif d == best_dist:
                best.append((d, cand))
        if best_dist > 1 or not best:
            return None
        # Ambiguous candidates are not rewritten automatically.
        unique = {cand for _, cand in best}
        if len(unique) != 1:
            return None
        return next(iter(unique))

    def suggestions(self, word: str, limit: int = 3) -> List[str]:
        low = word.lower()
        if len(low) < 3:
            return []
        found: List[Tuple[int, str]] = []
        for cand in self._spell_buckets.get(low[:1], ()):
            if abs(len(cand) - len(low)) > 1:
                continue
            d = _damerau(low, cand, 2)
            if d <= 2:
                found.append((d, cand))
        found.sort(key=lambda x: (x[0], x[1]))
        return [c for _, c in found[:limit]]


def _is_cvc(word: str) -> bool:
    if len(word) < 3:
        return False
    vowels = "aeiou"
    return (
        word[-1] not in vowels + "wxy"
        and word[-2] in vowels
        and word[-3] not in vowels
        and sum(1 for ch in word if ch in vowels) == 1
    )


def _damerau(a: str, b: str, limit: int = 2) -> int:
    """Damerau-Levenshtein distance with an early length guard.

    Implemented as an optimal-string-alignment distance.  The strings here are
    short English words, so the compact O(n*m) table is more than fast enough.
    """
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if a == b:
        return 0
    da: Dict[str, int] = {}
    maxdist = len(a) + len(b)
    d = [[0] * (len(b) + 2) for _ in range(len(a) + 2)]
    d[0][0] = maxdist
    for i in range(len(a) + 1):
        d[i + 1][0] = maxdist
        d[i + 1][1] = i
    for j in range(len(b) + 1):
        d[0][j + 1] = maxdist
        d[1][j + 1] = j
    for i in range(1, len(a) + 1):
        db = 0
        for j in range(1, len(b) + 1):
            i1 = da.get(b[j - 1], 0)
            j1 = db
            cost = 1
            if a[i - 1] == b[j - 1]:
                cost = 0
                db = j
            d[i + 1][j + 1] = min(
                d[i][j] + cost,
                d[i + 1][j] + 1,
                d[i][j + 1] + 1,
                d[i1][j1] + (i - i1 - 1) + 1 + (j - j1 - 1),
            )
        da[a[i - 1]] = i
    return d[len(a) + 1][len(b) + 1]
