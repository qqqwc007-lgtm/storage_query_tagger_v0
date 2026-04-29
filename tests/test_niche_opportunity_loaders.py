from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from storage_taxonomy.niche_opportunity.loaders import (
    KEYWORD_ASIN_FACT_COLUMNS,
    SALES_SUMMARY_COLUMNS,
    SEARCH_VOLUME_HISTORY_COLUMNS,
    SourceSchemaError,
    load_keyword_asin_facts,
    load_sales_summary,
    load_search_volume_history,
)


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str], encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_load_keyword_asin_facts_maps_bom_chinese_headers_and_coerces_values(tmp_path: Path) -> None:
    csv_path = tmp_path / "keyword_asin_fact_v1.csv"
    _write_csv(
        csv_path,
        [
            {
                "canonical_scenario_need": "床下收纳",
                "kw": "under bed shoe storage",
                "kw中文翻译": "床底鞋子收纳",
                "rank": "1",
                "ASIN": "B0TEST",
                "标题": "Under Bed Shoe Storage",
                "主图": "https://example.com/main.jpg",
                "品牌": "BrandA",
                "卖家": "SellerA",
                "价格": "$29.99",
                "Units": "1,234",
                "GMV": "$36,999.66",
                "ASIN_ASP": "29.99",
                "上架日期": "2025-10-01",
                "上架天数": "210",
                "星级": "4.8",
                "评论数量": "510",
                "2025-Q3起新品": "True",
                "product_detail_status": "cached",
                "product_detail_raw_json": "{}",
                "keyword_top20_asin_list_json": "[]",
                "source_record_json": "{}",
            }
        ],
        KEYWORD_ASIN_FACT_COLUMNS,
        encoding="utf-8-sig",
    )

    table = load_keyword_asin_facts(csv_path, today=date(2026, 4, 28))

    assert table.metadata.source_name == "keyword_asin_fact_v1"
    assert table.metadata.row_count == 1
    assert table.metadata.freshness_status == "current"
    row = table.rows[0]
    assert row.canonical_scenario_need == "床下收纳"
    assert row.search_term == "under bed shoe storage"
    assert row.keyword_translation == "床底鞋子收纳"
    assert row.rank == 1
    assert row.asin == "B0TEST"
    assert row.price == 29.99
    assert row.units == 1234
    assert row.gmv == 36999.66
    assert row.launch_date == date(2025, 10, 1)
    assert row.review_count == 510
    assert row.is_new_asin is True


def test_keyword_asin_facts_missing_required_column_raises_schema_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "keyword_asin_fact_v1.csv"
    columns = [column for column in KEYWORD_ASIN_FACT_COLUMNS if column != "ASIN"]
    _write_csv(csv_path, [{column: "" for column in columns}], columns)

    with pytest.raises(SourceSchemaError) as exc_info:
        load_keyword_asin_facts(csv_path)

    assert exc_info.value.source_name == "keyword_asin_fact_v1"
    assert exc_info.value.missing_columns == ["ASIN"]
    assert str(csv_path) in str(exc_info.value)


def test_load_search_volume_history_coerces_values_and_marks_current(tmp_path: Path) -> None:
    csv_path = tmp_path / "keyword_search_volume_history.csv"
    _write_csv(
        csv_path,
        [
            {
                "search_term": "under bed shoe storage",
                "month": "2026-03",
                "search_volume": "300,001",
                "search_rank": "99",
                "marketplace": "US",
            },
            {
                "search_term": "under bed shoe storage",
                "month": "2026-02",
                "search_volume": "",
                "search_rank": "",
                "marketplace": "US",
            },
        ],
        SEARCH_VOLUME_HISTORY_COLUMNS,
        encoding="utf-8-sig",
    )

    table = load_search_volume_history(csv_path, today=date(2026, 4, 28))

    assert table.metadata.row_count == 2
    assert table.metadata.latest_period == "2026-03"
    assert table.metadata.freshness_status == "current"
    assert table.rows[0].search_volume == 300001
    assert table.rows[0].search_rank == 99
    assert table.rows[1].search_volume is None
    assert table.rows[1].search_rank is None


def test_load_search_volume_history_marks_stale_when_latest_month_is_old(tmp_path: Path) -> None:
    csv_path = tmp_path / "keyword_search_volume_history.csv"
    _write_csv(
        csv_path,
        [
            {
                "search_term": "shoe rack",
                "month": "2025-12",
                "search_volume": "100",
                "search_rank": "1",
                "marketplace": "US",
            }
        ],
        SEARCH_VOLUME_HISTORY_COLUMNS,
    )

    table = load_search_volume_history(csv_path, today=date(2026, 4, 28))

    assert table.metadata.latest_period == "2025-12"
    assert table.metadata.freshness_status == "stale"
    assert table.metadata.freshness_basis == "latest_month_age_months=4"


def test_load_sales_summary_maps_images_and_numeric_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "keyword_sales_summary_v1.csv"
    _write_csv(
        csv_path,
        [
            {
                "维度": "关键词",
                "canonical_scenario_need": "床下收纳",
                "kw": "under bed shoe storage",
                "kw中文翻译": "床底鞋子收纳",
                "关键词数量": "1",
                "ASIN数量": "20",
                "去重ASIN数量": "18",
                "新ASIN数量": "4",
                "整体GMV": "6,755,294",
                "整体Units": "267,083",
                "整体ASP": "25.29",
                "整体平均上架天数": "810.5",
                "整体平均星级": "4.5",
                "整体平均评论数量": "1234.5",
                "整体Top1 ASIN主图": "https://example.com/1.jpg",
                "整体Top2 ASIN主图": "",
                "整体Top3 ASIN主图": "https://example.com/3.jpg",
                "2025-Q3起新品GMV": "1,509,664",
                "2025-Q3起新品Units": "43,514",
                "2025-Q3起新品ASP": "34.69",
                "2025-Q3起新品平均上架天数": "120",
                "2025-Q3起新品平均星级": "4.8",
                "2025-Q3起新品平均评论数量": "510",
                "2025-Q3起新品Top1 ASIN主图": "https://example.com/new1.jpg",
                "2025-Q3起新品Top2 ASIN主图": "",
                "2025-Q3起新品Top3 ASIN主图": "",
            }
        ],
        SALES_SUMMARY_COLUMNS,
    )

    table = load_sales_summary(csv_path, source_name="keyword_sales_summary_v1", today=date(2026, 4, 28))

    row = table.rows[0]
    assert row.dimension == "关键词"
    assert row.keyword_count == 1
    assert row.asin_count == 20
    assert row.deduped_asin_count == 18
    assert row.overall_gmv == 6755294.0
    assert row.overall_units == 267083
    assert row.overall_asp == 25.29
    assert row.overall_top_image_urls == ("https://example.com/1.jpg", "https://example.com/3.jpg")
    assert row.new_product_gmv == 1509664.0
    assert row.new_product_units == 43514
    assert row.new_product_asp == 34.69
    assert row.new_product_top_image_urls == ("https://example.com/new1.jpg",)


def test_sales_summary_missing_required_column_raises_schema_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "scenario_sales_summary_v1.csv"
    columns = [column for column in SALES_SUMMARY_COLUMNS if column != "整体ASP"]
    _write_csv(csv_path, [{column: "" for column in columns}], columns)

    with pytest.raises(SourceSchemaError) as exc_info:
        load_sales_summary(csv_path, source_name="scenario_sales_summary_v1")

    assert exc_info.value.source_name == "scenario_sales_summary_v1"
    assert exc_info.value.missing_columns == ["整体ASP"]
