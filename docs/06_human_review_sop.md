# 06. 人审 SOP

## 每周审核对象

1. Top 搜索量低置信词
2. 新增高增长词
3. 聚类候选标签
4. 线上严重误标 case
5. 合并/拆分建议

## 审核决策

### approve_new_tag

稳定需求、边界清楚、非同义、有业务价值。

### merge_to_existing

只是 alias 或同义词。

### split_cluster

聚类混入多个对象、地点或产品形态。

### reject

非收纳、噪声、临时热点、仅颜色/尺寸/风格。

## 输出

写入：

```text
review/candidate_tag_review_template.csv
review/human_labeling_template.csv
```

## Niche Opportunity 审核

产品机会判断使用另一条审核流，不写入 taxonomy review template。

每周产品开发会先确认 `confirmed_niche_boundary_v1.csv`：

1. 保留属于同一具体场景需求的 included keywords。
2. 排除相邻但不同产品形态的 excluded keywords。
3. 标记混入 Top20 但不属于当前产品形态的 invalid ASIN。

系统生成 `<niche_id>_decision_card.md` 后，运营经理记录结论：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src \
python scripts/run_niche_opportunity.py record-review \
  --niche-id under_bed_shoe_storage \
  --reviewer operations \
  --final-conclusion defer \
  --rejection-type evidence_not_enough \
  --review-comment "Need supplier cost confirmation"
```

输出：

```text
opportunity_review_v1.csv
calibration_backlog_v1.csv
```

`defer/reject` 必须写明 `rejection_type` 或 `review_comment`，用于后续校准立项卡片。
