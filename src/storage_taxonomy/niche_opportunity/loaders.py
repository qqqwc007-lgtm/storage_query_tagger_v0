from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Generic, TypeVar

from .config import NicheOpportunityConfig, load_niche_opportunity_config


T = TypeVar("T")


class SourceSchemaError(ValueError):
    def __init__(
        self,
        source_name: str,
        path: Path,
        missing_columns: list[str],
        available_columns: list[str],
    ):
        self.source_name = source_name
        self.path = path
        self.missing_columns = missing_columns
        self.available_columns = available_columns
        super().__init__(
            f"{source_name} schema error in {path}: missing columns "
            f"{missing_columns}; available columns: {available_columns}"
        )


@dataclass(frozen=True)
class SourceMetadata:
    source_name: str
    path: Path
    row_count: int
    loaded_at: datetime
    latest_period: str
    freshness_status: str
    freshness_basis: str


@dataclass(frozen=True)
class LoadedTable(Generic[T]):
    rows: list[T]
    metadata: SourceMetadata


@dataclass(frozen=True)
class KeywordAsinFactRow:
    canonical_scenario_need: str
    search_term: str
    keyword_translation: str
    rank: int | None
    asin: str
    title: str
    main_image_url: str
    brand: str
    seller_name: str
    price: float | None
    units: int | None
    gmv: float | None
    asin_asp: float | None
    launch_date: date | None
    days_since_launch: int | None
    rating: float | None
    review_count: int | None
    is_new_asin: bool
    product_detail_status: str
    product_detail_raw_json: str
    keyword_top20_asin_list_json: str
    source_record_json: str


@dataclass(frozen=True)
class SearchVolumeHistoryRow:
    search_term: str
    month: str
    search_volume: int | None
    search_rank: int | None
    marketplace: str


@dataclass(frozen=True)
class SalesSummaryRow:
    dimension: str
    canonical_scenario_need: str
    search_term: str
    keyword_translation: str
    keyword_count: int | None
    asin_count: int | None
    deduped_asin_count: int | None
    new_asin_count: int | None
    overall_gmv: float | None
    overall_units: int | None
    overall_asp: float | None
    overall_avg_days_since_launch: float | None
    overall_avg_rating: float | None
    overall_avg_review_count: float | None
    overall_top_image_urls: tuple[str, ...]
    new_product_gmv: float | None
    new_product_units: int | None
    new_product_asp: float | None
    new_product_avg_days_since_launch: float | None
    new_product_avg_rating: float | None
    new_product_avg_review_count: float | None
    new_product_top_image_urls: tuple[str, ...]


KEYWORD_ASIN_FACT_COLUMNS = [
    "canonical_scenario_need",
    "kw",
    "kw中文翻译",
    "rank",
    "ASIN",
    "标题",
    "主图",
    "品牌",
    "卖家",
    "价格",
    "Units",
    "GMV",
    "ASIN_ASP",
    "上架日期",
    "上架天数",
    "星级",
    "评论数量",
    "2025-Q3起新品",
    "product_detail_status",
    "product_detail_raw_json",
    "keyword_top20_asin_list_json",
    "source_record_json",
]

SEARCH_VOLUME_HISTORY_COLUMNS = [
    "search_term",
    "month",
    "search_volume",
    "search_rank",
    "marketplace",
]

SALES_SUMMARY_COLUMNS = [
    "维度",
    "canonical_scenario_need",
    "kw",
    "kw中文翻译",
    "关键词数量",
    "ASIN数量",
    "去重ASIN数量",
    "新ASIN数量",
    "整体GMV",
    "整体Units",
    "整体ASP",
    "整体平均上架天数",
    "整体平均星级",
    "整体平均评论数量",
    "整体Top1 ASIN主图",
    "整体Top2 ASIN主图",
    "整体Top3 ASIN主图",
    "2025-Q3起新品GMV",
    "2025-Q3起新品Units",
    "2025-Q3起新品ASP",
    "2025-Q3起新品平均上架天数",
    "2025-Q3起新品平均星级",
    "2025-Q3起新品平均评论数量",
    "2025-Q3起新品Top1 ASIN主图",
    "2025-Q3起新品Top2 ASIN主图",
    "2025-Q3起新品Top3 ASIN主图",
]


