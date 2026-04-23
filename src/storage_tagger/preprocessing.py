from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s\-']+")


def normalize_query(query: str) -> str:
    """Normalize raw search query for rule matching."""
    if query is None:
        return ""
    text = str(query).strip().lower()
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def word_boundary_pattern(phrase: str) -> re.Pattern[str]:
    phrase = normalize_query(phrase)
    pattern = r"(?<![a-z0-9])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.compile(pattern)


def contains_phrase(text: str, phrase: str) -> bool:
    return word_boundary_pattern(phrase).search(text) is not None
