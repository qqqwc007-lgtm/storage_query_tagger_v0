from __future__ import annotations

from dataclasses import dataclass

from .config import NicheOpportunityConfig
from .signals import EvidenceSignal, NicheSignalSet


@dataclass(frozen=True)
class DecisionResult:
    conclusion: str
    market_signal_count: int
    supply_chain_match: bool
    hard_veto: bool
    capped_by_proxy: bool
    reason: str
    signals: NicheSignalSet


def decide_launch(
    signals: NicheSignalSet,
    config: NicheOpportunityConfig,
    human_override_reason: str = "",
) -> DecisionResult:
    hard_veto = signals.demand.state == "warn" and signals.asp.state == "warn"
    market_signal_count = signals.market_support_count
    supply_chain_match = signals.supply_chain.is_support
    capped_by_proxy = False

    if hard_veto:
        conclusion = "风险/否决"
        reason = "需求趋势和 ASP 代理信号同时转弱。"
    elif market_signal_count >= config.decision_thresholds.recommend_market_signal_min:
        conclusion = "推荐立项"
        reason = f"{market_signal_count} 个市场/产品信号支持。"
    elif (
        market_signal_count == config.decision_thresholds.deep_dive_market_signal_count
        and supply_chain_match
    ):
        conclusion = "建议深挖"
        reason = "1 个市场/产品信号支持，且供应链材料匹配。"
    elif market_signal_count == 0 and supply_chain_match:
        conclusion = "暂缓观察"
        reason = "市场/产品信号不足，但供应链材料匹配。"
    elif _all_business_signals_warn(signals):
        conclusion = "风险/否决"
        reason = "5 个市场/供应链信号均不支持。"
    elif market_signal_count == config.decision_thresholds.deep_dive_market_signal_count:
        conclusion = config.decision_thresholds.unresolved_non_fit_conclusion
        reason = "1 个市场/产品信号支持，但非能力圈或供应链待验证。"
    else:
        conclusion = "暂缓观察"
        reason = "证据不足或信号混合，先观察。"

    if (
        conclusion == "推荐立项"
        and not human_override_reason
        and _positive_evidence_is_proxy_only(signals.all_signals)
    ):
        conclusion = config.decision_thresholds.proxy_only_conclusion_cap
        capped_by_proxy = True
        reason = "所有正向证据都是代理信号，系统结论上限为建议深挖。"

    return DecisionResult(
        conclusion=conclusion,
        market_signal_count=market_signal_count,
        supply_chain_match=supply_chain_match,
        hard_veto=hard_veto,
        capped_by_proxy=capped_by_proxy,
        reason=reason,
        signals=signals,
    )


def _positive_evidence_is_proxy_only(signals: tuple[EvidenceSignal, ...]) -> bool:
    positive = [signal for signal in signals if signal.is_support]
    return bool(positive) and all(signal.evidence_status == "proxy" for signal in positive)


def _all_business_signals_warn(signals: NicheSignalSet) -> bool:
    return all(signal.state == "warn" for signal in signals.all_signals)
