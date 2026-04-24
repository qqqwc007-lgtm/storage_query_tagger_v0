import argparse
import logging

import pandas as pd
import pytest

from storage_tagger.cli import cmd_tag


def test_cmd_tag_rejects_missing_query_column_by_default(tmp_path):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    pd.DataFrame([{"id": 1, "term": "shoe rack"}]).to_csv(input_csv, index=False)
    args = argparse.Namespace(
        input=input_csv,
        output=output_csv,
        query_column="query",
        config_dir=None,
        allow_column_fallback=False,
    )

    with pytest.raises(ValueError, match="Missing query column 'query'"):
        cmd_tag(args)


def test_cmd_tag_allows_explicit_column_fallback(tmp_path, caplog):
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    pd.DataFrame([{"id": 1, "term": "shoe rack"}]).to_csv(input_csv, index=False)
    args = argparse.Namespace(
        input=input_csv,
        output=output_csv,
        query_column="query",
        config_dir=None,
        allow_column_fallback=True,
    )

    with caplog.at_level(logging.WARNING):
        cmd_tag(args)

    assert output_csv.exists()
    assert "fallback to column term" in caplog.text