def load_keyword_asin_facts(
    path: str | Path,
    config: NicheOpportunityConfig | None = None,
    today: date | None = None,
) -> LoadedTable[KeywordAsinFactRow]:
    config = config or load_niche_opportunity_config()
    csv_path = Path(path)
    raw_rows, fieldnames = _read_csv_rows(csv_path)
    _require_columns("keyword_asin_fact_v1", csv_path, fieldnames, KEYWORD_ASIN_FACT_COLUMNS)
    rows = [_keyword_asin_fact_row(row) for row in raw_rows]
    return LoadedTable(
        rows=rows,
        metadata=_file_metadata("keyword_asin_fact_v1", csv_path, len(rows), config, today),
    )


def load_search_volume_history(
    path: str | Path,
    config: NicheOpportunityConfig | None = None,
    today: date | None = None,
) -> LoadedTable[SearchVolumeHistoryRow]:
    config = config or load_niche_opportunity_config()
    csv_path = Path(path)
    raw_rows, fieldnames = _read_csv_rows(csv_path)
    _require_columns("keyword_search_volume_history", csv_path, fieldnames, SEARCH_VOLUME_HISTORY_COLUMNS)
    rows = [
        SearchVolumeHistoryRow(
            search_term=_clean(row.get("search_term")),
            month=_clean(row.get("month")),
            search_volume=_parse_int(row.get("search_volume")),
            search_rank=_parse_int(row.get("search_rank")),
            marketplace=_clean(row.get("marketplace")),
        )
        for row in raw_rows
    ]
    latest_period = _latest_month(row.month for row in rows)
    metadata = _period_metadata(
        source_name="keyword_search_volume_history",
        path=csv_path,
        row_count=len(rows),
        latest_period=latest_period,
        max_age_months=config.evidence.max_search_history_age_months,
        today=today,
    )
    return LoadedTable(rows=rows, metadata=metadata)


def load_sales_summary(
    path: str | Path,
    source_name: str = "sales_summary_v1",
    config: NicheOpportunityConfig | None = None,
    today: date | None = None,
) -> LoadedTable[SalesSummaryRow]:
    config = config or load_niche_opportunity_config()
    csv_path = Path(path)
    raw_rows, fieldnames = _read_csv_rows(csv_path)
    _require_columns(source_name, csv_path, fieldnames, SALES_SUMMARY_COLUMNS)
    rows = [_sales_summary_row(row) for row in raw_rows]
    return LoadedTable(
        rows=rows,
        metadata=_file_metadata(source_name, csv_path, len(rows), config, today),
    )


def _keyword_asin_fact_row(row: dict[str, str]) -> KeywordAsinFactRow:
    return KeywordAsinFactRow(
        canonical_scenario_need=_clean(row.get("canonical_scenario_need")),
        search_term=_clean(row.get("kw")),
        keyword_translation=_clean(row.get("kw中文翻译")),
        rank=_parse_int(row.get("rank")),
        asin=_clean(row.get("ASIN")),
        title=_clean(row.get("标题")),
        main_image_url=_clean(row.get("主图")),
        brand=_clean(row.get("品牌")),
        seller_name=_clean(row.get("卖家")),
        price=_parse_float(row.get("价格")),
        units=_parse_int(row.get("Units")),
        gmv=_parse_float(row.get("GMV")),
        asin_asp=_parse_float(row.get("ASIN_ASP")),
        launch_date=_parse_date(row.get("上架日期")),
        days_since_launch=_parse_int(row.get("上架天数")),
        rating=_parse_float(row.get("星级")),
        review_count=_parse_int(row.get("评论数量")),
        is_new_asin=_parse_bool(row.get("2025-Q3起新品")),
        product_detail_status=_clean(row.get("product_detail_status")),
        product_detail_raw_json=_clean(row.get("product_detail_raw_json")),
        keyword_top20_asin_list_json=_clean(row.get("keyword_top20_asin_list_json")),
        source_record_json=_clean(row.get("source_record_json")),
    )


