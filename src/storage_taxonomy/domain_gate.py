from __future__ import annotations

import re
from typing import Tuple

from .normalizer import contains_phrase
from .taxonomy_registry import TaxonomyRegistry


class DomainGate:
    def __init__(self, registry: TaxonomyRegistry):
        self.registry = registry
        gate = registry.rules.get("domain_gate", {})
        domain_thresholds = registry.thresholds.get("domain", {})
        self.positive_patterns = [re.compile(p, re.IGNORECASE) for p in gate.get("positive_patterns", [])]
        self.negative_patterns = [
            re.compile(p, re.IGNORECASE) for p in registry.negative_rules.get("not_storage_patterns", [])
        ]
        self.ambiguous_terms = registry.negative_rules.get("ambiguous_terms", [])
        self.positive_confidence = float(domain_thresholds.get("positive_confidence", 0.95))
        self.negative_confidence = float(domain_thresholds.get("negative_confidence", 0.98))
        self.ambiguous_confidence = float(domain_thresholds.get("ambiguous_confidence", 0.55))
        self.empty_confidence = float(domain_thresholds.get("empty_confidence", 0.99))
        self.no_evidence_confidence = float(domain_thresholds.get("no_evidence_confidence", 0.88))

    def classify(self, text: str) -> Tuple[str, float, str]:
        if not text:
            return "not_storage", self.empty_confidence, "empty"

        for pattern in self.negative_patterns:
            if pattern.search(text):
                return "not_storage", self.negative_confidence, f"negative:{pattern.pattern}"

        for pattern in self.positive_patterns:
            if pattern.search(text):
                return "mapped", self.positive_confidence, f"positive:{pattern.pattern}"

        for term in self.ambiguous_terms:
            if contains_phrase(text, term):
                return "ambiguous", self.ambiguous_confidence, f"ambiguous:{term}"

        return "not_storage", self.no_evidence_confidence, "no_storage_evidence"
