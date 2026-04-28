from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from .boundary import NicheAsinBridgeRow, NicheKeywordBridgeRow
from .config import NicheOpportunityConfig
from .loaders import SalesSummaryRow
from .raw_detail_parser import ProductAsinFactRow


@dataclass(frozen=True)
class EvidenceSignal:
    key: str
    state: str
    evidence_status: str
    value: str
    reason: str
    evidence: tuple[str, ...] = ()

    @property
    def is_support(self) -> bool:
        return self.state == "support"


@dataclass(frozen=True)
class NicheSignalSet:
    demand: EvidenceSignal
    asp: EvidenceSignal
    new_product: EvidenceSignal
    structure_upgrade: EvidenceSignal
    supply_chain: EvidenceSignal

    @property
    def market_signals(self) -> tuple[EvidenceSignal, ...]:
        return (self.demand, self.asp, self.new_product, self.structure_upgrade)

    @property
    def all_signals(self) -> tuple[EvidenceSignal, ...]:
        return (*self.market_signals, self.supply_chain)

    @property
    def market_support_count(self) -> int:
        return sum(1 for signal in self.market_signals if signal.is_support)


def build_niche_signals(
    keyword_bridge_rows: list[NicheKeywordBridgeRow],
    asin_bridge_rows: list[NicheAsinBridgeRow],
    product_facts: list[ProductAsinFactRow],
    sales_summary: SalesSummaryRow | None,
    config: NicheOpportunityConfig,
) -> NicheSignalSet:
    return NicheSignalSet(
        demand=compute_demand_signal(keyword_bridge_rows),
        asp=compute_asp_signal(sales_summary),
        new_product=compute_new_product_signal(asin_bridge_rows),
        structure_upgrade=compute_structure_upgrade_signal(product_facts),
        supply_chain=compute_supply_chain_signal(product_facts, config),
    )


def summarize_boundary_sales(
    niche_id: str,
    keyword_bridge_rows: list[NicheKeywordBridgeRow],
    asin_bridge_rows: list[NicheAsinBridgeRow],
) -> SalesSummaryRow:
    valid_rows = [row for row in asin_bridge_rows if row.asin and row.asin_validity_override != "invalid"]
    deduped_rows = _dedupe_asin_bridge_rows(valid_rows)
    new_rows = [row for row in deduped_rows if row.is_new_asin]
    included_keyword_count = sum(1 for row in keyword_bridge_rows if row.inclusion_status == "included")
    overall_gmv = _sum_float(row.gmv for row in deduped_rows)
    overall_units = _sum_int(row.units for row in deduped_rows)
    new_product_gmv = _sum_float(row.gmv for row in new_rows)
    new_product_units = _sum_int(row.units for row in new_rows)
    return SalesSummaryRow(
        dimension="niche_boundary",
        canonical_scenario_need="",
        search_term=niche_id,
        keyword_translation="",
        keyword_count=included_keyword_count,
        asin_count=len(valid_rows),
        deduped_asin_count=len(deduped_rows),
        new_asin_count=len(new_rows),
        overall_gmv=overall_gmv,
        overall_units=overall_units,
        overall_asp=_asp(overall_gmv, overall_units),
        overall_avg_days_since_launch=None,
        overall_avg_rating=_average(row.rating for row in deduped_rows),
        overall_avg_review_count=_average(row.review_count for row in deduped_rows),
        overall_top_image_urls=_top_image_urls(deduped_rows),
        new_product_gmv=new_product_gmv,
        new_product_units=new_product_units,
        new_product_asp=_asp(new_product_gmv, new_product_units),
        new_product_avg_days_since_launch=None,
        new_product_avg_rating=_average(row.rating for row in new_rows),
        new_product_avg_review_count=_average(row.review_count for row in new_rows),
        new_product_top_image_urls=_top_image_urls(new_rows),
    )


