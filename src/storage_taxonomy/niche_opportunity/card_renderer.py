from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from .boundary import NicheAsinBridgeRow, NicheKeywordBridgeRow
from .cost import NicheCostEstimate
from .decision_engine import DecisionResult
from .loaders import SalesSummaryRow
from .raw_detail_parser import ProductAsinFactRow


MAX_TOP_ASINS = 10
MAX_CELL_LENGTH = 160
T = TypeVar("T")


@dataclass(frozen=True)
class _TopAsinEvidence:
    asin: str
    rank: int | None
    is_new_asin: bool
    is_repeated_new_asin: bool
    price: float | None
    units: int | None
    gmv: float | None
    rating: float | None
    review_count: int | None
    title: str
    material_raw: str
    dimension_raw: str
    parse_status: str
    source_status: str


def render_decision_card(
    *,
    niche_id: str,
    niche_name: str,
    keywords: list[str],
    keyword_bridge_rows: list[NicheKeywordBridgeRow],
    asin_bridge_rows: list[NicheAsinBridgeRow],
    product_facts: list[ProductAsinFactRow],
    sales_summary: SalesSummaryRow,
    decision: DecisionResult,
    cost: NicheCostEstimate,
    generated_at: str = "",
) -> str:
    """Render a one-page Markdown decision card from prepared evidence objects."""
    lines: list[str] = [
        f"# Niche Decision Card: {_plain(niche_name or niche_id)}",
        "",
        "## Summary",
        f"- niche_id: `{_plain(niche_id)}`",
        f"- niche_name: {_plain(niche_name or niche_id)}",
        f"- generated_at: {_plain(generated_at) if generated_at else 'not_provided'}",
        f"- conclusion: {_plain(decision.conclusion)}",
        f"- reason: {_plain(decision.reason)}",
        f"- market_signal_count: {decision.market_signal_count}",
        f"- supply_chain_match: {_bool(decision.supply_chain_match)}",
        f"- hard_veto: {_bool(decision.hard_veto)}",
        f"- capped_by_proxy: {_bool(decision.capped_by_proxy)}",
        f"- keywords: {_format_keywords(keywords)}",
        "",
        "## Signal Evidence",
        "| Signal | State | Evidence status | Value | Reason |",
        "|---|---:|---:|---|---|",
    ]
    lines.extend(_signal_rows(decision))
    lines.extend(
        [
            "",
            "## Sales Summary",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    lines.extend(_sales_rows(sales_summary, keyword_bridge_rows, asin_bridge_rows))
    lines.extend(
        [
            "",
            "## Cost Ceiling",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    lines.extend(_cost_rows(cost))
    lines.extend(
        [
            "",
            "## Top ASIN Evidence",
        ]
    )
    top_asins = _top_asin_evidence(asin_bridge_rows, product_facts)
    if top_asins:
        lines.extend(
            [
                "| ASIN | Rank | New | Repeated new | Price | Units | GMV | Rating | "
                "Reviews | Material | Dimension | Parse | Title |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|",
            ]
        )
        lines.extend(_top_asin_rows(top_asins))
    else:
        lines.append("- missing_top_asin_evidence")
    lines.extend(
        [
            "",
            "## Evidence Gaps",
        ]
    )
    lines.extend(_evidence_gap_lines(decision, cost, top_asins))
    return "\n".join(lines).rstrip() + "\n"


def build_top_asin_evidence(
    asin_bridge_rows: list[NicheAsinBridgeRow],
    product_facts: list[ProductAsinFactRow],
) -> list[_TopAsinEvidence]:
    return _top_asin_evidence(asin_bridge_rows, product_facts)


def _signal_rows(decision: DecisionResult) -> list[str]:
    rows = []
    for signal in decision.signals.all_signals:
        rows.append(
            "| "
            f"{_cell(signal.key)} | "
            f"{_cell(signal.state)} | "
            f"{_cell(signal.evidence_status)} | "
            f"{_cell(signal.value)} | "
            f"{_cell(signal.reason)} |"
        )
    return rows


def _sales_rows(
    sales_summary: SalesSummaryRow,
    keyword_bridge_rows: list[NicheKeywordBridgeRow],
    asin_bridge_rows: list[NicheAsinBridgeRow],
) -> list[str]:
    included_keyword_count = sum(
        1 for row in keyword_bridge_rows if row.inclusion_status == "included"
    )
    valid_asin_count = sum(
        1 for row in asin_bridge_rows if row.asin_validity_override != "invalid"
    )
    return [
        f"| dimension | {_cell(sales_summary.dimension)} |",
        f"| search_term | {_cell(sales_summary.search_term)} |",
        f"| keyword_count | {_cell(_first_present(sales_summary.keyword_count, included_keyword_count))} |",
        f"| asin_count | {_cell(_first_present(sales_summary.asin_count, valid_asin_count))} |",
        f"| deduped_asin_count | {_cell(sales_summary.deduped_asin_count)} |",
        f"| new_asin_count | {_cell(sales_summary.new_asin_count)} |",
        f"| overall_gmv | {_cell(_money(sales_summary.overall_gmv))} |",
        f"| overall_units | {_cell(_int(sales_summary.overall_units))} |",
        f"| overall_asp | {_cell(_money(sales_summary.overall_asp))} |",
        f"| new_product_gmv | {_cell(_money(sales_summary.new_product_gmv))} |",
        f"| new_product_units | {_cell(_int(sales_summary.new_product_units))} |",
        f"| new_product_asp | {_cell(_money(sales_summary.new_product_asp))} |",
        f"| overall_avg_rating | {_cell(_number(sales_summary.overall_avg_rating))} |",
        f"| new_product_avg_rating | {_cell(_number(sales_summary.new_product_avg_rating))} |",
    ]


def _cost_rows(cost: NicheCostEstimate) -> list[str]:
    return [
        f"| selling_price_usd | {_cell(_money(cost.selling_price_usd))} |",
        f"| referral_fee_usd | {_cell(_money(cost.referral_fee_usd))} |",
        f"| fba_fulfillment_fee_usd | {_cell(_money(cost.fba_fulfillment_fee_usd))} |",
        "| first_leg_shipping_estimate_usd | "
        f"{_cell(_money(cost.first_leg_shipping_estimate_usd))} |",
        "| storage_return_loss_reserve_usd | "
        f"{_cell(_money(cost.storage_return_loss_reserve_usd))} |",
        f"| target_gross_margin_usd | {_cell(_money(cost.target_gross_margin_usd))} |",
        "| suggested_purchase_cost_ceiling_usd | "
        f"{_cell(_money(cost.suggested_purchase_cost_ceiling_usd))} |",
        "| suggested_purchase_cost_ceiling_rmb | "
        f"{_cell(_rmb(cost.suggested_purchase_cost_ceiling_rmb))} |",
        f"| suggested_first_order_qty | {_cell(cost.suggested_first_order_qty)} |",
        f"| cost_confidence | {_cell(cost.cost_confidence)} |",
        f"| shipping_estimate_basis | {_cell(cost.shipping_estimate_basis)} |",
    ]


def _top_asin_rows(top_asins: list[_TopAsinEvidence]) -> list[str]:
    rows = []
    for item in top_asins:
        rows.append(
            "| "
            f"{_cell(item.asin)} | "
            f"{_cell(item.rank)} | "
            f"{_cell(_bool(item.is_new_asin))} | "
            f"{_cell(_bool(item.is_repeated_new_asin))} | "
            f"{_cell(_money(item.price))} | "
            f"{_cell(_int(item.units))} | "
            f"{_cell(_money(item.gmv))} | "
            f"{_cell(_number(item.rating))} | "
            f"{_cell(_int(item.review_count))} | "
            f"{_cell(item.material_raw)} | "
            f"{_cell(item.dimension_raw)} | "
            f"{_cell(item.parse_status or item.source_status)} | "
            f"{_cell(item.title)} |"
        )
    return rows


def _evidence_gap_lines(
    decision: DecisionResult,
    cost: NicheCostEstimate,
    top_asins: list[_TopAsinEvidence],
) -> list[str]:
    missing = [
        signal.key
        for signal in decision.signals.all_signals
        if signal.evidence_status == "missing"
    ]
    proxy = [
        signal.key
        for signal in decision.signals.all_signals
        if signal.evidence_status == "proxy"
    ]
    cost_missing = sorted(
        {
            missing_field
            for estimate in cost.asin_estimates
            for missing_field in estimate.missing_fields
        }
    )
    lines = [
        "- VOC: missing/not enabled in v1",
        f"- missing_evidence: {_comma_list(missing)}",
        f"- proxy_evidence: {_comma_list(proxy)}",
        f"- cost_missing_fields: {_comma_list(cost_missing)}",
    ]
    if cost.suggested_purchase_cost_ceiling_usd is None:
        lines.append("- cost_ceiling_status: missing")
    elif cost.suggested_purchase_cost_ceiling_usd <= 0:
        lines.append("- cost_ceiling_status: non_positive")
    else:
        lines.append("- cost_ceiling_status: available")
    if not top_asins:
        lines.append("- top_asin_evidence_status: missing")
    elif any(item.parse_status in {"missing_raw", "parse_error", "partial"} for item in top_asins):
        lines.append("- top_asin_evidence_status: partial")
    else:
        lines.append("- top_asin_evidence_status: available")
    return lines


def _top_asin_evidence(
    asin_bridge_rows: list[NicheAsinBridgeRow],
    product_facts: list[ProductAsinFactRow],
) -> list[_TopAsinEvidence]:
    facts_by_asin = {fact.asin.upper(): fact for fact in product_facts if fact.asin}
    invalid_asins = {
        row.asin.upper()
        for row in asin_bridge_rows
        if row.asin and row.asin_validity_override == "invalid"
    }
    valid_bridge_rows = [
        row for row in asin_bridge_rows if row.asin and row.asin_validity_override != "invalid"
    ]
    sorted_bridge_rows = sorted(
        valid_bridge_rows,
        key=lambda row: (
            row.rank is None,
            row.rank if row.rank is not None else 999999,
            -(row.units or 0),
            row.asin,
        ),
    )
    evidence: list[_TopAsinEvidence] = []
    seen: set[str] = set()
    for row in sorted_bridge_rows:
        asin_key = row.asin.upper()
        if asin_key in seen:
            continue
        seen.add(asin_key)
        fact = facts_by_asin.get(asin_key)
        evidence.append(_top_asin_from_sources(row, fact))
        if len(evidence) >= MAX_TOP_ASINS:
            return evidence

    remaining_facts = sorted(
        (
            fact
            for fact in product_facts
            if fact.asin
            and fact.asin.upper() not in seen
            and fact.asin.upper() not in invalid_asins
        ),
        key=lambda fact: (-(fact.monthly_units or 0), fact.asin),
    )
    for fact in remaining_facts:
        evidence.append(_top_asin_from_fact(fact))
        if len(evidence) >= MAX_TOP_ASINS:
            break
    return evidence


def _top_asin_from_sources(
    row: NicheAsinBridgeRow,
    fact: ProductAsinFactRow | None,
) -> _TopAsinEvidence:
    return _TopAsinEvidence(
        asin=row.asin,
        rank=row.rank,
        is_new_asin=row.is_new_asin,
        is_repeated_new_asin=row.is_repeated_new_asin,
        price=_first_present(row.price, fact.price if fact else None),
        units=_first_present(row.units, fact.monthly_units if fact else None),
        gmv=_first_present(row.gmv, fact.monthly_gmv if fact else None),
        rating=_first_present(row.rating, fact.rating if fact else None),
        review_count=_first_present(row.review_count, fact.review_count if fact else None),
        title=_first_present(fact.title if fact else "", row.title),
        material_raw=fact.material_raw if fact else "",
        dimension_raw=fact.dimension_raw if fact else "",
        parse_status=fact.parse_status if fact else "missing_product_fact",
        source_status=row.asin_validity_system or row.asin_validity_override,
    )


def _top_asin_from_fact(fact: ProductAsinFactRow) -> _TopAsinEvidence:
    return _TopAsinEvidence(
        asin=fact.asin,
        rank=None,
        is_new_asin=False,
        is_repeated_new_asin=False,
        price=fact.price,
        units=fact.monthly_units,
        gmv=fact.monthly_gmv,
        rating=fact.rating,
        review_count=fact.review_count,
        title=fact.title,
        material_raw=fact.material_raw,
        dimension_raw=fact.dimension_raw,
        parse_status=fact.parse_status,
        source_status="product_fact_only",
    )


def _format_keywords(keywords: list[str]) -> str:
    cleaned = [keyword.strip() for keyword in keywords if keyword.strip()]
    return ", ".join(f"`{_plain(keyword)}`" for keyword in cleaned) if cleaned else "missing"


def _money(value: float | int | None) -> str:
    if value is None:
        return "missing"
    return f"${value:,.2f}"


def _rmb(value: float | int | None) -> str:
    if value is None:
        return "missing"
    return f"RMB {value:,.2f}"


def _int(value: int | None) -> str:
    if value is None:
        return "missing"
    return f"{value:,}"


def _number(value: float | int | None) -> str:
    if value is None:
        return "missing"
    return f"{value:,.2f}"


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _comma_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _first_present(primary: T | None, fallback: T | None) -> T | None:
    return primary if primary is not None and primary != "" else fallback


def _cell(value: Any) -> str:
    return _truncate(_plain(value)).replace("|", "\\|")


def _plain(value: Any) -> str:
    return "missing" if value is None or value == "" else str(value).replace("\n", " ").strip()


def _truncate(value: str) -> str:
    if len(value) <= MAX_CELL_LENGTH:
        return value
    return f"{value[: MAX_CELL_LENGTH - 3]}..."
