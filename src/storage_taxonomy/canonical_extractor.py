from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .domain_gate import DomainGate
from .normalizer import tokenize
from .taxonomy_registry import (
    ALL_FIELDS,
    FUNCTION_FIELD,
    LOCATION_FIELD,
    OBJECT_FIELD,
    PRODUCT_FORM_FIELD,
    SCENARIO_FIELD,
    SIZE_FIELD,
    TaxonomyRegistry,
)

_ORGANIZATION_RE = re.compile(r"\b(organizer|organizers|organization)\b")
_STORAGE_RE = re.compile(r"\bstorage\b")
_DISPLAY_RE = re.compile(r"\bdisplay\b")
_SIZE_PATTERNS = [
    re.compile(r"\b(small|medium|large)\b"),
    re.compile(r"\b(\d+)\s*(inch|inches|in)\b"),
    re.compile(r"\b(\d+)\s*(l|liter|liters)\b"),
    re.compile(r"\b(\d+)\s*(tier|tiers|cube|cubes|drawer|drawers)\b"),
]


@dataclass
class ExtractionResult:
    source_text: str
    normalized_text: str
    mapping_status: str
    taxonomy_version: str
    fields: dict[str, Any]
    confidence: float
    matched_aliases: dict[str, list[str]]
    unmapped_phrases: list[str]
    evidence: dict[str, list[str]]

    def to_csv_row(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        row = {**(extra or {})}
        for field in ALL_FIELDS:
            value = self.fields[field]
            row[field] = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
        row.update({
            "taxonomy_version": self.taxonomy_version,
            "mapping_status": self.mapping_status,
            "confidence": round(self.confidence, 4),
            "matched_aliases": json.dumps(self.matched_aliases, ensure_ascii=False),
            "unmapped_phrases": json.dumps(self.unmapped_phrases, ensure_ascii=False),
            "evidence": json.dumps(self.evidence, ensure_ascii=False),
        })
        return row


class CanonicalExtractor:
    def __init__(self, registry: TaxonomyRegistry | None = None):
        self.registry = registry or TaxonomyRegistry()
        self.domain_gate = DomainGate(self.registry)
        self.multi_value_fields = set(self.registry.field_constraints.get("multi_value_fields", [PRODUCT_FORM_FIELD]))
        self.stopwords = set(self.registry.rules.get("normalizer", {}).get("stopwords", []))

    def extract(self, text: str) -> ExtractionResult:
        normalized = self.registry.normalize(text)
        gate_status, domain_conf, _reason = self.domain_gate.classify(normalized)
        fields = self.registry.empty_fields()

        if gate_status in {"not_storage", "ambiguous"}:
            return ExtractionResult(
                source_text=text,
                normalized_text=normalized,
                mapping_status=gate_status,
                taxonomy_version=self.registry.taxonomy_version,
                fields=fields,
                confidence=domain_conf,
                matched_aliases={},
                unmapped_phrases=[],
                evidence={},
            )

        matches = self.registry.iter_alias_matches(normalized)
        matched_aliases: dict[str, list[str]] = {}
        evidence: dict[str, list[str]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}

        for match in matches:
            axis = match["axis"]
            grouped.setdefault(axis, []).append(match)
            matched_aliases.setdefault(axis, [])
            evidence.setdefault(axis, [])
            if match["alias"] not in matched_aliases[axis]:
                matched_aliases[axis].append(match["alias"])
            if match["canonical_value"] not in evidence[axis]:
                evidence[axis].append(match["canonical_value"])

        for axis, axis_matches in grouped.items():
            unique_matches = self._unique_matches(axis_matches)
            if axis in self.multi_value_fields:
                fields[axis] = [match["canonical_value"] for match in unique_matches]
            elif axis != SCENARIO_FIELD:
                best = self.registry.best_scalar_match(unique_matches)
                if best:
                    fields[axis] = best["canonical_value"]

        direct_scenario = self.registry.best_scalar_match(grouped.get(SCENARIO_FIELD, []))
        fields[SCENARIO_FIELD] = self._derive_scenario(normalized, fields, direct_scenario)
        if not fields[SIZE_FIELD]:
            fields[SIZE_FIELD] = self._extract_size(normalized)

        mapping_status = self._mapping_status(fields)
        selected_matches = self._selected_matches(grouped, fields, direct_scenario)
        confidence = self._compute_confidence(domain_conf, selected_matches, mapping_status)
        unmapped_phrases = self._extract_unmapped_phrases(normalized, matched_aliases, fields)

        return ExtractionResult(
            source_text=text,
            normalized_text=normalized,
            mapping_status=mapping_status,
            taxonomy_version=self.registry.taxonomy_version,
            fields=fields,
            confidence=confidence,
            matched_aliases=matched_aliases,
            unmapped_phrases=unmapped_phrases,
            evidence=evidence,
        )

    @staticmethod
    def _unique_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for match in sorted(matches, key=lambda item: (-item["priority"], -(item["end"] - item["start"]))):
            deduped.setdefault(match["canonical_value"], match)
        return sorted(
            deduped.values(),
            key=lambda item: (-item["priority"], -(item["end"] - item["start"]), item["canonical_value"]),
        )

    def _derive_scenario(
        self,
        normalized_text: str,
        fields: dict[str, Any],
        direct_scenario: dict[str, Any] | None,
    ) -> str:
        if direct_scenario:
            return direct_scenario["canonical_value"]

        object_value = fields[OBJECT_FIELD]
        location_value = fields[LOCATION_FIELD]
        has_storage = bool(_STORAGE_RE.search(normalized_text))
        has_organization = bool(_ORGANIZATION_RE.search(normalized_text))
        has_display = bool(_DISPLAY_RE.search(normalized_text)) or fields[FUNCTION_FIELD] == "display"
        has_form = bool(fields[PRODUCT_FORM_FIELD])

        if location_value == "under sink" and (has_storage or has_organization):
            return "under sink organization"
        if location_value == "bathroom" and (has_storage or has_organization):
            return "bathroom organization"
        if location_value == "over toilet" and has_storage:
            return "toilet storage"
        if location_value == "garage" and object_value == "tool" and has_storage:
            return "garage tool storage"
        if object_value and has_display:
            if not fields[FUNCTION_FIELD]:
                fields[FUNCTION_FIELD] = "display"
            return f"{object_value} display"
        if object_value and has_organization:
            return f"{object_value} organization"
        if object_value and (has_storage or has_form):
            return f"{object_value} storage"
        return ""

    @staticmethod
    def _extract_size(normalized_text: str) -> str:
        for pattern in _SIZE_PATTERNS:
            match = pattern.search(normalized_text)
            if not match:
                continue
            groups = [group for group in match.groups() if group]
            return " ".join(groups)
        return ""

    def _mapping_status(self, fields: dict[str, Any]) -> str:
        filled = 0
        for field, value in fields.items():
            if field == PRODUCT_FORM_FIELD and value:
                filled += 1
            elif isinstance(value, str) and value:
                filled += 1
        if fields[SCENARIO_FIELD] or filled >= int(
            self.registry.thresholds.get("mapping", {}).get("mapped_min_non_empty_fields", 2)
        ):
            return "mapped"
        if filled > 0:
            return "partial"
        return "ambiguous"

    def _compute_confidence(
        self,
        domain_confidence: float,
        matches: list[dict[str, Any]],
        mapping_status: str,
    ) -> float:
        if mapping_status == "ambiguous":
            return 0.55
        if not matches:
            return domain_confidence
        avg_match_conf = sum(self._match_confidence(match) for match in matches) / len(matches)
        return min(0.99, round((domain_confidence * 0.45) + (avg_match_conf * 0.55), 4))

    @staticmethod
    def _match_confidence(match: dict[str, Any]) -> float:
        base = 0.86
        if match["priority"] >= 90:
            return 0.96
        if match["priority"] >= 70:
            return 0.92
        return base

    def _selected_matches(
        self,
        grouped_matches: dict[str, list[dict[str, Any]]],
        fields: dict[str, Any],
        direct_scenario: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for axis, axis_matches in grouped_matches.items():
            if axis == PRODUCT_FORM_FIELD:
                selected.extend(self._unique_matches(axis_matches))
            elif axis == SCENARIO_FIELD:
                if direct_scenario:
                    selected.append(direct_scenario)
            else:
                best = self.registry.best_scalar_match(axis_matches)
                if best and fields.get(axis):
                    selected.append(best)
        return selected

    def _extract_unmapped_phrases(
        self,
        normalized_text: str,
        matched_aliases: dict[str, list[str]],
        fields: dict[str, Any],
    ) -> list[str]:
        consumed_tokens = set(self.stopwords)
        for aliases in matched_aliases.values():
            for alias in aliases:
                consumed_tokens.update(tokenize(alias))
        if fields[SIZE_FIELD]:
            consumed_tokens.update(tokenize(fields[SIZE_FIELD]))
        if fields[SCENARIO_FIELD]:
            consumed_tokens.update({"storage", "organizer", "organizers", "organization", "display"})

        unmapped: list[str] = []
        for token in tokenize(normalized_text):
            if token in consumed_tokens or token.isdigit() or len(token) <= 2:
                continue
            if token not in unmapped:
                unmapped.append(token)
        return unmapped
