from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .normalizer import normalize_text, word_boundary_pattern

PRODUCT_FORM_FIELD = "产品形态关键词"
SCENARIO_FIELD = "产品使用场景"
OBJECT_FIELD = "存储对象"
MATERIAL_FIELD = "产品材质"
SIZE_FIELD = "尺寸"
LOCATION_FIELD = "产品使用场地"
FUNCTION_FIELD = "产品功能"

ALL_FIELDS = [
    PRODUCT_FORM_FIELD,
    SCENARIO_FIELD,
    OBJECT_FIELD,
    MATERIAL_FIELD,
    SIZE_FIELD,
    LOCATION_FIELD,
    FUNCTION_FIELD,
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_ROOT = PROJECT_ROOT / "config"


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


class TaxonomyRegistry:
    def __init__(self, config_root: str | Path | None = None):
        self.config_root = Path(config_root) if config_root else DEFAULT_CONFIG_ROOT
        self.workflow_config = load_yaml(self.config_root / "workflow_config.yaml")
        self.rules = load_yaml(self.config_root / "rules" / "extraction_rules_v0.yaml")
        self.field_constraints = load_yaml(self.config_root / "rules" / "field_constraints_v0.yaml")
        self.thresholds = load_yaml(self.config_root / "rules" / "thresholds.yaml")
        self.canonical_values = load_json(self.config_root / "taxonomy" / "canonical_values_v0.json")
        self.alias_records = load_json(self.config_root / "taxonomy" / "aliases_v0.json")
        self.rollup_records = load_json(self.config_root / "taxonomy" / "rollups_v0.json")
        self.negative_rules = load_json(self.config_root / "taxonomy" / "negative_rules_v0.json")
        self.taxonomy_version = self.workflow_config.get("taxonomy_version", "taxonomy_v0")
        self.phrase_rewrites = self.rules.get("normalizer", {}).get("phrase_rewrites", {})

        self.values_by_axis: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for record in self.canonical_values:
            axis = record["axis"]
            value = record["canonical_value"]
            self.values_by_axis[axis][value] = record

        self.rollup_map: dict[str, dict[str, str]] = defaultdict(dict)
        for record in self.rollup_records:
            self.rollup_map[record["axis"]][record["child"]] = record["parent"]
        for record in self.canonical_values:
            parent = record.get("rollup_parent")
            if parent:
                self.rollup_map[record["axis"]][record["canonical_value"]] = parent

        self.alias_patterns: list[dict[str, Any]] = []
        for record in self.alias_records:
            axis = record["axis"]
            canonical_value = record["canonical_value"]
            alias = record["alias"]
            meta = self.values_by_axis.get(axis, {}).get(canonical_value, {})
            self.alias_patterns.append({
                "axis": axis,
                "canonical_value": canonical_value,
                "alias": alias,
                "pattern": word_boundary_pattern(alias),
                "priority": int(record.get("priority", meta.get("priority", 0))),
                "rollup_parent": self.rollup_map.get(axis, {}).get(canonical_value, ""),
                "status": meta.get("status", "active"),
                "alias_length": len(normalize_text(alias)),
            })
        self.alias_patterns.sort(key=lambda item: (item["alias_length"], item["priority"]), reverse=True)

    def normalize(self, text: str | None) -> str:
        return normalize_text(text, self.phrase_rewrites)

    def empty_fields(self) -> dict[str, Any]:
        return {
            PRODUCT_FORM_FIELD: [],
            SCENARIO_FIELD: "",
            OBJECT_FIELD: "",
            MATERIAL_FIELD: "",
            SIZE_FIELD: "",
            LOCATION_FIELD: "",
            FUNCTION_FIELD: "",
        }

    def iter_alias_matches(self, text: str, axis: str | None = None) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for item in self.alias_patterns:
            if axis and item["axis"] != axis:
                continue
            if item["status"] != "active":
                continue
            for match in item["pattern"].finditer(text):
                matches.append({
                    **item,
                    "start": match.start(),
                    "end": match.end(),
                })
        matches.sort(
            key=lambda item: (
                item["axis"],
                -item["priority"],
                -(item["end"] - item["start"]),
                item["canonical_value"],
            )
        )
        return matches

    def get_rollup_parent(self, axis: str, value: str) -> str:
        return self.rollup_map.get(axis, {}).get(value, "")

    def expand_with_rollups(self, axis: str, values: list[str] | set[str]) -> set[str]:
        expanded = set(values)
        frontier = list(values)
        while frontier:
            current = frontier.pop()
            parent = self.get_rollup_parent(axis, current)
            if parent and parent not in expanded:
                expanded.add(parent)
                frontier.append(parent)
        return expanded

    def rollup_overlap(self, axis: str, left: list[str] | set[str], right: list[str] | set[str]) -> set[str]:
        left_expanded = self.expand_with_rollups(axis, left)
        right_expanded = self.expand_with_rollups(axis, right)
        return left_expanded & right_expanded

    def best_scalar_match(self, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda item: (-item["priority"], -(item["end"] - item["start"]), item["canonical_value"]),
        )[0]
