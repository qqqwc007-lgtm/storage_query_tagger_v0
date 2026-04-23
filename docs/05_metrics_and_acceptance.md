# 05. 指标与验收标准

## 离线指标

| 指标 | 说明 |
|---|---|
| Domain Gate Precision / Recall | 是否正确识别收纳词 |
| Per-dimension F1 | 各维度单独评估 |
| Micro-F1 | 多标签总体准确 |
| Volume-weighted F1 | 按搜索量加权 |
| Exact Match | 所有标签完全匹配 |
| Ambiguous Accuracy | 模糊词是否不乱猜 |

## 覆盖率

```text
keyword_coverage
search_volume_coverage
unknown_rate
low_confidence_rate
needs_review_rate
```

## 稳定性

```text
tag_assignment_churn
taxonomy_churn
duplicate_tag_rate
human_override_rate
```

## v0 建议验收线

```text
Domain Gate Precision >= 0.90
核心高频 query 覆盖率 >= 0.70
严重误标率 <= 0.10
```
