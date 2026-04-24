import pandas as pd
import pytest

from storage_taxonomy.diff_engine import build_diff_df, resolve_join_keys
from storage_taxonomy.taxonomy_registry import SCENARIO_FIELD


def test_build_diff_uses_composite_join_keys():
    kw_df = pd.DataFrame([
        {
            "marketplace": "US",
            "date": "2026-01-01",
            "search_term": "shoe rack",
            SCENARIO_FIELD: "shoe storage",
            "search_frequency_rank": "1",
        },
        {
            "marketplace": "UK",
            "date": "2026-01-01",
            "search_term": "shoe rack",
            SCENARIO_FIELD: "closet organization",
            "search_frequency_rank": "2",
        },
    ])
    st_df = pd.DataFrame([
        {
            "marketplace": "US",
            "date": "2026-01-01",
            "search_term": "shoe rack",
            "asin": "A1",
            SCENARIO_FIELD: "shoe storage",
        },
        {
            "marketplace": "UK",
            "date": "2026-01-01",
            "search_term": "shoe rack",
            "asin": "A2",
            SCENARIO_FIELD: "shoe storage",
        },
    ])

    diff_df = build_diff_df(kw_df, st_df)
    scenario_conflicts = diff_df[
        (diff_df["field_name"] == SCENARIO_FIELD) & (diff_df["diff_type"] == "true_conflict")
    ]

    assert len(scenario_conflicts) == 1
    assert scenario_conflicts.iloc[0]["marketplace"] == "UK"
    assert scenario_conflicts.iloc[0]["kw_value"] == "closet organization"


def test_build_diff_rejects_duplicate_keyword_join_key():
    kw_df = pd.DataFrame([
        {"marketplace": "US", "date": "2026-01-01", "search_term": "shoe rack"},
        {"marketplace": "US", "date": "2026-01-01", "search_term": "shoe rack"},
    ])
    st_df = pd.DataFrame([
        {"marketplace": "US", "date": "2026-01-01", "search_term": "shoe rack", "asin": "A1"},
    ])

    with pytest.raises(ValueError, match="duplicate keyword rows"):
        build_diff_df(kw_df, st_df)


def test_resolve_join_keys_requires_search_term():
    with pytest.raises(ValueError, match="requires search_term"):
        resolve_join_keys(pd.DataFrame([{"date": "2026-01-01"}]), pd.DataFrame([{"date": "2026-01-01"}]))


def test_search_term_only_inputs_still_work():
    kw_df = pd.DataFrame([{"search_term": "shoe rack", SCENARIO_FIELD: "shoe storage"}])
    st_df = pd.DataFrame([{"search_term": "shoe rack", "asin": "A1", SCENARIO_FIELD: "closet organization"}])

    diff_df = build_diff_df(kw_df, st_df)

    assert "true_conflict" in set(diff_df["diff_type"])
