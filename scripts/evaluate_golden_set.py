from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from storage_tagger.evaluation import evaluate_golden_rows
from storage_tagger.tagger import StorageQueryTagger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/sample/golden_set_example.csv")
    parser.add_argument("--output", default="outputs/golden_eval_report.json")
    parser.add_argument("--config-dir", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    tagger = StorageQueryTagger(config_dir=args.config_dir)
    report = evaluate_golden_rows(df.to_dict("records"), tagger=tagger)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2))
    print(f"Wrote full report to {args.output}")


if __name__ == "__main__":
    main()