def _sales_summary_row(row: dict[str, str]) -> SalesSummaryRow:
    return SalesSummaryRow(
        dimension=_clean(row.get("维度")),
        canonical_scenario_need=_clean(row.get("canonical_scenario_need")),
        search_term=_clean(row.get("kw")),
        keyword_translation=_clean(row.get("kw中文翻译")),
        keyword_count=_parse_int(row.get("关键词数量")),
        asin_count=_parse_int(row.get("ASIN数量")),
        deduped_asin_count=_parse_int(row.get("去重ASIN数量")),
        new_asin_count=_parse_int(row.get("新ASIN数量")),
        overall_gmv=_parse_float(row.get("整体GMV")),
        overall_units=_parse_int(row.get("整体Units")),
        overall_asp=_parse_float(row.get("整体ASP")),
        overall_avg_days_since_launch=_parse_float(row.get("整体平均上架天数")),
        overall_avg_rating=_parse_float(row.get("整体平均星级")),
        overall_avg_review_count=_parse_float(row.get("整体平均评论数量")),
        overall_top_image_urls=_non_empty_tuple(
            row.get("整体Top1 ASIN主图"),
            row.get("整体Top2 ASIN主图"),
            row.get("整体Top3 ASIN主图"),
        ),
        new_product_gmv=_parse_float(row.get("2025-Q3起新品GMV")),
        new_product_units=_parse_int(row.get("2025-Q3起新品Units")),
        new_product_asp=_parse_float(row.get("2025-Q3起新品ASP")),
        new_product_avg_days_since_launch=_parse_float(row.get("2025-Q3起新品平均上架天数")),
        new_product_avg_rating=_parse_float(row.get("2025-Q3起新品平均星级")),
        new_product_avg_review_count=_parse_float(row.get("2025-Q3起新品平均评论数量")),
        new_product_top_image_urls=_non_empty_tuple(
            row.get("2025-Q3起新品Top1 ASIN主图"),
            row.get("2025-Q3起新品Top2 ASIN主图"),
            row.get("2025-Q3起新品Top3 ASIN主图"),
        ),
    )


def _read_csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return rows, fieldnames


def _require_columns(source_name: str, path: Path, fieldnames: list[str], required: list[str]) -> None:
    missing = [column for column in required if column not in fieldnames]
    if missing:
        raise SourceSchemaError(source_name, path, missing, fieldnames)


def _file_metadata(
    source_name: str,
    path: Path,
    row_count: int,
    config: NicheOpportunityConfig,
    today: date | None,
) -> SourceMetadata:
    today = today or date.today()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
    age_days = (today - mtime).days
    freshness_status = "current" if age_days <= config.evidence.max_source_age_days else "stale"
    return SourceMetadata(
        source_name=source_name,
        path=path,
        row_count=row_count,
        loaded_at=datetime.now(timezone.utc),
        latest_period=mtime.isoformat(),
        freshness_status=freshness_status,
        freshness_basis=f"file_mtime_age_days={age_days}",
    )


def _period_metadata(
    source_name: str,
    path: Path,
    row_count: int,
    latest_period: str,
    max_age_months: int,
    today: date | None,
) -> SourceMetadata:
    today = today or date.today()
    if latest_period:
        age_months = _month_age(latest_period, today)
        freshness_status = "current" if age_months <= max_age_months else "stale"
        freshness_basis = f"latest_month_age_months={age_months}"
    else:
        freshness_status = "unknown"
        freshness_basis = "missing_month"
    return SourceMetadata(
        source_name=source_name,
        path=path,
        row_count=row_count,
        loaded_at=datetime.now(timezone.utc),
        latest_period=latest_period,
        freshness_status=freshness_status,
        freshness_basis=freshness_basis,
    )


def _latest_month(months: object) -> str:
    valid_months = sorted(month for month in months if re.fullmatch(r"\d{4}-\d{2}", str(month or "")))
    return valid_months[-1] if valid_months else ""


def _month_age(month: str, today: date) -> int:
    year_text, month_text = month.split("-", 1)
    return (today.year - int(year_text)) * 12 + today.month - int(month_text)


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _parse_float(value: object) -> float | None:
    text = _clean(value)
    if not text or text in {"-", "--"}:
        return None
    normalized = text.replace(",", "").replace("$", "").replace("%", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    return float(match.group(0))


def _parse_int(value: object) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _parse_bool(value: object) -> bool:
    text = _clean(value).lower()
    return text in {"1", "true", "t", "yes", "y", "是", "新品", "new"}


def _parse_date(value: object) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _non_empty_tuple(*values: object) -> tuple[str, ...]:
    return tuple(text for text in (_clean(value) for value in values) if text)
