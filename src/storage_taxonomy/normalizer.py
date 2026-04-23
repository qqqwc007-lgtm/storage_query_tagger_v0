from __future__ import annotations

import re
import unicodedata
from typing import Mapping

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s\-']+")


def _normalize_base(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.lower().strip())
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = _PUNCT_RE.sub(" ", text)
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
    pattern = r"(?<![a-z0-9])" + re.escape(normalized).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.compile(pattern)


def contains_phrase(text: str, phrase: str) -> bool:
    return word_boundary_pattern(phrase).search(text) is not None


def tokenize(text: str) -> list[str]:
    return [token for token in normalize_text(text).split(" ") if token]