def compute_demand_signal(keyword_bridge_rows: list[NicheKeywordBridgeRow]) -> EvidenceSignal:
    included_rows = [row for row in keyword_bridge_rows if row.inclusion_status == "included"]
    slopes = [row.search_volume_24m_slope for row in included_rows if row.search_volume_24m_slope is not None]
    current_volume = sum(row.search_volume_current or 0 for row in included_rows)
    if not slopes:
        return EvidenceSignal(
            key="demand_trend",
            state="unknown",
            evidence_status="missing",
            value="missing_search_volume_slope",
            reason="No included keyword has enough search-volume history.",
        )
    average_slope = sum(slopes) / len(slopes)
    state = "support" if average_slope >= 0 else "warn"
    return EvidenceSignal(
        key="demand_trend",
        state=state,
        evidence_status="true",
        value=f"avg_slope={average_slope:.4f};current_volume={current_volume}",
        reason="Demand trend is not bad." if state == "support" else "Search volume trend is declining.",
        evidence=tuple(f"{row.search_term}:{row.search_volume_24m_slope}" for row in included_rows),
    )


def compute_asp_signal(sales_summary: SalesSummaryRow | None) -> EvidenceSignal:
    if (
        sales_summary is None
        or sales_summary.overall_asp is None
        or sales_summary.new_product_asp is None
    ):
        return EvidenceSignal(
            key="asp_trend",
            state="unknown",
            evidence_status="missing",
            value="missing_asp_proxy",
            reason="No ASP trend or new-vs-overall ASP proxy is available.",
        )
    state = "support" if sales_summary.new_product_asp >= sales_summary.overall_asp else "warn"
    return EvidenceSignal(
        key="asp_trend",
        state=state,
        evidence_status="proxy",
        value=(
            f"asp_trend_evidence_status=proxy_current_snapshot;"
            f"new_product_asp={sales_summary.new_product_asp};overall_asp={sales_summary.overall_asp}"
        ),
        reason="New-product ASP is at or above overall ASP." if state == "support" else "New-product ASP is below overall ASP.",
    )


def compute_new_product_signal(asin_bridge_rows: list[NicheAsinBridgeRow]) -> EvidenceSignal:
    valid_rows = [row for row in asin_bridge_rows if row.asin_validity_override != "invalid"]
    new_rows = [row for row in valid_rows if row.is_new_asin and ((row.units or 0) > 0 or (row.gmv or 0) > 0)]
    if not valid_rows:
        return EvidenceSignal(
            key="new_product_sales",
            state="unknown",
            evidence_status="missing",
            value="missing_valid_asin_rows",
            reason="No valid ASIN rows are available.",
        )
    if not new_rows:
        return EvidenceSignal(
            key="new_product_sales",
            state="warn",
            evidence_status="true",
            value="new_asin_sales_rows=0",
            reason="No new ASIN with sales was found in the confirmed boundary.",
        )
    repeated_asins = sorted({row.asin for row in new_rows if row.is_repeated_new_asin})
    return EvidenceSignal(
        key="new_product_sales",
        state="support",
        evidence_status="true",
        value=f"new_asin_sales_rows={len(new_rows)};repeated_new_asins={','.join(repeated_asins)}",
        reason="New ASINs have sales in the confirmed niche.",
        evidence=tuple(f"{row.asin}:{row.units or 0}" for row in new_rows[:10]),
    )


def compute_structure_upgrade_signal(product_facts: list[ProductAsinFactRow]) -> EvidenceSignal:
    evidence = extract_structure_upgrades(product_facts)
    parsed_count = sum(1 for fact in product_facts if fact.parse_status == "parsed")
    if evidence:
        return EvidenceSignal(
            key="structure_upgrade",
            state="support",
            evidence_status="proxy",
            value=" | ".join(evidence[:8]),
            reason="Top ASIN text shows structure or feature upgrades.",
            evidence=tuple(evidence),
        )
    if not product_facts or parsed_count == 0:
        return EvidenceSignal(
            key="structure_upgrade",
            state="unknown",
            evidence_status="missing",
            value="missing_product_detail_text",
            reason="No parsed product detail text is available for structure evidence.",
        )
    return EvidenceSignal(
        key="structure_upgrade",
        state="warn",
        evidence_status="true",
        value="no_structure_upgrade_terms_found",
        reason="Parsed Top20 product text did not show clear structure upgrade evidence.",
    )


