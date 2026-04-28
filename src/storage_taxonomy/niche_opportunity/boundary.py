from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .loaders import KeywordAsinFactRow, SearchVolumeHistoryRow, SourceSchemaError


BOUNDARY_COLUMNS = [
    "niche_id",
    "boundary_item_type",
    "boundary_item_value",
    "inclusion_status",
    "system_reason",
    "override_reason",
    "reviewer",
    "reviewed_at",
]


@dataclass(frozen=True)
class ConfirmedBoundaryRow:
    niche_id: str
    boundary_item_type: str
    boundary_item_value: str
    inclusion_status: str
    system_reason: str
    override_reason: str
    reviewer: str
    reviewed_at: str


@dataclass(frozen=True)
class NicheKeywordBridgeRow:
    niche_id: str
    search_term: str
    kw_chinese_translation: str
    search_volume_current: int | None
    search_volume_24m_slope: float | None
    search_rank_current: int | None
    seasonality_flag: str
    taxonomy_scene: str
    taxonomy_need: str
    taxonomy_form: str
    inclusion_status: str
    inclusion_reason: str
    override_status: str
    override_reason: str


@dataclass(frozen=True)
class NicheAsinBridgeRow:
    niche_id: str
    search_term: str
    asin: str
    rank: int | None
    is_new_asin: bool
    is_repeated_new_asin: bool
    title: str
    image_url: str
    price: float | None
    units: int | None
    gmv: float | None
    asin_asp: float | None
    launch_date: str
    rating: float | None
    review_count: int | None
    product_detail_raw_json: str
    asin_validity_system: str
    asin_validity_override: str
    asin_validity_reason: str


@dataclass(frozen=True)
class NicheBoundaryResult:
    niche_id: str
    keyword_bridge_rows: list[NicheKeywordBridgeRow]
    asin_bridge_rows: list[NicheAsinBridgeRow]
    valid_keyword_asin_rows: list[KeywordAsinFactRow]
    product_asins: tuple[str, ...]
    included_keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...]
    invalid_asins: tuple[str, ...]


