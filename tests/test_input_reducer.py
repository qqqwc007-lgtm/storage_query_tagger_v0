import csv
import json

import pandas as pd

from storage_taxonomy.input_parser import prepare_local_inputs
from storage_taxonomy.input_reducer import (
    prepare_rank_capped_inputs,
    reduce_inputs_by_storage_scope,
)


def test_prepare_local_inputs_applies_rank_cap_to_keywords_and_titles(tmp_path):
    raw_csv = tmp_path / "US_raw.csv"
    raw_csv.write_text(
        "\n".join([
            "Search Frequency Rank,Search Query,Top Clicked Product #1: ASIN,Top Clicked Product #1: Product Title,Report Date",
            "1,shoe rack,B001,Shoe Rack Organizer,2026-03-31",
            "200,storage bins,B002,Storage Bins,2026-03-31",
            "201,lego,B003,Lego Set,2026-03-31",
            "bad,basket,B004,Basket,2026-03-31",
        ]),
        encoding="utf-8",
    )

    keyword_output = tmp_path / "keyword_input.csv"
    top_asin_output = tmp_path / "top_asin_input.csv"
    result = prepare_local_inputs(
        raw_csv=raw_csv,
        keyword_output=keyword_output,
        top_asin_output=top_asin_output,
        max_search_frequency_rank=200,
    )

    assert result == {"keyword_rows": 2, "top_asin_rows": 2}
    keyword_rows = list(csv.DictReader(keyword_output.open("r", encoding="utf-8")))
    top_asin_rows = list(csv.DictReader(top_asin_output.open("r", encoding="utf-8")))
    assert [row["search_term"] for row in keyword_rows] == ["shoe rack", "storage bins"]
    assert [row["search_term"] for row in top_asin_rows] == ["shoe rack", "storage bins"]


def test_prepare_rank_capped_inputs_writes_summary(tmp_path):
    raw_csv = tmp_path / "US_raw.csv"
    raw_csv.write_text(
        "\n".join([
            "Search Frequency Rank,Search Query,Top Clicked Product #1: ASIN,Top Clicked Product #1: Product Title",
            "1,shoe rack,B001,Shoe Rack Organizer",
            "2,lego,B002,Lego Set",
        ]),
        encoding="utf-8",
    )

    output_dir = tmp_path / "reduced"
    result = prepare_rank_capped_inputs(raw_csv, output_dir, max_search_frequency_rank=1)

    assert result["keyword_rows"] == 1
    assert result["top_asin_rows"] == 1
    assert (output_dir / "keyword_input.csv").exists()
    summary = json.loads((output_dir / "selection_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "rank_cap"
    assert summary["max_search_frequency_rank"] == 1


def test_reduce_inputs_by_storage_scope_keeps_keyword_and_asin_rows_in_sync(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"
    cold_start_kw = tmp_path / "kw.csv"

    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "search_frequency_rank": 2, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "old spice", "search_frequency_rank": 3, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "shoe rack", "search_frequency_rank": 4, "search_volume": "", "date": "2026-03-31", "marketplace": "UK"},
    ]).to_csv(keyword_input, index=False)
    pd.DataFrame([
        {"search_term": "shoe rack", "asin": "A1", "title": "shoe storage rack", "asin_rank": 1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "asin": "A2", "title": "lego display shelf", "asin_rank": 1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "old spice", "asin": "A3", "title": "old spice deodorant", "asin_rank": 1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "shoe rack", "asin": "A4", "title": "shoe rack", "asin_rank": 1, "date": "2026-03-31", "marketplace": "UK"},
    ]).to_csv(top_asin_input, index=False)
    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "date": "2026-03-31", "marketplace": "US", "mapping_status": "mapped"},
        {"search_term": "lego", "search_frequency_rank": 2, "date": "2026-03-31", "marketplace": "US", "mapping_status": "ambiguous"},
        {"search_term": "old spice", "search_frequency_rank": 3, "date": "2026-03-31", "marketplace": "US", "mapping_status": "not_storage"},
        {"search_term": "shoe rack", "search_frequency_rank": 4, "date": "2026-03-31", "marketplace": "UK", "mapping_status": "partial"},
    ]).to_csv(cold_start_kw, index=False)

    output_dir = tmp_path / "storage_recall"
    result = reduce_inputs_by_storage_scope(
        keyword_input=keyword_input,
        top_asin_input=top_asin_input,
        cold_start_kw=cold_start_kw,
        output_dir=output_dir,
        scope="recall",
        max_search_frequency_rank=2,
    )

    assert result["keyword_rows"] == 2
    assert result["top_asin_rows"] == 2
    keyword_rows = list(csv.DictReader((output_dir / "keyword_input.csv").open("r", encoding="utf-8")))
    top_asin_rows = list(csv.DictReader((output_dir / "top_asin_input.csv").open("r", encoding="utf-8")))
    assert [row["search_term"] for row in keyword_rows] == ["shoe rack", "lego"]
    assert [row["asin"] for row in top_asin_rows] == ["A1", "A2"]
    assert result["keyword_join_keys"] == ["marketplace", "date", "search_term"]


def test_reduce_inputs_by_storage_scope_strict_excludes_ambiguous(tmp_path):
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"
    cold_start_kw = tmp_path / "kw.csv"

    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "search_frequency_rank": 2, "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(keyword_input, index=False)
    pd.DataFrame([
        {"search_term": "shoe rack", "asin": "A1", "title": "shoe rack", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "lego", "asin": "A2", "title": "lego display shelf", "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(top_asin_input, index=False)
    pd.DataFrame([
        {"search_term": "shoe rack", "search_frequency_rank": 1, "date": "2026-03-31", "marketplace": "US", "mapping_status": "mapped"},
        {"search_term": "lego", "search_frequency_rank": 2, "date": "2026-03-31", "marketplace": "US", "mapping_status": "ambiguous"},
    ]).to_csv(cold_start_kw, index=False)

    output_dir = tmp_path / "storage_strict"
    result = reduce_inputs_by_storage_scope(
        keyword_input=keyword_input,
        top_asin_input=top_asin_input,
        cold_start_kw=cold_start_kw,
        output_dir=output_dir,
        scope="strict",
    )

    assert result["included_statuses"] == ["mapped", "partial"]
    assert result["keyword_rows"] == 1
    rows = list(csv.DictReader((output_dir / "keyword_input.csv").open("r", encoding="utf-8")))
    assert rows[0]["search_term"] == "shoe rack"
