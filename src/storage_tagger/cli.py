from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .evaluation import evaluate_golden_rows
from .new_tag_discovery import discover_candidate_clusters
from .tagger import StorageQueryTagger, result_to_csv_row


def cmd_tag(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.input)
    query_col = args.query_column
    if query_col not in df.columns:
        if len(df.columns) >= 2:
            query_col = df.columns[1]
        else:
            raise ValueError(f"Cannot find query column: {args.query_column}")

    tagger = StorageQueryTagger(config_dir=args.config_dir)
    rows = [result_to_csv_row(tagger.tag(q)) for q in df[query_col].astype(str).tolist()]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f"Wrote {len(rows)} rows to {args.output}")


def cmd_eval(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.input)
    tagger = StorageQueryTagger(config_dir=args.config_dir)
    report = evaluate_golden_rows(df.to_dict("records"), tagger=tagger)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote evaluation report to {args.output}")


def cmd_discover(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.input)
    clusters = discover_candidate_clusters(
        df,
        query_col=args.query_column,
        status_col=args.status_column,
        max_clusters=args.max_clusters,
        min_cluster_size=args.min_cluster_size,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    clusters.to_csv(args.output, index=False)
    print(f"Wrote candidate clusters to {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Storage Query Tagger v0")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tag = sub.add_parser("tag", help="Tag queries from CSV")
    p_tag.add_argument("--input", required=True)
    p_tag.add_argument("--output", required=True)
    p_tag.add_argument("--query-column", default="query")
    p_tag.add_argument("--config-dir", default=None)
    p_tag.set_defaults(func=cmd_tag)

    p_eval = sub.add_parser("eval", help="Evaluate on golden set CSV")
    p_eval.add_argument("--input", required=True)
    p_eval.add_argument("--output", required=True)
    p_eval.add_argument("--config-dir", default=None)
    p_eval.set_defaults(func=cmd_eval)

    p_discover = sub.add_parser("discover", help="Discover candidate clusters from tagged CSV")
    p_discover.add_argument("--input", required=True)
    p_discover.add_argument("--output", required=True)
    p_discover.add_argument("--query-column", default="query")
    p_discover.add_argument("--status-column", default="coverage_status")
    p_discover.add_argument("--max-clusters", type=int, default=8)
    p_discover.add_argument("--min-cluster-size", type=int, default=2)
    p_discover.set_defaults(func=cmd_discover)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
