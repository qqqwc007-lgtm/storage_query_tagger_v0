from __future__ import annotations

import math
import re
from dataclasses import dataclass
from statistics import median

from .config import NicheOpportunityConfig
from .raw_detail_parser import ProductAsinFactRow


@dataclass(frozen=True)
class AsinCostEstimate:
    asin: str
    fba_fee_usd: float | None
    fba_fee_basis: str
    actual_weight_kg: float | None
    dimensional_weight_kg: float | None
    chargeable_weight_kg: float | None
    first_leg_shipping_usd: float | None
    first_leg_shipping_rmb: float | None
    shipping_estimate_basis: str
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class NicheCostEstimate:
    selling_price_usd: float | None
    referral_fee_usd: float | None
    fba_fulfillment_fee_usd: float | None
    first_leg_shipping_estimate_usd: float | None
    storage_return_loss_reserve_usd: float | None
    target_gross_margin_usd: float | None
    suggested_purchase_cost_ceiling_usd: float | None
    suggested_purchase_cost_ceiling_rmb: float | None
    suggested_first_order_qty: int | str
    cost_confidence: str
    shipping_estimate_basis: str
    asin_estimates: tuple[AsinCostEstimate, ...]


def estimate_niche_cost(
    product_facts: list[ProductAsinFactRow],
    overall_asp: float | None,
    new_asin_avg_monthly_units: float | None,
    config: NicheOpportunityConfig,
) -> NicheCostEstimate:
    asin_estimates = tuple(estimate_asin_cost(fact, config) for fact in product_facts)
    if overall_asp is None or overall_asp <= 0:
        return _empty_niche_cost(overall_asp, asin_estimates, "missing_price")

    fba_values = [estimate.fba_fee_usd for estimate in asin_estimates if estimate.fba_fee_usd is not None]
    shipping_values = [
        estimate.first_leg_shipping_usd
        for estimate in asin_estimates
        if estimate.first_leg_shipping_usd is not None
    ]
    fba_fee = median(fba_values) if fba_values else _estimate_fba_fee(None)
    first_leg = median(shipping_values) if shipping_values else None
    if first_leg is None:
        return _empty_niche_cost(overall_asp, asin_estimates, "missing_shipping")

    referral_fee = overall_asp * config.cost.referral_fee_rate
    reserve = overall_asp * config.cost.storage_return_loss_reserve_rate
    target_margin = overall_asp * config.cost.target_gross_margin_rate
    ceiling_usd = overall_asp - referral_fee - fba_fee - first_leg - reserve - target_margin
    ceiling_rmb = ceiling_usd * config.cost.exchange_rate
    shipping_basis = _combine_shipping_basis(asin_estimates)
    confidence = _cost_confidence(asin_estimates, ceiling_usd)
    return NicheCostEstimate(
        selling_price_usd=round(overall_asp, 4),
        referral_fee_usd=round(referral_fee, 4),
        fba_fulfillment_fee_usd=round(fba_fee, 4),
        first_leg_shipping_estimate_usd=round(first_leg, 4),
        storage_return_loss_reserve_usd=round(reserve, 4),
        target_gross_margin_usd=round(target_margin, 4),
        suggested_purchase_cost_ceiling_usd=round(ceiling_usd, 4),
        suggested_purchase_cost_ceiling_rmb=round(ceiling_rmb, 4),
        suggested_first_order_qty=_first_order_qty(new_asin_avg_monthly_units, ceiling_rmb),
        cost_confidence=confidence,
        shipping_estimate_basis=shipping_basis,
        asin_estimates=asin_estimates,
    )


def estimate_asin_cost(fact: ProductAsinFactRow, config: NicheOpportunityConfig) -> AsinCostEstimate:
    dimensions_cm = _dimensions_cm(fact)
    actual_weight_kg = _actual_weight_kg(fact)
    dimensional_weight_kg = None
    if len(dimensions_cm) == 3:
        dimensional_weight_kg = (
            dimensions_cm[0]
            * dimensions_cm[1]
            * dimensions_cm[2]
            / config.cost.chargeable_weight_divisor_cm3_per_kg
        )
    chargeable_candidates = [value for value in (actual_weight_kg, dimensional_weight_kg) if value is not None]
    chargeable_weight_kg = max(chargeable_candidates) if chargeable_candidates else None
    first_leg_rmb = (
        chargeable_weight_kg * config.cost.first_leg_rmb_per_kg
        if chargeable_weight_kg is not None
        else None
    )
    first_leg_usd = first_leg_rmb / config.cost.exchange_rate if first_leg_rmb is not None else None
    fba_fee = fact.fba_fee if fact.fba_fee is not None else _estimate_fba_fee(chargeable_weight_kg)
    missing_fields = []
    if fact.fba_fee is None:
        missing_fields.append("fba_fee")
    if chargeable_weight_kg is None:
        missing_fields.append("chargeable_weight")
    return AsinCostEstimate(
        asin=fact.asin,
        fba_fee_usd=round(fba_fee, 4) if fba_fee is not None else None,
        fba_fee_basis="parsed" if fact.fba_fee is not None else "estimated",
        actual_weight_kg=round(actual_weight_kg, 4) if actual_weight_kg is not None else None,
        dimensional_weight_kg=round(dimensional_weight_kg, 4) if dimensional_weight_kg is not None else None,
        chargeable_weight_kg=round(chargeable_weight_kg, 4) if chargeable_weight_kg is not None else None,
        first_leg_shipping_usd=round(first_leg_usd, 4) if first_leg_usd is not None else None,
        first_leg_shipping_rmb=round(first_leg_rmb, 4) if first_leg_rmb is not None else None,
        shipping_estimate_basis=_shipping_basis(fact, dimensions_cm, actual_weight_kg),
        missing_fields=tuple(missing_fields),
    )


