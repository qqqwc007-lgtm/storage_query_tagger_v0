from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Protocol

INSTRUCTION_FOOTER_MARKERS = (
    "依据这些数据进行总结",
    "如无明确指令不要延伸调用其他工具",
)


@dataclass(frozen=True)
class ProductDetail:
    asin: str
    parent_asin: str
    title: str
    main_image_url: str
    price: float | None
    rating: float | None
    review_count: int | None
    brand: str
    seller_name: str
    seller_origin: str
    category: str
    attributes: dict[str, Any]
    launch_date: date | None
    days_since_launch: int | None
    fba_fee: float | None
    monthly_units: int | None
    monthly_gmv: float | None
    description_text: str
    feature_ratings: dict[str, Any]
    package_dimensions_cm: tuple[float, ...]
    weight_g: float | None
    material_raw: str
    dimension_raw: str
    weight_raw: str
    source_text: str
    source_raw_json: str
    parse_status: str
    parse_errors: tuple[str, ...]


@dataclass(frozen=True)
class ProductAsinFactRow:
    asin: str
    parent_asin: str
    title: str
    main_image_url: str
    brand: str
    seller_name: str
    seller_origin: str
    price: float | None
    monthly_units: int | None
    monthly_gmv: float | None
    asin_asp: float | None
    launch_date: date | None
    days_since_launch: int | None
    rating: float | None
    review_count: int | None
    material_raw: str
    dimension_raw: str
    weight_raw: str
    fba_fee: float | None
    attributes_json: str
    description_text: str
    source_raw_json: str
    parse_status: str
    package_dimensions_cm: tuple[float, ...] = ()
    weight_g: float | None = None


class ProductFactSourceRow(Protocol):
    asin: str
    title: str
    price: float | None
    units: int | None
    gmv: float | None
    asin_asp: float | None
    launch_date: date | str | None
    rating: float | None
    review_count: int | None


