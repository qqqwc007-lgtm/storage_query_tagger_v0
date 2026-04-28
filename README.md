# Storage Query Tagger v0

这是一个面向 **Storage & Organization / 收纳整理** 搜索词的初始项目框架。
它把用户搜索词打成多维标签，用于商品推荐、类目运营、用户需求洞察和搜索召回。

## 核心流程

```text
搜索词输入
  → 预处理 normalize
  → Domain Gate: storage_related / not_storage / ambiguous
  → 多维规则打标
  → 低置信/未覆盖词输出
  → 聚类发现候选新标签
  → 人工审核
  → Taxonomy 更新
```

## 目录结构

```text
storage_query_tagger_v0/
├── README.md
├── requirements.txt
├── pyproject.toml
├── config/
│   ├── taxonomy_v0.yaml
│   ├── rules_v0.yaml
│   ├── thresholds.yaml
│   ├── model_config.yaml
│   └── niche_opportunity_v1.yaml
├── docs/
│   ├── 00_project_overview.md
│   ├── 01_v0_tagging_boundary.md
│   ├── 02_taxonomy_design.md
│   ├── 03_labeling_guideline.md
│   ├── 04_self_learning_workflow.md
│   ├── 05_metrics_and_acceptance.md
│   ├── 06_human_review_sop.md
│   ├── 07_data_schema.md
│   ├── 08_workflow_v1_breakdown.md
│   └── 09_niche_opportunity_v1.md
├── src/storage_tagger/
│   ├── schemas.py
│   ├── config_loader.py
│   ├── preprocessing.py
│   ├── domain_gate.py
│   ├── rule_tagger.py
│   ├── tagger.py
│   ├── evaluation.py
│   ├── new_tag_discovery.py
│   ├── cli.py
│   └── utils.py
├── scripts/
│   ├── run_tagging_demo.py
│   ├── evaluate_golden_set.py
│   ├── discover_new_tags.py
│   ├── run_workflow.py
│   └── run_niche_opportunity.py
├── data/sample/
│   ├── sample_queries.csv
│   └── golden_set_example.csv
├── review/
│   ├── candidate_tag_review_template.csv
│   └── human_labeling_template.csv
├── outputs/
├── notebooks/
└── tests/
```

## 快速开始

```bash
cd storage_query_tagger_v0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python scripts/run_tagging_demo.py \
  --input data/sample/sample_queries.csv \
  --output outputs/sample_tagged_queries.csv

PYTHONPATH=src python scripts/evaluate_golden_set.py \
  --input data/sample/golden_set_example.csv \
  --output outputs/golden_eval_report.json

PYTHONPATH=src python scripts/discover_new_tags.py \
  --input outputs/sample_tagged_queries.csv \
  --output outputs/candidate_tag_clusters.csv
```

也可以安装为命令行工具：

```bash
pip install -e .
storage-tagger tag --input data/sample/sample_queries.csv --output outputs/sample_tagged_queries.csv
storage-tagger eval --input data/sample/golden_set_example.csv --output outputs/golden_eval_report.json
storage-tagger discover --input outputs/sample_tagged_queries.csv --output outputs/candidate_tag_clusters.csv
```

## 文档索引

- [docs/00_project_overview.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/00_project_overview.md)：项目总览、v0/v1/niche opportunity 边界
- [docs/01_v0_tagging_boundary.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/01_v0_tagging_boundary.md)：v0 打标边界
- [docs/02_taxonomy_design.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/02_taxonomy_design.md)：taxonomy 设计
- [docs/03_labeling_guideline.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/03_labeling_guideline.md)：人工标注准则
- [docs/04_self_learning_workflow.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/04_self_learning_workflow.md)：自学习闭环
- [docs/05_metrics_and_acceptance.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/05_metrics_and_acceptance.md)：指标与验收
- [docs/06_human_review_sop.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/06_human_review_sop.md)：人审 SOP
- [docs/07_data_schema.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/07_data_schema.md)：输入输出 schema
- [docs/08_workflow_v1_breakdown.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/08_workflow_v1_breakdown.md)：workflow v1 拆解
- [docs/09_niche_opportunity_v1.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/09_niche_opportunity_v1.md)：niche opportunity v1 使用说明
- [docs/niche_opportunity_phase_e_todo.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/niche_opportunity_phase_e_todo.md)：niche opportunity Phase E 交付记录
- [docs/storage_keyword_distribution_dashboard_design.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/storage_keyword_distribution_dashboard_design.md)：关键词分布看板设计
- [storage_taxonomy_prd_final_v1.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/storage_taxonomy_prd_final_v1.md)：taxonomy workflow v1 PRD

