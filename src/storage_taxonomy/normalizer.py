from __future__ import annotations

import re
import unicodedata
from typing import Mapping

_SPACE_RE = re.compile(r"\s+")


def _is_kept_char(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category.startswith(("L", "N")) or ch in {" ", "-", "'"}


def _normalize_base(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.lower().strip())
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = "".join(ch if _is_kept_char(ch) else " " for ch in text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def normalize_text(text: str | None, phrase_rewrites: Mapping[str, str] | None = None) -> str:
    if text is None:
        return ""
    normalized = _normalize_base(str(text))
    if not normalized:
        return ""
    if phrase_rewrites:
        for source, target in sorted(phrase_rewrites.items(), key=lambda item: len(item[0]), reverse=True):
            pattern = word_boundary_pattern(source)
            replacement = _normalize_base(target)
            normalized = pattern.sub(replacement, normalized)
        normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized


def word_boundary_pattern(phrase: str) -> re.Pattern[str]:
    normalized = _normalize_base(phrase)
    if not normalized:
        return re.compile(r"(?!x)x")
    pattern = r"(?<![\w])" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?![\w])"
    return re.compile(pattern)


def contains_phrase(text: str, phrase: str) -> bool:
    return word_boundary_pattern(phrase).search(text) is not None


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split(" ") if token]
