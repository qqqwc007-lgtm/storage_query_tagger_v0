import csv

import pytest

from storage_taxonomy.input_parser import prepare_local_inputs


def test_prepare_local_inputs_supports_english_export_without_metadata(tmp_path):
    raw_csv = tmp_path / "US_raw.csv"
    raw_csv.write_text(
        "\n".join([
            "Search Frequency Rank,Search Query,Top Clicked Product #1: ASIN,Top Clicked Product #1: Product Title,Top Clicked Product #1: Click Share,Top Clicked Product #1: Conversion Share,Report Date",
            "1,shoe rack,B001,Shoe Rack Organizer,12.3,4.1,2026-03-31",
        ]),
        encoding="utf-8",
    )
    kw_output = tmp_path / "keyword_input.csv"
    st_output = tmp_path / "top_asin_input.csv"

    result = prepare_local_inputs(raw_csv, kw_output, st_output)

    assert result == {"keyword_rows": 1, "top_asin_rows": 1}
    kw_rows = list(csv.DictReader(kw_output.open("r", encoding="utf-8")))
    st_rows = list(csv.DictReader(st_output.open("r", encoding="utf-8")))
    assert kw_rows[0]["search_term"] == "shoe rack"
    assert kw_rows[0]["search_frequency_rank"] == "1"
    assert kw_rows[0]["date"] == "2026-03-31"
    assert st_rows[0]["asin"] == "B001"
    assert st_rows[0]["title"] == "Shoe Rack Organizer"


def test_prepare_local_inputs_rejects_missing_required_columns(tmp_path):
    raw_csv = tmp_path / "US_raw.csv"
    raw_csv.write_text(
        "\n".join([
            "Search Frequency Rank,Top Clicked Product #1: ASIN",
            "1,B001",
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required columns"):
        prepare_local_inputs(raw_csv, tmp_path / "keyword_input.csv", tmp_path / "top_asin_input.csv")
