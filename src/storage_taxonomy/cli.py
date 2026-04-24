from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .candidate_discovery import discover_candidate_values
from .diff_engine import build_diff_df
from .input_reducer import load_input_reduction_config, reduce_inputs_by_storage_scope
from .input_parser import prepare_local_inputs
from .keyword_metrics import build_keyword_metrics_from_csv, write_keyword_metrics_result
from .review_queue import build_review_queue
from .sorftime_client import SorftimeMCPClient, load_sorftime_config
from .workflow import StorageTaxonomyWorkflow


def cmd_prepare_inputs(args: argparse.Namespace) -> None:
    data_local = Path(args.data_local_dir)
    raw_csv = Path(args.raw_csv) if args.raw_csv else _find_default_raw_csv(data_local)
    result = prepare_local_inputs(
        raw_csv=raw_csv,
        keyword_output=data_local / "keyword_input.csv",
        top_asin_output=data_local / "top_asin_input.csv",
        max_search_frequency_rank=args.max_search_frequency_rank,
    )
    print(f"Prepared inputs from {raw_csv}")
    print(result)


def cmd_run(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    if args.mode == "chunked":
        result = workflow.run_chunked(
            args.keyword_input,
            args.top_asin_input,
            args.output_dir,
            keyword_chunk_size=args.keyword_chunk_size,
            title_chunk_size=args.title_chunk_size,
            candidate_chunk_size=args.candidate_chunk_size,
            keyword_metrics_enabled=args.with_keyword_metrics,
            keyword_metrics_amz_site=args.keyword_metrics_amz_site,
        )
    elif args.mode == "auto":
        keyword_size = Path(args.keyword_input).stat().st_size if Path(args.keyword_input).exists() else 0
        title_size = Path(args.top_asin_input).stat().st_size if Path(args.top_asin_input).exists() else 0
        if max(keyword_size, title_size) >= 100 * 1024 * 1024:
            result = workflow.run_chunked(
                args.keyword_input,
                args.top_asin_input,
                args.output_dir,
                keyword_chunk_size=args.keyword_chunk_size,
                title_chunk_size=args.title_chunk_size,
                candidate_chunk_size=args.candidate_chunk_size,
                keyword_metrics_enabled=args.with_keyword_metrics,
                keyword_metrics_amz_site=args.keyword_metrics_amz_site,
            )
        else:
            result = workflow.run(
                args.keyword_input,
                args.top_asin_input,
                args.output_dir,
                keyword_metrics_enabled=args.with_keyword_metrics,
                keyword_metrics_amz_site=args.keyword_metrics_amz_site,
            )
    else:
        result = workflow.run(
            args.keyword_input,
            args.top_asin_input,
            args.output_dir,
            keyword_metrics_enabled=args.with_keyword_metrics,
            keyword_metrics_amz_site=args.keyword_metrics_amz_site,
        )
    print(f"Wrote workflow outputs to {args.output_dir}")
    print(result["metrics"])
    if "keyword_metrics_path" in result:
        print(f"Wrote keyword metrics to {result['keyword_metrics_path']}")


def cmd_extract_kw(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    df = pd.read_csv(args.input)
    kw_df = workflow.extract_keywords(df)
    kw_df.to_csv(args.output, index=False)
    print(f"Wrote keyword extraction to {args.output}")


def cmd_extract_st(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    df = pd.read_csv(args.input)
    st_df = workflow.extract_titles(df)
    st_df.to_csv(args.output, index=False)
    print(f"Wrote title extraction to {args.output}")


def cmd_diff(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    kw_df = pd.read_csv(args.kw_csv)
    st_df = pd.read_csv(args.st_csv)
    diff_df = build_diff_df(kw_df, st_df, registry=workflow.registry)
    diff_df.to_csv(args.output, index=False)
    print(f"Wrote diff to {args.output}")


def cmd_review_queue(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    diff_df = pd.read_csv(args.diff_csv)
    kw_df = pd.read_csv(args.kw_csv)
    queue_df = build_review_queue(diff_df, kw_df, registry=workflow.registry)
    queue_df.to_csv(args.output, index=False)
    print(f"Wrote review queue to {args.output}")


def cmd_discover(args: argparse.Namespace) -> None:
    workflow = StorageTaxonomyWorkflow(config_root=args.config_root)
    kw_df = pd.read_csv(args.kw_csv)
    st_df = pd.read_csv(args.st_csv)
    diff_df = pd.read_csv(args.diff_csv)
    candidate_df = discover_candidate_values(kw_df, st_df, diff_df, registry=workflow.registry)
    candidate_df.to_csv(args.output, index=False)
    print(f"Wrote candidate values to {args.output}")


def cmd_keyword_metrics(args: argparse.Namespace) -> None:
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


def cmd_reduce_inputs(args: argparse.Namespace) -> None:
    defaults = load_input_reduction_config(args.config_root)
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
    print(result)


def _find_default_raw_csv(data_local: Path) -> Path:
    csv_files = sorted(path for path in data_local.glob("*.csv") if path.name not in {"keyword_input.csv", "top_asin_input.csv"})
    if len(csv_files) != 1:
        raise ValueError(f"Expected exactly one raw CSV in {data_local}, found {len(csv_files)}. Pass --raw-csv explicitly.")
    return csv_files[0]


def _parse_statuses(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage taxonomy workflow v1")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare-inputs", help="Split raw Amazon export into keyword_input.csv and top_asin_input.csv")
    p_prepare.add_argument("--raw-csv", default=None)
    p_prepare.add_argument("--data-local-dir", default="data/local")
    p_prepare.add_argument("--max-search-frequency-rank", type=int, default=None)
    p_prepare.set_defaults(func=cmd_prepare_inputs)

    p_run = sub.add_parser("run", help="Run the full v1 workflow")
    p_run.add_argument("--keyword-input", required=True)
    p_run.add_argument("--top-asin-input", required=True)
    p_run.add_argument("--output-dir", required=True)
    p_run.add_argument("--config-root", default=None)
    p_run.add_argument("--mode", choices=["auto", "in-memory", "chunked"], default="auto")
    p_run.add_argument("--keyword-chunk-size", type=int, default=100000)
    p_run.add_argument("--title-chunk-size", type=int, default=100000)
    p_run.add_argument("--candidate-chunk-size", type=int, default=200000)
    p_run.add_argument("--with-keyword-metrics", action="store_true", help="Fetch Sorftime keyword rank and volume history")
    p_run.add_argument("--keyword-metrics-amz-site", default=None, help="Sorftime Amazon site code, for example US")
    p_run.set_defaults(func=cmd_run)

    p_kw = sub.add_parser("extract-kw", help="Extract canonical fields from keywords")
    p_kw.add_argument("--input", required=True)
    p_kw.add_argument("--output", required=True)
    p_kw.add_argument("--config-root", default=None)
    p_kw.set_defaults(func=cmd_extract_kw)

    p_st = sub.add_parser("extract-st", help="Extract canonical fields from titles")
    p_st.add_argument("--input", required=True)
    p_st.add_argument("--output", required=True)
    p_st.add_argument("--config-root", default=None)
    p_st.set_defaults(func=cmd_extract_st)

    p_diff = sub.add_parser("generate-diff", help="Generate kw/st diff file")
    p_diff.add_argument("--kw-csv", required=True)
    p_diff.add_argument("--st-csv", required=True)
    p_diff.add_argument("--output", required=True)
    p_diff.add_argument("--config-root", default=None)
    p_diff.set_defaults(func=cmd_diff)

    p_queue = sub.add_parser("build-review-queue", help="Build review queue from diff")
    p_queue.add_argument("--diff-csv", required=True)
    p_queue.add_argument("--kw-csv", required=True)
    p_queue.add_argument("--output", required=True)
    p_queue.add_argument("--config-root", default=None)
    p_queue.set_defaults(func=cmd_review_queue)

    p_discover = sub.add_parser("discover-candidates", help="Discover candidate taxonomy values")
    p_discover.add_argument("--kw-csv", required=True)
    p_discover.add_argument("--st-csv", required=True)
    p_discover.add_argument("--diff-csv", required=True)
    p_discover.add_argument("--output", required=True)
    p_discover.add_argument("--config-root", default=None)
    p_discover.set_defaults(func=cmd_discover)

    p_metrics = sub.add_parser("keyword-metrics", help="Fetch Sorftime keyword rank and volume history")
    p_metrics.add_argument("--keyword-input", required=True)
    p_metrics.add_argument("--output", required=True)
    p_metrics.add_argument("--errors-output", default=None)
    p_metrics.add_argument("--keyword-column", default="search_term")
    p_metrics.add_argument("--amz-site", default="US")
    p_metrics.add_argument("--timeout", type=int, default=30)
    p_metrics.add_argument("--request-interval-seconds", type=float, default=0)
    p_metrics.add_argument("--cache-dir", default=None)
    p_metrics.set_defaults(func=cmd_keyword_metrics)

    p_reduce = sub.add_parser("reduce-inputs", help="Reduce standard inputs from an existing cold-start kw.csv")
    p_reduce.add_argument("--keyword-input", default="data/local/keyword_input.csv")
    p_reduce.add_argument("--top-asin-input", default="data/local/top_asin_input.csv")
    p_reduce.add_argument("--cold-start-kw", default="outputs/workflow_v1_full/kw.csv")
    p_reduce.add_argument("--output-dir", default="data/local/reduced")
    p_reduce.add_argument("--config-root", default="config")
    p_reduce.add_argument("--scope", choices=["recall", "strict"], default=None)
    p_reduce.add_argument("--statuses", default=None)
    p_reduce.add_argument("--max-search-frequency-rank", type=int, default=None)
    p_reduce.set_defaults(func=cmd_reduce_inputs)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
