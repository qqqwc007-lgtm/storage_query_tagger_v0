# 09. Niche Opportunity v1

## 目标

`niche opportunity v1` 是产品开发会使用的下游决策工作流。它不替代 taxonomy workflow，也不做批量市场机会排行；它只回答一个已经选定或人工确认的 niche：

> 这个 niche 值不值得继续做产品深挖或立项？

第一版锁定流程：

```text
selected or suggested niche
  -> confirmed boundary
  -> one-page decision card
  -> opportunity review log
  -> calibration backlog
```

## 非目标

- 不生成批量 niche 排名
- 不自动抓取 VOC
- 不生成 PRD handoff
- 不提供 Web UI
- 不把运营审核流写入数据库
- 不做图片识别式结构拆解

## 数据来源

默认配置在 `config/niche_opportunity_v1.yaml`。

| Source | 默认路径 | 用途 |
|---|---|---|
| `keyword_asin_fact` | `outputs/workflow_v1/scenario_need_market_capacity_report/dashboard/keyword_asin_fact_v1.csv` | Top ASIN、标题、图片、价格、Units、GMV、新品标记 |
| `keyword_search_volume_history` | `outputs/workflow_v1/keyword_search_volume_history.csv` | 关键词搜索量趋势 |
| `product_detail_raw_dir` | `outputs/sorftime_product_detail_cache/US/product_detail_raw` | ASIN 详情、材质、尺寸、FBA、重量、产品描述 |
| `keyword_sales_summary` | `outputs/workflow_v1/scenario_need_market_capacity_report/dashboard/keyword_sales_summary_v1.csv` | 保留为 source evidence |
| `scenario_sales_summary` | `outputs/workflow_v1/scenario_need_market_capacity_report/dashboard/scenario_sales_summary_v1.csv` | 保留为 source evidence |

决策卡片的销售摘要会从 confirmed boundary 里的关键词和 ASIN 重新计算，不直接复用原始 summary 行。

## 运行前提

1. 已经跑过 `workflow v1`，并有 `keyword_asin_fact_v1.csv`。
2. 已经有 `keyword_search_volume_history.csv`。
3. 已经有 Sorftime product detail raw cache。
4. 产品开发先给出一个 niche id 和一组初始关键词。

## 生成决策卡片

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src \
python scripts/run_niche_opportunity.py generate-card \
  --niche-id under_bed_shoe_storage \
  --niche-name "under bed shoe storage" \
  --keywords "under bed shoe storage,underbed shoe storage,shoe organizer under bed,shoe storage under bed" \
  --output-dir outputs/workflow_v1/niche_opportunity_workflow
```

行为：

- 如果 `confirmed_niche_boundary_v1.csv` 不存在，或没有当前 `niche_id`，系统会用 `--keywords` seed included keyword rows。
- 如果 boundary 已存在，系统尊重人工维护的 included/excluded keyword 和 invalid ASIN。
- 系统只读取 confirmed boundary 中涉及的 ASIN raw JSON。
- 系统不会扫描全部 product raw cache。

## 确认 niche 边界

输出目录里的 `confirmed_niche_boundary_v1.csv` 是产品开发需要维护的边界文件。

典型行：

```csv
niche_id,boundary_item_type,boundary_item_value,inclusion_status,system_reason,override_reason,reviewer,reviewed_at
under_bed_shoe_storage,keyword,under bed shoe storage,included,seed_keyword,,system,2026-04-29T00:00:00Z
under_bed_shoe_storage,keyword,shoe rack,excluded,manual,not under-bed soft storage,wayne,2026-04-29T00:00:00Z
under_bed_shoe_storage,asin,B0BADASIN,invalid,manual,wrong product form,wayne,2026-04-29T00:00:00Z
```

人工确认建议：

- `included keyword`：属于同一个具体场景需求。
- `excluded keyword`：相邻但不是同一个 niche，例如鞋架、普通鞋盒、金属抽屉混入软质床底鞋收纳。
- `invalid ASIN`：Top20 里出现但不属于当前产品形态的 ASIN。

修改 boundary 后，重新运行 `generate-card` 即可重算卡片。

## 输出文件

| 文件 | 说明 |
|---|---|
| `<niche_id>_decision_card.md` | 一页 Markdown 决策卡片 |
| `decision_card_manifest_v1.json` | 按 `niche_id` upsert 的卡片索引 |
| `niche_opportunity_quality_v1.json` | 运行质量、source row counts、parse status、missing/proxy evidence counts |
| `confirmed_niche_boundary_v1.csv` | 人工确认的关键词和 ASIN 边界 |
| `opportunity_review_v1.csv` | 运营审核记录 |
| `calibration_backlog_v1.csv` | defer/reject 自动进入校准 backlog |

## 决策卡片内容

卡片包含：

- 系统结论：`推荐立项`、`建议深挖`、`暂缓观察`、`风险/否决`
- 信号表：需求趋势、ASP proxy、新品销量、结构升级、供应链匹配
- 销售摘要：confirmed boundary 内 GMV、Units、ASP、新品 GMV、Units、ASP
- 成本上限：售价、referral fee、FBA、头程、损耗预留、30% 毛利目标后的采购成本上限
- Top ASIN evidence：ASIN、rank、新品标记、Units、GMV、材质、尺寸、parse status
- Evidence gaps：VOC 缺失、proxy evidence、cost missing fields

## 成本规则

成本默认值在 `config/niche_opportunity_v1.yaml`：

```text
target_gross_margin_rate = 0.30
referral_fee_rate = 0.15
storage_return_loss_reserve_rate = 0.04
first_leg_rmb_per_kg = 8
exchange_rate = 7.20
chargeable_weight_divisor_cm3_per_kg = 6000
```

采购成本上限：

```text
overall_ASP
  - referral_fee
  - FBA_fulfillment_fee
  - first_leg_shipping_estimate
  - storage_return_loss_reserve
  - target_gross_margin
```

头程按商品外包装尺寸和重量估算计费重；缺少外包装时会 fallback 到商品尺寸，并在卡片中标注 estimate basis。

## 记录运营审核

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

规则：

- `--final-conclusion` 只能是 `approve`、`defer`、`reject`。
- 如果同目录存在 `decision_card_manifest_v1.json`，review log 会回填该 niche 的系统结论、系统理由和卡片路径，便于后续校准。
- `defer/reject` 必须提供 `--rejection-type` 或 `--review-comment`。
- `defer/reject` 会同时写入 `opportunity_review_v1.csv` 和 `calibration_backlog_v1.csv`。
- CSV 输出会转义以 `=`、`+`、`-`、`@` 开头的文本，避免表格公式注入。

## 测试

完整验证命令：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src pytest -q
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 PYTHONPATH=src \
python -m ruff check src/storage_taxonomy/niche_opportunity scripts/run_niche_opportunity.py tests/test_niche_opportunity_*.py
```

当前 Phase A-E 验证结果：

```text
66 passed
ruff: All checks passed
```

## 后续扩展点

- 批量 niche list：等单张卡片质量校准后再做。
- 自动 VOC：第一版先显示 missing，不伪造 coverage。
- PRD handoff：等运营审核字段稳定后再做。
- Review DB：第一版只用 CSV log。
