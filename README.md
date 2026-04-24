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
├── AGENTS.md
├── Makefile
├── README.md
├── pyproject.toml
├── requirements.txt
├── config/
│   ├── rules/
│   ├── taxonomy/
│   └── model_config.yaml
├── data/
│   ├── sample/
│   └── local/              # 本地原始数据，已 gitignore
├── docs/
│   ├── README.md
│   ├── 00_project_overview.md
│   ├── 01_v0_tagging_boundary.md
│   ├── 02_taxonomy_design.md
│   ├── 03_labeling_guideline.md
│   ├── 04_self_learning_workflow.md
│   ├── 05_metrics_and_acceptance.md
│   ├── 06_human_review_sop.md
│   ├── 07_data_schema.md
│   └── 08_workflow_v1_breakdown.md
├── src/storage_tagger/
│   └── ...
├── src/storage_taxonomy/
│   └── ...
├── scripts/
│   └── ...
├── review/
│   ├── candidate_tag_review_template.csv
│   └── human_labeling_template.csv
├── outputs/                # 派生产物，只保留 .gitkeep
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

## v0 打标原则

v0 采用偏保守边界：

1. 只有明确表达 `storage`、`organization`、`organizer`、`rack`、`shelf`、`cabinet`、`bin`、`basket`、`box`、`container`、`caddy`、`drawer organizer`、`hanger`、`hook`、`display shelf` 等收纳意图或收纳产品形态的 query 才进入 `storage_related`。
2. 单独物品词不直接入域，例如 `lego`、`makeup`、`shoes for women`。
3. 负例优先，例如 `old spice deodorant`、`under cabinet lighting`、`trash bags`。
4. v0 只输出显式证据，不强推断地点。例如 `food storage containers with lids` 不直接高置信标为 `kitchen`。
5. 新标签不能自动上线，只进入候选审核池。

详见 `docs/01_v0_tagging_boundary.md`。

## Workflow v1

仓库现在同时包含 `workflow v1`，用于把 Amazon 搜索词和 Top ASIN 标题按同一套 canonical taxonomy 抽取、diff，并生成复核队列。

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

如果全量关键词太大，正式 workflow 前先只保留搜索频率排名前 20w 的关键词，并同步裁剪 top ASIN 行：

```bash
PYTHONPATH=src python scripts/reduce_workflow_inputs.py \
  --mode rank-cap \
  --max-search-frequency-rank 200000 \
  --output-dir data/local/reduced
```

这会生成：

- `data/local/reduced/keyword_input.csv`
- `data/local/reduced/top_asin_input.csv`
- `data/local/reduced/selection_summary.json`

如果已经跑完一次冷启动，可以用冷启动产物 `kw.csv` 把样本缩到收纳相关关键词。默认 `recall` 会保留 `mapped`、`partial`、`ambiguous`，适合继续发现 taxonomy 漏覆盖；如果只要干净样本，用 `--scope strict` 只保留 `mapped`、`partial`。

```bash
PYTHONPATH=src python scripts/reduce_workflow_inputs.py \
  --mode storage-scope \
  --keyword-input data/local/keyword_input.csv \
  --top-asin-input data/local/top_asin_input.csv \
  --cold-start-kw outputs/workflow_v1_full/kw.csv \
  --scope recall \
  --max-search-frequency-rank 200000 \
  --output-dir data/local/reduced
```

### 一键运行 v1 workflow

```bash
PYTHONPATH=src python scripts/run_workflow.py \
  --keyword-input data/local/keyword_input.csv \
  --top-asin-input data/local/top_asin_input.csv \
  --output-dir outputs/workflow_v1
```

如需同时接入 Sorftime 的关键词历史搜索排名和搜索容量：

```bash
PYTHONPATH=src python scripts/run_workflow.py \
  --keyword-input data/local/keyword_input.csv \
  --top-asin-input data/local/top_asin_input.csv \
  --output-dir outputs/workflow_v1 \
  --with-keyword-metrics \
  --keyword-metrics-amz-site US
```

这会额外生成 `outputs/workflow_v1/keyword_metrics.csv`，表头固定为：

```text
关键词,时间,关键词搜索排名,关键词搜索容量
```

`时间` 会规范为 `YYYY-MM`，例如 `2024-04`。

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
- `keyword_metrics.csv`：可选，使用 `--with-keyword-metrics` 时生成

### v1 模块

`src/storage_taxonomy/` 下已实现：

- `input_parser.py`：把原始 Amazon 导出拆成两张标准输入表
- `taxonomy_registry.py`：加载 canonical values / aliases / rollups / negative rules
- `canonical_extractor.py`：抽取固定 7 字段
- `diff_engine.py`：生成字段级 diff
- `review_queue.py`：筛选 true conflict 和高价值 missing
- `candidate_discovery.py`：从 unmapped/conflict 生成候选新值
- `keyword_metrics.py`：调用 Sorftime `keyword_trend` 并生成关键词历史排名/容量表
- `workflow.py`：串起完整本地 workflow

更完整的拆解见 [docs/08_workflow_v1_breakdown.md](docs/08_workflow_v1_breakdown.md)。
