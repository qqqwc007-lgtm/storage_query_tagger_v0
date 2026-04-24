from __future__ import annotations

from typing import Any

import pandas as pd

from .taxonomy_registry import TaxonomyRegistry

REVIEW_QUEUE_COLUMNS = [
    "queue_source",
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
    "review_reason",
    "review_priority",
    "search_frequency_rank",
    "asin_rank",
    "rollup_parent_if_any",
    "resolution_note",
    "kw_mapping_status",
    "st_mapping_status",
    "taxonomy_version",
]

QUEUE_ID_COLUMNS = [
    "queue_source",
    "marketplace",
    "report_date",
    "date",
    "reporting_period",
    "search_term",
    "asin",
    "field_name",
    "diff_type",
]


def _rank_cutoff(series: pd.Series, quantile: float) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.quantile(quantile))


def build_review_queue(
    diff_df: pd.DataFrame,
    kw_df: pd.DataFrame,
    registry: TaxonomyRegistry | None = None,
) -> pd.DataFrame:
    registry = registry or TaxonomyRegistry()
    review_cfg = registry.thresholds.get("review_queue", {})
    core_fields = set(review_cfg.get("core_fields", []))
    rank_quantile = float(review_cfg.get("high_value_rank_quantile", 0.2))
    pattern_quantile = float(review_cfg.get("high_frequency_pattern_quantile", 0.8))

    queue_rows: list[dict[str, Any]] = []
    if not diff_df.empty:
        conflicts = diff_df[diff_df["diff_type"] == "true_conflict"].copy()
        if not conflicts.empty:
            conflicts["queue_source"] = "diff"
            conflicts["review_reason"] = "true_conflict"
            conflicts["review_priority"] = 100
            queue_rows.extend(conflicts.to_dict("records"))

        missing = diff_df[diff_df["diff_type"] == "missing_value"].copy()
        if not missing.empty:
            cutoff = _rank_cutoff(missing["search_frequency_rank"], rank_quantile)
            missing["pattern_key"] = missing["field_name"].astype(str) + "::" + missing["kw_value"].astype(str) + "::" + missing["st_value"].astype(str)
            pattern_counts = missing["pattern_key"].value_counts()
            pattern_cutoff = float(pattern_counts.quantile(pattern_quantile)) if not pattern_counts.empty else 0.0
            missing["pattern_frequency"] = missing["pattern_key"].map(pattern_counts)
            missing["is_core_field"] = missing["field_name"].isin(core_fields)
            missing["is_top_rank"] = False if cutoff is None else pd.to_numeric(
                missing["search_frequency_rank"], errors="coerce"
            ).le(cutoff)
            missing["is_high_frequency_pattern"] = missing["pattern_frequency"].ge(pattern_cutoff)
            selected = missing[
                missing["is_core_field"] | missing["is_top_rank"] | missing["is_high_frequency_pattern"]
            ].copy()
            if not selected.empty:
                selected["queue_source"] = "diff"
                selected["review_reason"] = selected.apply(_missing_reason, axis=1)
                selected["review_priority"] = selected.apply(_missing_priority, axis=1)
                queue_rows.extend(selected.to_dict("records"))

    if "mapping_status" in kw_df.columns and not kw_df.empty:
        ambiguous = kw_df[kw_df["mapping_status"] == "ambiguous"].copy()
        if not ambiguous.empty:
            cutoff = _rank_cutoff(ambiguous["search_frequency_rank"], rank_quantile)
            if cutoff is not None:
                ambiguous = ambiguous[pd.to_numeric(ambiguous["search_frequency_rank"], errors="coerce").le(cutoff)]
            if not ambiguous.empty:
                ambiguous["queue_source"] = "keyword"
                ambiguous["asin"] = ""
                ambiguous["field_name"] = ""
                ambiguous["kw_value"] = ""
                ambiguous["st_value"] = ""
                ambiguous["diff_type"] = "ambiguous_keyword"
                ambiguous["rollup_parent_if_any"] = ""
                ambiguous["resolution_note"] = ""
                ambiguous["review_reason"] = "high_value_ambiguous_keyword"
                ambiguous["review_priority"] = 85
                queue_rows.extend(ambiguous.to_dict("records"))

    if not queue_rows:
        return pd.DataFrame(columns=REVIEW_QUEUE_COLUMNS)
    queue_df = pd.DataFrame(queue_rows)
    queue_df = queue_df.drop_duplicates(subset=[col for col in QUEUE_ID_COLUMNS if col in queue_df.columns])
    queue_df = queue_df.sort_values(["review_priority", "search_frequency_rank"], ascending=[False, True])
    return queue_df.reindex(columns=REVIEW_QUEUE_COLUMNS)


def _missing_reason(row: pd.Series) -> str:
    reasons = []
    if row.get("is_core_field"):
        reasons.append("core_field_missing")
    if row.get("is_top_rank"):
        reasons.append("top_20_percent_rank")
    if row.get("is_high_frequency_pattern"):
        reasons.append("high_frequency_missing_pattern")
    return "|".join(reasons) or "high_value_missing"


def _missing_priority(row: pd.Series) -> int:
    priority = 60
    if row.get("is_core_field"):
        priority += 20
    if row.get("is_top_rank"):
        priority += 10
    if row.get("is_high_frequency_pattern"):
        priority += 5
    return priority
