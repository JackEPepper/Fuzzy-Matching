"""
Text normalization and *weighted* fuzzy scoring.

The idea
--------
A normal edit distance (Levenshtein) says every character edit costs 1.
Here every character instead has a WEIGHT, and an edit costs that weight:

    * inserting/deleting a character costs that character's weight
    * substituting one character for another costs the larger of the two
      weights (optionally scaled by a custom cost for look-alike pairs such
      as "0" vs "o")

So if spaces have weight 0.1, "ACME CO" vs "ACMECO" differs by only 0.1
instead of a full 1.0. Words can also be down-weighted (e.g. "inc", "llc"),
which multiplies the weight of every character inside that word.

The final score is 0-100, where 100 means identical after normalization:

    score = 100 * (1 - weighted_distance / max(total_weight_a, total_weight_b))

Everything in this file is plain Python (no compiled dependencies), so it is
easy to read and change.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass
class WeightSettings:
    """All knobs that control normalization and weighting.

    You normally set these in ``config.py``; see that file for explanations.
    """

    case_sensitive: bool = False
    strip_accents: bool = True
    collapse_whitespace: bool = True

    # Plain-text replacements applied before scoring, e.g. {"&": " and "}
    replacements: Dict[str, str] = field(default_factory=dict)
    # Regex replacements applied after plain ones, e.g. {r"\bst\b": "street"}
    regex_replacements: Dict[str, str] = field(default_factory=dict)

    # Weight used when nothing more specific applies
    default_char_weight: float = 1.0
    # Weights by character class: letter, digit, whitespace, punctuation, other
    char_class_weights: Dict[str, float] = field(default_factory=dict)
    # Weights for specific characters (override the class weight)
    char_weights: Dict[str, float] = field(default_factory=dict)
    # Multipliers for whole words, e.g. {"inc": 0.2}
    word_weights: Dict[str, float] = field(default_factory=dict)
    # Cost multiplier for substituting specific character pairs, e.g.
    # {("0", "o"): 0.2}. Pairs are symmetric. Default multiplier is 1.0.
    substitution_costs: Dict[Tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Make the lookup keys match the normalized text (e.g. lower-case).
        fold = (lambda s: s) if self.case_sensitive else (lambda s: s.lower())
        self.char_weights = {fold(k): float(v) for k, v in self.char_weights.items()}
        self.word_weights = {fold(k): float(v) for k, v in self.word_weights.items()}
        self.replacements = {fold(k): v for k, v in self.replacements.items()}
        self._sub_lookup: Dict[str, Dict[str, float]] = {}
        for (a, b), cost in self.substitution_costs.items():
            a, b = fold(a), fold(b)
            self._sub_lookup.setdefault(a, {})[b] = float(cost)
            self._sub_lookup.setdefault(b, {})[a] = float(cost)
        self._compiled_regex = [
            (re.compile(p, 0 if self.case_sensitive else re.IGNORECASE), r)
            for p, r in self.regex_replacements.items()
        ]
        self._weight_cache: Dict[str, List[float]] = {}


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"\w+")


def is_missing(value) -> bool:
    """True for None / NaN / pandas NA."""
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN is the only value not equal to itself
    except (TypeError, ValueError):  # pandas.NA raises on bool()
        return True


def normalize(value, settings: WeightSettings) -> str:
    """Turn a raw cell value into the string that actually gets compared."""
    if is_missing(value):
        return ""
    text = str(value)

    if settings.strip_accents:
        # "Café" -> "Cafe"
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))

    if not settings.case_sensitive:
        text = text.lower()

    for old, new in settings.replacements.items():
        text = text.replace(old, new)
    for pattern, new in settings._compiled_regex:
        text = pattern.sub(new, text)

    if settings.collapse_whitespace:
        text = _WHITESPACE.sub(" ", text).strip()
    return text


# --------------------------------------------------------------------------- #
# Weights
# --------------------------------------------------------------------------- #
def char_class(c: str) -> str:
    """Classify one character as letter/digit/whitespace/punctuation/other."""
    if c.isspace():
        return "whitespace"
    if c.isdigit():
        return "digit"
    if c.isalpha():
        return "letter"
    if unicodedata.category(c)[0] in ("P", "S"):  # punctuation & symbols
        return "punctuation"
    return "other"


def char_weight(c: str, settings: WeightSettings) -> float:
    """Weight of a single character, ignoring any word-level multiplier."""
    if c in settings.char_weights:
        return settings.char_weights[c]
    return settings.char_class_weights.get(char_class(c), settings.default_char_weight)


def position_weights(text: str, settings: WeightSettings) -> List[float]:
    """Weight of every character in an (already normalized) string.

    Character weight x word multiplier (if the character is inside a word
    listed in ``word_weights``).
    """
    cached = settings._weight_cache.get(text)
    if cached is not None:
        return cached

    weights = [char_weight(c, settings) for c in text]
    if settings.word_weights:
        for m in _WORD.finditer(text):
            multiplier = settings.word_weights.get(m.group())
            if multiplier is not None:
                for i in range(m.start(), m.end()):
                    weights[i] *= multiplier

    settings._weight_cache[text] = weights
    return weights


# --------------------------------------------------------------------------- #
# Weighted edit distance
# --------------------------------------------------------------------------- #
def weighted_distance(
    a: str,
    b: str,
    settings: WeightSettings,
    wa: Optional[List[float]] = None,
    wb: Optional[List[float]] = None,
) -> float:
    """Weighted Levenshtein distance between two normalized strings."""
    if wa is None:
        wa = position_weights(a, settings)
    if wb is None:
        wb = position_weights(b, settings)

    sub_lookup = settings._sub_lookup
    empty: Dict[str, float] = {}

    # Classic dynamic-programming table, kept one row at a time.
    prev = [0.0]
    for w in wb:
        prev.append(prev[-1] + w)

    for i, ca in enumerate(a):
        w_a = wa[i]
        pair_costs = sub_lookup.get(ca, empty)
        cur = [prev[0] + w_a]
        for j, cb in enumerate(b):
            w_b = wb[j]
            if ca == cb:
                substitute = prev[j]
            else:
                substitute = prev[j] + pair_costs.get(cb, 1.0) * (w_a if w_a > w_b else w_b)
            delete = prev[j + 1] + w_a
            insert = cur[j] + w_b
            best = substitute
            if delete < best:
                best = delete
            if insert < best:
                best = insert
            cur.append(best)
        prev = cur
    return prev[-1]


def similarity_normalized(a: str, b: str, settings: WeightSettings) -> float:
    """0-100 similarity between two strings that are ALREADY normalized."""
    if a == b:
        return 100.0
    wa = position_weights(a, settings)
    wb = position_weights(b, settings)
    total = max(sum(wa), sum(wb))
    if total <= 0:
        # Both strings consist only of zero-weight characters.
        return 100.0
    dist = weighted_distance(a, b, settings, wa, wb)
    return max(0.0, 1.0 - dist / total) * 100.0


def similarity(a, b, settings: Optional[WeightSettings] = None) -> float:
    """0-100 similarity between two raw values (normalizes them first).

    Handy for trying out settings:  similarity("Acme, Inc.", "ACME Inc", s)
    """
    settings = settings or WeightSettings()
    na, nb = normalize(a, settings), normalize(b, settings)
    if not na and not nb:
        return 0.0  # two blanks are not a meaningful match
    return similarity_normalized(na, nb, settings)


def explain(a, b, settings: Optional[WeightSettings] = None) -> str:
    """Human-readable breakdown of how two values are scored."""
    settings = settings or WeightSettings()
    lines = []
    for label, raw in (("A", a), ("B", b)):
        norm = normalize(raw, settings)
        weights = position_weights(norm, settings)
        lines.append(f"{label} raw:        {raw!r}")
        lines.append(f"{label} normalized: {norm!r}")
        lines.append(
            f"{label} weights:    "
            + " ".join(f"{c!r}={w:g}" for c, w in zip(norm, weights))
        )
        lines.append(f"{label} total weight: {sum(weights):g}")
    na, nb = normalize(a, settings), normalize(b, settings)
    lines.append(f"weighted distance: {weighted_distance(na, nb, settings):g}")
    lines.append(f"score: {similarity(a, b, settings):.2f}")
    return "\n".join(lines)
