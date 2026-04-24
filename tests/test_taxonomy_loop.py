import json
from pathlib import Path

import pandas as pd

from storage_taxonomy.taxonomy_loop import (
    TaxonomyLoopConfig,
    collect_output_metrics,
    compare_iteration_metrics,
    run_taxonomy_loop,
)


class FakeLoopReviewClient:
    model = "fake-loop-model"

    def chat(self, messages, temperature=0, max_tokens=1200):
        payload = json.loads(messages[-1]["content"])
        decisions = []
        for candidate in payload["candidates"]:
            if candidate["candidate_value"] == "adjustable":
                decisions.append({
                    "candidate_id": candidate["candidate_id"],
                    "decision": "reject_noise",
                    "target_axis": candidate["axis"],
                    "canonical_value": "",
                    "suggested_aliases": [],
                    "rollup_parent": "",
                    "confidence": 0.95,
                    "reason": "Generic modifier, not taxonomy value.",
                    "risk_flags": [],
                    "evidence_terms": candidate["example_terms"][:1],
                })
            else:
                decisions.append({
                    "candidate_id": candidate["candidate_id"],
                    "decision": "needs_human_review",
                    "target_axis": candidate["axis"],
                    "canonical_value": "",
                    "suggested_aliases": [],
                    "rollup_parent": "",
                    "confidence": 0.2,
                    "reason": "Needs human review.",
                    "risk_flags": ["polysemous"],
                    "evidence_terms": candidate["example_terms"][:1],
                })
        return {"choices": [{"message": {"content": json.dumps({"decisions": decisions}, ensure_ascii=False)}}]}


def test_compare_iteration_metrics_regression():
    comparison = compare_iteration_metrics(
        {"review_queue_size": 10, "candidate_count": 3, "true_conflict_rate": 0.1},
        {"review_queue_size": 12, "candidate_count": 4, "true_conflict_rate": 0.11},
    )
    assert comparison["regressed"]
    assert "review_queue_size_increased" in comparison["regressed_reasons"]
    assert "candidate_count_increased" in comparison["regressed_reasons"]


def test_run_taxonomy_loop_uses_overlay_config_and_stops_without_regression(tmp_path):
    output_root = tmp_path / "loop"
    baseline = output_root / "baseline"
    baseline.mkdir(parents=True)
    keyword_input = tmp_path / "keyword_input.csv"
    top_asin_input = tmp_path / "top_asin_input.csv"

    pd.DataFrame([
        {"search_term": "adjustable storage box", "search_frequency_rank": 1, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "shoe rack", "search_frequency_rank": 2, "search_volume": "", "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(keyword_input, index=False)
    pd.DataFrame([
        {"search_term": "adjustable storage box", "asin": "A1", "title": "adjustable storage box", "asin_rank": 1, "click_share": 10.0, "conversion_share": 1.1, "date": "2026-03-31", "marketplace": "US"},
        {"search_term": "shoe rack", "asin": "A2", "title": "shoe storage cabinet", "asin_rank": 1, "click_share": 9.0, "conversion_share": 1.0, "date": "2026-03-31", "marketplace": "US"},
    ]).to_csv(top_asin_input, index=False)

    candidate_rows = pd.DataFrame([
        {
            "candidate_value": "adjustable",
            "axis": "unknown",
            "source_phrases": "adjustable",
            "example_terms": "adjustable shelf",
            "frequency": 5,
            "search_volume_sum": 10,
            "suggested_aliases": "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_candidate_phrase",
            "review_status": "pending",
        }
    ])
    candidate_rows.to_csv(baseline / "candidate_values.csv", index=False)

    kw_rows = pd.DataFrame([
        {"search_term": "adjustable shelf", "mapping_status": "mapped"},
        {"search_term": "shoe rack", "mapping_status": "mapped"},
    ])
    kw_rows.to_csv(baseline / "kw.csv", index=False)
    st_rows = pd.DataFrame([
        {"title": "adjustable shelf", "mapping_status": "mapped"},
        {"title": "shoe rack", "mapping_status": "mapped"},
    ])
    st_rows.to_csv(baseline / "st.csv", index=False)
    pd.DataFrame([{"search_term": "shoe rack", "asin": "A1", "diff_type": "true_conflict"}]).to_csv(
        baseline / "diff.csv", index=False
    )
    pd.DataFrame([{"queue_source": "diff", "search_term": "shoe rack", "asin": "A1", "diff_type": "true_conflict"}]).to_csv(
        baseline / "review_queue.csv", index=False
    )
    metrics = {
        "comparable_pair_count": 1,
        "true_conflict_pair_count": 1,
        "true_conflict_rate": 1.0,
        "review_queue_size": 1,
    }
    (baseline / "metrics_summary.json").write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")

    config = TaxonomyLoopConfig(
        keyword_input=keyword_input,
        top_asin_input=top_asin_input,
        output_root=output_root,
        source_config_root=Path("config"),
        candidate_limit=10,
        max_iterations=1,
        mode="in-memory",
        baseline_output_dir=baseline,
    )

    report = run_taxonomy_loop(config, reviewer_client=FakeLoopReviewClient())

    assert Path(report["report_path"]).exists()
    assert (output_root / "config_iter_01" / "taxonomy" / "candidate_suppression_v0.json").exists()
    suppression = json.loads((output_root / "config_iter_01" / "taxonomy" / "candidate_suppression_v0.json").read_text(encoding="utf-8"))
    assert "adjustable" in suppression["suppressed_terms"]
    assert not (Path("config") / "taxonomy" / "candidate_suppression_v0.json").exists()


def test_collect_output_metrics_counts_rows(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    pd.DataFrame([{"search_term": "a", "mapping_status": "mapped"}]).to_csv(output_dir / "kw.csv", index=False)
    pd.DataFrame([{"title": "a", "mapping_status": "mapped"}]).to_csv(output_dir / "st.csv", index=False)
    pd.DataFrame([{"candidate_value": "x"}]).to_csv(output_dir / "candidate_values.csv", index=False)
    pd.DataFrame([{"queue_source": "diff"}]).to_csv(output_dir / "review_queue.csv", index=False)
    (output_dir / "metrics_summary.json").write_text(
        json.dumps({"true_conflict_rate": 0.0, "review_queue_size": 1}),
        encoding="utf-8",
    )

    metrics = collect_output_metrics(output_dir)
    assert metrics["candidate_count"] == 1
    assert metrics["mapped_ratio"] == 1.0
