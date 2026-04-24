from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from .input_parser import parse_search_frequency_rank, prepare_local_inputs
from .taxonomy_registry import DEFAULT_CONFIG_ROOT, load_yaml

JOIN_KEY_CANDIDATES = [
    "marketplace",
    "report_date",
    "date",
    "reporting_period",
    "search_term",
]

STORAGE_SCOPE_STATUSES = {
    "recall": ["mapped", "partial", "ambiguous"],
    "strict": ["mapped", "partial"],
}


def load_input_reduction_config(config_root: str | Path | None = None) -> dict[str, object]:
    config_dir = Path(config_root) if config_root else DEFAULT_CONFIG_ROOT
    workflow_config = load_yaml(config_dir / "workflow_config.yaml")
    reduction_cfg = workflow_config.get("input_reduction", {})
    scope_cfg = reduction_cfg.get("storage_scope", {})
    return {
        "max_search_frequency_rank": int(reduction_cfg.get("max_search_frequency_rank", 200_000)),
        "default_scope": str(scope_cfg.get("default", "recall")),
        "scope_statuses": {
            "recall": list(scope_cfg.get("recall_statuses", STORAGE_SCOPE_STATUSES["recall"])),
            "strict": list(scope_cfg.get("strict_statuses", STORAGE_SCOPE_STATUSES["strict"])),
        },
    }


def prepare_rank_capped_inputs(
    raw_csv: str | Path,
    output_dir: str | Path,
    max_search_frequency_rank: int = 200_000,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    keyword_output = output_dir / "keyword_input.csv"
    top_asin_output = output_dir / "top_asin_input.csv"
    result = prepare_local_inputs(
        raw_csv=raw_csv,
        keyword_output=keyword_output,
        top_asin_output=top_asin_output,
        max_search_frequency_rank=max_search_frequency_rank,
    )
    summary = {
        "mode": "rank_cap",
        "raw_csv": str(raw_csv),
        "keyword_output": str(keyword_output),
        "top_asin_output": str(top_asin_output),
        "max_search_frequency_rank": max_search_frequency_rank,
        **result,
    }
    _write_summary(output_dir, summary)
    return summary


def reduce_inputs_by_storage_scope(
    keyword_input: str | Path,
    top_asin_input: str | Path,
    cold_start_kw: str | Path,
    output_dir: str | Path,
    scope: str = "recall",
    statuses: Iterable[str] | None = None,
    max_search_frequency_rank: int | None = None,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    keyword_output = output_dir / "keyword_input.csv"
    top_asin_output = output_dir / "top_asin_input.csv"

    keyword_header = _read_csv_header(keyword_input)
    top_asin_header = _read_csv_header(top_asin_input)
    cold_kw_header = _read_csv_header(cold_start_kw)
    keyword_join_keys = _resolve_join_keys(cold_kw_header, keyword_header)
    top_asin_join_keys = _resolve_join_keys(cold_kw_header, top_asin_header)

    included_statuses = _included_statuses(scope, statuses)
    keyword_keys: set[tuple[str, ...]] = set()
    top_asin_keys: set[tuple[str, ...]] = set()
    status_counts: Counter[str] = Counter()
    selected_status_counts: Counter[str] = Counter()
    source_kw_rows = 0
    selected_cold_start_rows = 0

    with Path(cold_start_kw).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_kw_rows += 1
            status = str(row.get("mapping_status", "")).strip()
            status_counts[status] += 1
            if status not in included_statuses:
                continue
            if max_search_frequency_rank is not None:
                rank = parse_search_frequency_rank(row.get("search_frequency_rank"))
                if rank is None or rank > max_search_frequency_rank:
                    continue
            keyword_keys.add(_row_key(row, keyword_join_keys))
            top_asin_keys.add(_row_key(row, top_asin_join_keys))
            selected_status_counts[status] += 1
            selected_cold_start_rows += 1

    keyword_rows = _copy_matching_rows(
        input_csv=keyword_input,
        output_csv=keyword_output,
        join_keys=keyword_join_keys,
        allowed_keys=keyword_keys,
    )
    top_asin_rows = _copy_matching_rows(
        input_csv=top_asin_input,
        output_csv=top_asin_output,
        join_keys=top_asin_join_keys,
        allowed_keys=top_asin_keys,
    )

    summary = {
        "mode": "storage_scope",
        "scope": scope,
        "included_statuses": included_statuses,
        "max_search_frequency_rank": max_search_frequency_rank,
        "keyword_input": str(keyword_input),
        "top_asin_input": str(top_asin_input),
        "cold_start_kw": str(cold_start_kw),
        "keyword_output": str(keyword_output),
        "top_asin_output": str(top_asin_output),
        "keyword_join_keys": keyword_join_keys,
        "top_asin_join_keys": top_asin_join_keys,
        "source_kw_rows": source_kw_rows,
        "selected_cold_start_rows": selected_cold_start_rows,
        "keyword_rows": keyword_rows,
        "top_asin_rows": top_asin_rows,
        "status_counts": dict(status_counts),
        "selected_status_counts": dict(selected_status_counts),
    }
    _write_summary(output_dir, summary)
    return summary


def _included_statuses(scope: str, statuses: Iterable[str] | None) -> list[str]:
    if statuses is not None:
        cleaned = [str(status).strip() for status in statuses if str(status).strip()]
        if not cleaned:
            raise ValueError("At least one mapping status is required.")
        return cleaned
    if scope not in STORAGE_SCOPE_STATUSES:
        raise ValueError(f"Unknown storage scope: {scope}. Expected one of {sorted(STORAGE_SCOPE_STATUSES)}.")
    return STORAGE_SCOPE_STATUSES[scope]


def _read_csv_header(path: str | Path) -> list[str]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            return next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {path}") from exc


def _resolve_join_keys(left_header: list[str], right_header: list[str]) -> list[str]:
    left_columns = set(left_header)
    right_columns = set(right_header)
    join_keys = [
        col for col in JOIN_KEY_CANDIDATES
        if col in left_columns and col in right_columns
    ]
    if "search_term" not in join_keys:
        raise ValueError(
            "Input reduction requires search_term in cold-start kw output and standard input files. "
            f"Cold-start columns: {left_header}. Input columns: {right_header}"
        )
    return join_keys


def _row_key(row: dict[str, object], join_keys: list[str]) -> tuple[str, ...]:
    return tuple(str(row.get(col, "") or "").strip() for col in join_keys)


def _copy_matching_rows(
    input_csv: str | Path,
    output_csv: str | Path,
    join_keys: list[str],
    allowed_keys: set[tuple[str, ...]],
) -> int:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with Path(input_csv).open("r", encoding="utf-8-sig", newline="") as in_f, output_csv.open(
        "w", encoding="utf-8", newline=""
    ) as out_f:
        reader = csv.DictReader(in_f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is missing a header: {input_csv}")
        writer = csv.DictWriter(out_f, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if _row_key(row, join_keys) not in allowed_keys:
                continue
            writer.writerow(row)
            rows_written += 1
    return rows_written


def _write_summary(output_dir: Path, summary: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "selection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
