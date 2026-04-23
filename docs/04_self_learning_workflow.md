# 04. 自学习流程

## 候选池来源

```text
domain_label = ambiguous
coverage_status = partial
coverage_status = needs_review
needs_review = true
高搜索量低置信 query
新增长 query
人工标注为 unknown/other 的 query
```

## 流程

```text
候选池
  → TF-IDF/Embedding 向量化
  → KMeans/HDBSCAN/BERTopic 聚类
  → 生成候选标签卡片
  → 与已有标签去重
  → 人审 approve/reject/merge/split
  → Taxonomy Registry 更新
  → 规则库/训练集/评估集更新
```

## 候选标签卡片字段

```text
candidate_tag_name
dimension
parent_tag_id
definition
positive_examples
negative_examples
cluster_size
top_queries
top_terms
similar_existing_tags
recommended_action
review_status
```

## 人审动作

```text
approve_new_tag
merge_to_existing
split_cluster
reject
rename
add_alias
add_negative_example
```
