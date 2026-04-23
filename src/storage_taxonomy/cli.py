from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .candidate_discovery import discover_candidate_values
from .diff_engine import build_diff_df
from .input_parser import prepare_local_inputs
from .review_queue import build_review_queue
from .workflow import StorageTaxonomyWorkflow


def cmd_prepare_inputs(args: argparse.Namespace) -> None:
    data_local = Path(args.data_local_dir)
    raw_csv = Path(args.raw_csv) if args.raw_csv else _find_default_raw_csv(data_local)
    result = prepare_local_inputs(
        raw_csv=raw_csv,
        keyword_output=data_local / "keyword_input.csv",
        top_asin_output=data_local / "top_asin_input.csv",
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
            )
        else:
            result = workflow.run(args.keyword_input, args.top_asin_input, args.output_dir)
    else:
        result = workflow.run(args.keyword_input, args.top_asin_input, args.output_dir)
    print(f"Wrote workflow outputs to {args.output_dir}")
    print(result["metrics"])


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


def _find_default_raw_csv(data_local: Path) -> Path:
    csv_files = sorted(path for path in data_local.glob("*.csv") if path.name not in {"keyword_input.csv", "top_asin_input.csv"})
    if len(csv_files) != 1:
        raise ValueError(f"Expected exactly one raw CSV in {data_local}, found {len(csv_files)}. Pass --raw-csv explicitly.")
    return csv_files[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage taxonomy workflow v1")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare-inputs", help="Split raw Amazon export into keyword_input.csv and top_asin_input.csv")
    p_prepare.add_argument("--raw-csv", default=None)
    p_prepare.add_argument("--data-local-dir", default="data/local")
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
