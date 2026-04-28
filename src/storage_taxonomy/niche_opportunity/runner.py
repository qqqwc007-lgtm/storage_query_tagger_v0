from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from .boundary import (
    BOUNDARY_COLUMNS,
    ConfirmedBoundaryRow,
    NicheBoundaryResult,
    load_confirmed_boundary,
    resolve_niche_boundary,
    seed_confirmed_boundary,
)
from .business_workbook import write_business_delivery_workbook
from .config import NicheOpportunityConfig, load_niche_opportunity_config
from .cost import NicheCostEstimate, estimate_niche_cost
from .decision_engine import DecisionResult, decide_launch
from .exports import DECISION_CARD_MANIFEST_FILENAME
from .loaders import (
    LoadedTable,
    load_keyword_asin_facts,
    load_search_volume_history,
)
from .raw_detail_parser import ProductAsinFactRow, build_product_asin_facts
from .signals import NicheSignalSet, build_niche_signals, summarize_boundary_sales


DEFAULT_OUTPUT_DIR = Path("outputs/workflow_v1/niche_opportunity_workflow")
BOUNDARY_FILENAME = "confirmed_niche_boundary_v1.csv"
QUALITY_FILENAME = "niche_opportunity_quality_v1.json"


@dataclass(frozen=True)
class GenerateCardResult:
    niche_id: str
    niche_name: str
    card_path: Path
    workbook_path: Path
    manifest_path: Path
    quality_path: Path
    boundary_path: Path
    seeded_boundary: bool
    boundary: NicheBoundaryResult
    product_facts: tuple[ProductAsinFactRow, ...]
    signals: NicheSignalSet
    decision: DecisionResult
    cost: NicheCostEstimate


@dataclass(frozen=True)
class RecordReviewResult:
    niche_id: str
    final_conclusion: str
    review_path: Path
    calibration_backlog_path: Path | None


def render_decision_card(**kwargs: Any) -> str:
    from .card_renderer import render_decision_card as implementation

    return implementation(**kwargs)


