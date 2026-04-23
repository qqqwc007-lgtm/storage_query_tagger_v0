# 08. Workflow v1 拆解与落地

## 目标

把 `storage_taxonomy_prd_final_v1.md` 从文档变成可执行的本地 workflow，稳定产出：

- `kw.csv`
- `st.csv`
- `diff.csv`
- `review_queue.csv`
- `candidate_values.csv`

## 现状 vs v1 差距

仓库原始状态只覆盖了 `v0` 单边 query tagging：

- 输入只有一列 query
- 输出是 faceted tags，不是固定 7 字段
- 没有 keyword / title 双边对齐
- 没有字段级 diff
- 没有 review queue

v1 新增了一层 `storage_taxonomy` 包，保留 v0 原型资产，同时补上 workflow 面。

## 模块拆分

### 1. 输入标准化

文件：

- `src/storage_taxonomy/input_parser.py`
- `scripts/prepare_local_inputs.py`

职责：

- 读取原始 Amazon 导出
- 跳过第一行 metadata
- 提取 `search_term`
- 把 Top 商品拆成逐行 `search_term + asin + title`

产物：

- `data/local/keyword_input.csv`
- `data/local/top_asin_input.csv`

### 2. Canonical registry

文件：

- `config/taxonomy/canonical_values_v0.json`
- `config/taxonomy/aliases_v0.json`
- `config/taxonomy/rollups_v0.json`
- `config/taxonomy/negative_rules_v0.json`
- `config/rules/*.yaml`
- `src/storage_taxonomy/taxonomy_registry.py`

职责：

- 统一加载 canonical values / aliases / rollups / negative rules
- 提供 longest alias 优先匹配
- 提供 roll-up 判断

### 3. 7 字段抽取

文件：

- `src/storage_taxonomy/domain_gate.py`
- `src/storage_taxonomy/canonical_extractor.py`

职责：

- `mapped / partial / ambiguous / not_storage`
- 输出固定 7 字段
- 保留 `confidence / matched_aliases / unmapped_phrases / evidence`

### 4. 双边 diff

文件：

- `src/storage_taxonomy/diff_engine.py`

职责：

- 比较 keyword 和 title 的字段值
- 输出 `exact_match / rollup_match / missing_value / true_conflict`
- 支持 `产品形态关键词` 的集合比较

### 5. Review queue

文件：

- `src/storage_taxonomy/review_queue.py`

职责：

- 所有 `true_conflict` 必进队列
- `missing_value` 按核心字段 / Top rank / 高频模式筛选
- 高价值 `ambiguous keyword` 入队

### 6. Candidate discovery

文件：

- `src/storage_taxonomy/candidate_discovery.py`

职责：

- 从 `unmapped_phrases`
- 从 `true_conflict`
- 生成 `candidate_values.csv`

### 7. 一键 workflow

文件：

- `src/storage_taxonomy/workflow.py`
- `src/storage_taxonomy/cli.py`
- `scripts/run_workflow.py`

职责：

- 串联 extract -> diff -> review queue -> candidate discovery
- 写出全部 CSV 和 `metrics_summary.json`

## 执行顺序

```text
原始 CSV
  -> prepare_local_inputs.py
  -> keyword_input.csv + top_asin_input.csv
  -> run_workflow.py
  -> kw.csv / st.csv / diff.csv / review_queue.csv / candidate_values.csv
```

## 当前限制

1. v1 仍是规则驱动 baseline，不含 LLM 自动命名。
2. 候选新值只是候选，不会自动写回 taxonomy。
3. 当前 workflow 以内存 DataFrame 为主，适合本地批处理和中等规模迭代。
4. 如果后续跑更大批次，需要再加 chunked processing 和增量 rerun。

## 下一步建议

1. 补 100 条 keyword 金标和 100 条 title 金标。
2. 先跑一轮真实 storage 数据，观察 `true_conflict_rate`。
3. 针对高频 conflict 更新 alias / rollup / negative rules。
4. 等 review queue 收敛后，再考虑 embedding 或 LLM 辅助命名。
