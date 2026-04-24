from __future__ import annotations

import re
import unicodedata

_SPACE_RE = re.compile(r"\s+")


def _is_kept_char(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category.startswith(("L", "N")) or ch in {" ", "-", "'"}


def normalize_query(query: str) -> str:
    """Normalize raw search query for rule matching."""
    if query is None:
        return ""
    text = str(query).strip().lower()
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = "".join(ch if _is_kept_char(ch) else " " for ch in text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def word_boundary_pattern(phrase: str) -> re.Pattern[str]:
    phrase = normalize_query(phrase)
    if not phrase:
        return re.compile(r"(?!x)x")
    pattern = r"(?<![\w])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![\w])"
    return re.compile(pattern)


def contains_phrase(text: str, phrase: str) -> bool:
    return word_boundary_pattern(phrase).search(text) is not None
