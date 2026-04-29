# 00. 项目总览

## 项目目标

构建一个可持续迭代的搜索词多维打标系统，对 Storage & Organization 相关 query 输出结构化标签。

当前仓库包含三条连续但边界不同的工作流：

- `v0`：单边 query tagging baseline，用于快速判断 query 是否收纳相关并输出多维标签。
- `workflow v1`：本地 taxonomy workflow，用 keyword/title 双边事实生成 diff、review queue、candidate values。
- `niche opportunity v1`：workflow v1 的下游选定 niche 决策卡片，用人工确认的关键词/ASIN 边界生成产品机会判断、采购成本上限和运营 review log。

## v0 范围

v0 是 **Taxonomy + 规则库 + 人审闭环** 的 baseline，重点解决：

- 先判断是否收纳相关
- 输出核心维度标签
- 识别未覆盖和低置信 query
- 支持候选新标签发现
- 支持人工审核和版本治理

## 核心维度

| 维度 | 说明 | 示例 |
|---|---|---|
| domain | 是否收纳相关 | storage_related / not_storage / ambiguous |
| location | 使用场地/位置 | bathroom, closet, garage, under sink |
| target_object | 被收纳物 | shoes, makeup, jewelry, spices |
| product_form | 产品形态 | rack, shelf, cabinet, bin, container |
| purpose | 用途 | storage, organization, display |
| attribute | 属性 | with lid, stackable, glass, clear |
| scenario | 可运营复合场景 | closet organization, holiday storage |

## v0 非目标

- 不做完全自动标签上线
- 不追求长尾全覆盖
- 不强行把单一物品词解释为收纳需求
- 不把颜色、尺寸、风格等低价值修饰词扩成 Scenario

## Niche Opportunity v1 范围

`niche opportunity v1` 只处理已经选定或建议后人工确认的一个 niche：

```text
confirmed niche boundary
  -> one-page decision card
  -> opportunity review log
  -> calibration backlog
```

它复用已有 `workflow_v1` dashboard facts、24 个月关键词搜索量历史和 Sorftime product detail raw cache。系统会重算 confirmed boundary 内的销售摘要、信号、采购成本上限和首批采购数量建议。

非目标：

- 不输出批量 niche 排名
- 不自动抓取 VOC
- 不生成 PRD handoff
- 不提供 Web UI
- 不把运营 review 写入数据库

详见 [09. Niche Opportunity v1](/Users/wayneqqq/Desktop/storage_query_tagger_v0/docs/09_niche_opportunity_v1.md)。
