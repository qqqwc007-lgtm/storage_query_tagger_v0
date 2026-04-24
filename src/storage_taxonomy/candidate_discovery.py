from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .taxonomy_registry import TaxonomyRegistry

_NOISE_CANDIDATE_TERMS = {
    "black",
    "white",
    "gray",
    "grey",
    "blue",
    "red",
    "green",
    "pink",
    "brown",
    "beige",
    "clear",
    "small",
    "medium",
    "large",
    "pack",
    "pcs",
    "pc",
    "piece",
    "pieces",
    "set",
    "sets",
    "home",
    "office",
    "room",
    "living",
    "bedroom",
    "kitchen",
    "bathroom",
    "school",
    "dorm",
    "decor",
    "indoor",
    "outdoor",
}


def _parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return [part.strip() for part in text.split("|") if part.strip()]


def _is_noise_candidate(value: str, suppressed_terms: set[str] | None = None) -> bool:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return True
    if suppressed_terms and candidate in suppressed_terms:
        return True
    if candidate in _NOISE_CANDIDATE_TERMS:
        return True
    if len(candidate) <= 2:
        return True
    if re.fullmatch(r"[\d\W_]+", candidate):
        return True
    if re.search(r"\d", candidate) and " <> " not in candidate:
        return True
    return False


def discover_candidate_values(
    kw_df: pd.DataFrame,
    st_df: pd.DataFrame,
    diff_df: pd.DataFrame,
    registry: TaxonomyRegistry | None = None,
) -> pd.DataFrame:
    registry = registry or TaxonomyRegistry()
    candidate_cfg = registry.thresholds.get("candidate_discovery", {})
    min_frequency = int(candidate_cfg.get("min_frequency", 1))
    suppressed_terms = registry.candidate_suppression_terms

    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "source_phrases": set(),
        "example_terms": set(),
        "frequency": 0,
        "search_volume_sum": 0.0,
    })

    for df in [kw_df, st_df]:
        if df.empty or "unmapped_phrases" not in df.columns:
            continue
        for row in df.to_dict("records"):
            search_volume = pd.to_numeric(row.get("search_volume", 0), errors="coerce")
            for phrase in _parse_json_list(row.get("unmapped_phrases")):
                if _is_noise_candidate(phrase, suppressed_terms):
                    continue
                key = ("unknown", phrase)
                bucket = buckets[key]
                bucket["source_phrases"].add(phrase)
                bucket["example_terms"].add(str(row.get("search_term") or row.get("title") or ""))
                bucket["frequency"] += 1
                bucket["search_volume_sum"] += 0.0 if pd.isna(search_volume) else float(search_volume)

    if not diff_df.empty:
        conflicts = diff_df[diff_df["diff_type"] == "true_conflict"]
        for row in conflicts.to_dict("records"):
            axis = str(row.get("field_name", "unknown"))
            phrase = f"{row.get('kw_value', '')} <> {row.get('st_value', '')}".strip()
            if _is_noise_candidate(phrase, suppressed_terms):
                continue
            key = (axis, phrase)
            bucket = buckets[key]
            bucket["source_phrases"].add(phrase)
            bucket["example_terms"].add(str(row.get("search_term", "")))
            bucket["frequency"] += 1

    rows = []
    for (axis, candidate_value), bucket in buckets.items():
        if bucket["frequency"] < min_frequency:
            continue
        rows.append({
            "candidate_value": candidate_value,
            "axis": axis,
            "source_phrases": " | ".join(sorted(bucket["source_phrases"])),
            "example_terms": " | ".join(sorted(term for term in bucket["example_terms"] if term)),
            "frequency": bucket["frequency"],
            "search_volume_sum": round(bucket["search_volume_sum"], 2),
            "suggested_aliases": candidate_value if axis != "unknown" else "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_as_alias_or_new_canonical" if axis != "unknown" else "review_candidate_phrase",
            "review_status": "pending",
        })

    columns = [
        "candidate_value",
        "axis",
        "source_phrases",
        "example_terms",
        "frequency",
        "search_volume_sum",
        "suggested_aliases",
        "suggested_rollup_parent",
        "suggested_action",
        "review_status",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(["frequency", "candidate_value"], ascending=[False, True])


def discover_candidate_values_from_files(
    kw_csv: str | Path,
    st_csv: str | Path,
    diff_csv: str | Path,
    registry: TaxonomyRegistry | None = None,
    chunk_size: int = 200_000,
) -> pd.DataFrame:
    registry = registry or TaxonomyRegistry()
    candidate_cfg = registry.thresholds.get("candidate_discovery", {})
    min_frequency = int(candidate_cfg.get("min_frequency", 1))
    suppressed_terms = registry.candidate_suppression_terms

    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "source_phrases": set(),
        "example_terms": set(),
        "frequency": 0,
        "search_volume_sum": 0.0,
    })

    def add_candidate(axis: str, candidate_value: str, source_phrase: str, example_term: str, search_volume: Any = 0) -> None:
        if _is_noise_candidate(candidate_value, suppressed_terms):
            return
        key = (axis, candidate_value)
        bucket = buckets[key]
        bucket["source_phrases"].add(source_phrase)
        if example_term:
            bucket["example_terms"].add(example_term)
        bucket["frequency"] += 1
        numeric_volume = pd.to_numeric(search_volume, errors="coerce")
        bucket["search_volume_sum"] += 0.0 if pd.isna(numeric_volume) else float(numeric_volume)

    for path, example_col in [(kw_csv, "search_term"), (st_csv, "title")]:
        if not Path(path).exists():
            continue
        with Path(path).open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unmapped_value = str(row.get("unmapped_phrases", "")).strip()
                if not unmapped_value or unmapped_value == "[]":
                    continue
                for phrase in _parse_json_list(unmapped_value):
                    add_candidate("unknown", phrase, phrase, str(row.get(example_col, "")), row.get("search_volume", 0))

    if Path(diff_csv).exists():
        with Path(diff_csv).open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("diff_type") != "true_conflict":
                    continue
                phrase = f"{row.get('kw_value', '')} <> {row.get('st_value', '')}".strip()
                add_candidate(str(row.get("field_name", "unknown")), phrase, phrase, str(row.get("search_term", "")), 0)

    rows = []
    for (axis, candidate_value), bucket in buckets.items():
        if bucket["frequency"] < min_frequency:
            continue
        rows.append({
            "candidate_value": candidate_value,
            "axis": axis,
            "source_phrases": " | ".join(sorted(bucket["source_phrases"])),
            "example_terms": " | ".join(sorted(term for term in bucket["example_terms"] if term)),
            "frequency": bucket["frequency"],
            "search_volume_sum": round(bucket["search_volume_sum"], 2),
            "suggested_aliases": candidate_value if axis != "unknown" else "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_as_alias_or_new_canonical" if axis != "unknown" else "review_candidate_phrase",
            "review_status": "pending",
        })

    columns = [
        "candidate_value",
        "axis",
        "source_phrases",
        "example_terms",
        "frequency",
        "search_volume_sum",
        "suggested_aliases",
        "suggested_rollup_parent",
        "suggested_action",
        "review_status",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(["frequency", "candidate_value"], ascending=[False, True])
