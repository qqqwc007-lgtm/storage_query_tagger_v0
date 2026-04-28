from __future__ import annotations

from datetime import date

from storage_taxonomy.niche_opportunity.boundary import (
    NicheAsinBridgeRow,
    NicheKeywordBridgeRow,
)
from storage_taxonomy.niche_opportunity.card_renderer import render_decision_card
from storage_taxonomy.niche_opportunity.cost import AsinCostEstimate, NicheCostEstimate
from storage_taxonomy.niche_opportunity.decision_engine import DecisionResult
from storage_taxonomy.niche_opportunity.loaders import SalesSummaryRow
from storage_taxonomy.niche_opportunity.raw_detail_parser import ProductAsinFactRow
from storage_taxonomy.niche_opportunity.signals import EvidenceSignal, NicheSignalSet


def _signal(key: str, state: str, evidence_status: str = "true") -> EvidenceSignal:
    return EvidenceSignal(
        key=key,
        state=state,
        evidence_status=evidence_status,
        value=f"{key}:{state}",
        reason=f"{key} reason",
    )


def _signals(
    demand: EvidenceSignal | None = None,
    asp: EvidenceSignal | None = None,
    new_product: EvidenceSignal | None = None,
    structure: EvidenceSignal | None = None,
    supply: EvidenceSignal | None = None,
) -> NicheSignalSet:
    return NicheSignalSet(
        demand=demand or _signal("demand_trend", "support"),
        asp=asp or _signal("asp_trend", "support", "proxy"),
        new_product=new_product or _signal("new_product_sales", "support"),
        structure_upgrade=structure or _signal("structure_upgrade", "support", "proxy"),
        supply_chain=supply or _signal("supply_chain_match", "support"),
    )


def _decision(signals: NicheSignalSet | None = None) -> DecisionResult:
    signals = signals or _signals()
    return DecisionResult(
        conclusion="推荐立项",
        market_signal_count=signals.market_support_count,
        supply_chain_match=signals.supply_chain.is_support,
        hard_veto=False,
        capped_by_proxy=False,
        reason="3 个市场/产品信号支持。",
        signals=signals,
    )


def _keyword_bridge(term: str = "under bed shoe storage") -> NicheKeywordBridgeRow:
    return NicheKeywordBridgeRow(
        niche_id="under_bed_shoe_storage",
        search_term=term,
        kw_chinese_translation="床底鞋子收纳",
        search_volume_current=300000,
        search_volume_24m_slope=1200,
        search_rank_current=10,
        seasonality_flag="not_evaluated",
        taxonomy_scene="",
        taxonomy_need="",
        taxonomy_form="",
        inclusion_status="included",
        inclusion_reason="seed_keyword",
        override_status="",
        override_reason="",
    )


def _asin_bridge(
    asin: str = "B0TOP",
    rank: int | None = 1,
    invalid: bool = False,
    repeated: bool = True,
) -> NicheAsinBridgeRow:
    return NicheAsinBridgeRow(
        niche_id="under_bed_shoe_storage",
        search_term="under bed shoe storage",
        asin=asin,
        rank=rank,
        is_new_asin=True,
        is_repeated_new_asin=repeated,
        title="Under Bed Shoe Storage with Adjustable Dividers",
        image_url="https://example.com/top.jpg",
        price=29.99,
        units=500,
        gmv=14995.0,
        asin_asp=29.99,
        launch_date="2025-10-01",
        rating=4.8,
        review_count=510,
        product_detail_raw_json="/raw/B0TOP.json",
        asin_validity_system="valid",
        asin_validity_override="invalid" if invalid else "",
        asin_validity_reason="wrong product form" if invalid else "",
    )


def _product_fact(asin: str = "B0TOP", parse_status: str = "parsed") -> ProductAsinFactRow:
    return ProductAsinFactRow(
        asin=asin,
        parent_asin="",
        title="2 Pack Under Bed Shoe Storage with Clear Cover and Reinforced Handles",
        main_image_url="https://example.com/top.jpg",
        brand="Brand",
        seller_name="Seller",
        seller_origin="CN",
        price=29.99,
        monthly_units=500,
        monthly_gmv=14995.0,
        asin_asp=29.99,
        launch_date=date(2025, 10, 1),
        days_since_launch=120,
        rating=4.8,
        review_count=510,
        material_raw="Oxford Fabric + PVC",
        dimension_raw="30 x 24 x 5.9 inches",
        weight_raw="2.3 Pounds",
        fba_fee=6.05,
        attributes_json='{"Material":"Oxford Fabric, PVC"}',
        description_text="Clear cover, adjustable dividers, reinforced handles.",
        source_raw_json="/raw/B0TOP.json",
        parse_status=parse_status,
        package_dimensions_cm=(30.0, 20.0, 10.0),
        weight_g=800.0,
    )


def _sales_summary() -> SalesSummaryRow:
    return SalesSummaryRow(
        dimension="niche_boundary",
        canonical_scenario_need="",
        search_term="under_bed_shoe_storage",
        keyword_translation="",
        keyword_count=1,
        asin_count=20,
        deduped_asin_count=18,
        new_asin_count=4,
        overall_gmv=6755294.0,
        overall_units=267083,
        overall_asp=25.29,
        overall_avg_days_since_launch=810.0,
        overall_avg_rating=4.5,
        overall_avg_review_count=1000.0,
        overall_top_image_urls=(),
        new_product_gmv=1509664.0,
        new_product_units=43514,
        new_product_asp=34.69,
        new_product_avg_days_since_launch=120.0,
        new_product_avg_rating=4.8,
        new_product_avg_review_count=510.0,
        new_product_top_image_urls=(),
    )


