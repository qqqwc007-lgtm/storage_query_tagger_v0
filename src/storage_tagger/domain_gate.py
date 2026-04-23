from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from .preprocessing import normalize_query, contains_phrase


class DomainGate:
    """v0 high-precision domain gate.

    Returns:
        (domain_label, confidence, reason)
    """

    def __init__(self, rules_config: Dict[str, Any]):
        gate = rules_config.get("domain_gate", {})
        self.positive_patterns = [
            re.compile(p, re.IGNORECASE) for p in gate.get("high_precision_positive_patterns", [])
        ]
        self.negative_patterns = [
            re.compile(p, re.IGNORECASE) for p in gate.get("high_precision_negative_patterns", [])
        ]
        self.ambiguous_terms = gate.get("ambiguous_standalone_terms", [])

    def classify(self, query: str) -> Tuple[str, float, str]:
        text = normalize_query(query)
        if not text:
            return "not_storage", 0.99, "empty_query"

        for pattern in self.negative_patterns:
            if pattern.search(text):
                return "not_storage", 0.97, f"negative_pattern:{pattern.pattern}"

        for pattern in self.positive_patterns:
            if pattern.search(text):
                return "storage_related", 0.95, f"positive_pattern:{pattern.pattern}"

        for term in self.ambiguous_terms:
            if contains_phrase(text, term):
                return "ambiguous", 0.55, f"ambiguous_term:{term}"

        return "not_storage", 0.90, "no_storage_evidence"
