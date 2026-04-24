from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    duckdb = None


def ensure_duckdb_available() -> None:
    if duckdb is None:
        raise ImportError("Install duckdb to use taxonomy loop storage.")


def initialize_loop_db(db_path: str | Path) -> None:
    ensure_duckdb_available()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS iterations (
                iteration_id INTEGER PRIMARY KEY,
                output_dir VARCHAR,
                config_root VARCHAR,
                taxonomy_fingerprint VARCHAR,
                created_at VARCHAR,
                metrics_json VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS candidate_values (
                iteration_id INTEGER,
                candidate_key VARCHAR,
                candidate_value VARCHAR,
                axis VARCHAR,
                source_phrases VARCHAR,
                example_terms VARCHAR,
                frequency BIGINT,
                search_volume_sum DOUBLE,
                suggested_aliases VARCHAR,
                suggested_rollup_parent VARCHAR,
                suggested_action VARCHAR,
                review_status VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS candidate_review_cache (
                candidate_key VARCHAR PRIMARY KEY,
                candidate_value VARCHAR,
                axis VARCHAR,
                taxonomy_fingerprint VARCHAR,
                decision_json VARCHAR,
                reviewed_at VARCHAR,
                model VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS candidate_decisions (
                iteration_id INTEGER,
                candidate_key VARCHAR,
                candidate_value VARCHAR,
                axis VARCHAR,
                decision VARCHAR,
                canonical_value VARCHAR,
                confidence DOUBLE,
                auto_apply_eligible BOOLEAN,
                reviewed_at VARCHAR,
                model VARCHAR,
                row_json VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS patch_applications (
                iteration_id INTEGER,
                summary_json VARCHAR,
                applied_count INTEGER,
                skipped_count INTEGER,
                created_at VARCHAR
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS iteration_metrics (
                iteration_id INTEGER,
                metric_key VARCHAR,
                metric_value DOUBLE,
                metric_json VARCHAR
            )
        """)


def record_iteration(
    db_path: str | Path,
    iteration_id: int,
    output_dir: str | Path,
    config_root: str | Path,
    taxonomy_fingerprint: str,
    metrics: dict[str, Any],
) -> None:
    initialize_loop_db(db_path)
    with duckdb.connect(str(db_path)) as con:
        con.execute("DELETE FROM iterations WHERE iteration_id = ?", [iteration_id])
        con.execute(
            "INSERT INTO iterations VALUES (?, ?, ?, ?, ?, ?)",
            [
                iteration_id,
                str(output_dir),
                str(config_root),
                taxonomy_fingerprint,
                _now(),
                json.dumps(metrics, ensure_ascii=False),
            ],
        )
        con.execute("DELETE FROM iteration_metrics WHERE iteration_id = ?", [iteration_id])
        for key, value in metrics.items():
            numeric_value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            con.execute(
                "INSERT INTO iteration_metrics VALUES (?, ?, ?, ?)",
                [iteration_id, key, numeric_value, json.dumps(value, ensure_ascii=False)],
            )


def import_candidate_values(
    db_path: str | Path,
    iteration_id: int,
    candidate_values_csv: str | Path,
    taxonomy_fingerprint: str,
) -> int:
    initialize_loop_db(db_path)
    candidate_path = Path(candidate_values_csv)
    if not candidate_path.exists():
        return 0
    with duckdb.connect(str(db_path)) as con:
        con.execute("DELETE FROM candidate_values WHERE iteration_id = ?", [iteration_id])
        con.execute(
            f"""
            INSERT INTO candidate_values
            SELECT
                ? AS iteration_id,
                lower(coalesce(axis, '')) || '|' || lower(coalesce(candidate_value, '')) || '|' || ? AS candidate_key,
                candidate_value,
                axis,
                source_phrases,
                example_terms,
                try_cast(frequency AS BIGINT) AS frequency,
                try_cast(search_volume_sum AS DOUBLE) AS search_volume_sum,
                suggested_aliases,
                suggested_rollup_parent,
                suggested_action,
                review_status
            FROM read_csv_auto({_sql_string(candidate_path)}, header = true, all_varchar = true)
            """,
            [iteration_id, taxonomy_fingerprint],
        )
        return int(con.execute(
            "SELECT count(*) FROM candidate_values WHERE iteration_id = ?",
            [iteration_id],
        ).fetchone()[0])


def export_candidates_for_review(
    db_path: str | Path,
    iteration_id: int,
    output_csv: str | Path,
    limit: int,
    min_frequency: int = 1,
) -> int:
    initialize_loop_db(db_path)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            f"""
            COPY (
                SELECT
                    candidate_value,
                    axis,
                    source_phrases,
                    example_terms,
                    frequency,
                    search_volume_sum,
                    suggested_aliases,
                    suggested_rollup_parent,
                    suggested_action,
                    review_status
                FROM candidate_values cv
                WHERE cv.iteration_id = ?
                  AND coalesce(cv.frequency, 0) >= ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM candidate_review_cache cache
                      WHERE cache.candidate_key = cv.candidate_key
                  )
                ORDER BY coalesce(cv.frequency, 0) DESC,
                         coalesce(cv.search_volume_sum, 0) DESC,
                         cv.candidate_value ASC
                LIMIT ?
            ) TO {_sql_string(output_csv)} (HEADER, DELIMITER ',')
            """,
            [iteration_id, min_frequency, limit],
        )
        return int(con.execute(
            f"SELECT count(*) FROM read_csv_auto({_sql_string(output_csv)}, header = true)"
        ).fetchone()[0])


def import_candidate_decisions(
    db_path: str | Path,
    iteration_id: int,
    decisions_csv: str | Path,
    taxonomy_fingerprint: str,
) -> int:
    initialize_loop_db(db_path)
    decisions_path = Path(decisions_csv)
    if not decisions_path.exists():
        return 0
    with duckdb.connect(str(db_path)) as con:
        con.execute("DELETE FROM candidate_decisions WHERE iteration_id = ?", [iteration_id])
        con.execute(
            f"""
            INSERT INTO candidate_decisions
            SELECT
                ? AS iteration_id,
                lower(coalesce(axis, '')) || '|' || lower(coalesce(candidate_value, '')) || '|' || ? AS candidate_key,
                candidate_value,
                axis,
                decision,
                canonical_value,
                try_cast(confidence AS DOUBLE) AS confidence,
                try_cast(auto_apply_eligible AS BOOLEAN) AS auto_apply_eligible,
                reviewed_at,
                model,
                to_json(src) AS row_json
            FROM read_csv_auto({_sql_string(decisions_path)}, header = true, all_varchar = true) src
            """,
            [iteration_id, taxonomy_fingerprint],
        )
        con.execute(
            """
            INSERT OR REPLACE INTO candidate_review_cache
            SELECT
                candidate_key,
                candidate_value,
                axis,
                ? AS taxonomy_fingerprint,
                row_json AS decision_json,
                reviewed_at,
                model
            FROM candidate_decisions
            WHERE iteration_id = ?
              AND trim(coalesce(json_extract_string(row_json, '$.reason'), '')) <> ''
              AND coalesce(json_extract_string(row_json, '$.reason'), '') NOT LIKE 'review_error:%'
            """,
            [taxonomy_fingerprint, iteration_id],
        )
        return int(con.execute(
            "SELECT count(*) FROM candidate_decisions WHERE iteration_id = ?",
            [iteration_id],
        ).fetchone()[0])


def record_patch_application(db_path: str | Path, iteration_id: int, summary: dict[str, Any]) -> None:
    initialize_loop_db(db_path)
    with duckdb.connect(str(db_path)) as con:
        con.execute("DELETE FROM patch_applications WHERE iteration_id = ?", [iteration_id])
        con.execute(
            "INSERT INTO patch_applications VALUES (?, ?, ?, ?, ?)",
            [
                iteration_id,
                json.dumps(summary, ensure_ascii=False),
                int(summary.get("applied_count", 0)),
                int(summary.get("skipped_count", 0)),
                _now(),
            ],
        )


def _sql_string(path: str | Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
