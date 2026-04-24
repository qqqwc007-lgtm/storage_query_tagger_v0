import json

import pandas as pd

from storage_taxonomy.candidate_value_reviewer import (
    CandidateReviewConfig,
    _parse_json_object,
    review_candidate_values,
)


class FakeReviewClient:
    model = "fake-model"

    def chat(self, messages, temperature=0, max_tokens=1200):
        payload = json.loads(messages[-1]["content"])
        decisions = []
        for candidate in payload["candidates"]:
            decisions.append({
                "candidate_id": candidate["candidate_id"],
                "decision": "add_alias",
                "target_axis": "产品形态关键词",
                "canonical_value": "storage drawer",
                "suggested_aliases": [candidate["candidate_value"]],
                "rollup_parent": "",
                "confidence": 0.91,
                "reason": "Clearly describes a drawer storage form.",
                "risk_flags": [],
                "evidence_terms": candidate["example_terms"][:1],
            })
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"decisions": decisions}, ensure_ascii=False)
                    }
                }
            ]
        }


class FailingReviewClient:
    model = "failing-model"

    def chat(self, messages, temperature=0, max_tokens=1200):
        raise TimeoutError("simulated timeout")


class RetryThenSuccessReviewClient:
    model = "retry-model"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature=0, max_tokens=1200):
        self.calls += 1
        if self.calls == 1:
            return {"choices": [{"message": {"content": "{not valid json}"}}]}
        payload = json.loads(messages[-1]["content"])
        if "candidates" in payload:
            candidate = payload["candidates"][0]
            candidate_id = candidate["candidate_id"]
            evidence_terms = candidate["example_terms"][:1]
            target_axis = candidate["axis"]
        else:
            candidate_id = payload["candidate_ids"][0]
            evidence_terms = []
            target_axis = "unknown"
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "decisions": [
                                {
                                    "candidate_id": candidate_id,
                                    "decision": "reject_noise",
                                    "target_axis": target_axis,
                                    "canonical_value": "",
                                    "suggested_aliases": [],
                                    "rollup_parent": "",
                                    "confidence": 0.95,
                                    "reason": "Generic modifier.",
                                    "risk_flags": [],
                                    "evidence_terms": evidence_terms,
                                }
                            ]
                        }, ensure_ascii=False)
                    }
                }
            ]
        }


def test_parse_json_object_from_fenced_response():
    parsed = _parse_json_object('```json\n{"decisions": []}\n```')
    assert parsed == {"decisions": []}


def test_parse_json_object_skips_invalid_leading_braces():
    parsed = _parse_json_object('not-json {broken}\n```json\n{"decisions": []}\n```')
    assert parsed == {"decisions": []}


def test_review_candidate_values_writes_decisions(tmp_path):
    candidate_csv = tmp_path / "candidate_values.csv"
    pd.DataFrame([
        {
            "candidate_value": "storage drawers",
            "axis": "unknown",
            "source_phrases": "storage drawers",
            "example_terms": "clear storage drawers | storage drawers for closet",
            "frequency": 3,
            "search_volume_sum": 12,
            "suggested_aliases": "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_candidate_phrase",
            "review_status": "pending",
        }
    ]).to_csv(candidate_csv, index=False)

    result = review_candidate_values(
        candidate_values_csv=candidate_csv,
        output_dir=tmp_path,
        client=FakeReviewClient(),
        limit=1,
        config=CandidateReviewConfig(batch_size=1),
    )

    decisions = pd.read_csv(result["decisions_path"])
    assert decisions.loc[0, "decision"] == "add_alias"
    assert decisions.loc[0, "canonical_value"] == "storage drawer"
    assert bool(decisions.loc[0, "auto_apply_eligible"])

    patch_lines = (tmp_path / "taxonomy_patch_proposals.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(patch_lines) == 1
    assert json.loads(patch_lines[0])["patch_type"] == "taxonomy_alias"


def test_review_candidate_values_falls_back_on_review_error(tmp_path):
    candidate_csv = tmp_path / "candidate_values.csv"
    pd.DataFrame([
        {
            "candidate_value": "case",
            "axis": "unknown",
            "source_phrases": "case",
            "example_terms": "display case",
            "frequency": 10,
            "search_volume_sum": 100,
            "suggested_aliases": "",
            "suggested_rollup_parent": "",
            "suggested_action": "review_candidate_phrase",
            "review_status": "pending",
        }
    ]).to_csv(candidate_csv, index=False)

    result = review_candidate_values(
        candidate_values_csv=candidate_csv,
        output_dir=tmp_path,
        client=FailingReviewClient(),
        limit=1,
        config=CandidateReviewConfig(batch_size=1),
    )

    decisions = pd.read_csv(result["decisions_path"])
    assert decisions.loc[0, "decision"] == "needs_human_review"
    assert decisions.loc[0, "reason"] == "review_error:TimeoutError"
    assert not bool(decisions.loc[0, "auto_apply_eligible"])


def test_review_candidate_values_retries_parse_failures(tmp_path):
    candidate_csv = tmp_path / "candidate_values.csv"
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
        }
    ]).to_csv(candidate_csv, index=False)

    client = RetryThenSuccessReviewClient()
    result = review_candidate_values(
        candidate_values_csv=candidate_csv,
        output_dir=tmp_path,
        client=client,
        limit=1,
        config=CandidateReviewConfig(batch_size=1, max_attempts=2),
    )

    decisions = pd.read_csv(result["decisions_path"])
    assert client.calls == 2
    assert decisions.loc[0, "decision"] == "reject_noise"
    assert bool(decisions.loc[0, "auto_apply_eligible"])