def parse_product_detail_raw(path: str | Path) -> ProductDetail:
    raw_path = Path(path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _empty_product_detail(
            asin=_asin_from_path(raw_path),
            source_raw_json=str(raw_path),
            parse_status="parse_error",
            parse_errors=(f"json_error:{exc}",),
        )
    return parse_product_detail_payload(payload, source_raw_json=str(raw_path))


def parse_product_detail_payload(payload: dict[str, Any], source_raw_json: str = "") -> ProductDetail:
    fallback_asin = str(payload.get("asin") or "").strip()
    text = extract_product_detail_text(payload)
    if not text:
        return _empty_product_detail(
            asin=fallback_asin,
            source_raw_json=source_raw_json,
            parse_status="parse_error",
            parse_errors=("missing_product_detail_text",),
        )
    return parse_product_detail_text(text, source_raw_json=source_raw_json, fallback_asin=fallback_asin)


def parse_product_detail_text(
    text: str,
    source_raw_json: str = "",
    fallback_asin: str = "",
) -> ProductDetail:
    clean_text = strip_instruction_footer(text)
    fields = _parse_key_value_text(clean_text)
    attributes = _parse_json_object_prefix(_field(fields, "属性"))
    feature_ratings = _parse_json_object_prefix(_field(fields, "特征"))
    package_dimensions_cm = _parse_dimensions_cm(_field(fields, "外包装尺寸（cm）", "外包装尺寸(cm)"))
    weight_g = _parse_float(_field(fields, "重量（g）", "重量(g)"))

    asin = _field(fields, "产品ASIN码") or fallback_asin
    material_raw = _clean(attributes.get("Material") or attributes.get("材质") or _field(fields, "材质"))
    dimension_raw = _clean(
        attributes.get("Product Dimensions")
        or attributes.get("Dimensions")
        or attributes.get("产品尺寸")
        or _field(fields, "尺寸")
    )
    weight_raw = _clean(attributes.get("Item Weight") or attributes.get("重量") or _field(fields, "重量（g）", "重量(g)"))
    parse_errors = tuple(() if asin else ("missing_asin",))

    return ProductDetail(
        asin=asin,
        parent_asin=_field(fields, "父级ASIN码"),
        title=_field(fields, "标题"),
        main_image_url=_field(fields, "主图"),
        price=_parse_float(_field(fields, "价格")),
        rating=_parse_float(_field(fields, "星级")),
        review_count=_parse_int(_field(fields, "评论数", "评论数量")),
        brand=_field(fields, "品牌"),
        seller_name=_field(fields, "卖家名称", "卖家"),
        seller_origin=_field(fields, "卖家来源"),
        category=_field(fields, "分类"),
        attributes=attributes,
        launch_date=_parse_date(_field(fields, "上架时间", "上架日期")),
        days_since_launch=_parse_int(_field(fields, "已上架天数", "上架天数")),
        fba_fee=_parse_float(_field(fields, "FBA费用")),
        monthly_units=_parse_int(_field(fields, "月销量")),
        monthly_gmv=_parse_float(_field(fields, "月销额")),
        description_text=_field(fields, "产品描述"),
        feature_ratings=feature_ratings,
        package_dimensions_cm=package_dimensions_cm,
        weight_g=weight_g,
        material_raw=material_raw,
        dimension_raw=dimension_raw,
        weight_raw=weight_raw,
        source_text=clean_text,
        source_raw_json=source_raw_json,
        parse_status="parsed" if not parse_errors else "partial",
        parse_errors=parse_errors,
    )


def extract_product_detail_text(payload: dict[str, Any]) -> str:
    texts = list(_walk_text_content(payload.get("messages")))
    if not texts:
        texts = list(_walk_text_content(payload.get("first_result")))
    if not texts:
        texts = _texts_from_sse_raw_text(str(payload.get("raw_text") or ""))
    if not texts:
        texts = list(_walk_text_content(payload))
    return "\n".join(text for text in texts if text.strip()).strip()


def strip_instruction_footer(text: str) -> str:
    cutoff = len(text)
    for marker in INSTRUCTION_FOOTER_MARKERS:
        index = text.find(marker)
        if index >= 0:
            cutoff = min(cutoff, index)
    return text[:cutoff].strip()


def build_product_asin_facts(
    source_rows: Iterable[ProductFactSourceRow],
    raw_detail_dir: str | Path,
) -> list[ProductAsinFactRow]:
    raw_dir = Path(raw_detail_dir)
    facts: list[ProductAsinFactRow] = []
    seen: set[str] = set()
    for source_row in source_rows:
        if _source_is_invalid(source_row):
            continue
        asin = source_row.asin.strip()
        asin_key = asin.upper()
        if not asin_key or asin_key in seen:
            continue
        seen.add(asin_key)
        raw_path = raw_dir / f"{asin_key}_product_detail_raw.json"
        detail = (
            parse_product_detail_raw(raw_path)
            if raw_path.exists()
            else _empty_product_detail(
                asin=asin_key,
                source_raw_json=str(raw_path),
                parse_status="missing_raw",
                parse_errors=("raw_detail_file_missing",),
            )
        )
        facts.append(_merge_product_fact(source_row, detail))
    return facts


def _merge_product_fact(source_row: ProductFactSourceRow, detail: ProductDetail) -> ProductAsinFactRow:
    attributes_json = json.dumps(detail.attributes, ensure_ascii=False, sort_keys=True)
    return ProductAsinFactRow(
        asin=source_row.asin or detail.asin,
        parent_asin=detail.parent_asin,
        title=detail.title or source_row.title,
        main_image_url=detail.main_image_url or _source_image_url(source_row),
        brand=detail.brand or _source_optional_str(source_row, "brand"),
        seller_name=detail.seller_name or _source_optional_str(source_row, "seller_name"),
        seller_origin=detail.seller_origin,
        price=detail.price if detail.price is not None else source_row.price,
        monthly_units=detail.monthly_units if detail.monthly_units is not None else source_row.units,
        monthly_gmv=detail.monthly_gmv if detail.monthly_gmv is not None else source_row.gmv,
        asin_asp=source_row.asin_asp,
        launch_date=detail.launch_date or _source_launch_date(source_row),
        days_since_launch=detail.days_since_launch
        if detail.days_since_launch is not None
        else _source_optional_int(source_row, "days_since_launch"),
        rating=detail.rating if detail.rating is not None else source_row.rating,
        review_count=detail.review_count if detail.review_count is not None else source_row.review_count,
        material_raw=detail.material_raw,
        dimension_raw=detail.dimension_raw,
        weight_raw=detail.weight_raw,
        fba_fee=detail.fba_fee,
        attributes_json=attributes_json,
        description_text=detail.description_text,
        source_raw_json=detail.source_raw_json,
        parse_status=detail.parse_status,
        package_dimensions_cm=detail.package_dimensions_cm,
        weight_g=detail.weight_g,
    )


def _source_is_invalid(source_row: ProductFactSourceRow) -> bool:
    return _source_optional_str(source_row, "asin_validity_override") == "invalid"


def _source_image_url(source_row: ProductFactSourceRow) -> str:
    return _source_optional_str(source_row, "main_image_url") or _source_optional_str(source_row, "image_url")


def _source_optional_str(source_row: ProductFactSourceRow, field_name: str) -> str:
    return _clean(getattr(source_row, field_name, ""))


def _source_optional_int(source_row: ProductFactSourceRow, field_name: str) -> int | None:
    value = getattr(source_row, field_name, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_launch_date(source_row: ProductFactSourceRow) -> date | None:
    value = source_row.launch_date
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return _parse_date(value)
    return None


def _empty_product_detail(
    asin: str,
    source_raw_json: str,
    parse_status: str,
    parse_errors: tuple[str, ...],
) -> ProductDetail:
    return ProductDetail(
        asin=asin,
        parent_asin="",
        title="",
        main_image_url="",
        price=None,
        rating=None,
        review_count=None,
        brand="",
        seller_name="",
        seller_origin="",
        category="",
        attributes={},
        launch_date=None,
        days_since_launch=None,
        fba_fee=None,
        monthly_units=None,
        monthly_gmv=None,
        description_text="",
        feature_ratings={},
        package_dimensions_cm=(),
        weight_g=None,
        material_raw="",
        dimension_raw="",
        weight_raw="",
        source_text="",
        source_raw_json=source_raw_json,
        parse_status=parse_status,
        parse_errors=parse_errors,
    )


def _parse_key_value_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key = ""
    current_value: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^：:]{1,40})[：:](.*)$", line)
        if match:
            if current_key:
                fields[current_key] = "\n".join(current_value).strip()
            current_key = match.group(1).strip()
            current_value = [match.group(2).strip()]
        elif current_key:
            current_value.append(line)
    if current_key:
        fields[current_key] = "\n".join(current_value).strip()
    return fields