def slugify_niche_id(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unnamed_niche"


def seed_confirmed_boundary(
    niche_id: str,
    keywords: list[str],
    reviewer: str = "",
    reviewed_at: str = "",
    system_reason: str = "seed_keyword",
) -> list[ConfirmedBoundaryRow]:
    rows: list[ConfirmedBoundaryRow] = []
    seen: set[str] = set()
    for keyword in keywords:
        search_term = str(keyword or "").strip()
        if not search_term or search_term in seen:
            continue
        seen.add(search_term)
        rows.append(
            ConfirmedBoundaryRow(
                niche_id=niche_id,
                boundary_item_type="keyword",
                boundary_item_value=search_term,
                inclusion_status="included",
                system_reason=system_reason,
                override_reason="",
                reviewer=reviewer,
                reviewed_at=reviewed_at,
            )
        )
    return rows


def load_confirmed_boundary(path: str | Path) -> list[ConfirmedBoundaryRow]:
    boundary_path = Path(path)
    with boundary_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        missing = [column for column in BOUNDARY_COLUMNS if column not in fieldnames]
        if missing:
            raise SourceSchemaError("confirmed_niche_boundary_v1", boundary_path, missing, fieldnames)
        return [_boundary_row(row) for row in reader]


def resolve_niche_boundary(
    niche_id: str,
    boundary_rows: list[ConfirmedBoundaryRow],
    keyword_asin_rows: list[KeywordAsinFactRow],
    search_volume_rows: list[SearchVolumeHistoryRow] | None = None,
) -> NicheBoundaryResult:
    scoped_rows = [row for row in boundary_rows if row.niche_id == niche_id]
    keyword_rows = [row for row in scoped_rows if row.boundary_item_type == "keyword"]
    asin_rows = [row for row in scoped_rows if row.boundary_item_type == "asin"]
    included_keywords = tuple(
        row.boundary_item_value
        for row in keyword_rows
        if row.inclusion_status == "included" and row.boundary_item_value
    )
    excluded_keywords = tuple(
        row.boundary_item_value
        for row in keyword_rows
        if row.inclusion_status == "excluded" and row.boundary_item_value
    )
    invalid_asins = tuple(
        row.boundary_item_value.upper()
        for row in asin_rows
        if row.inclusion_status == "invalid" and row.boundary_item_value
    )
    invalid_reason_by_asin = {
        row.boundary_item_value.upper(): row.override_reason or row.system_reason
        for row in asin_rows
        if row.inclusion_status == "invalid"
    }
    stats_by_keyword = _search_stats_by_keyword(search_volume_rows or [])
    translation_by_keyword = _translation_by_keyword(keyword_asin_rows)

    keyword_bridge_rows = [
        _keyword_bridge_row(
            niche_id=niche_id,
            boundary_row=row,
            translation=translation_by_keyword.get(row.boundary_item_value, ""),
            stats=stats_by_keyword.get(row.boundary_item_value),
        )
        for row in sorted(keyword_rows, key=lambda item: (item.inclusion_status, item.boundary_item_value))
    ]

    included_set = set(included_keywords)
    excluded_set = set(excluded_keywords)
    invalid_set = set(invalid_asins)
    candidate_rows = [
        row
        for row in keyword_asin_rows
        if row.search_term in included_set and row.search_term not in excluded_set
    ]
    new_asin_keyword_counts = _new_asin_keyword_counts(candidate_rows)
    asin_bridge_rows = [
        _asin_bridge_row(
            niche_id=niche_id,
            source_row=row,
            invalid_set=invalid_set,
            invalid_reason_by_asin=invalid_reason_by_asin,
            repeated_new_asin=new_asin_keyword_counts.get(row.asin.upper(), 0) > 1,
        )
        for row in candidate_rows
    ]
    valid_keyword_asin_rows = [
        row for row in candidate_rows if row.asin and row.asin.upper() not in invalid_set
    ]
    product_asins = tuple(dict.fromkeys(row.asin for row in valid_keyword_asin_rows if row.asin))

    return NicheBoundaryResult(
        niche_id=niche_id,
        keyword_bridge_rows=keyword_bridge_rows,
        asin_bridge_rows=asin_bridge_rows,
        valid_keyword_asin_rows=valid_keyword_asin_rows,
        product_asins=product_asins,
        included_keywords=included_keywords,
        excluded_keywords=excluded_keywords,
        invalid_asins=invalid_asins,
    )


def _boundary_row(row: dict[str, str]) -> ConfirmedBoundaryRow:
    return ConfirmedBoundaryRow(
        niche_id=_clean(row.get("niche_id")),
        boundary_item_type=_clean(row.get("boundary_item_type")),
        boundary_item_value=_clean(row.get("boundary_item_value")),
        inclusion_status=_clean(row.get("inclusion_status")),
        system_reason=_clean(row.get("system_reason")),
        override_reason=_clean(row.get("override_reason")),
        reviewer=_clean(row.get("reviewer")),
        reviewed_at=_clean(row.get("reviewed_at")),
    )


def _keyword_bridge_row(
    niche_id: str,
    boundary_row: ConfirmedBoundaryRow,
    translation: str,
    stats: dict[str, int | float | None] | None,
) -> NicheKeywordBridgeRow:
    stats = stats or {}
    override_status = boundary_row.inclusion_status if boundary_row.override_reason else ""
    return NicheKeywordBridgeRow(
        niche_id=niche_id,
        search_term=boundary_row.boundary_item_value,
        kw_chinese_translation=translation,
        search_volume_current=_optional_int(stats.get("search_volume_current")),
        search_volume_24m_slope=_optional_float(stats.get("search_volume_24m_slope")),
        search_rank_current=_optional_int(stats.get("search_rank_current")),
        seasonality_flag="not_evaluated",
        taxonomy_scene="",
        taxonomy_need="",
        taxonomy_form="",
        inclusion_status=boundary_row.inclusion_status,
        inclusion_reason=boundary_row.system_reason,
        override_status=override_status,
        override_reason=boundary_row.override_reason,
    )


def _asin_bridge_row(
    niche_id: str,
    source_row: KeywordAsinFactRow,
    invalid_set: set[str],
    invalid_reason_by_asin: dict[str, str],
    repeated_new_asin: bool,
) -> NicheAsinBridgeRow:
    asin = source_row.asin.upper()
    is_invalid = asin in invalid_set
    return NicheAsinBridgeRow(
        niche_id=niche_id,
        search_term=source_row.search_term,
        asin=source_row.asin,
        rank=source_row.rank,
        is_new_asin=source_row.is_new_asin,
        is_repeated_new_asin=source_row.is_new_asin and repeated_new_asin,
        title=source_row.title,
        image_url=source_row.main_image_url,
        price=source_row.price,
        units=source_row.units,
        gmv=source_row.gmv,
        asin_asp=source_row.asin_asp,
        launch_date=source_row.launch_date.isoformat() if source_row.launch_date else "",
        rating=source_row.rating,
        review_count=source_row.review_count,
        product_detail_raw_json=source_row.product_detail_raw_json,
        asin_validity_system="valid",
        asin_validity_override="invalid" if is_invalid else "",
        asin_validity_reason=invalid_reason_by_asin.get(asin, ""),
    )


def _search_stats_by_keyword(rows: list[SearchVolumeHistoryRow]) -> dict[str, dict[str, int | float | None]]:
    grouped: dict[str, list[SearchVolumeHistoryRow]] = {}
    for row in rows:
        grouped.setdefault(row.search_term, []).append(row)

    result: dict[str, dict[str, int | float | None]] = {}
    for search_term, term_rows in grouped.items():
        ordered = sorted(term_rows, key=lambda item: item.month)
        latest = ordered[-1]
        volumes = [row.search_volume for row in ordered if row.search_volume is not None]
        slope = None
        if len(volumes) >= 2:
            slope = round((volumes[-1] - volumes[0]) / (len(volumes) - 1), 4)
        result[search_term] = {
            "search_volume_current": latest.search_volume,
            "search_rank_current": latest.search_rank,
            "search_volume_24m_slope": slope,
        }
    return result


def _translation_by_keyword(rows: list[KeywordAsinFactRow]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        if row.search_term and row.keyword_translation and row.search_term not in result:
            result[row.search_term] = row.keyword_translation
    return result


def _new_asin_keyword_counts(rows: list[KeywordAsinFactRow]) -> dict[str, int]:
    keyword_sets: dict[str, set[str]] = {}
    for row in rows:
        if row.is_new_asin and row.asin:
            keyword_sets.setdefault(row.asin.upper(), set()).add(row.search_term)
    return {asin: len(search_terms) for asin, search_terms in keyword_sets.items()}


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text