def write_decision_card_manifest(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
    from .exports import write_decision_card_manifest as implementation

    return implementation(path_or_dir, row)


def append_opportunity_review(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
    from .exports import append_opportunity_review as implementation

    return implementation(path_or_dir, row)


def append_calibration_backlog(path_or_dir: str | Path, row: dict[str, Any]) -> Path:
    from .exports import append_calibration_backlog as implementation

    return implementation(path_or_dir, row)


def generate_card(
    *,
    niche_id: str,
    niche_name: str = "",
    keywords: Iterable[str] | str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    config_path: str | Path | None = None,
    reviewer: str = "system",
) -> GenerateCardResult:
    started_at = perf_counter()
    generated_at = _utc_now()
    clean_niche_id = _require_text(niche_id, "niche_id")
    clean_niche_name = niche_name.strip() or clean_niche_id
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    config = load_niche_opportunity_config(config_path)
    keyword_asin_table = load_keyword_asin_facts(config.source_paths["keyword_asin_fact"], config=config)
    search_volume_table = load_search_volume_history(
        config.source_paths["keyword_search_volume_history"],
        config=config,
    )
    boundary_path = output_path / BOUNDARY_FILENAME
    boundary_rows, seeded_boundary = _load_or_seed_boundary(
        boundary_path=boundary_path,
        niche_id=clean_niche_id,
        keywords=_normalize_keywords(keywords),
        reviewer=reviewer,
        reviewed_at=generated_at,
    )
    resolved = resolve_niche_boundary(
        niche_id=clean_niche_id,
        boundary_rows=boundary_rows,
        keyword_asin_rows=keyword_asin_table.rows,
        search_volume_rows=search_volume_table.rows,
    )
    raw_dir = config.source_paths["product_detail_raw_dir"]
    product_facts = build_product_asin_facts(resolved.asin_bridge_rows, raw_dir)
    sales_summary = summarize_boundary_sales(
        niche_id=clean_niche_id,
        keyword_bridge_rows=resolved.keyword_bridge_rows,
        asin_bridge_rows=resolved.asin_bridge_rows,
    )
    signals = build_niche_signals(
        keyword_bridge_rows=resolved.keyword_bridge_rows,
        asin_bridge_rows=resolved.asin_bridge_rows,
        product_facts=product_facts,
        sales_summary=sales_summary,
        config=config,
    )
    decision = decide_launch(signals, config)
    cost = estimate_niche_cost(
        product_facts=product_facts,
        overall_asp=sales_summary.overall_asp,
        new_asin_avg_monthly_units=_new_asin_avg_monthly_units(sales_summary),
        config=config,
    )
    card_path = output_path / f"{clean_niche_id}_decision_card.md"
    workbook_path = output_path / f"{clean_niche_id}_opportunity_delivery_v1.xlsx"
    card_text = render_decision_card(
        niche_id=clean_niche_id,
        niche_name=clean_niche_name,
        keywords=list(resolved.included_keywords),
        keyword_bridge_rows=resolved.keyword_bridge_rows,
        asin_bridge_rows=resolved.asin_bridge_rows,
        product_facts=product_facts,
        sales_summary=sales_summary,
        decision=decision,
        cost=cost,
        generated_at=generated_at,
    )
    card_path.write_text(card_text, encoding="utf-8")

    manifest_row = _decision_card_manifest_row(
        niche_id=clean_niche_id,
        niche_name=clean_niche_name,
        card_path=card_path,
        workbook_path=workbook_path,
        decision=decision,
        cost=cost,
        config=config,
        generated_at=generated_at,
    )
    manifest_path = write_decision_card_manifest(output_path, manifest_row)
    quality_path = _write_quality_report(
        output_path=output_path,
        row=_quality_row(
            niche_id=clean_niche_id,
            niche_name=clean_niche_name,
            generated_at=generated_at,
            elapsed_seconds=perf_counter() - started_at,
            config=config,
            keyword_asin_table=keyword_asin_table,
            search_volume_table=search_volume_table,
            boundary=resolved,
            product_facts=product_facts,
            signals=signals,
            card_path=card_path,
            manifest_path=manifest_path,
        ),
    )
    workbook_path = write_business_delivery_workbook(
        output_dir=output_path,
        niche_id=clean_niche_id,
        niche_name=clean_niche_name,
        generated_at=generated_at,
        keywords=list(resolved.included_keywords),
        boundary=resolved,
        product_facts=product_facts,
        sales_summary=sales_summary,
        decision=decision,
        cost=cost,
        card_path=card_path,
        boundary_path=boundary_path,
        manifest_path=manifest_path,
        quality_path=quality_path,
    )

    return GenerateCardResult(
        niche_id=clean_niche_id,
        niche_name=clean_niche_name,
        card_path=card_path,
        workbook_path=workbook_path,
        manifest_path=manifest_path,
        quality_path=quality_path,
        boundary_path=boundary_path,
        seeded_boundary=seeded_boundary,
        boundary=resolved,
        product_facts=tuple(product_facts),
        signals=signals,
        decision=decision,
        cost=cost,
    )


def record_review(
    *,
    niche_id: str,
    reviewer: str,
    final_conclusion: str,
    rejection_type: str = "",
    review_comment: str = "",
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    reviewed_at: str | None = None,
) -> RecordReviewResult:
    clean_niche_id = _require_text(niche_id, "niche_id")
    clean_reviewer = _require_text(reviewer, "reviewer")
    clean_conclusion = final_conclusion.strip().lower()
    if clean_conclusion not in {"approve", "defer", "reject"}:
        raise ValueError("final_conclusion must be one of: approve, defer, reject")

    clean_rejection_type = rejection_type.strip()
    clean_review_comment = review_comment.strip()
    if clean_conclusion in {"defer", "reject"} and not (clean_rejection_type or clean_review_comment):
        raise ValueError("defer/reject review requires a non-empty rejection_type or review_comment")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    clean_reviewed_at = reviewed_at or _utc_now()
    manifest_row = _decision_manifest_entry(output_path, clean_niche_id)
    decision_card_path = _manifest_text(
        manifest_row,
        "decision_card_path",
        str(output_path / f"{clean_niche_id}_decision_card.md"),
    )
    system_conclusion = _manifest_text(manifest_row, "conclusion")
    system_reason = _manifest_text(manifest_row, "decision_reason")
    review_row = {
        "niche_id": clean_niche_id,
        "reviewer": clean_reviewer,
        "review_outcome": clean_conclusion,
        "system_conclusion": system_conclusion,
        "system_reason": system_reason,
        "rejection_type": clean_rejection_type,
        "review_comment": clean_review_comment,
        "reviewed_at": clean_reviewed_at,
        "decision_card_path": decision_card_path,
    }
    review_path = append_opportunity_review(output_path, review_row)

    backlog_path = None
    if clean_conclusion in {"defer", "reject"}:
        backlog_path = append_calibration_backlog(
            output_path,
            {
                "niche_id": clean_niche_id,
                "created_at": clean_reviewed_at,
                "reviewer": clean_reviewer,
                "review_outcome": clean_conclusion,
                "rejection_type": clean_rejection_type,
                "review_comment": clean_review_comment,
                "system_conclusion": system_conclusion,
                "decision_card_path": decision_card_path,
            },
        )

    return RecordReviewResult(
        niche_id=clean_niche_id,
        final_conclusion=clean_conclusion,
        review_path=review_path,
        calibration_backlog_path=backlog_path,
    )


def _decision_manifest_entry(output_path: Path, niche_id: str) -> dict[str, Any]:
    manifest_path = output_path / DECISION_CARD_MANIFEST_FILENAME
    if not manifest_path.exists() or manifest_path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list):
        return {}
    for item in payload:
        if isinstance(item, dict) and str(item.get("niche_id", "")).strip() == niche_id:
            return item
    return {}


def _manifest_text(row: dict[str, Any], key: str, default: str = "") -> str:
    value = row.get(key, default)
    if value is None:
        return default
    return str(value).strip() or default


def _load_or_seed_boundary(
    *,
    boundary_path: Path,
    niche_id: str,
    keywords: list[str],
    reviewer: str,
    reviewed_at: str,
) -> tuple[list[ConfirmedBoundaryRow], bool]:
    if boundary_path.exists():
        rows = load_confirmed_boundary(boundary_path)
        if any(row.niche_id == niche_id for row in rows):
            return rows, False
    else:
        rows = []

    if not keywords:
        raise ValueError(
            f"No confirmed boundary rows found for niche_id={niche_id!r}; pass --keywords to seed included rows."
        )
    seeded_rows = seed_confirmed_boundary(
        niche_id=niche_id,
        keywords=keywords,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        system_reason="seed_keyword",
    )
    merged_rows = [*rows, *seeded_rows]
    _write_boundary_rows(boundary_path, merged_rows)
    return merged_rows, True


def _write_boundary_rows(path: Path, rows: list[ConfirmedBoundaryRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BOUNDARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "niche_id": row.niche_id,
                    "boundary_item_type": row.boundary_item_type,
                    "boundary_item_value": row.boundary_item_value,
                    "inclusion_status": row.inclusion_status,
                    "system_reason": row.system_reason,
                    "override_reason": row.override_reason,
                    "reviewer": row.reviewer,
                    "reviewed_at": row.reviewed_at,
                }
            )


def _normalize_keywords(keywords: Iterable[str] | str | None) -> list[str]:
    if keywords is None:
        return []
    if isinstance(keywords, str):
        raw_values = keywords.split(",")
    else:
        raw_values = []
        for keyword in keywords:
            raw_values.extend(str(keyword).split(","))

    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        keyword = value.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
    return result


def _decision_card_manifest_row(
    *,
    niche_id: str,
    niche_name: str,
    card_path: Path,
    workbook_path: Path,
    decision: DecisionResult,
    cost: NicheCostEstimate,
    config: NicheOpportunityConfig,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "workflow_version": config.workflow_version,
        "niche_id": niche_id,
        "niche_name": niche_name,
        "decision_card_path": str(card_path),
        "delivery_workbook_path": str(workbook_path),
        "generated_at": generated_at,
        "conclusion": decision.conclusion,
        "decision_reason": decision.reason,
        "market_signal_count": decision.market_signal_count,
        "supply_chain_match": decision.supply_chain_match,
        "hard_veto": decision.hard_veto,
        "capped_by_proxy": decision.capped_by_proxy,
        "selling_price_usd": cost.selling_price_usd,
        "suggested_purchase_cost_ceiling_usd": cost.suggested_purchase_cost_ceiling_usd,
        "suggested_purchase_cost_ceiling_rmb": cost.suggested_purchase_cost_ceiling_rmb,
        "suggested_first_order_qty": cost.suggested_first_order_qty,
        "cost_confidence": cost.cost_confidence,
        "shipping_estimate_basis": cost.shipping_estimate_basis,
    }


def _quality_row(
    *,
    niche_id: str,
    niche_name: str,
    generated_at: str,
    elapsed_seconds: float,
    config: NicheOpportunityConfig,
    keyword_asin_table: LoadedTable[Any],
    search_volume_table: LoadedTable[Any],
    boundary: NicheBoundaryResult,
    product_facts: list[ProductAsinFactRow],
    signals: NicheSignalSet,
    card_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    parse_status_counts: dict[str, int] = {}
    parse_error_count = 0
    for fact in product_facts:
        parse_status_counts[fact.parse_status] = parse_status_counts.get(fact.parse_status, 0) + 1
        if fact.parse_status not in {"parsed", "partial"}:
            parse_error_count += 1

    return {
        "workflow_version": config.workflow_version,
        "niche_id": niche_id,
        "niche_name": niche_name,
        "generated_at": generated_at,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "input_paths": {key: str(value) for key, value in config.source_paths.items()},
        "output_paths": {
            "decision_card": str(card_path),
            "decision_card_manifest": str(manifest_path),
        },
        "source_row_counts": {
            keyword_asin_table.metadata.source_name: keyword_asin_table.metadata.row_count,
            search_volume_table.metadata.source_name: search_volume_table.metadata.row_count,
        },
        "included_keyword_count": len(boundary.included_keywords),
        "excluded_keyword_count": len(boundary.excluded_keywords),
        "invalid_asin_count": len(boundary.invalid_asins),
        "asin_bridge_row_count": len(boundary.asin_bridge_rows),
        "selected_product_asin_count": len(boundary.product_asins),
        "product_fact_count": len(product_facts),
        "parse_status_counts": parse_status_counts,
        "parse_error_count": parse_error_count,
        "missing_evidence_signal_count": sum(
            1 for signal in signals.all_signals if signal.evidence_status == "missing"
        ),
        "proxy_evidence_signal_count": sum(
            1 for signal in signals.all_signals if signal.evidence_status == "proxy"
        ),
    }


def _write_quality_report(output_path: Path, row: dict[str, Any]) -> Path:
    quality_path = output_path / QUALITY_FILENAME
    rows: list[dict[str, Any]] = []
    if quality_path.exists():
        existing = json.loads(quality_path.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and isinstance(existing.get("rows"), list):
            rows = [item for item in existing["rows"] if isinstance(item, dict)]
        elif isinstance(existing, list):
            rows = [item for item in existing if isinstance(item, dict)]

    rows = [item for item in rows if item.get("niche_id") != row["niche_id"]]
    rows.append(row)
    payload = {
        "workflow_version": row["workflow_version"],
        "updated_at": _utc_now(),
        "rows": rows,
    }
    quality_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return quality_path


def _new_asin_avg_monthly_units(sales_summary: Any) -> float | None:
    if not sales_summary.new_product_units or not sales_summary.new_asin_count:
        return None
    return sales_summary.new_product_units / sales_summary.new_asin_count


def _require_text(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
