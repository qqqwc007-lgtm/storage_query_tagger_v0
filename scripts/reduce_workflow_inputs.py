#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from storage_taxonomy.input_reducer import (
    load_input_reduction_config,
    prepare_rank_capped_inputs,
    reduce_inputs_by_storage_scope,
)


def _find_default_raw_csv(data_local: Path) -> Path:
    excluded = {"keyword_input.csv", "top_asin_input.csv"}
    csv_files = sorted(path for path in data_local.glob("*.csv") if path.name not in excluded)
    if len(csv_files) != 1:
        raise ValueError(
            f"Expected exactly one raw CSV in {data_local}, found {len(csv_files)}. Pass --raw-csv explicitly."
        )
    return csv_files[0]


def _parse_statuses(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reduce workflow input CSVs before running storage taxonomy v1.")
    parser.add_argument("--mode", choices=["rank-cap", "storage-scope"], default="storage-scope")
    parser.add_argument("--config-root", default="config")
    parser.add_argument("--output-dir", default="data/local/reduced")
    parser.add_argument("--raw-csv", default=None)
    parser.add_argument("--data-local-dir", default="data/local")
    parser.add_argument("--keyword-input", default="data/local/keyword_input.csv")
    parser.add_argument("--top-asin-input", default="data/local/top_asin_input.csv")
    parser.add_argument("--cold-start-kw", default="outputs/workflow_v1_full/kw.csv")
    parser.add_argument("--scope", choices=["recall", "strict"], default=None)
    parser.add_argument("--statuses", default=None, help="Comma-separated mapping_status allowlist.")
    parser.add_argument("--max-search-frequency-rank", type=int, default=None)
    args = parser.parse_args()
    defaults = load_input_reduction_config(args.config_root)

    if args.mode == "rank-cap":
        data_local = Path(args.data_local_dir)
        raw_csv = Path(args.raw_csv) if args.raw_csv else _find_default_raw_csv(data_local)
        max_rank = (
            args.max_search_frequency_rank
            if args.max_search_frequency_rank is not None
            else int(defaults["max_search_frequency_rank"])
        )
        result = prepare_rank_capped_inputs(
            raw_csv=raw_csv,
            output_dir=args.output_dir,
            max_search_frequency_rank=max_rank,
        )
    else:
        scope = args.scope or str(defaults["default_scope"])
        statuses = _parse_statuses(args.statuses)
        if statuses is None:
            statuses = dict(defaults["scope_statuses"]).get(scope)
        result = reduce_inputs_by_storage_scope(
            keyword_input=args.keyword_input,
            top_asin_input=args.top_asin_input,
            cold_start_kw=args.cold_start_kw,
            output_dir=args.output_dir,
            scope=scope,
            statuses=statuses,
            max_search_frequency_rank=args.max_search_frequency_rank,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