def _cost(
    ceiling_usd: float | None = 8.1338,
    ceiling_rmb: float | None = 58.5634,
) -> NicheCostEstimate:
    return NicheCostEstimate(
        selling_price_usd=29.99,
        referral_fee_usd=4.4985,
        fba_fulfillment_fee_usd=6.05,
        first_leg_shipping_estimate_usd=1.1111,
        storage_return_loss_reserve_usd=1.1996,
        target_gross_margin_usd=8.997,
        suggested_purchase_cost_ceiling_usd=ceiling_usd,
        suggested_purchase_cost_ceiling_rmb=ceiling_rmb,
        suggested_first_order_qty=500 if ceiling_usd is not None else "待供应链补充",
        cost_confidence="high" if ceiling_usd is not None else "low",
        shipping_estimate_basis=(
            "package_dimension_weight" if ceiling_usd is not None else "missing_shipping"
        ),
        asin_estimates=(
            AsinCostEstimate(
                asin="B0TOP",
                fba_fee_usd=6.05,
                fba_fee_basis="parsed",
                actual_weight_kg=0.8,
                dimensional_weight_kg=1.0,
                chargeable_weight_kg=1.0,
                first_leg_shipping_usd=1.1111,
                first_leg_shipping_rmb=8.0,
                shipping_estimate_basis="package_dimension_weight",
                missing_fields=(),
            ),
        ),
    )


def _render(
    decision: DecisionResult | None = None,
    cost: NicheCostEstimate | None = None,
    asin_bridge_rows: list[NicheAsinBridgeRow] | None = None,
    product_facts: list[ProductAsinFactRow] | None = None,
) -> str:
    return render_decision_card(
        niche_id="under_bed_shoe_storage",
        niche_name="Under Bed Shoe Storage",
        keywords=["under bed shoe storage", "shoe organizer under bed"],
        keyword_bridge_rows=[_keyword_bridge()],
        asin_bridge_rows=asin_bridge_rows if asin_bridge_rows is not None else [_asin_bridge()],
        product_facts=product_facts if product_facts is not None else [_product_fact()],
        sales_summary=_sales_summary(),
        decision=decision or _decision(),
        cost=cost or _cost(),
        generated_at="2026-04-29T00:00:00+08:00",
    )


def test_render_decision_card_outputs_ready_one_page_card() -> None:
    card = _render()

    assert card.startswith("# Niche Decision Card: Under Bed Shoe Storage")
    assert "- conclusion: 推荐立项" in card
    assert "- reason: 3 个市场/产品信号支持。" in card
    assert "| demand_trend | support | true | demand_trend:support |" in card
    assert "| overall_gmv | $6,755,294.00 |" in card
    assert "| suggested_purchase_cost_ceiling_usd | $8.13 |" in card
    assert "| suggested_purchase_cost_ceiling_rmb | RMB 58.56 |" in card
    assert "| suggested_first_order_qty | 500 |" in card
    assert "| shipping_estimate_basis | package_dimension_weight |" in card
    assert "- VOC: missing/not enabled in v1" in card


def test_render_decision_card_marks_proxy_and_missing_evidence() -> None:
    signals = _signals(
        demand=_signal("demand_trend", "unknown", "missing"),
        asp=_signal("asp_trend", "support", "proxy"),
        structure=_signal("structure_upgrade", "support", "proxy"),
    )
    card = _render(decision=_decision(signals))

    assert "| demand_trend | unknown | missing | demand_trend:unknown |" in card
    assert "| asp_trend | support | proxy | asp_trend:support |" in card
    assert "- missing_evidence: demand_trend" in card
    assert "- proxy_evidence: asp_trend, structure_upgrade" in card


def test_render_decision_card_makes_missing_cost_visible() -> None:
    card = _render(cost=_cost(ceiling_usd=None, ceiling_rmb=None))

    assert "| suggested_purchase_cost_ceiling_usd | missing |" in card
    assert "| suggested_purchase_cost_ceiling_rmb | missing |" in card
    assert "| suggested_first_order_qty | 待供应链补充 |" in card
    assert "| cost_confidence | low |" in card
    assert "| shipping_estimate_basis | missing_shipping |" in card
    assert "- cost_ceiling_status: missing" in card


def test_render_decision_card_includes_top_asin_evidence_and_skips_invalid_asin() -> None:
    card = _render(
        asin_bridge_rows=[
            _asin_bridge(asin="B0BAD", rank=1, invalid=True),
            _asin_bridge(asin="B0TOP", rank=2, repeated=True),
        ],
        product_facts=[
            _product_fact(asin="B0BAD"),
            _product_fact(asin="B0TOP", parse_status="parsed"),
        ],
    )

    assert "B0BAD" not in card
    assert "| B0TOP | 2 | true | true | $29.99 | 500 | $14,995.00 | 4.80 | 510 |" in card
    assert "Oxford Fabric + PVC" in card
    assert "30 x 24 x 5.9 inches" in card
    assert "2 Pack Under Bed Shoe Storage with Clear Cover and Reinforced Handles" in card
    assert "- top_asin_evidence_status: available" in card
