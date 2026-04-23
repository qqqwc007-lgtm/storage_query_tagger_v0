# 00. 项目总览

## 项目目标

构建一个可持续迭代的搜索词多维打标系统，对 Storage & Organization 相关 query 输出结构化标签。

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
