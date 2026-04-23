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
