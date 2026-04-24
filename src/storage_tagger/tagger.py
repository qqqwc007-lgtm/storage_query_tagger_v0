from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .config_loader import load_default_configs, taxonomy_version
from .domain_gate import DomainGate
from .preprocessing import normalize_query
from .rule_tagger import RuleTagger
from .schemas import Tag, TaggingResult


class StorageQueryTagger:
    def __init__(self, config_dir: str | None = None):
        configs = load_default_configs(config_dir)
        self.taxonomy = configs["taxonomy"]
        self.rules = configs["rules"]
        self.thresholds = configs["thresholds"]
        self.version = taxonomy_version(self.taxonomy)
        self.domain_gate = DomainGate(self.rules, thresholds=self.thresholds)
        self.rule_tagger = RuleTagger(self.taxonomy, self.rules)

        self.core_dimensions = set(
            self.thresholds.get("coverage", {}).get(
                "core_dimensions",
                ["target_object", "product_form", "location", "purpose", "scenario"],
            )
        )
        self.min_core_tags_for_covered = int(
            self.thresholds.get("coverage", {}).get("min_core_tags_for_covered", 2)
        )
        self.min_conf = float(self.thresholds.get("tagging", {}).get("min_tag_confidence", 0.70))
        self.review_max_conf_threshold = float(
            self.thresholds.get("review", {}).get("needs_review_if_max_tag_confidence_below", 0.75)
        )

    def tag(self, query: str) -> TaggingResult:
        normalized = normalize_query(query)
        domain_label, domain_conf, _reason = self.domain_gate.classify(normalized)

        tags: List[Tag] = []
        if domain_label == "storage_related":
            tags = [tag for tag in self.rule_tagger.tag(normalized) if tag.confidence >= self.min_conf]

        coverage_status = self._coverage_status(domain_label, tags)
        needs_review = self._needs_review(domain_label, tags, coverage_status)

        return TaggingResult(
            query=query,
            normalized_query=normalized,
            domain_label=domain_label,
            domain_confidence=domain_conf,
            tags=tags,
            coverage_status=coverage_status,
            needs_review=needs_review,
            taxonomy_version=self.version,
        )

    def batch_tag(self, queries: Iterable[str]) -> List[TaggingResult]:
        return [self.tag(q) for q in queries]

    def _coverage_status(self, domain_label: str, tags: List[Tag]) -> str:
        if domain_label == "not_storage":
            return "not_storage"
        if domain_label == "ambiguous":
            return "ambiguous"
        core_tag_count = sum(1 for tag in tags if tag.dimension in self.core_dimensions)
        if core_tag_count >= self.min_core_tags_for_covered:
            return "covered"
        if core_tag_count > 0:
            return "partial"
        return "needs_review"

    def _needs_review(self, domain_label: str, tags: List[Tag], coverage_status: str) -> bool:
        if domain_label == "ambiguous":
            return True
        if coverage_status in {"partial", "needs_review"}:
            return True
        if tags:
            max_conf = max(tag.confidence for tag in tags)
            if max_conf < self.review_max_conf_threshold:
                return True
        return False


def result_to_csv_row(result: TaggingResult) -> Dict[str, Any]:
    data = result.to_dict()
    return {
        "query": data["query"],
        "normalized_query": data["normalized_query"],
        "domain_label": data["domain_label"],
        "domain_confidence": data["domain_confidence"],
        "tags": json.dumps(data["tags"], ensure_ascii=False),
        "tag_ids": ";".join(data["tag_ids"]),
        "coverage_status": data["coverage_status"],
        "needs_review": data["needs_review"],
        "taxonomy_version": data["taxonomy_version"],
    }
