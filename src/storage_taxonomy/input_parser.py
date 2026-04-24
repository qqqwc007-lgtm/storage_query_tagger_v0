from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable

RAW_COLUMN_ALIASES = {
    "search_term": {"搜索词", "Search Query", "Search Term", "Search term", "search_term"},
    "search_frequency_rank": {
        "搜索频率排名",
        "Search Frequency Rank",
        "Search frequency rank",
        "search_frequency_rank",
    },
    "report_date": {"报告日期", "Report Date", "Date", "date", "report_date"},
    "reporting_period": {"报告周期", "Reporting Period", "Reporting period", "reporting_period"},
}

REQUIRED_RAW_COLUMNS = {"search_term", "search_frequency_rank"}

TOP_ASIN_PATTERNS = [
    (re.compile(r"点击量最高的商品 #(\d+)：ASIN"), "top_asin_{rank}"),
    (re.compile(r"点击量最高的商品 #(\d+)：商品名称"), "top_title_{rank}"),
    (re.compile(r"点击量最高的商品 #(\d+)：点击份额"), "top_click_share_{rank}"),
    (re.compile(r"点击量最高的商品 #(\d+)：转化份额"), "top_conversion_share_{rank}"),
    (re.compile(r"Top Clicked Product #(\d+): ASIN", re.IGNORECASE), "top_asin_{rank}"),
    (re.compile(r"Top Clicked Product #(\d+): Product Title", re.IGNORECASE), "top_title_{rank}"),
    (re.compile(r"Top Clicked Product #(\d+): Click Share", re.IGNORECASE), "top_click_share_{rank}"),
    (
        re.compile(r"Top Clicked Product #(\d+): Conversion Share", re.IGNORECASE),
        "top_conversion_share_{rank}",
    ),
]


def _detect_marketplace(path: str | Path) -> str:
    match = re.match(r"([A-Z]{2})_", Path(path).name)
    return match.group(1) if match else ""


def _canonical_column_name(column: str) -> str:
    text = str(column).strip()
    for canonical, aliases in RAW_COLUMN_ALIASES.items():
        if text in aliases:
            return canonical
    for pattern, template in TOP_ASIN_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return template.format(rank=match.group(1))
    return text


def canonicalize_columns(columns: list[str]) -> list[str]:
    return [_canonical_column_name(col) for col in columns]


def validate_raw_export_columns(columns: list[str]) -> None:
    canonical_columns = canonicalize_columns(columns)
    missing = REQUIRED_RAW_COLUMNS - set(canonical_columns)
    if missing:
        raise ValueError(
            f"Raw Amazon export missing required columns: {sorted(missing)}. "
            f"Available columns: {columns}"
        )


def _looks_like_header(row: list[str]) -> bool:
    canonical_columns = set(canonicalize_columns(row))
    has_top_asin = any(col.startswith("top_asin_") for col in canonical_columns)
    return "search_term" in canonical_columns and ("search_frequency_rank" in canonical_columns or has_top_asin)


def _read_header(path: str | Path) -> tuple[list[str], list[str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            first_row = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Raw Amazon export is empty: {path}") from exc
        if _looks_like_header(first_row):
            meta: list[str] = []
            header = first_row
        else:
            meta = first_row
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError(f"Raw Amazon export missing header row: {path}") from exc
        validate_raw_export_columns(header)
    header = canonicalize_columns(header)
    return meta, header


def iter_source_rows(path: str | Path) -> Iterable[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            first_row = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Raw Amazon export is empty: {path}") from exc
        if _looks_like_header(first_row):
            header = first_row
        else:
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError(f"Raw Amazon export missing header row: {path}") from exc
        validate_raw_export_columns(header)
        header = canonicalize_columns(header)
        for row in reader:
            if not row:
                continue
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            yield dict(zip(header, row))


def parse_search_frequency_rank(value: object) -> int | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        rank = int(float(text))
    except ValueError:
        return None
    return rank if rank > 0 else None


def prepare_local_inputs(
    raw_csv: str | Path,
    keyword_output: str | Path,
    top_asin_output: str | Path,
    max_search_frequency_rank: int | None = None,
) -> dict[str, int]:
    raw_csv = Path(raw_csv)
    keyword_output = Path(keyword_output)
    top_asin_output = Path(top_asin_output)
    keyword_output.parent.mkdir(parents=True, exist_ok=True)
    top_asin_output.parent.mkdir(parents=True, exist_ok=True)

    _, header = _read_header(raw_csv)
    marketplace = _detect_marketplace(raw_csv)
    asin_slots = []
    for col in header:
        asin_match = re.match(r"top_asin_(\d+)", col)
        if asin_match:
            rank = int(asin_match.group(1))
            asin_slots.append(rank)
    asin_slots = sorted(set(asin_slots))

    kw_columns = [
        "search_term",
        "search_frequency_rank",
        "search_volume",
        "date",
        "report_date",
        "reporting_period",
        "marketplace",
    ]
    st_columns = [
        "search_term",
        "asin",
        "title",
        "asin_rank",
        "click_share",
        "conversion_share",
        "date",
        "report_date",
        "reporting_period",
        "marketplace",
    ]

    keyword_count = 0
    title_count = 0

    with keyword_output.open("w", encoding="utf-8", newline="") as kw_f, top_asin_output.open(
        "w", encoding="utf-8", newline=""
    ) as st_f:
        kw_writer = csv.DictWriter(kw_f, fieldnames=kw_columns)
        st_writer = csv.DictWriter(st_f, fieldnames=st_columns)
        kw_writer.writeheader()
        st_writer.writeheader()

        for row in iter_source_rows(raw_csv):
            search_term = str(row.get("search_term", "")).strip()
            if not search_term:
                continue
            search_frequency_rank = str(row.get("search_frequency_rank", "")).strip()
            if max_search_frequency_rank is not None:
                rank_value = parse_search_frequency_rank(search_frequency_rank)
                if rank_value is None or rank_value > max_search_frequency_rank:
                    continue
            report_date = str(row.get("report_date", "")).strip()
            reporting_period = str(row.get("reporting_period", "")).strip()
            date = report_date or str(row.get("date", "")).strip()
            kw_writer.writerow({
                "search_term": search_term,
                "search_frequency_rank": search_frequency_rank,
                "search_volume": "",
                "date": date,
                "report_date": report_date,
                "reporting_period": reporting_period,
                "marketplace": marketplace,
            })
            keyword_count += 1

            for rank in asin_slots:
                asin = str(row.get(f"top_asin_{rank}", "")).strip()
                title = str(row.get(f"top_title_{rank}", "")).strip()
                if not asin and not title:
                    continue
                st_writer.writerow({
                    "search_term": search_term,
                    "asin": asin,
                    "title": title,
                    "asin_rank": rank,
                    "click_share": str(row.get(f"top_click_share_{rank}", "")).strip(),
                    "conversion_share": str(row.get(f"top_conversion_share_{rank}", "")).strip(),
                    "date": date,
                    "report_date": report_date,
                    "reporting_period": reporting_period,
                    "marketplace": marketplace,
                })
                title_count += 1

    return {"keyword_rows": keyword_count, "top_asin_rows": title_count}
