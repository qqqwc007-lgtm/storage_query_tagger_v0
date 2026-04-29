from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from storage_taxonomy.niche_opportunity.boundary import (
    BOUNDARY_COLUMNS,
    ConfirmedBoundaryRow,
    load_confirmed_boundary,
    resolve_niche_boundary,
    seed_confirmed_boundary,
    slugify_niche_id,
)
from storage_taxonomy.niche_opportunity.loaders import KeywordAsinFactRow, SearchVolumeHistoryRow, SourceSchemaError


def _fact(search_term: str, asin: str, rank: int, is_new: bool, title: str = "") -> KeywordAsinFactRow:
    return KeywordAsinFactRow(
        canonical_scenario_need="床下收纳",
        search_term=search_term,
        keyword_translation=f"{search_term} zh",
        rank=rank,
        asin=asin,
        title=title or f"{asin} title",
        main_image_url=f"https://example.com/{asin}.jpg",
        brand="Brand",
        seller_name="Seller",
        price=29.99,
        units=100 + rank,
        gmv=2999.0,
        asin_asp=29.99,
        launch_date=date(2025, 10, rank),
        days_since_launch=rank,
        rating=4.5,
        review_count=50 + rank,
        is_new_asin=is_new,
        product_detail_status="cached",
        product_detail_raw_json=f"/raw/{asin}.json",
        keyword_top20_asin_list_json="[]",
        source_record_json="{}",
    )


def _boundary(
    item_type: str,
    value: str,
    status: str,
    reason: str = "manual",
) -> ConfirmedBoundaryRow:
    return ConfirmedBoundaryRow(
        niche_id="under_bed_shoe_storage",
        boundary_item_type=item_type,
        boundary_item_value=value,
        inclusion_status=status,
        system_reason="system",
        override_reason=reason,
        reviewer="wayne",
        reviewed_at="2026-04-28T00:00:00Z",
    )


def test_seed_confirmed_boundary_and_slugify_niche_id() -> None:
    assert slugify_niche_id("Under Bed Shoe Storage!") == "under_bed_shoe_storage"

    rows = seed_confirmed_boundary(
        niche_id="under_bed_shoe_storage",
        keywords=["under bed shoe storage", "under bed shoe storage", "shoe organizer under bed"],
        reviewer="wayne",
    )

    assert [row.boundary_item_value for row in rows] == [
        "under bed shoe storage",
        "shoe organizer under bed",
    ]
    assert all(row.inclusion_status == "included" for row in rows)
    assert rows[0].reviewer == "wayne"


def test_load_confirmed_boundary_validates_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "confirmed_niche_boundary_v1.csv"
    columns = [column for column in BOUNDARY_COLUMNS if column != "inclusion_status"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({column: "" for column in columns})

    with pytest.raises(SourceSchemaError) as exc_info:
        load_confirmed_boundary(csv_path)

    assert exc_info.value.source_name == "confirmed_niche_boundary_v1"
    assert exc_info.value.missing_columns == ["inclusion_status"]


def test_resolve_niche_boundary_recomputes_bridges_and_dedupes_product_asins() -> None:
    keyword_asin_rows = [
        _fact("under bed shoe storage", "B0A", 1, True),
        _fact("shoe organizer under bed", "B0A", 2, True),
        _fact("under bed shoe storage", "B0B", 3, False),
        _fact("shoe rack", "B0C", 4, True),
    ]
    search_rows = [
        SearchVolumeHistoryRow("under bed shoe storage", "2026-02", 1000, 20, "US"),
        SearchVolumeHistoryRow("under bed shoe storage", "2026-03", 1300, 18, "US"),
        SearchVolumeHistoryRow("shoe organizer under bed", "2026-02", 500, 80, "US"),
        SearchVolumeHistoryRow("shoe organizer under bed", "2026-03", 900, 60, "US"),
        SearchVolumeHistoryRow("shoe rack", "2026-03", 2000, 5, "US"),
    ]
    boundary_rows = [
        _boundary("keyword", "under bed shoe storage", "included"),
        _boundary("keyword", "shoe organizer under bed", "included"),
        _boundary("keyword", "shoe rack", "excluded", reason="not under-bed niche"),
        _boundary("asin", "B0B", "invalid", reason="shoe rack, not under-bed soft storage"),
    ]

    result = resolve_niche_boundary(
        niche_id="under_bed_shoe_storage",
        boundary_rows=boundary_rows,
        keyword_asin_rows=keyword_asin_rows,
        search_volume_rows=search_rows,
    )

    assert result.included_keywords == ("under bed shoe storage", "shoe organizer under bed")
    assert result.excluded_keywords == ("shoe rack",)
    assert result.invalid_asins == ("B0B",)
    assert result.product_asins == ("B0A",)
    assert [row.asin for row in result.valid_keyword_asin_rows] == ["B0A", "B0A"]

    keyword_bridge = {row.search_term: row for row in result.keyword_bridge_rows}
    assert keyword_bridge["under bed shoe storage"].search_volume_current == 1300
    assert keyword_bridge["under bed shoe storage"].search_volume_24m_slope == 300
    assert keyword_bridge["shoe organizer under bed"].search_rank_current == 60
    assert keyword_bridge["shoe rack"].inclusion_status == "excluded"
    assert keyword_bridge["shoe rack"].override_reason == "not under-bed niche"

    asin_bridge_by_asin = {}
    for row in result.asin_bridge_rows:
        asin_bridge_by_asin.setdefault(row.asin, []).append(row)

    assert len(asin_bridge_by_asin["B0A"]) == 2
    assert all(row.is_repeated_new_asin for row in asin_bridge_by_asin["B0A"])
    assert asin_bridge_by_asin["B0B"][0].asin_validity_override == "invalid"
    assert asin_bridge_by_asin["B0B"][0].asin_validity_reason == "shoe rack, not under-bed soft storage"
    assert "B0C" not in asin_bridge_by_asin
