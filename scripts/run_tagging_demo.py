from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from storage_tagger.tagger import StorageQueryTagger, result_to_csv_row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/sample/sample_queries.csv")
    parser.add_argument("--output", default="outputs/sample_tagged_queries.csv")
    parser.add_argument("--query-column", default="query")
    parser.add_argument("--config-dir", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    query_col = args.query_column if args.query_column in df.columns else df.columns[-1]

    tagger = StorageQueryTagger(config_dir=args.config_dir)
    rows = [result_to_csv_row(tagger.tag(q)) for q in df[query_col].astype(str).tolist()]

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f"Wrote {len(rows)} tagged queries to {args.output}")


if __name__ == "__main__":
    main()
