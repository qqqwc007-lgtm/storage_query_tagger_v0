from pathlib import Path

import pytest

from storage_taxonomy.niche_opportunity.config import (
    ConfigError,
    load_niche_opportunity_config,
)


def test_load_default_niche_opportunity_config() -> None:
    config = load_niche_opportunity_config()

    assert config.workflow_version == "niche_opportunity_v1.0"
    assert config.cost.target_gross_margin_rate == 0.30
    assert config.cost.referral_fee_rate == 0.15
    assert config.cost.first_leg_rmb_per_kg == 8.0
    assert config.supply_chain.material_priority == (
        "fabric",
        "bamboo_wood",
        "steel_frame",
        "plastic",
    )
    assert config.supply_chain.lead_time_days["fabric"] == 30
    assert config.supply_chain.lead_time_days["plastic"] == 60
    assert config.decision_thresholds.big_volume_monthly_search_volume == 300000
    assert config.source_paths["keyword_asin_fact"].name == "keyword_asin_fact_v1.csv"


def test_config_missing_required_key_raises_actionable_error(tmp_path: Path) -> None:
    config_path = tmp_path / "niche_opportunity_v1.yaml"
    config_path.write_text(
        """
workflow_version: niche_opportunity_v1.0
cost:
  target_gross_margin_rate: 0.30
  referral_fee_rate: 0.15
  storage_return_loss_reserve_rate: 0.04
  first_leg_rmb_per_kg: 8.0
  chargeable_weight_divisor_cm3_per_kg: 6000.0
evidence:
  max_source_age_days: 45
  max_search_history_age_months: 2
  stale_policy: warn
supply_chain:
  material_priority: [fabric]
  composite_material_bonus: 1.0
  lead_time_days:
    fabric: 30
decision_thresholds:
  recommend_market_signal_min: 2
  deep_dive_market_signal_count: 1
  big_volume_monthly_search_volume: 300000
  proxy_only_conclusion_cap: 建议深挖
  unresolved_non_fit_conclusion: 暂缓观察
source_paths:
  keyword_asin_fact: outputs/keyword_asin_fact_v1.csv
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="cost.exchange_rate"):
        load_niche_opportunity_config(config_path)


def test_config_requires_lead_time_for_each_material(tmp_path: Path) -> None:
    config_path = tmp_path / "niche_opportunity_v1.yaml"
    config_path.write_text(
        """
workflow_version: niche_opportunity_v1.0
cost:
  target_gross_margin_rate: 0.30
  referral_fee_rate: 0.15
  storage_return_loss_reserve_rate: 0.04
  exchange_rate: 7.2
  first_leg_rmb_per_kg: 8.0
  chargeable_weight_divisor_cm3_per_kg: 6000.0
evidence:
  max_source_age_days: 45
  max_search_history_age_months: 2
  stale_policy: warn
supply_chain:
  material_priority: [fabric, plastic]
  composite_material_bonus: 1.0
  lead_time_days:
    fabric: 30
decision_thresholds:
  recommend_market_signal_min: 2
  deep_dive_market_signal_count: 1
  big_volume_monthly_search_volume: 300000
  proxy_only_conclusion_cap: 建议深挖
  unresolved_non_fit_conclusion: 暂缓观察
source_paths:
  keyword_asin_fact: outputs/keyword_asin_fact_v1.csv
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="plastic"):
        load_niche_opportunity_config(config_path)
