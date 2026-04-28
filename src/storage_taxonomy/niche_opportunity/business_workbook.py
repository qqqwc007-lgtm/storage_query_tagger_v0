from __future__ import annotations

from pathlib import Path
from typing import Any

from .boundary import NicheAsinBridgeRow, NicheBoundaryResult, NicheKeywordBridgeRow
from .card_renderer import build_top_asin_evidence
from .cost import NicheCostEstimate
from .decision_engine import DecisionResult
from .exports import BUSINESS_DELIVERY_WORKBOOK_SUFFIX, XlsxSheet, write_xlsx_workbook
from .loaders import SalesSummaryRow
from .raw_detail_parser import ProductAsinFactRow


def write_business_delivery_workbook(
    *,
    output_dir: str | Path,
    niche_id: str,
    niche_name: str,
    generated_at: str,
    keywords: list[str],
    boundary: NicheBoundaryResult,
    product_facts: list[ProductAsinFactRow],
    sales_summary: SalesSummaryRow,
    decision: DecisionResult,
    cost: NicheCostEstimate,
    card_path: str | Path,
    boundary_path: str | Path,
    manifest_path: str | Path,
    quality_path: str | Path,
) -> Path:
    workbook_path = Path(output_dir) / f"{niche_id}{BUSINESS_DELIVERY_WORKBOOK_SUFFIX}"
    sheets = (
        _decision_sheet(
            niche_id=niche_id,
            niche_name=niche_name,
            generated_at=generated_at,
            keywords=keywords,
            decision=decision,
            card_path=card_path,
            boundary_path=boundary_path,
        ),
        _signal_sheet(decision),
        _sales_sheet(sales_summary, boundary),
        _cost_sheet(cost),
        _top_asin_sheet(boundary.asin_bridge_rows, product_facts, cost),
        _boundary_sheet(boundary),
        _delivery_notes_sheet(
            workbook_path=workbook_path,
            card_path=card_path,
            boundary_path=boundary_path,
            manifest_path=manifest_path,
            quality_path=quality_path,
        ),
    )
    return write_xlsx_workbook(workbook_path, sheets)


def _decision_sheet(
    *,
    niche_id: str,
    niche_name: str,
    generated_at: str,
    keywords: list[str],
    decision: DecisionResult,
    card_path: str | Path,
    boundary_path: str | Path,
) -> XlsxSheet:
    return XlsxSheet(
        name="立项卡片",
        headers=("字段", "值"),
        rows=(
            ("niche_id", niche_id),
            ("niche_name", niche_name),
            ("generated_at", generated_at),
            ("system_conclusion", decision.conclusion),
            ("system_reason", decision.reason),
            ("market_signal_count", decision.market_signal_count),
            ("supply_chain_match", decision.supply_chain_match),
            ("hard_veto", decision.hard_veto),
            ("capped_by_proxy", decision.capped_by_proxy),
            ("confirmed_keywords", ", ".join(keywords)),
            ("decision_card_path", str(card_path)),
            ("boundary_path", str(boundary_path)),
        ),
    )


def _signal_sheet(decision: DecisionResult) -> XlsxSheet:
    return XlsxSheet(
        name="信号证据",
        headers=("signal", "state", "evidence_status", "value", "reason"),
        rows=tuple(
            (
                signal.key,
                signal.state,
                signal.evidence_status,
                signal.value,
                signal.reason,
            )
            for signal in decision.signals.all_signals
        ),
    )


def _sales_sheet(sales_summary: SalesSummaryRow, boundary: NicheBoundaryResult) -> XlsxSheet:
    included_keyword_count = sum(
        1 for row in boundary.keyword_bridge_rows if row.inclusion_status == "included"
    )
    valid_asin_count = sum(
        1 for row in boundary.asin_bridge_rows if row.asin_validity_override != "invalid"
    )
    return XlsxSheet(
        name="销售摘要",
        headers=("metric", "value"),
        rows=(
            ("dimension", sales_summary.dimension),
            ("search_term", sales_summary.search_term),
            ("keyword_count", _first_present(sales_summary.keyword_count, included_keyword_count)),
            ("asin_count", _first_present(sales_summary.asin_count, valid_asin_count)),
            ("deduped_asin_count", sales_summary.deduped_asin_count),
            ("new_asin_count", sales_summary.new_asin_count),
            ("overall_gmv", sales_summary.overall_gmv),
            ("overall_units", sales_summary.overall_units),
            ("overall_asp", sales_summary.overall_asp),
            ("new_product_gmv", sales_summary.new_product_gmv),
            ("new_product_units", sales_summary.new_product_units),
            ("new_product_asp", sales_summary.new_product_asp),
            ("overall_avg_rating", sales_summary.overall_avg_rating),
            ("new_product_avg_rating", sales_summary.new_product_avg_rating),
        ),
    )


