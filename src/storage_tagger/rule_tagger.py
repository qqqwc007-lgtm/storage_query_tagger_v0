from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .preprocessing import normalize_query, word_boundary_pattern
from .schemas import Tag


class RuleTagger:
    def __init__(self, taxonomy: Dict[str, Any], rules_config: Dict[str, Any]):
        self.taxonomy = taxonomy
        self.rules_config = rules_config
        self.tag_index = {tag["tag_id"]: tag for tag in taxonomy.get("tags", [])}
        self.alias_patterns = self._compile_alias_patterns(taxonomy)
        self.pattern_rules = self._compile_pattern_rules(rules_config)

        confidence_cfg = rules_config.get("confidence", {})
        self.alias_default_conf = float(confidence_cfg.get("alias_match_default", 0.82))
        self.alias_purpose_conf = float(confidence_cfg.get("alias_match_purpose", 0.88))
        self.alias_attribute_conf = float(confidence_cfg.get("alias_match_attribute", 0.84))

    def _compile_alias_patterns(self, taxonomy: Dict[str, Any]) -> List[Tuple[re.Pattern[str], Dict[str, Any], str]]:
        patterns: List[Tuple[re.Pattern[str], Dict[str, Any], str]] = []
        for tag in taxonomy.get("tags", []):
            if tag.get("dimension") == "domain":
                continue
            for alias in tag.get("aliases", []):
                if not alias or len(str(alias).strip()) <= 1:
                    continue
                patterns.append((word_boundary_pattern(str(alias)), tag, str(alias)))
        patterns.sort(key=lambda x: len(x[2]), reverse=True)
        return patterns

    def _compile_pattern_rules(self, rules_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        compiled = []
        for rule in rules_config.get("tagging", {}).get("pattern_rules", []):
            compiled.append({
                "name": rule.get("name", "unnamed_rule"),
                "pattern": re.compile(rule["pattern"], re.IGNORECASE),
                "tags": rule.get("tags", []),
            })
        return compiled

    def _tag_from_id(self, tag_id: str, confidence: float, evidence: str, source: str) -> Tag | None:
        meta = self.tag_index.get(tag_id)
        if not meta:
            return None
        return Tag(
            dimension=meta["dimension"],
            tag_id=tag_id,
            canonical_name=meta.get("canonical_name", tag_id),
            confidence=float(confidence),
            evidence=evidence,
            source=source,
        )

    def tag(self, query: str) -> List[Tag]:
        text = normalize_query(query)
        candidates: Dict[str, Tag] = {}

        for rule in self.pattern_rules:
            match = rule["pattern"].search(text)
            if not match:
                continue
            for tag_spec in rule.get("tags", []):
                tag = self._tag_from_id(
                    tag_id=tag_spec["tag_id"],
                    confidence=float(tag_spec.get("confidence", 0.92)),
                    evidence=str(tag_spec.get("evidence", match.group(0))),
                    source=f"pattern:{rule['name']}",
                )
                if tag:
                    self._upsert_best(candidates, tag)

        for pattern, meta, alias in self.alias_patterns:
            if not pattern.search(text):
                continue
            dimension = meta.get("dimension", "")
            if dimension == "purpose":
                conf = self.alias_purpose_conf
            elif dimension == "attribute":
                conf = self.alias_attribute_conf
            else:
                conf = self.alias_default_conf

            if alias in {"bag", "bags", "box", "boxes", "basket", "baskets", "shelf", "shelves", "cabinet"}:
                conf = min(conf, 0.78)

            tag = Tag(
                dimension=dimension,
                tag_id=meta["tag_id"],
                canonical_name=meta.get("canonical_name", meta["tag_id"]),
                confidence=conf,
                evidence=alias,
                source="alias",
            )
            self._upsert_best(candidates, tag)

        tags = list(candidates.values())
        tags.sort(key=lambda t: (t.dimension, -t.confidence, t.tag_id))
        return tags

    @staticmethod
    def _upsert_best(candidates: Dict[str, Tag], tag: Tag) -> None:
        existing = candidates.get(tag.tag_id)
        if existing is None or tag.confidence > existing.confidence:
            candidates[tag.tag_id] = tag