def _field(fields: dict[str, str], *labels: str) -> str:
    for label in labels:
        value = _clean(fields.get(label))
        if value:
            return value
    return ""


def _walk_text_content(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "text" and isinstance(nested, str):
                yield nested
            else:
                yield from _walk_text_content(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_text_content(item)


def _texts_from_sse_raw_text(raw_text: str) -> list[str]:
    texts: list[str] = []
    for line in raw_text.splitlines():
        if not line.startswith("data:"):
            continue
        payload_text = line.removeprefix("data:").strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        texts.extend(_walk_text_content(payload))
    return texts


def _parse_json_object_prefix(value: str) -> dict[str, Any]:
    text = _clean(value)
    match = re.search(r"\{.*?\}", text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_dimensions_cm(value: str) -> tuple[float, ...]:
    numbers = re.findall(r"\d+(?:\.\d+)?", _clean(value))
    return tuple(float(number) for number in numbers[:3])


def _parse_float(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    normalized = text.replace(",", "").replace("$", "").replace("%", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    return float(match.group(0))


def _parse_int(value: object) -> int | None:
    number = _parse_float(value)
    if number is None:
        return None
    return int(number)


def _parse_date(value: object) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _asin_from_path(path: Path) -> str:
    return path.name.split("_", 1)[0].strip()
