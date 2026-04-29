from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "niche_opportunity_v1.yaml"


class ConfigError(ValueError):
    """Raised when the niche opportunity config is missing required keys."""


@dataclass(frozen=True)
class CostConfig:
    target_gross_margin_rate: float
    referral_fee_rate: float
    storage_return_loss_reserve_rate: float
    exchange_rate: float
    first_leg_rmb_per_kg: float
    chargeable_weight_divisor_cm3_per_kg: float


@dataclass(frozen=True)
class EvidenceConfig:
    max_source_age_days: int
    max_search_history_age_months: int
    stale_policy: str


@dataclass(frozen=True)
class SupplyChainConfig:
    material_priority: tuple[str, ...]
    composite_material_bonus: float
    lead_time_days: dict[str, int]


@dataclass(frozen=True)
class DecisionThresholds:
    recommend_market_signal_min: int
    deep_dive_market_signal_count: int
    big_volume_monthly_search_volume: int
    proxy_only_conclusion_cap: str
    unresolved_non_fit_conclusion: str


@dataclass(frozen=True)
class NicheOpportunityConfig:
    workflow_version: str
    cost: CostConfig
    evidence: EvidenceConfig
    supply_chain: SupplyChainConfig
    decision_thresholds: DecisionThresholds
    source_paths: dict[str, Path]
    config_path: Path


def load_niche_opportunity_config(path: str | Path | None = None) -> NicheOpportunityConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = _load_yaml(config_path)

    workflow_version = _required_str(data, "workflow_version", config_path)
    cost_data = _required_section(data, "cost", config_path)
    evidence_data = _required_section(data, "evidence", config_path)
    supply_chain_data = _required_section(data, "supply_chain", config_path)
    threshold_data = _required_section(data, "decision_thresholds", config_path)
    source_paths_data = _required_section(data, "source_paths", config_path)

    cost = CostConfig(
        target_gross_margin_rate=_required_float(cost_data, "cost.target_gross_margin_rate", config_path),
        referral_fee_rate=_required_float(cost_data, "cost.referral_fee_rate", config_path),
        storage_return_loss_reserve_rate=_required_float(
            cost_data,
            "cost.storage_return_loss_reserve_rate",
            config_path,
        ),
        exchange_rate=_required_float(cost_data, "cost.exchange_rate", config_path),
        first_leg_rmb_per_kg=_required_float(cost_data, "cost.first_leg_rmb_per_kg", config_path),
        chargeable_weight_divisor_cm3_per_kg=_required_float(
            cost_data,
            "cost.chargeable_weight_divisor_cm3_per_kg",
            config_path,
        ),
    )

    evidence = EvidenceConfig(
        max_source_age_days=_required_int(evidence_data, "evidence.max_source_age_days", config_path),
        max_search_history_age_months=_required_int(
            evidence_data,
            "evidence.max_search_history_age_months",
            config_path,
        ),
        stale_policy=_required_str(evidence_data, "evidence.stale_policy", config_path),
    )

    material_priority = tuple(_required_list(supply_chain_data, "supply_chain.material_priority", config_path))
    lead_time_days = _required_int_map(supply_chain_data, "supply_chain.lead_time_days", config_path)
    missing_lead_times = [material for material in material_priority if material not in lead_time_days]
    if missing_lead_times:
        raise ConfigError(
            f"{config_path}: supply_chain.lead_time_days missing entries for: "
            f"{', '.join(missing_lead_times)}"
        )
    supply_chain = SupplyChainConfig(
        material_priority=material_priority,
        composite_material_bonus=_required_float(
            supply_chain_data,
            "supply_chain.composite_material_bonus",
            config_path,
        ),
        lead_time_days=lead_time_days,
    )

    decision_thresholds = DecisionThresholds(
        recommend_market_signal_min=_required_int(
            threshold_data,
            "decision_thresholds.recommend_market_signal_min",
            config_path,
        ),
        deep_dive_market_signal_count=_required_int(
            threshold_data,
            "decision_thresholds.deep_dive_market_signal_count",
            config_path,
        ),
        big_volume_monthly_search_volume=_required_int(
            threshold_data,
            "decision_thresholds.big_volume_monthly_search_volume",
            config_path,
        ),
        proxy_only_conclusion_cap=_required_str(
            threshold_data,
            "decision_thresholds.proxy_only_conclusion_cap",
            config_path,
        ),
        unresolved_non_fit_conclusion=_required_str(
            threshold_data,
            "decision_thresholds.unresolved_non_fit_conclusion",
            config_path,
        ),
    )

    source_paths = {
        str(key): _resolve_config_path(config_path, _required_str(source_paths_data, f"source_paths.{key}", config_path))
        for key in sorted(source_paths_data)
    }

    return NicheOpportunityConfig(
        workflow_version=workflow_version,
        cost=cost,
        evidence=evidence,
        supply_chain=supply_chain,
        decision_thresholds=decision_thresholds,
        source_paths=source_paths,
        config_path=config_path,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected top-level YAML mapping")
    return data


def _resolve_config_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    base_dir = config_path.parent.parent if config_path.parent.name == "config" else config_path.parent
    return (base_dir / path).resolve()


def _lookup(mapping: dict[str, Any], dotted_key: str, path: Path) -> Any:
    key = dotted_key.split(".")[-1]
    if key not in mapping or mapping[key] is None:
        raise ConfigError(f"{path}: missing required config key `{dotted_key}`")
    return mapping[key]


def _required_section(mapping: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = _lookup(mapping, key, path)
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: `{key}` must be a mapping")
    return value


def _required_str(mapping: dict[str, Any], dotted_key: str, path: Path) -> str:
    value = _lookup(mapping, dotted_key, path)
    text = str(value).strip()
    if not text:
        raise ConfigError(f"{path}: `{dotted_key}` must not be empty")
    return text


def _required_float(mapping: dict[str, Any], dotted_key: str, path: Path) -> float:
    value = _lookup(mapping, dotted_key, path)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: `{dotted_key}` must be numeric") from exc


def _required_int(mapping: dict[str, Any], dotted_key: str, path: Path) -> int:
    value = _required_float(mapping, dotted_key, path)
    if int(value) != value:
        raise ConfigError(f"{path}: `{dotted_key}` must be an integer")
    return int(value)


def _required_list(mapping: dict[str, Any], dotted_key: str, path: Path) -> list[str]:
    value = _lookup(mapping, dotted_key, path)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{path}: `{dotted_key}` must be a non-empty list")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise ConfigError(f"{path}: `{dotted_key}` must contain non-empty values")
    return items


def _required_int_map(mapping: dict[str, Any], dotted_key: str, path: Path) -> dict[str, int]:
    value = _lookup(mapping, dotted_key, path)
    if not isinstance(value, dict) or not value:
        raise ConfigError(f"{path}: `{dotted_key}` must be a non-empty mapping")
    result: dict[str, int] = {}
    for key, raw_value in value.items():
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{path}: `{dotted_key}.{key}` must be numeric") from exc
        if int(numeric_value) != numeric_value:
            raise ConfigError(f"{path}: `{dotted_key}.{key}` must be an integer")
        result[str(key).strip()] = int(numeric_value)
    return result