def _cost_sheet(cost: NicheCostEstimate) -> XlsxSheet:
    return XlsxSheet(
        name="采购成本",
        headers=("metric", "value", "note"),
        rows=(
            ("selling_price_usd", cost.selling_price_usd, "整体 ASP"),
            ("referral_fee_usd", cost.referral_fee_usd, "按配置 referral fee rate"),
            ("fba_fulfillment_fee_usd", cost.fba_fulfillment_fee_usd, "ASIN FBA 中位数或估算值"),
            (
                "first_leg_shipping_estimate_usd",
                cost.first_leg_shipping_estimate_usd,
                "头程按 8 RMB/kg 和计费重粗估",
            ),
            (
                "storage_return_loss_reserve_usd",
                cost.storage_return_loss_reserve_usd,
                "仓储/退货/损耗预留",
            ),
            ("target_gross_margin_usd", cost.target_gross_margin_usd, "30% 毛利率目标"),
            (
                "suggested_purchase_cost_ceiling_usd",
                cost.suggested_purchase_cost_ceiling_usd,
                "不含推广费的采购成本上限",
            ),
            (
                "suggested_purchase_cost_ceiling_rmb",
                cost.suggested_purchase_cost_ceiling_rmb,
                "含头程后的采购成本空间",
            ),
            ("suggested_first_order_qty", cost.suggested_first_order_qty, "系统建议首批数量"),
            ("cost_confidence", cost.cost_confidence, ""),
            ("shipping_estimate_basis", cost.shipping_estimate_basis, ""),
        ),
    )


def _top_asin_sheet(
    asin_bridge_rows: list[NicheAsinBridgeRow],
    product_facts: list[ProductAsinFactRow],
    cost: NicheCostEstimate,
) -> XlsxSheet:
    cost_by_asin = {estimate.asin.upper(): estimate for estimate in cost.asin_estimates if estimate.asin}
    rows: list[tuple[object, ...]] = []
    for item in build_top_asin_evidence(asin_bridge_rows, product_facts):
        asin_cost = cost_by_asin.get(item.asin.upper())
        rows.append(
            (
                item.asin,
                item.rank,
                item.is_new_asin,
                item.is_repeated_new_asin,
                item.price,
                item.units,
                item.gmv,
                item.rating,
                item.review_count,
                item.material_raw,
                item.dimension_raw,
                asin_cost.fba_fee_usd if asin_cost else None,
                asin_cost.chargeable_weight_kg if asin_cost else None,
                asin_cost.first_leg_shipping_rmb if asin_cost else None,
                asin_cost.shipping_estimate_basis if asin_cost else "",
                item.parse_status or item.source_status,
                item.title,
            )
        )
    return XlsxSheet(
        name="Top ASIN",
        headers=(
            "asin",
            "rank",
            "is_new_asin",
            "is_repeated_new_asin",
            "price",
            "units",
            "gmv",
            "rating",
            "review_count",
            "material_raw",
            "dimension_raw",
            "fba_fee_usd",
            "chargeable_weight_kg",
            "first_leg_shipping_rmb",
            "shipping_estimate_basis",
            "parse_status",
            "title",
        ),
        rows=tuple(rows),
    )


def _boundary_sheet(boundary: NicheBoundaryResult) -> XlsxSheet:
    rows: list[tuple[object, ...]] = []
    for row in boundary.keyword_bridge_rows:
        rows.append(_keyword_boundary_row(row))
    for row in boundary.asin_bridge_rows:
        rows.append(_asin_boundary_row(row))
    return XlsxSheet(
        name="边界确认",
        headers=(
            "item_type",
            "item_value",
            "status",
            "reason",
            "search_term",
            "search_volume_current",
            "search_volume_24m_slope",
            "rank",
        ),
        rows=tuple(rows),
    )


def _delivery_notes_sheet(
    *,
    workbook_path: Path,
    card_path: str | Path,
    boundary_path: str | Path,
    manifest_path: str | Path,
    quality_path: str | Path,
) -> XlsxSheet:
    return XlsxSheet(
        name="交付说明",
        headers=("file", "purpose"),
        rows=(
            (str(workbook_path), "业务交付主文件：产品开发、供应链、运营经理周会查看"),
            (str(card_path), "Markdown 一页决策卡片，便于代码审查和文本 diff"),
            (str(boundary_path), "confirmed niche 边界确认文件"),
            (str(manifest_path), "系统索引和结论 manifest"),
            (str(quality_path), "运行质量和证据缺口报告"),
        ),
    )


def _keyword_boundary_row(row: NicheKeywordBridgeRow) -> tuple[object, ...]:
    return (
        "keyword",
        row.search_term,
        row.inclusion_status,
        row.override_reason or row.inclusion_reason,
        row.search_term,
        row.search_volume_current,
        row.search_volume_24m_slope,
        "",
    )


def _asin_boundary_row(row: NicheAsinBridgeRow) -> tuple[object, ...]:
    return (
        "asin",
        row.asin,
        row.asin_validity_override or row.asin_validity_system,
        row.asin_validity_reason,
        row.search_term,
        "",
        "",
        row.rank,
    )


def _first_present(primary: Any, fallback: Any) -> Any:
    return primary if primary is not None and primary != "" else fallback
