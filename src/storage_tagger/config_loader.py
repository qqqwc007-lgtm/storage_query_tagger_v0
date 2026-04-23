from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


def load_yaml(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_default_configs(config_dir: str | Path | None = None) -> Dict[str, Any]:
    config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    return {
        "taxonomy": load_yaml(config_dir / "taxonomy_v0.yaml"),
        "rules": load_yaml(config_dir / "rules_v0.yaml"),
        "thresholds": load_yaml(config_dir / "thresholds.yaml"),
        "model_config": load_yaml(config_dir / "model_config.yaml"),
    }


def taxonomy_version(taxonomy: Dict[str, Any]) -> str:
    return taxonomy.get("taxonomy_version", "unknown")
