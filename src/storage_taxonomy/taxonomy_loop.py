from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidate_value_reviewer import CandidateReviewConfig, CandidateReviewChatClient, review_candidate_values
from .duckdb_store import (
    export_candidates_for_review,
    import_candidate_decisions,
    import_candidate_values,
    initialize_loop_db,
    record_iteration,
    record_patch_application,
)
from .opencode_go_client import OpenCodeGoChatClient, load_opencode_go_api_key
from .taxonomy_patch import (
    apply_taxonomy_patch_proposals,
    copy_config_tree,
    taxonomy_fingerprint,
    write_patch_summary,
)
from .workflow import StorageTaxonomyWorkflow


@dataclass(frozen=True)
class TaxonomyLoopConfig:
    keyword_input: Path
    top_asin_input: Path
    output_root: Path
    source_config_root: Path
    candidate_limit: int = 50
    max_iterations: int = 1
    mode: str = "auto"
    keyword_chunk_size: int = 100_000
    title_chunk_size: int = 100_000
    candidate_chunk_size: int = 200_000
    model: str = "kimi-k2.6"
    candidate_min_frequency: int = 1
    baseline_output_dir: Path | None = None


def run_taxonomy_loop(
    config: TaxonomyLoopConfig,
    reviewer_client: CandidateReviewChatClient | None = None,
) -> dict[str, Any]:
    config.output_root.mkdir(parents=True, exist_ok=True)
    db_path = config.output_root / "taxonomy_loop.duckdb"
    initialize_loop_db(db_path)

    loop_events: list[dict[str, Any]] = []
    config_roots = _prepare_initial_config(config)
    current_config_root = config_roots[0]
    current_output_dir = config.baseline_output_dir or config.output_root / "iter_00"

    if config.baseline_output_dir is None:
        current_result = _run_workflow_iteration(config, current_config_root, current_output_dir)
    else:
        current_result = _result_from_existing_output(current_output_dir)

    current_metrics = collect_output_metrics(current_output_dir, current_result.get("metrics", {}))
    current_fingerprint = taxonomy_fingerprint(current_config_root)
    record_iteration(db_path, 0, current_output_dir, current_config_root, current_fingerprint, current_metrics)
    import_candidate_values(db_path, 0, current_output_dir / "candidate_values.csv", current_fingerprint)
    loop_events.append({
        "event": "iteration_completed",
        "iteration_id": 0,
        "output_dir": str(current_output_dir),
        "metrics": current_metrics,
    })

    client = reviewer_client or OpenCodeGoChatClient(
        api_key=load_opencode_go_api_key(),
        model=config.model,
    )

    for iteration_id in range(config.max_iterations):
        review_input = config.output_root / f"iter_{iteration_id:02d}" / "candidate_values_for_review.csv"
        selected_count = export_candidates_for_review(
            db_path=db_path,
            iteration_id=iteration_id,
            output_csv=review_input,
            limit=config.candidate_limit,
            min_frequency=config.candidate_min_frequency,
        )
        loop_events.append({
            "event": "candidates_selected",
            "iteration_id": iteration_id,
            "selected_count": selected_count,
            "review_input": str(review_input),
        })
        if selected_count == 0:
            loop_events.append({"event": "stopped", "reason": "no_candidates_to_review"})
            break

        review_output_dir = config.output_root / f"iter_{iteration_id:02d}" / "candidate_review"
        review_result = review_candidate_values(
            candidate_values_csv=review_input,
            output_dir=review_output_dir,
            client=client,
            registry=None,
            limit=None,
            config=CandidateReviewConfig(batch_size=1),
        )
        decisions_count = import_candidate_decisions(
            db_path=db_path,
            iteration_id=iteration_id,
            decisions_csv=review_result["decisions_path"],
            taxonomy_fingerprint=current_fingerprint,
        )
        loop_events.append({
            "event": "candidates_reviewed",
            "iteration_id": iteration_id,
            "reviewed_count": decisions_count,
            **review_result,
        })

        next_config_root = config.output_root / f"config_iter_{iteration_id + 1:02d}"
        copy_config_tree(current_config_root, next_config_root, overwrite=True)
        patch_result = apply_taxonomy_patch_proposals(
            config_root=next_config_root,
            proposals_jsonl=review_result["patch_proposals_path"],
            output_dir=config.output_root / f"iter_{iteration_id:02d}",
            apply=True,
            auto_apply_only=True,
            backup=True,
        )
        patch_summary_path = config.output_root / f"iter_{iteration_id:02d}" / "taxonomy_patch_summary.json"
        write_patch_summary(patch_summary_path, patch_result)
        record_patch_application(db_path, iteration_id, patch_result.to_dict())
        loop_events.append({
            "event": "patches_applied",
            "iteration_id": iteration_id,
            "summary_path": str(patch_summary_path),
            **patch_result.to_dict(),
        })

        if not patch_result.applied:
            loop_events.append({"event": "stopped", "reason": "no_safe_patches_applied"})
            break

        next_iteration_id = iteration_id + 1
        next_output_dir = config.output_root / f"iter_{next_iteration_id:02d}"
        next_result = _run_workflow_iteration(config, next_config_root, next_output_dir)
        next_metrics = collect_output_metrics(next_output_dir, next_result.get("metrics", {}))
        next_fingerprint = taxonomy_fingerprint(next_config_root)
        record_iteration(db_path, next_iteration_id, next_output_dir, next_config_root, next_fingerprint, next_metrics)
        import_candidate_values(db_path, next_iteration_id, next_output_dir / "candidate_values.csv", next_fingerprint)
        comparison = compare_iteration_metrics(current_metrics, next_metrics)
        loop_events.append({
            "event": "iteration_compared",
            "from_iteration_id": iteration_id,
            "to_iteration_id": next_iteration_id,
            "comparison": comparison,
        })

        if comparison["regressed"]:
            loop_events.append({"event": "stopped", "reason": "metrics_regressed"})
            break

        current_config_root = next_config_root
        current_output_dir = next_output_dir
        current_metrics = next_metrics
        current_fingerprint = next_fingerprint

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(config.output_root),
        "db_path": str(db_path),
        "events": loop_events,
        "final_event": loop_events[-1] if loop_events else {},
    }
    report_path = config.output_root / "loop_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def collect_output_metrics(output_dir: str | Path, workflow_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    output_dir = Path(output_dir)
    metrics = dict(workflow_metrics or {})
    metrics_path = output_dir / "metrics_summary.json"
    if metrics_path.exists():
        metrics.update(json.loads(metrics_path.read_text(encoding="utf-8")))

    metrics["candidate_count"] = _csv_row_count(output_dir / "candidate_values.csv")
    metrics["review_queue_size"] = metrics.get("review_queue_size", _csv_row_count(output_dir / "review_queue.csv"))
    metrics["kw_mapped_count"] = _mapping_status_count(output_dir / "kw.csv", "mapped")
    metrics["st_mapped_count"] = _mapping_status_count(output_dir / "st.csv", "mapped")
    metrics["kw_row_count"] = _csv_row_count(output_dir / "kw.csv")
    metrics["st_row_count"] = _csv_row_count(output_dir / "st.csv")
    metrics["mapped_ratio"] = _safe_ratio(
        metrics["kw_mapped_count"] + metrics["st_mapped_count"],
        metrics["kw_row_count"] + metrics["st_row_count"],
    )
    return metrics


