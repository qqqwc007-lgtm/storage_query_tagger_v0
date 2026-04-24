from pathlib import Path

import pandas as pd

from storage_taxonomy.duckdb_store import (
    export_candidates_for_review,
    import_candidate_decisions,
    import_candidate_values,
    initialize_loop_db,
)


def test_review_error_decisions_are_not_cached(tmp_path):
    db_path = tmp_path / "loop.duckdb"
    candidate_csv = tmp_path / "candidate_values.csv"
    decisions_csv = tmp_path / "candidate_decisions.csv"
    output_csv = tmp_path / "selected.csv"
    fingerprint = "fp-1"

    initialize_loop_db(db_path)
    pd.DataFrame([
        {
            "candidate_value": "adjustable",
            "axis": "unknown",
            "source_phrases": "adjustable storage box",
            "example_terms": "adjustable shelf organizer",
            "frequency": 10,
            "search_volume_sum": 100,
            "suggested_aliases": "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_candidate_phrase",
            "review_status": "pending",
        },
        {
            "candidate_value": "case",
            "axis": "unknown",
            "source_phrases": "display case",
            "example_terms": "display case",
            "frequency": 9,
            "search_volume_sum": 80,
            "suggested_aliases": "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_candidate_phrase",
            "review_status": "pending",
        },
    ]).to_csv(candidate_csv, index=False)
    import_candidate_values(db_path, 0, candidate_csv, fingerprint)

    pd.DataFrame([
        {
            "candidate_value": "adjustable",
            "axis": "unknown",
            "decision": "needs_human_review",
            "canonical_value": "",
            "confidence": 0.0,
            "auto_apply_eligible": False,
            "reviewed_at": "2026-04-24T00:00:00+00:00",
            "model": "test-model",
            "reason": "review_error:TimeoutError",
        },
        {
            "candidate_value": "case",
            "axis": "unknown",
            "decision": "needs_human_review",
            "canonical_value": "",
            "confidence": 0.5,
            "auto_apply_eligible": False,
            "reviewed_at": "2026-04-24T00:00:00+00:00",
            "model": "test-model",
            "reason": "polysemous",
        },
    ]).to_csv(decisions_csv, index=False)
    import_candidate_decisions(db_path, 0, decisions_csv, fingerprint)

    selected_count = export_candidates_for_review(db_path, 0, output_csv, limit=10, min_frequency=1)
    assert selected_count == 1

    selected = pd.read_csv(output_csv)
    assert selected["candidate_value"].tolist() == ["adjustable"]