## v0 打标原则

v0 采用偏保守边界：

1. 只有明确表达 `storage`、`organization`、`organizer`、`rack`、`shelf`、`cabinet`、`bin`、`basket`、`box`、`container`、`caddy`、`drawer organizer`、`hanger`、`hook`、`display shelf` 等收纳意图或收纳产品形态的 query 才进入 `storage_related`。
2. 单独物品词不直接入域，例如 `lego`、`makeup`、`shoes for women`。
3. 负例优先，例如 `old spice deodorant`、`under cabinet lighting`、`trash bags`。
4. v0 只输出显式证据，不强推断地点。例如 `food storage containers with lids` 不直接高置信标为 `kitchen`。
5. 新标签不能自动上线，只进入候选审核池。

详见 `docs/01_v0_tagging_boundary.md`。

## Workflow v1

仓库现在同时包含基于 `storage_taxonomy_prd_final_v1.md` 落地的 `workflow v1`。

### 推荐数据目录

```text
data/local/
├── 原始 Amazon 导出.csv
├── keyword_input.csv
└── top_asin_input.csv
```

如果你手头只有一张原始 Amazon Search Query Performance 导出，先拆输入：

```bash
PYTHONPATH=src python scripts/prepare_local_inputs.py
```

这会自动读取 `data/local/` 中唯一的原始 CSV，并生成：

- `data/local/keyword_input.csv`
- `data/local/top_asin_input.csv`

### 一键运行 v1 workflow

```bash
PYTHONPATH=src python scripts/run_workflow.py \
  --keyword-input data/local/keyword_input.csv \
  --top-asin-input data/local/top_asin_input.csv \
  --output-dir outputs/workflow_v1
```

也可以使用 CLI：

```bash
storage-taxonomy run \
  --keyword-input data/local/keyword_input.csv \
  --top-asin-input data/local/top_asin_input.csv \
  --output-dir outputs/workflow_v1
```

### v1 产物

`outputs/workflow_v1/` 默认会生成：

- `kw.csv`
- `st.csv`
- `diff.csv`
- `review_queue.csv`
- `candidate_values.csv`
- `metrics_summary.json`

### v1 模块

`src/storage_taxonomy/` 下已实现：

- `input_parser.py`：把原始 Amazon 导出拆成两张标准输入表
- `taxonomy_registry.py`：加载 canonical values / aliases / rollups / negative rules
- `canonical_extractor.py`：抽取固定 7 字段
- `diff_engine.py`：生成字段级 diff
- `review_queue.py`：筛选 true conflict 和高价值 missing
- `candidate_discovery.py`：从 unmapped/conflict 生成候选新值
- `workflow.py`：串起完整本地 workflow

更完整的拆解见 [docs/08_workflow_v1_breakdown.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/08_workflow_v1_breakdown.md)。

## Niche Opportunity v1

`niche_opportunity` 是 `workflow v1` 的下游产品机会判断流程。它不做批量市场排行，也不自动抓 VOC；第一版只服务一个已经选定或人工确认的 niche：

```text
confirmed niche boundary
  -> one-page decision card
  -> opportunity review log
  -> calibration backlog
```

默认读取这些已有产物：

- `outputs/workflow_v1/scenario_need_market_capacity_report/dashboard/keyword_asin_fact_v1.csv`
- `outputs/workflow_v1/keyword_search_volume_history.csv`
- `outputs/sorftime_product_detail_cache/US/product_detail_raw/*.json`

生成一个 niche 的立项卡片：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src \
python scripts/run_niche_opportunity.py generate-card \
  --niche-id under_bed_shoe_storage \
  --niche-name "under bed shoe storage" \
  --keywords "under bed shoe storage,underbed shoe storage,shoe organizer under bed,shoe storage under bed" \
  --output-dir outputs/workflow_v1/niche_opportunity_workflow
```

记录运营审核结论：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src \
python scripts/run_niche_opportunity.py record-review \
  --niche-id under_bed_shoe_storage \
  --reviewer operations \
  --final-conclusion defer \
  --rejection-type evidence_not_enough \
  --review-comment "Need supplier cost confirmation" \
  --output-dir outputs/workflow_v1/niche_opportunity_workflow
```

默认输出：

- `confirmed_niche_boundary_v1.csv`
- `<niche_id>_decision_card.md`
- `decision_card_manifest_v1.json`
- `opportunity_review_v1.csv`
- `calibration_backlog_v1.csv`
- `niche_opportunity_quality_v1.json`

更完整的使用说明见 [docs/09_niche_opportunity_v1.md](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/09_niche_opportunity_v1.md)。
