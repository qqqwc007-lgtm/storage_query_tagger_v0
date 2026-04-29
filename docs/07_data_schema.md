# 07. 数据 Schema

## 输入

最低字段：

```text
query
```

可选字段：

```text
query_id
rank
search_volume
locale
marketplace
date
clicked_category
clicked_product_title
```

## 打标输出

```text
query
normalized_query
domain_label
domain_confidence
tags
tag_ids
coverage_status
needs_review
taxonomy_version
```

`tags` 为 JSON 字符串：

```json
[
  {
    "dimension": "target_object",
    "tag_id": "obj_shoes",
    "canonical_name": "Shoes",
    "confidence": 0.95,
    "evidence": "shoe",
    "source": "alias"
  }
]
```

## 黄金集

```text
query
expected_domain_label
expected_tag_ids
note
```

`expected_tag_ids` 使用英文分号分隔。

## Niche Opportunity v1 输入

`niche opportunity v1` 默认通过 `config/niche_opportunity_v1.yaml` 读取下游证据源。

### keyword_asin_fact_v1.csv

来自 `workflow_v1` dashboard 的 Top ASIN 事实表。最低需要：

```text
canonical_scenario_need
kw
kw中文翻译
rank
ASIN
标题
主图
品牌
卖家
价格
Units
GMV
ASIN_ASP
上架日期
上架天数
星级
评论数量
2025-Q3起新品
product_detail_status
product_detail_raw_json
keyword_top20_asin_list_json
source_record_json
```

### keyword_search_volume_history.csv

用于 24 个月需求趋势判断：

```text
search_term
month
search_volume
search_rank
marketplace
```

### product_detail_raw/*.json

Sorftime product detail raw cache。系统只读取 confirmed boundary 中涉及的 ASIN 文件，文件名格式：

```text
<ASIN>_product_detail_raw.json
```

解析字段包括标题、主图、价格、星级、评论数、材质、尺寸、重量、FBA fee、月销量、月销额、外包装尺寸和描述文本。

## Niche Opportunity v1 输出

### confirmed_niche_boundary_v1.csv

人工确认的 niche 边界。不存在时，`generate-card --keywords ...` 会 seed included keyword rows。

```text
niche_id
boundary_item_type
boundary_item_value
inclusion_status
system_reason
override_reason
reviewer
reviewed_at
```

约定：

- `boundary_item_type=keyword`，`inclusion_status=included` 表示纳入该关键词。
- `boundary_item_type=keyword`，`inclusion_status=excluded` 表示排除相邻但不属于该 niche 的关键词。
- `boundary_item_type=asin`，`inclusion_status=invalid` 表示该 ASIN 不属于当前产品形态，需要从决策证据中排除。

### <niche_id>_decision_card.md

一页 Markdown 立项卡片，包含：

```text
niche_id / niche_name
final conclusion
signal evidence table
sales summary
cost ceiling
top ASIN evidence
evidence gaps
```

VOC 在 v1 中明确显示为 `missing/not enabled in v1`，不会伪造自动抓取结果。

### decision_card_manifest_v1.json

按 `niche_id` upsert 的卡片索引：

```text
workflow_version
niche_id
niche_name
decision_card_path
generated_at
conclusion
decision_reason
market_signal_count
supply_chain_match
hard_veto
capped_by_proxy
selling_price_usd
suggested_purchase_cost_ceiling_usd
suggested_purchase_cost_ceiling_rmb
suggested_first_order_qty
cost_confidence
shipping_estimate_basis
```

### opportunity_review_v1.csv

运营审核记录：

```text
reviewed_at
reviewer
niche_id
review_outcome
system_conclusion
system_reason
rejection_type
review_comment
decision_card_path
```

`review_outcome` 只能是 `approve`、`defer`、`reject`。`defer/reject` 必须提供 `rejection_type` 或 `review_comment`。

### calibration_backlog_v1.csv

`defer/reject` 自动写入校准 backlog：

```text
created_at
reviewer
niche_id
review_outcome
rejection_type
review_comment
system_conclusion
decision_card_path
calibration_status
```

### niche_opportunity_quality_v1.json

运行质量报告，记录 source row counts、input/output paths、confirmed boundary 数量、ASIN 数量、parse status、missing/proxy evidence counts 和 elapsed seconds。
