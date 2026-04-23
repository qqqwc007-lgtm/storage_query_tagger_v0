from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class Tag:
    dimension: str
    tag_id: str
    canonical_name: str
    confidence: float
    evidence: str
    source: str = "rule"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaggingResult:
    query: str
    normalized_query: str
    domain_label: str
    domain_confidence: float
    tags: List[Tag]
    coverage_status: str
    needs_review: bool
    taxonomy_version: str

    @property
    def tag_ids(self) -> List[str]:
        return [tag.tag_id for tag in self.tags]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "domain_label": self.domain_label,
            "domain_confidence": round(self.domain_confidence, 4),
            "tags": [tag.to_dict() for tag in self.tags],
            "tag_ids": self.tag_ids,
            "coverage_status": self.coverage_status,
            "needs_review": self.needs_review,
            "taxonomy_version": self.taxonomy_version,
        }
