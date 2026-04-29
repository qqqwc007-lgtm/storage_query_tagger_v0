from __future__ import annotations

from datetime import date

from storage_taxonomy.niche_opportunity.config import load_niche_opportunity_config
from storage_taxonomy.niche_opportunity.cost import estimate_asin_cost, estimate_niche_cost
from storage_taxonomy.niche_opportunity.raw_detail_parser import ProductAsinFactRow


def _product_fact(
    asin: str = "B0A",
    fba_fee: float | None = 6.05,
    package_dimensions_cm: tuple[float, ...] = (30.0, 20.0, 10.0),
    weight_g: float | None = 800.0,
    dimension_raw: str = "",
    weight_raw: str = "",
) -> ProductAsinFactRow:
    return ProductAsinFactRow(
        asin=asin,
        parent_asin="",
        title="Under Bed Shoe Storage",
        main_image_url="https://example.com/main.jpg",
        brand="Brand",
        seller_name="Seller",
        seller_origin="CN",
        price=29.99,
        monthly_units=500,
        monthly_gmv=14995,
        asin_asp=29.99,
        launch_date=date(2025, 10, 1),
        days_since_launch=120,
        rating=4.7,
        review_count=100,
        material_raw="Oxford Fabric",
        dimension_raw=dimension_raw,
        weight_raw=weight_raw,
        fba_fee=fba_fee,
        attributes_json="{}",
        description_text="",
        source_raw_json="/raw/B0A.json",
        parse_status="parsed",
        package_dimensions_cm=package_dimensions_cm,
        weight_g=weight_g,
    )


def test_estimate_asin_cost_uses_package_dimensions_and_weight() -> None:
    config = load_niche_opportunity_config()

    estimate = estimate_asin_cost(_product_fact(), config)

    assert estimate.fba_fee_usd == 6.05
    assert estimate.fba_fee_basis == "parsed"
    assert estimate.actual_weight_kg == 0.8
    assert estimate.dimensional_weight_kg == 1.0
    assert estimate.chargeable_weight_kg == 1.0
    assert estimate.first_leg_shipping_rmb == 8.0
    assert estimate.first_leg_shipping_usd == 1.1111
    assert estimate.shipping_estimate_basis == "package_dimension_weight"


def test_estimate_niche_cost_calculates_purchase_ceiling_and_first_order_qty() -> None:
    config = load_niche_opportunity_config()

    estimate = estimate_niche_cost(
        product_facts=[_product_fact()],
        overall_asp=29.99,
        new_asin_avg_monthly_units=500,
        config=config,
    )

    assert estimate.referral_fee_usd == 4.4985
    assert estimate.fba_fulfillment_fee_usd == 6.05
    assert estimate.first_leg_shipping_estimate_usd == 1.1111
    assert estimate.storage_return_loss_reserve_usd == 1.1996
    assert estimate.target_gross_margin_usd == 8.997
    assert estimate.suggested_purchase_cost_ceiling_usd == 8.1338
    assert estimate.suggested_purchase_cost_ceiling_rmb == 58.5634
    assert estimate.suggested_first_order_qty == 500
    assert estimate.cost_confidence == "high"


def test_estimate_niche_cost_labels_product_dimension_fallback_and_negative_ceiling() -> None:
    config = load_niche_opportunity_config()
    fact = _product_fact(
        fba_fee=None,
        package_dimensions_cm=(),
        weight_g=None,
        dimension_raw="30 x 20 x 10 inches",
        weight_raw="",
    )

    estimate = estimate_niche_cost(
        product_facts=[fact],
        overall_asp=10.0,
        new_asin_avg_monthly_units=200,
        config=config,
    )

    assert estimate.asin_estimates[0].fba_fee_basis == "estimated"
    assert estimate.shipping_estimate_basis == "product_dimension_estimated"
    assert estimate.suggested_purchase_cost_ceiling_usd is not None
    assert estimate.suggested_purchase_cost_ceiling_usd < 0
    assert estimate.suggested_first_order_qty == "待供应链补充"
    assert estimate.cost_confidence == "low"
