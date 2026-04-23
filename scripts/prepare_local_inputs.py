from __future__ import annotations

import argparse
from pathlib import Path

from storage_taxonomy.input_parser import prepare_local_inputs


def _find_default_raw_csv(data_local: Path) -> Path:
    csv_files = sorted(path for path in data_local.glob("*.csv") if path.name not in {"keyword_input.csv", "top_asin_input.csv"})
    if len(csv_files) != 1:
        raise ValueError(
            f"Expected exactly one raw CSV in {data_local}, found {len(csv_files)}. Pass --raw-csv explicitly."
        )
    return csv_files[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare keyword_input.csv and top_asin_input.csv from the raw Amazon export.")
    parser.add_argument("--raw-csv", default=None)
    parser.add_argument("--data-local-dir", default="data/local")
    args = parser.parse_args()

    data_local = Path(args.data_local_dir)
    raw_csv = Path(args.raw_csv) if args.raw_csv else _find_default_raw_csv(data_local)
    keyword_output = data_local / "keyword_input.csv"
    top_asin_output = data_local / "top_asin_input.csv"

    result = prepare_local_inputs(raw_csv, keyword_output, top_asin_output)
    print(f"Raw CSV: {raw_csv}")
    print(f"Wrote {result['keyword_rows']} keyword rows to {keyword_output}")
    print(f"Wrote {result['top_asin_rows']} top ASIN rows to {top_asin_output}")


if __name__ == "__main__":
    main()
