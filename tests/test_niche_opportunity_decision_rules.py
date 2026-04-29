from storage_taxonomy.niche_opportunity.config import load_niche_opportunity_config
from storage_taxonomy.niche_opportunity.decision_engine import decide_launch
from storage_taxonomy.niche_opportunity.signals import EvidenceSignal, NicheSignalSet


def _signal(key: str, state: str, evidence_status: str = "true") -> EvidenceSignal:
    return EvidenceSignal(
        key=key,
        state=state,
        evidence_status=evidence_status,
        value=f"{key}:{state}",
        reason=f"{key} {state}",
    )


def _signals(
    demand: EvidenceSignal,
    asp: EvidenceSignal,
    new_product: EvidenceSignal,
    structure: EvidenceSignal,
    supply: EvidenceSignal,
) -> NicheSignalSet:
    return NicheSignalSet(
        demand=demand,
        asp=asp,
        new_product=new_product,
        structure_upgrade=structure,
        supply_chain=supply,
    )


def test_decision_recommends_when_two_market_signals_support() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "support"),
            _signal("asp", "support"),
            _signal("new", "warn"),
            _signal("structure", "warn"),
            _signal("supply", "support"),
        ),
        config,
    )

    assert result.conclusion == "推荐立项"
    assert result.market_signal_count == 2
    assert result.supply_chain_match is True
    assert result.hard_veto is False


def test_decision_caps_recommendation_when_all_positive_evidence_is_proxy() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "support", "proxy"),
            _signal("asp", "support", "proxy"),
            _signal("new", "unknown", "missing"),
            _signal("structure", "warn", "true"),
            _signal("supply", "unknown", "missing"),
        ),
        config,
    )

    assert result.conclusion == "建议深挖"
    assert result.capped_by_proxy is True


def test_decision_deep_dives_when_one_market_signal_and_supply_chain_match() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "support"),
            _signal("asp", "warn"),
            _signal("new", "unknown", "missing"),
            _signal("structure", "warn"),
            _signal("supply", "support"),
        ),
        config,
    )

    assert result.conclusion == "建议深挖"
    assert result.market_signal_count == 1


def test_decision_temporarily_observes_when_only_supply_chain_matches() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "warn"),
            _signal("asp", "unknown", "missing"),
            _signal("new", "warn"),
            _signal("structure", "warn"),
            _signal("supply", "support"),
        ),
        config,
    )

    assert result.conclusion == "暂缓观察"


def test_decision_hard_veto_when_demand_and_asp_both_warn() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "warn"),
            _signal("asp", "warn", "proxy"),
            _signal("new", "support"),
            _signal("structure", "support"),
            _signal("supply", "support"),
        ),
        config,
    )

    assert result.conclusion == "风险/否决"
    assert result.hard_veto is True


def test_decision_all_warn_is_risk() -> None:
    config = load_niche_opportunity_config()
    result = decide_launch(
        _signals(
            _signal("demand", "warn"),
            _signal("asp", "warn", "proxy"),
            _signal("new", "warn"),
            _signal("structure", "warn"),
            _signal("supply", "warn"),
        ),
        config,
    )

    assert result.conclusion == "风险/否决"
