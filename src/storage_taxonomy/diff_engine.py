from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .taxonomy_registry import ALL_FIELDS, PRODUCT_FORM_FIELD, TaxonomyRegistry

DEFAULT_JOIN_KEY_CANDIDATES = [
    "marketplace",
    "report_date",
    "date",
    "reporting_period",
    "search_term",
]

JOIN_CONTEXT_COLUMNS = [
    "marketplace",
    "report_date",
    "date",
    "reporting_period",
]

DIFF_COLUMNS = [
    "search_term",
    "marketplace",
    "report_date",
    "date",
    "reporting_period",
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


def resolve_join_keys(
    kw_df: pd.DataFrame,
    st_df: pd.DataFrame,
    configured_join_keys: list[str] | None = None,
) -> list[str]:
    if configured_join_keys:
        missing = [
            col for col in configured_join_keys
            if col not in kw_df.columns or col not in st_df.columns
        ]
        if missing:
            raise ValueError(
                f"Configured diff join keys missing from keyword or top ASIN inputs: {missing}. "
                f"Keyword columns: {list(kw_df.columns)}. Top ASIN columns: {list(st_df.columns)}"
            )
        join_keys = list(configured_join_keys)
    else:
        join_keys = [
            col for col in DEFAULT_JOIN_KEY_CANDIDATES
            if col in kw_df.columns and col in st_df.columns
        ]

    if "search_term" not in join_keys:
        raise ValueError("diff requires search_term in both keyword and top ASIN inputs")
    return join_keys


def _join_value(value: Any) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value)


def _join_key(row: dict[str, Any], join_keys: list[str]) -> str | tuple[str, ...]:
    values = tuple(_join_value(row.get(col, "")) for col in join_keys)
    return values[0] if len(values) == 1 else values


def _configured_join_keys(registry: TaxonomyRegistry) -> list[str] | None:
    workflow_cfg = registry.workflow_config.get("workflow", {})
    configured = workflow_cfg.get("diff_join_keys") or registry.workflow_config.get("diff_join_keys")
    return list(configured) if configured else None


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
    join_keys: list[str] | None = None,
) -> pd.DataFrame:
    registry = registry or TaxonomyRegistry()
    rows: list[dict[str, Any]] = []
    if kw_df.empty or st_df.empty:
        return pd.DataFrame(rows, columns=DIFF_COLUMNS)

    resolved_join_keys = resolve_join_keys(
        kw_df,
        st_df,
        configured_join_keys=join_keys or _configured_join_keys(registry),
    )
    kw_key_df = kw_df.copy()
    st_key_df = st_df.copy()
    for col in resolved_join_keys:
        kw_key_df[col] = kw_key_df[col].map(_join_value)
        st_key_df[col] = st_key_df[col].map(_join_value)
    kw_index = kw_key_df.set_index(resolved_join_keys, drop=False)

    for st_row in st_key_df.to_dict("records"):
        key = _join_key(st_row, resolved_join_keys)
        if key not in kw_index.index:
            continue
        kw_row = kw_index.loc[key]
        if isinstance(kw_row, pd.DataFrame):
            raise ValueError(f"duplicate keyword rows for join key: {key}")
        search_term = st_row.get("search_term", "")
        for field_name in ALL_FIELDS:
            diff_type, rollup_parent = compare_field(field_name, kw_row.get(field_name, ""), st_row.get(field_name, ""), registry)
            if not diff_type:
                continue
            row = {
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
            }
            for context_col in JOIN_CONTEXT_COLUMNS:
                st_context = _join_value(st_row.get(context_col, ""))
                row[context_col] = st_context or _join_value(kw_row.get(context_col, ""))
            rows.append(row)

    return pd.DataFrame(rows, columns=DIFF_COLUMNS)
