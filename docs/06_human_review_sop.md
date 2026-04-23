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