def _empty_niche_cost(
    overall_asp: float | None,
    asin_estimates: tuple[AsinCostEstimate, ...],
    reason: str,
) -> NicheCostEstimate:
    return NicheCostEstimate(
        selling_price_usd=overall_asp,
        referral_fee_usd=None,
        fba_fulfillment_fee_usd=None,
        first_leg_shipping_estimate_usd=None,
        storage_return_loss_reserve_usd=None,
        target_gross_margin_usd=None,
        suggested_purchase_cost_ceiling_usd=None,
        suggested_purchase_cost_ceiling_rmb=None,
        suggested_first_order_qty="待供应链补充",
        cost_confidence="low",
        shipping_estimate_basis=reason,
        asin_estimates=asin_estimates,
    )


def _dimensions_cm(fact: ProductAsinFactRow) -> tuple[float, ...]:
    if len(fact.package_dimensions_cm) == 3:
        return fact.package_dimensions_cm
    raw = fact.dimension_raw.lower()
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", raw)[:3]]
    if len(numbers) != 3:
        return ()
    if any(unit in raw for unit in ("inch", "inches", '"')):
        return tuple(number * 2.54 for number in numbers)
    return tuple(numbers)


def _actual_weight_kg(fact: ProductAsinFactRow) -> float | None:
    if fact.weight_g is not None:
        return fact.weight_g / 1000
    raw = fact.weight_raw.lower()
    number_match = re.search(r"\d+(?:\.\d+)?", raw)
    if not number_match:
        return None
    value = float(number_match.group(0))
    if "pound" in raw or "lb" in raw:
        return value * 0.45359237
    if "ounce" in raw or "oz" in raw:
        return value * 0.0283495
    if "kg" in raw:
        return value
    if "g" in raw:
        return value / 1000
    return None


def _shipping_basis(
    fact: ProductAsinFactRow,
    dimensions_cm: tuple[float, ...],
    actual_weight_kg: float | None,
) -> str:
    if fact.package_dimensions_cm and actual_weight_kg is not None:
        return "package_dimension_weight"
    if fact.package_dimensions_cm:
        return "package_dimension_only"
    if dimensions_cm and actual_weight_kg is not None:
        return "product_dimension_estimated_with_weight"
    if dimensions_cm:
        return "product_dimension_estimated"
    if actual_weight_kg is not None:
        return "weight_only_estimated"
    return "missing_shipping_inputs"


def _estimate_fba_fee(chargeable_weight_kg: float | None) -> float:
    if chargeable_weight_kg is None:
        return 6.05
    if chargeable_weight_kg <= 0.5:
        return 3.50
    if chargeable_weight_kg <= 1.0:
        return 4.75
    if chargeable_weight_kg <= 2.5:
        return 6.05
    return 8.50


def _combine_shipping_basis(estimates: tuple[AsinCostEstimate, ...]) -> str:
    bases = {estimate.shipping_estimate_basis for estimate in estimates}
    if not bases:
        return "missing_shipping_inputs"
    if bases == {"package_dimension_weight"}:
        return "package_dimension_weight"
    if any("product_dimension_estimated" in basis for basis in bases):
        return "product_dimension_estimated"
    if any("missing" in basis for basis in bases):
        return "partial_missing_shipping_inputs"
    return "mixed_shipping_basis"


def _cost_confidence(estimates: tuple[AsinCostEstimate, ...], ceiling_usd: float) -> str:
    if ceiling_usd <= 0:
        return "low"
    if not estimates:
        return "low"
    parsed_fba_share = sum(1 for estimate in estimates if estimate.fba_fee_basis == "parsed") / len(estimates)
    package_basis_share = sum(
        1 for estimate in estimates if estimate.shipping_estimate_basis == "package_dimension_weight"
    ) / len(estimates)
    if parsed_fba_share >= 0.8 and package_basis_share >= 0.8:
        return "high"
    if parsed_fba_share >= 0.5 and package_basis_share >= 0.5:
        return "medium"
    return "low"


def _first_order_qty(new_asin_avg_monthly_units: float | None, ceiling_rmb: float) -> int | str:
    if ceiling_rmb <= 0:
        return "待供应链补充"
    demand_cap = int(new_asin_avg_monthly_units) if new_asin_avg_monthly_units and new_asin_avg_monthly_units > 0 else 1000
    budget_cap = math.floor(50000 / ceiling_rmb)
    return max(0, min(demand_cap, 1000, budget_cap))
