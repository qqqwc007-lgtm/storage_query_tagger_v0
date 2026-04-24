from __future__ import annotations

import hashlib
import json
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from .opencode_go_client import OpenCodeGoChatClient, load_opencode_go_api_key
from .taxonomy_registry import TaxonomyRegistry


DECISION_VALUES = {
    "add_alias",
    "add_canonical",
    "add_rollup",
    "add_negative_rule",
    "reject_noise",
    "needs_human_review",
}


class CandidateReviewChatClient(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class CandidateReviewConfig:
    batch_size: int = 1
    max_examples: int = 6
    max_example_chars: int = 160
    confidence_gate: float = 0.85
    max_tokens: int = 1200
    request_timeout_seconds: int = 90
    max_attempts: int = 2


def review_candidate_values(
    candidate_values_csv: str | Path,
    output_dir: str | Path | None = None,
    client: CandidateReviewChatClient | None = None,
    registry: TaxonomyRegistry | None = None,
    limit: int | None = 20,
    config: CandidateReviewConfig | None = None,
) -> dict[str, str | int]:
    config = config or CandidateReviewConfig()
    registry = registry or TaxonomyRegistry()
    client = client or OpenCodeGoChatClient(api_key=load_opencode_go_api_key())

    candidate_path = Path(candidate_values_csv)
    output_path = Path(output_dir) if output_dir else candidate_path.parent
    output_path.mkdir(parents=True, exist_ok=True)

    candidate_df = pd.read_csv(candidate_path)
    selected_df = _select_candidates(candidate_df, limit=limit)
    selected_records = selected_df.to_dict("records")

    decision_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    taxonomy_context = _build_taxonomy_context(registry)
    for batch in _batched(selected_records, config.batch_size):
        reviewed_at = datetime.now(timezone.utc).isoformat()
        try:
            prompt, decision_by_id, response_payload = _review_batch_with_retries(
                batch=batch,
                taxonomy_context=taxonomy_context,
                config=config,
                client=client,
            )
        except Exception as exc:
            prompt = _build_review_prompt(batch, taxonomy_context, config)
            decision_by_id = {
                str(record["candidate_id"]): _fallback_error_decision(record, exc)
                for record in batch
            }
            response_payload = {
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        for record in batch:
            candidate_id = str(record["candidate_id"])
            model_decision = decision_by_id.get(candidate_id, {})
            decision_row = _normalize_decision_row(
                original=record,
                model_decision=model_decision,
                model=getattr(client, "model", ""),
                reviewed_at=reviewed_at,
                confidence_gate=config.confidence_gate,
            )
            decision_rows.append(decision_row)
        audit_rows.append({
            "reviewed_at": reviewed_at,
            "model": getattr(client, "model", ""),
            "candidate_ids": [str(record["candidate_id"]) for record in batch],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "raw_response": response_payload,
        })

    decisions_df = pd.DataFrame(decision_rows)
    decisions_path = output_path / "candidate_decisions.csv"
    patch_path = output_path / "taxonomy_patch_proposals.jsonl"
    audit_path = output_path / "candidate_review_audit.jsonl"
    metrics_path = output_path / "candidate_review_metrics.json"

    decisions_df.to_csv(decisions_path, index=False)
    _write_patch_proposals(patch_path, decision_rows)
    _write_jsonl(audit_path, audit_rows)
    metrics = _build_metrics(decision_rows)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "decisions_path": str(decisions_path),
        "patch_proposals_path": str(patch_path),
        "audit_path": str(audit_path),
        "metrics_path": str(metrics_path),
        "reviewed_count": len(decision_rows),
    }


def _select_candidates(candidate_df: pd.DataFrame, limit: int | None) -> pd.DataFrame:
    working_df = candidate_df.copy()
    if "frequency" in working_df.columns:
        working_df["frequency"] = pd.to_numeric(working_df["frequency"], errors="coerce").fillna(0)
    if "search_volume_sum" in working_df.columns:
        working_df["search_volume_sum"] = pd.to_numeric(working_df["search_volume_sum"], errors="coerce").fillna(0)
    sort_columns = [col for col in ["frequency", "search_volume_sum", "candidate_value"] if col in working_df.columns]
    if sort_columns:
        ascending = [False if col in {"frequency", "search_volume_sum"} else True for col in sort_columns]
        working_df = working_df.sort_values(sort_columns, ascending=ascending)
    if limit and limit > 0:
        working_df = working_df.head(limit)
    working_df = working_df.reset_index(drop=False).rename(columns={"index": "source_row_index"})
    working_df["candidate_id"] = working_df.index.astype(str)
    return working_df


def _build_taxonomy_context(registry: TaxonomyRegistry) -> dict[str, Any]:
    values_by_axis: dict[str, list[str]] = {}
    for axis, value_records in registry.values_by_axis.items():
        values_by_axis[axis] = sorted(value_records.keys())
    rollups_by_axis: dict[str, dict[str, str]] = {}
    for axis, rollups in registry.rollup_map.items():
        rollups_by_axis[axis] = dict(sorted(rollups.items()))
    return {
        "fields": list(registry.values_by_axis.keys()),
        "canonical_values_by_axis": values_by_axis,
        "rollups_by_axis": rollups_by_axis,
    }


def _system_prompt(strict_json: bool = False) -> str:
    return (
        "You are a taxonomy reviewer for an Amazon Storage & Organization search workflow. "
        "Classify candidate values conservatively. "
        + (
            "Return only compact valid JSON with no markdown fences or extra prose. "
            if strict_json
            else "Return only valid JSON. "
        )
        + "Never invent evidence beyond the supplied examples."
    )


def _build_review_prompt(
    batch: list[dict[str, Any]],
    taxonomy_context: dict[str, Any],
    config: CandidateReviewConfig,
    strict_json: bool = False,
) -> str:
    prompt_records = []
    for record in batch:
        prompt_records.append({
            "candidate_id": str(record["candidate_id"]),
            "candidate_value": _safe_str(record.get("candidate_value")),
            "axis": _safe_str(record.get("axis")),
            "frequency": int(float(record.get("frequency", 0) or 0)),
            "search_volume_sum": float(record.get("search_volume_sum", 0) or 0),
            "suggested_action": _safe_str(record.get("suggested_action")),
            "source_phrases": _split_examples(record.get("source_phrases"), config.max_examples, config.max_example_chars),
            "example_terms": _split_examples(record.get("example_terms"), config.max_examples, config.max_example_chars),
        })

    expected_schema = {
        "decisions": [
            {
                "candidate_id": "string",
                "decision": "add_alias | add_canonical | add_rollup | add_negative_rule | reject_noise | needs_human_review",
                "target_axis": "string",
                "canonical_value": "string",
                "suggested_aliases": ["string"],
                "rollup_parent": "string",
                "confidence": 0.0,
                "reason": "short evidence-based reason",
                "risk_flags": ["polysemous | too_broad | brand | non_storage | low_evidence | other"],
                "evidence_terms": ["string"],
            }
        ]
    }
    instructions = {
        "decision_rules": [
            "Use add_alias when the candidate is clearly a synonym, inflection, or common phrasing for an existing canonical value.",
            "Use add_canonical when the candidate is a real storage taxonomy value but no existing canonical value fits.",
            "Use add_rollup only when the main issue is parent-child grouping between two values.",
            "Use add_negative_rule for non-storage or out-of-domain phrases that should be filtered.",
            "Use reject_noise for colors, sizes, brands, generic modifiers, malformed text, or phrases that do not add taxonomy value.",
            "Use needs_human_review when evidence is ambiguous, polysemous, or requires taxonomy design judgment.",
            "Prefer needs_human_review over a confident taxonomy expansion when unsure.",
        ],
        "output_constraints": [
            "Return one decision for every candidate_id.",
            "Return only JSON matching the schema.",
            "confidence must be between 0 and 1.",
            "Do not emit commentary outside the JSON object.",
        ],
    }
    return json.dumps(
        {
            "task": "Review candidate taxonomy values generated from unmapped phrases and true conflicts.",
            "taxonomy_context": taxonomy_context,
            "instructions": instructions,
            "expected_schema": expected_schema,
            "candidates": prompt_records,
            "response_style": (
                "Return a single minified JSON object only. No markdown fences."
                if strict_json
                else "Return a single JSON object."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


def _split_examples(value: Any, max_items: int, max_chars: int) -> list[str]:
    text = _safe_str(value)
    if not text:
        return []
    examples = []
    for part in text.split(" | "):
        cleaned = part.strip()
        if not cleaned:
            continue
        if len(cleaned) > max_chars:
            cleaned = cleaned[: max_chars - 3].rstrip() + "..."
        examples.append(cleaned)
        if len(examples) >= max_items:
            break
    return examples


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, dict)):
        return str(value).strip()
    if pd.isna(value):
        return ""
    return str(value).strip()


def _batched(records: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [records[index:index + batch_size] for index in range(0, len(records), batch_size)]


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char == "{":
            try:
                parsed, _ = decoder.raw_decode(stripped[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError(f"Could not parse JSON object from model content: {content[:500]}")


def _normalize_decision_row(
    original: dict[str, Any],
    model_decision: dict[str, Any],
    model: str,
    reviewed_at: str,
    confidence_gate: float,
) -> dict[str, Any]:
    decision = str(model_decision.get("decision") or "needs_human_review")
    if decision not in DECISION_VALUES:
        decision = "needs_human_review"
    confidence = _coerce_confidence(model_decision.get("confidence"))
    suggested_aliases = _coerce_list(model_decision.get("suggested_aliases"))
    risk_flags = _coerce_list(model_decision.get("risk_flags"))
    evidence_terms = _coerce_list(model_decision.get("evidence_terms"))
    auto_apply_eligible = (
        confidence >= confidence_gate
        and decision in {"add_alias", "reject_noise"}
        and "polysemous" not in risk_flags
        and "low_evidence" not in risk_flags
    )
    return {
        **original,
        "decision": decision,
        "target_axis": str(model_decision.get("target_axis") or original.get("axis") or ""),
        "canonical_value": str(model_decision.get("canonical_value") or ""),
        "llm_suggested_aliases": " | ".join(suggested_aliases),
        "llm_rollup_parent": str(model_decision.get("rollup_parent") or ""),
        "confidence": confidence,
        "reason": str(model_decision.get("reason") or ""),
        "risk_flags": " | ".join(risk_flags),
        "evidence_terms": " | ".join(evidence_terms),
        "auto_apply_eligible": auto_apply_eligible,
        "model": model,
        "reviewed_at": reviewed_at,
    }


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _fallback_error_decision(record: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "candidate_id": str(record.get("candidate_id", "")),
        "decision": "needs_human_review",
        "target_axis": str(record.get("axis") or ""),
        "canonical_value": "",
        "suggested_aliases": [],
        "rollup_parent": "",
        "confidence": 0.0,
        "reason": f"review_error:{type(exc).__name__}",
        "risk_flags": ["low_evidence", "other"],
        "evidence_terms": [],
    }


def _review_batch_with_retries(
    batch: list[dict[str, Any]],
    taxonomy_context: dict[str, Any],
    config: CandidateReviewConfig,
    client: CandidateReviewChatClient,
) -> tuple[str, dict[str, dict[str, Any]], dict[str, Any]]:
    attempts = max(1, int(config.max_attempts))
    last_exc: Exception | None = None
    repair_source: str | None = None
    for attempt in range(1, attempts + 1):
        strict_json = attempt > 1
        prompt = (
            _build_json_repair_prompt(batch, repair_source)
            if repair_source
            else _build_review_prompt(batch, taxonomy_context, config, strict_json=strict_json)
        )
        try:
            with _deadline(config.request_timeout_seconds):
                response = client.chat(
                    [
                        {
                            "role": "system",
                            "content": _system_prompt(strict_json=True if repair_source else strict_json),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=0,
                    max_tokens=min(config.max_tokens, 900 if strict_json else config.max_tokens),
                )
            content = OpenCodeGoChatClient.message_content(response)
            parsed = _parse_json_object(content)
            decisions = parsed.get("decisions", [])
            decision_by_id = {
                str(item.get("candidate_id")): item
                for item in decisions
                if isinstance(item, dict) and item.get("candidate_id") is not None
            }
            missing_ids = [
                str(record.get("candidate_id"))
                for record in batch
                if str(record.get("candidate_id")) not in decision_by_id
            ]
            if missing_ids:
                raise ValueError(f"Missing decisions for candidate_ids: {', '.join(missing_ids)}")
            return (
                prompt,
                decision_by_id,
                response,
            )
        except Exception as exc:
            last_exc = exc
            if isinstance(exc, ValueError):
                repair_source = str(exc).split("model content:", 1)[-1].strip()
    if last_exc is None:
        raise RuntimeError("candidate review failed without an exception")
    raise last_exc


def _build_json_repair_prompt(batch: list[dict[str, Any]], analysis_text: str | None) -> str:
    candidate_ids = [str(record.get("candidate_id", "")) for record in batch]
    return json.dumps(
        {
            "task": "Convert the prior taxonomy review analysis into final JSON.",
            "requirements": [
                "Return exactly one JSON object.",
                "Return one decision for every candidate_id.",
                "Do not add markdown fences.",
                "Do not add any prose outside the JSON object.",
            ],
            "candidate_ids": candidate_ids,
            "analysis_text": analysis_text or "",
        },
        ensure_ascii=False,
        indent=2,
    )


class _deadline:
    def __init__(self, seconds: int):
        self.seconds = max(0, int(seconds))
        self.enabled = hasattr(signal, "SIGALRM") and self.seconds > 0
        self._previous_handler = None

    def __enter__(self) -> None:
        if not self.enabled:
            return None
        self._previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._raise_timeout)
        signal.alarm(self.seconds)
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.enabled:
            return None
        signal.alarm(0)
        if self._previous_handler is not None:
            signal.signal(signal.SIGALRM, self._previous_handler)
        return None

    @staticmethod
    def _raise_timeout(signum, frame) -> None:
        raise TimeoutError("candidate review deadline exceeded")


def _write_patch_proposals(path: Path, decision_rows: list[dict[str, Any]]) -> None:
    proposals = []
    for row in decision_rows:
        proposal = _build_patch_proposal(row)
        if proposal:
            proposals.append(proposal)
    _write_jsonl(path, proposals)


def _build_patch_proposal(row: dict[str, Any]) -> dict[str, Any] | None:
    decision = row.get("decision")
    if decision == "add_alias":
        aliases = [item.strip() for item in str(row.get("llm_suggested_aliases", "")).split(" | ") if item.strip()]
        if not aliases:
            aliases = [str(row.get("candidate_value", "")).strip()]
        return {
            "patch_type": "taxonomy_alias",
            "auto_apply_eligible": bool(row.get("auto_apply_eligible")),
            "record": {
                "axis": row.get("target_axis"),
                "canonical_value": row.get("canonical_value"),
                "aliases": aliases,
            },
            "source": _proposal_source(row),
        }
    if decision == "add_canonical":
        return {
            "patch_type": "taxonomy_canonical_value",
            "auto_apply_eligible": False,
            "record": {
                "axis": row.get("target_axis"),
                "canonical_value": row.get("canonical_value") or row.get("candidate_value"),
                "status": "active",
                "priority": 50,
                "example_terms": _coerce_patch_examples(row.get("evidence_terms")),
                "negative_examples": [],
                "notes": str(row.get("reason", "")),
            },
            "source": _proposal_source(row),
        }
    if decision == "add_rollup":
        return {
            "patch_type": "taxonomy_rollup",
            "auto_apply_eligible": False,
            "record": {
                "axis": row.get("target_axis"),
                "child": row.get("canonical_value") or row.get("candidate_value"),
                "parent": row.get("llm_rollup_parent"),
            },
            "source": _proposal_source(row),
        }
    if decision == "add_negative_rule":
        return {
            "patch_type": "negative_rule_candidate",
            "auto_apply_eligible": False,
            "record": {
                "phrase": row.get("candidate_value"),
                "reason": row.get("reason"),
            },
            "source": _proposal_source(row),
        }
    if decision == "reject_noise":
        return {
            "patch_type": "candidate_suppression",
            "auto_apply_eligible": bool(row.get("auto_apply_eligible")),
            "record": {
                "terms": [row.get("candidate_value")],
                "reason": row.get("reason"),
            },
            "source": _proposal_source(row),
        }
    return None


def _proposal_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_value": row.get("candidate_value"),
        "axis": row.get("axis"),
        "frequency": row.get("frequency"),
        "search_volume_sum": row.get("search_volume_sum"),
        "confidence": row.get("confidence"),
        "risk_flags": row.get("risk_flags"),
    }


def _coerce_patch_examples(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(" | ") if item.strip()][:5]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_metrics(decision_rows: list[dict[str, Any]]) -> dict[str, Any]:
    decision_counts: dict[str, int] = {}
    auto_apply_count = 0
    for row in decision_rows:
        decision = str(row.get("decision", ""))
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        if row.get("auto_apply_eligible"):
            auto_apply_count += 1
    return {
        "reviewed_count": len(decision_rows),
        "decision_counts": dict(sorted(decision_counts.items())),
        "auto_apply_eligible_count": auto_apply_count,
    }
