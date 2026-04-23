from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from storage_tagger.new_tag_discovery import discover_candidate_clusters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="outputs/sample_tagged_queries.csv")
    parser.add_argument("--output", default="outputs/candidate_tag_clusters.csv")
    parser.add_argument("--query-column", default="query")
    parser.add_argument("--status-column", default="coverage_status")
    parser.add_argument("--max-clusters", type=int, default=8)
    parser.add_argument("--min-cluster-size", type=int, default=2)
    args = parser.parse_args()

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
    print(f"Wrote {len(clusters)} candidate clusters to {args.output}")


if __name__ == "__main__":
    main()
