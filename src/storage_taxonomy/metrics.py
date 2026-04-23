from __future__ import annotations

from typing import Any

import pandas as pd


def compute_workflow_metrics(diff_df: pd.DataFrame, review_queue_df: pd.DataFrame) -> dict[str, Any]:
    comparable_pairs = diff_df[["search_term", "asin"]].drop_duplicates() if not diff_df.empty else pd.DataFrame()
    true_conflict_pairs = (
        diff_df[diff_df["diff_type"] == "true_conflict"][["search_term", "asin"]].drop_duplicates()
        if not diff_df.empty
        else pd.DataFrame()
    )
    comparable_count = len(comparable_pairs)
    true_conflict_count = len(true_conflict_pairs)
    return {
        "comparable_pair_count": comparable_count,
        "true_conflict_pair_count": true_conflict_count,
        "true_conflict_rate": round(true_conflict_count / comparable_count, 4) if comparable_count else 0.0,
        "review_queue_size": int(len(review_queue_df)),
    }
