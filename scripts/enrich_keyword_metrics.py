from __future__ import annotations

import argparse
from pathlib import Path

from storage_taxonomy.keyword_metrics import build_keyword_metrics_from_csv, write_keyword_metrics_result
from storage_taxonomy.sorftime_client import SorftimeMCPClient, load_sorftime_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Sorftime keyword rank and search volume history")
    parser.add_argument("--keyword-input", default="data/local/keyword_input.csv")
    parser.add_argument("--output", default="outputs/workflow_v1/keyword_metrics.csv")
    parser.add_argument("--errors-output", default=None)
    parser.add_argument("--keyword-column", default="search_term")
    parser.add_argument("--amz-site", default="US")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--request-interval-seconds", type=float, default=0)
    parser.add_argument("--cache-dir", default=None)
    args = parser.parse_args()

    config = load_sorftime_config(timeout_seconds=args.timeout)
    client = SorftimeMCPClient(config)
    result = build_keyword_metrics_from_csv(
        args.keyword_input,
        client,
        amz_site=args.amz_site,
        keyword_column=args.keyword_column,
        request_interval_seconds=args.request_interval_seconds,
        cache_dir=args.cache_dir,
    )
    errors_output = args.errors_output
    if errors_output is None:
        output = Path(args.output)
        errors_output = str(output.with_name(f"{output.stem}_errors{output.suffix}"))
    paths = write_keyword_metrics_result(result, args.output, errors_csv=errors_output)
    print(f"Wrote keyword metrics to {paths['keyword_metrics_path']}")
    if "keyword_metrics_errors_path" in paths:
        print(f"Wrote keyword metric errors to {paths['keyword_metrics_errors_path']}")


if __name__ == "__main__":
    main()
