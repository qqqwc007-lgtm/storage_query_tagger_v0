# 02. Taxonomy 设计说明

## 标签元数据

每个标签都应有：

```yaml
tag_id: obj_shoes
dimension: target_object
canonical_name: Shoes
zh_name: 鞋类
aliases: [shoe, shoes, footwear]
definition: 用户明确表达要收纳、整理、展示或存放鞋类。
positive_examples: [shoe rack, shoe organizer, shoe storage]
negative_examples: [shoes for women, nike shoes men]
status: active
```

## MECE 原则

- 维度内尽量 MECE：`rack`、`shelf`、`cabinet` 边界清晰。
- 维度间允许组合：`shoe rack for entryway` 可同时标 shoes、rack、entryway。
- Scenario 维度必须克制，避免复合标签爆炸。

## 新增标签判断

候选新标签需满足：

1. 搜索量或增长率达到阈值。
2. 有稳定表达和清晰边界。
3. 与已有标签不是简单同义。
4. 有独立运营/召回/推荐价值。
5. 能写正例和负例。
6. 人审通过。

## 不应新增的标签

- 颜色：white, black
- 普通尺寸：large, small
- 普通风格：modern, farmhouse
- 可由原子标签组合表达的长词
- 临时热点且不稳定的词

## 版本治理

所有结果必须保留：

```text
taxonomy_version
tag_id
dimension
confidence
evidence
```

标签合并、拆分、废弃必须有 lineage。
