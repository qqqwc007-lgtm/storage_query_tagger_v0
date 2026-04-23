from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .taxonomy_registry import ALL_FIELDS, PRODUCT_FORM_FIELD, TaxonomyRegistry

DIFF_COLUMNS = [
    "search_term",
    "asin",
    "field_name",
    "kw_value",
    "st_value",
    "diff_type",
    "review_required",
    "rollup_parent_if_any",
    "resolution_note",
    "asin_rank",
    "search_frequency_rank",
    "review_priority",
    "kw_mapping_status",
    "st_mapping_status",
    "taxonomy_version",
]


def _parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in text.split("|") if part.strip()]


def compare_field(axis: str, kw_value: Any, st_value: Any, registry: TaxonomyRegistry) -> tuple[str | None, str]:
    if axis == PRODUCT_FORM_FIELD:
        left = _parse_list(kw_value)
        right = _parse_list(st_value)
        if not left and not right:
            return None, ""
        if set(left) == set(right):
            return "exact_match", ""
        if not left or not right:
            return "missing_value", ""
        overlap = registry.rollup_overlap(axis, left, right)
        if overlap:
            return "rollup_match", "|".join(sorted(overlap))
        return "true_conflict", ""

    left = str(kw_value or "").strip()
    right = str(st_value or "").strip()
    if not left and not right:
        return None, ""
    if left == right:
        return "exact_match", ""
    if not left or not right:
        return "missing_value", ""
    overlap = registry.rollup_overlap(axis, {left}, {right})
    if overlap:
        return "rollup_match", "|".join(sorted(overlap))
    return "true_conflict", ""


def build_diff_df(
    kw_df: pd.DataFrame,
    st_df: pd.DataFrame,
    registry: TaxonomyRegistry | None = None,
) -> pd.DataFrame:
    registry = registry or TaxonomyRegistry()
    rows: list[dict[str, Any]] = []
    kw_index = kw_df.set_index("search_term", drop=False)

    for st_row in st_df.to_dict("records"):
        search_term = st_row.get("search_term", "")
        if search_term not in kw_index.index:
            continue
        kw_row = kw_index.loc[search_term]
        if isinstance(kw_row, pd.DataFrame):
            kw_row = kw_row.iloc[0]
        for field_name in ALL_FIELDS:
            diff_type, rollup_parent = compare_field(field_name, kw_row.get(field_name, ""), st_row.get(field_name, ""), registry)
            if not diff_type:
                continue
            rows.append({
                "search_term": search_term,
                "asin": st_row.get("asin", ""),
                "field_name": field_name,
                "kw_value": kw_row.get(field_name, ""),
                "st_value": st_row.get(field_name, ""),
                "diff_type": diff_type,
                "review_required": diff_type == "true_conflict",
                "rollup_parent_if_any": rollup_parent,
                "resolution_note": "",
                "asin_rank": st_row.get("asin_rank", ""),
                "search_frequency_rank": kw_row.get("search_frequency_rank", ""),
                "review_priority": 100 if diff_type == "true_conflict" else 0,
                "kw_mapping_status": kw_row.get("mapping_status", ""),
                "st_mapping_status": st_row.get("mapping_status", ""),
                "taxonomy_version": st_row.get("taxonomy_version") or kw_row.get("taxonomy_version", ""),
            })

    return pd.DataFrame(rows, columns=DIFF_COLUMNS)
