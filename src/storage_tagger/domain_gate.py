from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from .preprocessing import normalize_query, contains_phrase


class DomainGate:
    """v0 high-precision domain gate.

    Returns:
        (domain_label, confidence, reason)
    """

    def __init__(self, rules_config: Dict[str, Any], thresholds: Dict[str, Any] | None = None):
        gate = rules_config.get("domain_gate", {})
        domain_thresholds = (thresholds or {}).get("domain", {})
        self.positive_patterns = [
            re.compile(p, re.IGNORECASE) for p in gate.get("high_precision_positive_patterns", [])
        ]
        self.negative_patterns = [
            re.compile(p, re.IGNORECASE) for p in gate.get("high_precision_negative_patterns", [])
        ]
        self.ambiguous_terms = gate.get("ambiguous_standalone_terms", [])
        self.positive_confidence = float(domain_thresholds.get("positive_confidence", 0.95))
        self.negative_confidence = float(domain_thresholds.get("negative_confidence", 0.97))
        self.ambiguous_confidence = float(domain_thresholds.get("ambiguous_confidence", 0.55))
        self.empty_confidence = float(domain_thresholds.get("empty_confidence", 0.99))
        self.no_evidence_confidence = float(domain_thresholds.get("no_evidence_confidence", 0.90))

    def classify(self, query: str) -> Tuple[str, float, str]:
        text = normalize_query(query)
        if not text:
            return "not_storage", self.empty_confidence, "empty_query"

        for pattern in self.negative_patterns:
            if pattern.search(text):
                return "not_storage", self.negative_confidence, f"negative_pattern:{pattern.pattern}"

        for pattern in self.positive_patterns:
            if pattern.search(text):
                return "storage_related", self.positive_confidence, f"positive_pattern:{pattern.pattern}"

        for term in self.ambiguous_terms:
            if contains_phrase(text, term):
                return "ambiguous", self.ambiguous_confidence, f"ambiguous_term:{term}"

        return "not_storage", self.no_evidence_confidence, "no_storage_evidence"
