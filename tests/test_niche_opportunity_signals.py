from __future__ import annotations

from datetime import date

from storage_taxonomy.niche_opportunity.boundary import NicheAsinBridgeRow, NicheKeywordBridgeRow
from storage_taxonomy.niche_opportunity.loaders import SalesSummaryRow
from storage_taxonomy.niche_opportunity.raw_detail_parser import ProductAsinFactRow
from storage_taxonomy.niche_opportunity.signals import (
    build_niche_signals,
    compute_demand_signal,
    extract_structure_upgrades,
    extract_supply_chain_materials,
    summarize_boundary_sales,
)
from storage_taxonomy.niche_opportunity.config import load_niche_opportunity_config


def _keyword_bridge(term: str, slope: float | None, volume: int | None = 1000) -> NicheKeywordBridgeRow:
    return NicheKeywordBridgeRow(
        niche_id="under_bed_shoe_storage",
        search_term=term,
        kw_chinese_translation="",
        search_volume_current=volume,
        search_volume_24m_slope=slope,
        search_rank_current=10,
        seasonality_flag="not_evaluated",
        taxonomy_scene="",
        taxonomy_need="",
        taxonomy_form="",
        inclusion_status="included",
        inclusion_reason="seed",
        override_status="",
        override_reason="",
    )


def _asin_bridge(
    asin: str,
    is_new: bool = True,
    repeated: bool = False,
    units: int | None = 120,
    gmv: float | None = 3598.8,
    invalid: bool = False,
) -> NicheAsinBridgeRow:
    return NicheAsinBridgeRow(
        niche_id="under_bed_shoe_storage",
        search_term="under bed shoe storage",
        asin=asin,
        rank=1,
        is_new_asin=is_new,
        is_repeated_new_asin=repeated,
        title="Under Bed Shoe Storage",
        image_url="https://example.com/main.jpg",
        price=29.99,
        units=units,
        gmv=gmv,
        asin_asp=29.99,
        launch_date="2025-10-01",
        rating=4.6,
        review_count=50,
        product_detail_raw_json="{}",
        asin_validity_system="valid",
        asin_validity_override="invalid" if invalid else "",
        asin_validity_reason="wrong product form" if invalid else "",
    )


def _product_fact() -> ProductAsinFactRow:
    return ProductAsinFactRow(
        asin="B0A",
        parent_asin="",
        title="2 Pack Under Bed Shoe Storage with Adjustable Dividers and Reinforced Handles",
        main_image_url="https://example.com/main.jpg",
        brand="Brand",
        seller_name="Seller",
        seller_origin="CN",
        price=29.99,
        monthly_units=120,
        monthly_gmv=3598.8,
        asin_asp=29.99,
        launch_date=date(2025, 10, 1),
        days_since_launch=120,
        rating=4.7,
        review_count=100,
        material_raw="Oxford Fabric + PVC",
        dimension_raw="30 x 24 x 5.9 inches",
        weight_raw="2.3 Pounds",
        fba_fee=6.05,
        attributes_json='{"Material":"Oxford Fabric, PVC"}',
        description_text="Clear cover, double zippers, reinforced handles, foldable PP board support.",
        source_raw_json="/raw/B0A.json",
        parse_status="parsed",
    )


def _sales_summary() -> SalesSummaryRow:
    return SalesSummaryRow(
        dimension="关键词",
        canonical_scenario_need="床下收纳",
        search_term="under bed shoe storage",
        keyword_translation="床底鞋子收纳",
        keyword_count=1,
        asin_count=20,
        deduped_asin_count=18,
        new_asin_count=4,
        overall_gmv=6755294,
        overall_units=267083,
        overall_asp=25.29,
        overall_avg_days_since_launch=810,
        overall_avg_rating=4.5,
        overall_avg_review_count=1000,
        overall_top_image_urls=(),
        new_product_gmv=1509664,
        new_product_units=43514,
        new_product_asp=34.69,
        new_product_avg_days_since_launch=120,
        new_product_avg_rating=4.8,
        new_product_avg_review_count=510,
        new_product_top_image_urls=(),
    )


def test_build_niche_signals_supports_market_and_supply_chain_match() -> None:
    config = load_niche_opportunity_config()

    signals = build_niche_signals(
        keyword_bridge_rows=[_keyword_bridge("under bed shoe storage", 300)],
        asin_bridge_rows=[_asin_bridge("B0A", repeated=True)],
        product_facts=[_product_fact()],
        sales_summary=_sales_summary(),
        config=config,
    )

    assert signals.demand.state == "support"
    assert signals.demand.evidence_status == "true"
    assert signals.asp.state == "support"
    assert signals.asp.evidence_status == "proxy"
    assert "proxy_current_snapshot" in signals.asp.value
    assert signals.new_product.state == "support"
    assert "B0A" in signals.new_product.value
    assert signals.structure_upgrade.state == "support"
    assert "adjustable dividers" in signals.structure_upgrade.value
    assert signals.supply_chain.state == "support"
    assert "fabric" in signals.supply_chain.value
    assert "plastic" in signals.supply_chain.value
    assert signals.market_support_count == 4


def test_demand_signal_is_unknown_when_history_missing() -> None:
    signal = compute_demand_signal([_keyword_bridge("under bed shoe storage", None)])

    assert signal.state == "unknown"
    assert signal.evidence_status == "missing"
    assert not signal.is_support


def test_extract_structure_and_materials_return_concrete_evidence() -> None:
    fact = _product_fact()

    upgrades = extract_structure_upgrades([fact])
    materials = extract_supply_chain_materials([fact])

    assert "reinforced handles" in upgrades
    assert "double zippers" in upgrades
    assert materials == ("fabric", "plastic")


def test_summarize_boundary_sales_recomputes_from_valid_deduped_asins() -> None:
    sales = summarize_boundary_sales(
        niche_id="under_bed_shoe_storage",
        keyword_bridge_rows=[
            _keyword_bridge("under bed shoe storage", 10),
            _keyword_bridge("shoe organizer under bed", 5),
        ],
        asin_bridge_rows=[
            _asin_bridge("B0A", is_new=True, units=100, gmv=3000),
            _asin_bridge("B0A", is_new=True, units=999, gmv=9999),
            _asin_bridge("B0B", is_new=False, units=50, gmv=1000),
            _asin_bridge("B0C", is_new=True, units=25, gmv=875, invalid=True),
        ],
    )

    assert sales.dimension == "niche_boundary"
    assert sales.search_term == "under_bed_shoe_storage"
    assert sales.keyword_count == 2
    assert sales.asin_count == 3
    assert sales.deduped_asin_count == 2
    assert sales.new_asin_count == 1
    assert sales.overall_units == 150
    assert sales.overall_gmv == 4000
    assert sales.overall_asp == 26.67
    assert sales.new_product_units == 100
    assert sales.new_product_gmv == 3000
    assert sales.new_product_asp == 30.0
