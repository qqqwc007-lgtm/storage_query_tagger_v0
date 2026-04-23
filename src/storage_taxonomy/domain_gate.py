from __future__ import annotations

import re
from typing import Tuple

from .normalizer import contains_phrase
from .taxonomy_registry import TaxonomyRegistry


class DomainGate:
    def __init__(self, registry: TaxonomyRegistry):
        self.registry = registry
        gate = registry.rules.get("domain_gate", {})
        self.positive_patterns = [re.compile(p, re.IGNORECASE) for p in gate.get("positive_patterns", [])]
        self.negative_patterns = [
            re.compile(p, re.IGNORECASE) for p in registry.negative_rules.get("not_storage_patterns", [])
        ]
        self.ambiguous_terms = registry.negative_rules.get("ambiguous_terms", [])

    def classify(self, text: str) -> Tuple[str, float, str]:
        if not text:
            return "not_storage", 0.99, "empty"

        for pattern in self.negative_patterns:
            if pattern.search(text):
                return "not_storage", 0.98, f"negative:{pattern.pattern}"

        for pattern in self.positive_patterns:
            if pattern.search(text):
                return "mapped", 0.95, f"positive:{pattern.pattern}"

        for term in self.ambiguous_terms:
            if contains_phrase(text, term):
                return "ambiguous", 0.55, f"ambiguous:{term}"

        return "not_storage", 0.88, "no_storage_evidence"