def compute_supply_chain_signal(
    product_facts: list[ProductAsinFactRow],
    config: NicheOpportunityConfig,
) -> EvidenceSignal:
    matched_materials = extract_supply_chain_materials(product_facts)
    if not product_facts:
        return EvidenceSignal(
            key="supply_chain_match",
            state="unknown",
            evidence_status="missing",
            value="missing_product_facts",
            reason="No product facts are available for material matching.",
        )
    if not matched_materials:
        return EvidenceSignal(
            key="supply_chain_match",
            state="warn",
            evidence_status="true",
            value="no_company_material_match",
            reason="No material evidence matched fabric, bamboo/wood, steel frame, or plastic.",
        )
    priority = {material: index for index, material in enumerate(config.supply_chain.material_priority)}
    best = sorted(matched_materials, key=lambda material: priority.get(material, 999))[0]
    composite = len(matched_materials) > 1
    return EvidenceSignal(
        key="supply_chain_match",
        state="support",
        evidence_status="true",
        value=f"best_material={best};matched_materials={','.join(matched_materials)};composite={composite}",
        reason="Material evidence falls inside the company supply-chain capability circle.",
        evidence=tuple(matched_materials),
    )


def extract_structure_upgrades(product_facts: Iterable[ProductAsinFactRow]) -> list[str]:
    patterns = [
        r"adjustable\s+divider[s]?",
        r"reinforced\s+handle[s]?",
        r"double\s+zipper[s]?",
        r"clear\s+(?:cover|window|lid)",
        r"low[-\s]?profile",
        r"fold(?:able|ing)",
        r"stackable",
        r"wheels?",
        r"sturdy\s+(?:board|side|base|panel)",
        r"pp\s+(?:board|panel)",
        r"modular",
        r"\b\d+\s*pack\b",
        r"sliding",
        r"expandable",
    ]
    evidence: list[str] = []
    seen: set[str] = set()
    for fact in product_facts:
        text = " ".join(
            [
                fact.title,
                fact.description_text,
                fact.attributes_json,
                fact.material_raw,
                fact.dimension_raw,
            ]
        ).lower()
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                phrase = " ".join(match.group(0).split())
                if phrase not in seen:
                    seen.add(phrase)
                    evidence.append(phrase)
    return evidence


def extract_supply_chain_materials(product_facts: Iterable[ProductAsinFactRow]) -> tuple[str, ...]:
    material_patterns = {
        "fabric": [r"fabric", r"non[-\s]?woven", r"oxford", r"linen", r"cloth", r"canvas", r"polyester"],
        "bamboo_wood": [r"bamboo", r"\bwood(?:en)?\b", r"\bmdf\b"],
        "steel_frame": [r"steel", r"\bmetal\b", r"\biron\b"],
        "plastic": [r"plastic", r"\bpvc\b", r"\bpeva\b", r"\bpp\b", r"polypropylene", r"acrylic"],
    }
    matched: list[str] = []
    seen: set[str] = set()
    for fact in product_facts:
        text = " ".join(
            [
                fact.material_raw,
                fact.title,
                fact.description_text,
                _json_values_text(fact.attributes_json),
            ]
        ).lower()
        for material, patterns in material_patterns.items():
            if material in seen:
                continue
            if any(re.search(pattern, text) for pattern in patterns):
                seen.add(material)
                matched.append(material)
    return tuple(matched)


def _dedupe_asin_bridge_rows(rows: list[NicheAsinBridgeRow]) -> list[NicheAsinBridgeRow]:
    sorted_rows = sorted(rows, key=lambda row: (row.rank is None, row.rank or 9999, row.asin.upper()))
    deduped: dict[str, NicheAsinBridgeRow] = {}
    for row in sorted_rows:
        deduped.setdefault(row.asin.upper(), row)
    return list(deduped.values())


def _sum_float(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _sum_int(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _asp(gmv: float | None, units: int | None) -> float | None:
    if gmv is None or not units:
        return None
    return round(gmv / units, 2)


def _average(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)


def _top_image_urls(rows: list[NicheAsinBridgeRow]) -> tuple[str, ...]:
    urls: list[str] = []
    seen: set[str] = set()
    for row in rows:
        url = row.image_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) == 3:
            break
    return tuple(urls)


def _json_values_text(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, dict):
        return " ".join(str(item) for item in parsed.values())
    return value