def compare_iteration_metrics(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    deltas = {}
    for key in sorted(set(before) | set(after)):
        left = before.get(key)
        right = after.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            deltas[key] = right - left

    regressed_reasons = []
    if float(after.get("true_conflict_rate", 0)) > float(before.get("true_conflict_rate", 0)):
        regressed_reasons.append("true_conflict_rate_increased")
    if int(after.get("review_queue_size", 0)) > int(before.get("review_queue_size", 0)):
        regressed_reasons.append("review_queue_size_increased")
    if int(after.get("candidate_count", 0)) > int(before.get("candidate_count", 0)):
        regressed_reasons.append("candidate_count_increased")

    return {
        "before": before,
        "after": after,
        "deltas": deltas,
        "regressed": bool(regressed_reasons),
        "regressed_reasons": regressed_reasons,
    }


def _prepare_initial_config(config: TaxonomyLoopConfig) -> dict[int, Path]:
    initial_config_root = config.output_root / "config_iter_00"
    copy_config_tree(config.source_config_root, initial_config_root, overwrite=True)
    return {0: initial_config_root}


def _run_workflow_iteration(
    config: TaxonomyLoopConfig,
    config_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    workflow = StorageTaxonomyWorkflow(config_root=config_root)
    if config.mode == "chunked":
        return workflow.run_chunked(
            keyword_input=config.keyword_input,
            top_asin_input=config.top_asin_input,
            output_dir=output_dir,
            keyword_chunk_size=config.keyword_chunk_size,
            title_chunk_size=config.title_chunk_size,
            candidate_chunk_size=config.candidate_chunk_size,
        )
    if config.mode == "in-memory":
        return workflow.run(config.keyword_input, config.top_asin_input, output_dir)
    keyword_size = config.keyword_input.stat().st_size if config.keyword_input.exists() else 0
    title_size = config.top_asin_input.stat().st_size if config.top_asin_input.exists() else 0
    if max(keyword_size, title_size) >= 100 * 1024 * 1024:
        return workflow.run_chunked(
            keyword_input=config.keyword_input,
            top_asin_input=config.top_asin_input,
            output_dir=output_dir,
            keyword_chunk_size=config.keyword_chunk_size,
            title_chunk_size=config.title_chunk_size,
            candidate_chunk_size=config.candidate_chunk_size,
        )
    return workflow.run(config.keyword_input, config.top_asin_input, output_dir)


def _result_from_existing_output(output_dir: Path) -> dict[str, Any]:
    metrics_path = output_dir / "metrics_summary.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    return {
        "kw_path": str(output_dir / "kw.csv"),
        "st_path": str(output_dir / "st.csv"),
        "diff_path": str(output_dir / "diff.csv"),
        "review_queue_path": str(output_dir / "review_queue.csv"),
        "candidate_path": str(output_dir / "candidate_values.csv"),
        "metrics_path": str(metrics_path),
        "metrics": metrics,
    }


def _csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as f:
        count = sum(1 for _ in f)
    return max(0, count - 1)


def _mapping_status_count(path: Path, status: str) -> int:
    if not path.exists():
        return 0
    try:
        import duckdb
    except ImportError:
        return 0
    escaped = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as con:
        return int(con.execute(
            f"""
            SELECT count(*)
            FROM read_csv_auto('{escaped}', header = true, all_varchar = true)
            WHERE mapping_status = ?
            """,
            [status],
        ).fetchone()[0])


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 6)
