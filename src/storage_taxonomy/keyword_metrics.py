from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import pandas as pd


KEYWORD_METRIC_COLUMNS = ["关键词", "时间", "关键词搜索排名", "关键词搜索容量"]
KEYWORD_METRIC_ERROR_COLUMNS = ["关键词", "error"]


class KeywordTrendClient(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


@dataclass(slots=True)
class KeywordMetricsResult:
    metrics_df: pd.DataFrame
    errors_df: pd.DataFrame


def unique_keywords_from_csv(input_csv: str | Path, keyword_column: str = "search_term") -> list[str]:
    df = pd.read_csv(input_csv, usecols=[keyword_column])
    return unique_keywords(df[keyword_column].tolist())


def unique_keywords(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for value in values:
        keyword = str(value).strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords


def build_keyword_metrics_from_csv(
    input_csv: str | Path,
    client: KeywordTrendClient,
    *,
    amz_site: str = "US",
    keyword_column: str = "search_term",
    tool_name: str = "keyword_trend",
    request_interval_seconds: float = 0,
    cache_dir: str | Path | None = None,
) -> KeywordMetricsResult:
    keywords = unique_keywords_from_csv(input_csv, keyword_column=keyword_column)
    return build_keyword_metrics_df(
        keywords,
        client,
        amz_site=amz_site,
        tool_name=tool_name,
        request_interval_seconds=request_interval_seconds,
        cache_dir=cache_dir,
    )


def build_keyword_metrics_df(
    keywords: Iterable[Any],
    client: KeywordTrendClient,
    *,
    amz_site: str = "US",
    tool_name: str = "keyword_trend",
    request_interval_seconds: float = 0,
    cache_dir: str | Path | None = None,
) -> KeywordMetricsResult:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    keyword_list = unique_keywords(keywords)
    cache_root = Path(cache_dir) if cache_dir else None
    if cache_root:
        cache_root.mkdir(parents=True, exist_ok=True)

    for index, keyword in enumerate(keyword_list):
        try:
            result_payload = _load_cached_result(cache_root, keyword, amz_site, tool_name)
            if result_payload is None:
                response = client.call_tool(tool_name, {"keyword": keyword, "amzSite": amz_site})
                result_payload = getattr(response, "first_result", response)
                _write_cached_result(cache_root, keyword, amz_site, tool_name, result_payload)

            keyword_df = parse_keyword_trend_result(result_payload, default_keyword=keyword)
            rows.extend(keyword_df.to_dict("records"))
        except Exception as exc:  # noqa: BLE001 - batch should preserve other keywords
            errors.append({"关键词": keyword, "error": str(exc)})

        if request_interval_seconds > 0 and index < len(keyword_list) - 1:
            time.sleep(request_interval_seconds)

    metrics_df = pd.DataFrame(rows, columns=KEYWORD_METRIC_COLUMNS)
    if not metrics_df.empty:
        metrics_df = metrics_df.sort_values(["关键词", "时间"], kind="stable").reset_index(drop=True)
    errors_df = pd.DataFrame(errors, columns=KEYWORD_METRIC_ERROR_COLUMNS)
    return KeywordMetricsResult(metrics_df=metrics_df, errors_df=errors_df)


def parse_keyword_trend_result(result: Any, *, default_keyword: str = "") -> pd.DataFrame:
    parsed = _extract_payload_object(result)
    if not isinstance(parsed, dict):
        return pd.DataFrame(columns=KEYWORD_METRIC_COLUMNS)

    keyword = str(parsed.get("关键词") or parsed.get("keyword") or default_keyword).strip()
    volumes = _parse_metric_series(parsed.get("搜索量趋势", []), metric_label="search_volume")
    ranks = _parse_metric_series(parsed.get("搜索排名趋势", []), metric_label="search_rank")

    rows = []
    for period in sorted(set(volumes) | set(ranks)):
        rows.append(
            {
                "关键词": keyword,
                "时间": period,
                "关键词搜索排名": ranks.get(period, ""),
                "关键词搜索容量": volumes.get(period, ""),
            }
        )
    return pd.DataFrame(rows, columns=KEYWORD_METRIC_COLUMNS)


def write_keyword_metrics_result(
    result: KeywordMetricsResult,
    output_csv: str | Path,
    *,
    errors_csv: str | Path | None = None,
) -> dict[str, str]:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result.metrics_df.to_csv(output_csv, index=False)
    paths = {"keyword_metrics_path": str(output_csv)}

    if errors_csv and not result.errors_df.empty:
        errors_path = Path(errors_csv)
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        result.errors_df.to_csv(errors_path, index=False)
        paths["keyword_metrics_errors_path"] = str(errors_path)

    return paths


def _parse_metric_series(values: Any, *, metric_label: str) -> dict[str, str]:
    if not isinstance(values, list):
        return {}

    series: dict[str, str] = {}
    for item in values:
        parsed = _parse_metric_entry(item, metric_label=metric_label)
        if parsed:
            period, value = parsed
            series[period] = value
    return series


def _parse_metric_entry(item: Any, *, metric_label: str) -> tuple[str, str] | None:
    if isinstance(item, dict):
        period = _normalize_period(item.get("period") or item.get("date") or item.get("时间") or item.get("月份"))
        value = _first_present_value(item, ["value", "搜索量", "搜索排名", "search_volume", "search_rank"])
        if period and value is not None and value != "":
            return period, _clean_metric_value(value)
        return None

    text = str(item).strip()
    period_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月|(\d{4})[-/](\d{1,2})", text)
    if not period_match:
        return None

    period = _normalize_period(period_match.group(0))
    value_text = text[period_match.end() :].strip()
    if "=" in value_text:
        value_text = value_text.split("=", 1)[1].strip()
    else:
        for token in _metric_tokens(metric_label):
            value_text = value_text.replace(token, "").strip()

    value_match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", value_text)
    if not period or not value_match:
        return None
    return period, _clean_metric_value(value_match.group(0))


def _metric_tokens(metric_label: str) -> list[str]:
    if metric_label == "search_volume":
        return ["搜索量", "search_volume", "volume"]
    if metric_label == "search_rank":
        return ["搜索排名", "search_rank", "rank"]
    return []


def _normalize_period(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    chinese_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if chinese_match:
        return f"{int(chinese_match.group(1)):04d}-{int(chinese_match.group(2)):02d}"

    iso_match = re.search(r"(\d{4})[-/](\d{1,2})", text)
    if iso_match:
        return f"{int(iso_match.group(1)):04d}-{int(iso_match.group(2)):02d}"

    return text


def _clean_metric_value(value: Any) -> str:
    return str(value).strip().replace(",", "")


def _first_present_value(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _extract_payload_object(result: Any) -> Any:
    if isinstance(result, dict):
        if "关键词" in result or "keyword" in result:
            return result
        if isinstance(result.get("content"), list):
            for item in result["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    parsed = _parse_prefixed_json_object(str(item.get("text", "")))
                    if parsed is not None:
                        return parsed
        return result
    if isinstance(result, str):
        return _parse_prefixed_json_object(result)
    return None


def _parse_prefixed_json_object(text: str) -> Any | None:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _load_cached_result(cache_root: Path | None, keyword: str, amz_site: str, tool_name: str) -> Any | None:
    if not cache_root:
        return None
    cache_path = _cache_path(cache_root, keyword, amz_site, tool_name)
    if not cache_path.exists():
        return None
    return json.loads(cache_path.read_text(encoding="utf-8")).get("result")


def _write_cached_result(cache_root: Path | None, keyword: str, amz_site: str, tool_name: str, result: Any) -> None:
    if not cache_root:
        return
    cache_path = _cache_path(cache_root, keyword, amz_site, tool_name)
    cache_path.write_text(
        json.dumps(
            {
                "tool": tool_name,
                "keyword": keyword,
                "amzSite": amz_site,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _cache_path(cache_root: Path, keyword: str, amz_site: str, tool_name: str) -> Path:
    digest = hashlib.sha1(f"{tool_name}|{amz_site}|{keyword}".encode("utf-8")).hexdigest()
    return cache_root / f"{digest}.json"
