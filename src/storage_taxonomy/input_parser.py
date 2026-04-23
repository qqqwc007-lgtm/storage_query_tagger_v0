from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


def _detect_marketplace(path: str | Path) -> str:
    match = re.match(r"([A-Z]{2})_", Path(path).name)
    return match.group(1) if match else ""


def _read_header(path: str | Path) -> tuple[list[str], list[str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        meta = next(reader)
        header = next(reader)
    return meta, header


def iter_source_rows(path: str | Path) -> Iterable[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # metadata row
        header = next(reader)
        for row in reader:
            if not row:
                continue
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            yield dict(zip(header, row))


def prepare_local_inputs(
    raw_csv: str | Path,
    keyword_output: str | Path,
    top_asin_output: str | Path,
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
        asin_match = re.match(r"点击量最高的商品 #(\d+)：ASIN", col)
        if asin_match:
            rank = int(asin_match.group(1))
            asin_slots.append(rank)
    asin_slots = sorted(set(asin_slots))

    kw_columns = ["search_term", "search_frequency_rank", "search_volume", "date", "marketplace"]
    st_columns = [
        "search_term",
        "asin",
        "title",
        "asin_rank",
        "click_share",
        "conversion_share",
        "date",
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
            search_term = str(row.get("搜索词", "")).strip()
            if not search_term:
                continue
            report_date = str(row.get("报告日期", "")).strip()
            kw_writer.writerow({
                "search_term": search_term,
                "search_frequency_rank": str(row.get("搜索频率排名", "")).strip(),
                "search_volume": "",
                "date": report_date,
                "marketplace": marketplace,
            })
            keyword_count += 1

            for rank in asin_slots:
                asin = str(row.get(f"点击量最高的商品 #{rank}：ASIN", "")).strip()
                title = str(row.get(f"点击量最高的商品 #{rank}：商品名称", "")).strip()
                if not asin and not title:
                    continue
                st_writer.writerow({
                    "search_term": search_term,
                    "asin": asin,
                    "title": title,
                    "asin_rank": rank,
                    "click_share": str(row.get(f"点击量最高的商品 #{rank}：点击份额", "")).strip(),
                    "conversion_share": str(row.get(f"点击量最高的商品 #{rank}：转化份额", "")).strip(),
                    "date": report_date,
                    "marketplace": marketplace,
                })
                title_count += 1

    return {"keyword_rows": keyword_count, "top_asin_rows": title_count}
