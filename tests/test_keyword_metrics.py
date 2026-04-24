import json

import pandas as pd

from storage_taxonomy.keyword_metrics import (
    KEYWORD_METRIC_COLUMNS,
    build_keyword_metrics_from_csv,
    parse_keyword_trend_result,
)
from storage_taxonomy.workflow import StorageTaxonomyWorkflow


def _keyword_trend_payload(keyword: str) -> dict:
    payload = {
        "关键词": keyword,
        "搜索量趋势": [
            "2024年04月搜索量2258474",
            "2024年05月搜索量2,387,389",
        ],
        "搜索排名趋势": [
            "2024年04月搜索排名31",
            "2024年05月搜索排名26",
        ],
        "推荐竞价趋势": [
            "2024年05月cpc推荐竞价1.91",
        ],
    }
    return {
        "content": [
            {
                "type": "text",
                "text": "直接罗列数据，然后依据这些数据进行总结\n" + json.dumps(payload, ensure_ascii=False),
            }
        ]
    }


class FakeKeywordTrendClient:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return _keyword_trend_payload(arguments["keyword"])


def test_parse_keyword_trend_result_pivots_rank_and_volume():
    df = parse_keyword_trend_result(_keyword_trend_payload("shoe rack"))

    assert df.columns.tolist() == KEYWORD_METRIC_COLUMNS
    assert df.to_dict("records") == [
        {
            "关键词": "shoe rack",
            "时间": "2024-04",
            "关键词搜索排名": "31",
            "关键词搜索容量": "2258474",
        },
        {
            "关键词": "shoe rack",
            "时间": "2024-05",
            "关键词搜索排名": "26",
            "关键词搜索容量": "2387389",
        },
    ]


def test_build_keyword_metrics_from_csv_dedupes_keywords(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    pd.DataFrame([
        {"search_term": "shoe rack"},
        {"search_term": "shoe rack"},
        {"search_term": "under sink organizer"},
    ]).to_csv(keyword_input, index=False)

    client = FakeKeywordTrendClient()
    result = build_keyword_metrics_from_csv(keyword_input, client, amz_site="US")

    assert [call[1]["keyword"] for call in client.calls] == ["shoe rack", "under sink organizer"]
    assert result.errors_df.empty
    assert result.metrics_df.columns.tolist() == KEYWORD_METRIC_COLUMNS
    assert len(result.metrics_df) == 4
    assert set(result.metrics_df["时间"]) == {"2024-04", "2024-05"}


def test_workflow_writes_keyword_metrics_when_enabled(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"

    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(keyword_input, index=False)
    pd.DataFrame([
        {"search_term": "shoe rack", "asin": "A1", "title": "shoe storage cabinet", "asin_rank": 1, "click_share": 10.0, "conversion_share": 1.1, "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(top_asin_input, index=False)

    output_dir = tmp_path / "outputs"
    workflow = StorageTaxonomyWorkflow(keyword_metrics_client=FakeKeywordTrendClient())
    result = workflow.run(
        keyword_input,
        top_asin_input,
        output_dir,
        keyword_metrics_enabled=True,
        keyword_metrics_amz_site="US",
    )

    assert "keyword_metrics_path" in result
    metrics_df = pd.read_csv(result["keyword_metrics_path"])
    assert metrics_df.columns.tolist() == KEYWORD_METRIC_COLUMNS
    assert metrics_df.loc[0, "时间"] == "2024-04"
