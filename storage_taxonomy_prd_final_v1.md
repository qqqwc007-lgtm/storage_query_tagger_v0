# 收纳关键词与 Top ASIN 标题 Canonical Taxonomy Workflow 需求文档

**版本**：Final v1.0
**Taxonomy 冷启动版本**：v0
**日期**：2026-04-23
**适用阶段**：MVP / 本地原型验证
**主用户**：产品开发
**领域**：Storage & Organization / 收纳市场拆解

---

## 1. 文档目的

本文档定义一个面向产品开发的本地化 canonical taxonomy workflow，用于将 Amazon 搜索词 `keyword` 与对应 `Top ASIN title` 按同一套受控标签库抽取为固定 7 字段，并通过分层 diff 找出真正需要人工复核和标签库迭代的问题。

本项目的核心不是“更快地填 Excel”，而是解决以下三个问题：

1. **标签标准漂移**：同一类词在不同时间、不同人手里被写成不同标签。
2. **关键词侧与 ASIN 标题侧口径不一致**：keyword 与 top ASIN title 分开人工处理，最终难以稳定比较。
3. **复核队列过大**：所有不一致都被当成错误，导致人工无法聚焦真正冲突。

Final v1.0 的目标是先建立一个**可重复执行、可复核、可迭代**的最小闭环：

```text
本地输入文件
  -> canonical 标签抽取
  -> kw.csv / st.csv
  -> 分层 diff.csv
  -> 人工只审 true_conflict 与高价值 missing_value
  -> 更新标签库
  -> rerun
```

---

## 2. 项目定位与最终决策

### 2.1 最终定位

本项目 v1.0 是一个**本地 canonical taxonomy workflow**，不是全自动标签平台。

它服务的第一个明确用户是**产品开发**。因此 canonical truth 优先满足产品开发对 niche mapping 的细颗粒度要求；运营需要的大类视角通过后置 `roll-up parent` 聚合获得。

### 2.2 与上一版“自学习搜索词标签系统”的差异

| 主题 | 上一版方案 | Final v1.0 决策 |
|---|---|---|
| 系统目标 | 面向海量搜索词的多维自学习标签系统 | 先做本地 MVP workflow，稳定产出 kw/st/diff |
| 标签维度 | Location、Scenario、Purpose、Target Object、Product Form、Material、Attribute 等多维 facet | 对外固定为 7 个中文字段；内部可保留 domain、confidence、rollup、version 等元数据 |
| 主用户 | 搜索、推荐、运营、用户洞察均可使用 | v1 只优先服务产品开发的细分 niche mapping |
| 自动化程度 | 规则 + Embedding + LLM + 聚类 + 主动学习 | v1 以冷启动标签库 + 规则抽取 + 分层 diff + 人审 rerun 为主；新标签只生成候选，不自动上线 |
| 标签治理 | 可扩展 Taxonomy Registry | v1 用本地 JSON/YAML 标签库，但必须预留 alias、rollup、version、status、priority |
| 输出形态 | 多维 tag list / API 风格 | 固定本地 CSV：`kw.csv`、`st.csv`、`diff.csv` |
| 质量优化 | 准确率、覆盖率、稳定性、主动学习 | v1 主指标为 `true_conflict_rate` 与 review queue 缩减 |

### 2.3 版本命名统一

为避免 `v0` 和 `v1` 混用，Final 版本采用以下命名：

- **项目版本**：`workflow v1.0`
- **冷启动标签库版本**：`taxonomy v0`
- **规则版本**：`rules v0`
- **输出中必须带**：`taxonomy_version`

---

## 3. 范围与非范围

### 3.1 v1.0 必做范围

1. 读取本地 keyword 输入文件。
2. 读取本地 Top ASIN title 输入文件。
3. 使用同一套 canonical 标签库抽取固定 7 字段。
4. 输出 `kw.csv`。
5. 输出 `st.csv`。
6. 基于 keyword 与 ASIN title 的标签结果输出 `diff.csv`。
7. diff 类型至少包含：
   - `exact_match`
   - `rollup_match`
   - `missing_value`
   - `true_conflict`
8. 人工复核只聚焦：
   - 所有 `true_conflict`
   - 高价值 `missing_value`
9. 人工结论可沉淀为：
   - canonical 新值
   - alias
   - roll-up parent
   - negative rule
   - 字段边界修订
10. 支持 rerun，并记录标签库版本。

### 3.2 v1.0 不做范围

1. 不做前端平台。
2. 不做数据库系统。
3. 不接 Amazon API。
4. 不接真实账号。
5. 不做线上服务 API。
6. 不直接训练大型模型。
7. 不允许模型自动新增 canonical 值并直接上线。
8. 不把所有搜索词都强行映射到收纳标签。
9. 不把运营聚合口径作为 canonical truth。
10. 不追求一次性穷举所有长尾场景。

---

## 4. 目标用户与使用场景

### 4.1 主用户：产品开发

产品开发需要回答的问题包括：

- 收纳市场可以拆成哪些细分 niche？
- 哪些搜索词和哪些 ASIN 标题指向同一个 niche？
- 某个 niche 的商品形态、场地、对象、材质、功能是否有供需错配？
- 某些关键词和 Top ASIN 标题不一致时，是正常信息缺失，还是标签标准冲突？

### 4.2 次级用户：运营与分析

运营需要的通常是上层聚合，例如 `bathroom storage`、`kitchen storage`、`closet organization`。这些不作为 v1 的优先 canonical truth，而是通过 `rollup_parent` 从细颗粒度标签聚合获得。

### 4.3 最小可交付价值

只要系统能把人工复核范围从“所有不一致”缩小为“真正冲突 + 高价值缺失”，就达到了 v1 的核心价值。

---

## 5. 输入数据要求

### 5.1 keyword 输入

建议文件名：`keyword_input.csv`

必需字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_term` | string | Amazon 搜索词 |

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_frequency_rank` | number | 搜索频率排名，用于高价值 missing 判断 |
| `search_volume` | number | 搜索量；如没有可为空 |
| `date` | string | 数据日期 |
| `marketplace` | string | 站点，如 US |

### 5.2 Top ASIN title 输入

建议文件名：`top_asin_input.csv`

必需字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `search_term` | string | 与 keyword 输入可 join 的搜索词 |
| `asin` | string | ASIN |
| `title` | string | Top ASIN 标题 |

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `asin_rank` | number | 该 search term 下 ASIN 排名 |
| `click_share` | number | 点击份额，如有 |
| `conversion_share` | number | 转化份额，如有 |
| `date` | string | 数据日期 |
| `marketplace` | string | 站点，如 US |

### 5.3 Top ASIN 的处理边界

Final v1.0 决策：

- 系统支持一个 `search_term` 对应多个 ASIN title。
- diff 以 `search_term + asin` 为默认比较粒度。
- 如果业务只想看 Top 1，可在输入侧只保留 `asin_rank = 1`。
- v1 不强制做 Top N 聚合；Top N 聚合可以作为后置分析报表。

---

## 6. 固定 7 字段输出模型

### 6.1 固定 JSON Shape

每条 keyword 或 title 抽取后，必须符合以下结构：

```json
{
  "产品形态关键词": [],
  "产品使用场景": "",
  "存储对象": "",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": ""
}
```

字段类型要求：

| 字段 | 类型 | 空值 |
|---|---|---|
| `产品形态关键词` | array[string] | `[]` |
| `产品使用场景` | string | `""` |
| `存储对象` | string | `""` |
| `产品材质` | string | `""` |
| `尺寸` | string | `""` |
| `产品使用场地` | string | `""` |
| `产品功能` | string | `""` |

除 `产品形态关键词` 外，其余字段 v1 统一为单值字符串。多值情况暂不输出数组，以避免下游 Excel/CSV 解析混乱。

### 6.2 附加元数据字段

`kw.csv` 和 `st.csv` 中除 7 字段外，必须保留：

| 字段 | 类型 | 说明 |
|---|---|---|
| `taxonomy_version` | string | 标签库版本，如 `taxonomy_v0.1` |
| `mapping_status` | string | `mapped` / `partial` / `ambiguous` / `not_storage` / `needs_review` |

建议保留调试字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `confidence` | number | 总体置信度 |
| `matched_aliases` | string/json | 命中的 alias |
| `unmapped_phrases` | string/json | 未映射词组 |
| `evidence` | string/json | 字段级证据 |

---

## 7. 7 字段语义与边界

### 7.1 产品形态关键词

**定义**：表示商品形态、商品类型、产品 head noun 或明确的商品类型短语。该字段可以多值。

**可以填**：

- `rack`
- `shelf`
- `cabinet`
- `bin`
- `basket`
- `box`
- `bag`
- `container`
- `drawer organizer`
- `caddy`
- `cart`
- `hanger`
- `hook`
- `storage cabinet`
- `storage bin`
- `display shelf`

**不可以填**：

- 纯用途词：`storage`、`organization`
- 纯场地词：`bathroom`、`under bed`
- 纯对象词：`shoe`、`pill`、`toy`
- 纯材质词：`plastic`、`wood`
- 纯功能词：`foldable`、`stackable`

**Final 修订说明**：

早期示例中曾把 `storage` 或 `shoe storage` 放入 `产品形态关键词`。Final v1.0 为避免字段重叠，做如下修订：

- `storage` 不能单独作为产品形态关键词。
- `shoe storage` 更适合放入 `产品使用场景`。
- 只有当短语包含明确商品实体词时，才可进入产品形态，例如 `shoe storage cabinet` 中的 `storage cabinet`。

**示例**：

| 输入 | 产品形态关键词 |
|---|---|
| `shoe rack` | `["rack"]` |
| `shoe storage cabinet` | `["storage cabinet", "cabinet"]` |
| `under bed shoe storage` | `[]` |
| `storage bins with lids` | `["storage bin", "bin"]` |
| `lego display shelf` | `["display shelf", "shelf"]` |

### 7.2 产品使用场景

**定义**：表示用户任务、使用意图或可运营的 niche 场景。它回答“用户想解决什么收纳/整理/展示问题”。

**可以填**：

- `shoe storage`
- `pill storage`
- `toy organization`
- `lego display`
- `makeup organization`
- `pet food storage`
- `holiday ornament storage`
- `garage tool storage`
- `toilet storage`
- `under sink organization`

**不可以填**：

- 纯物理位置：`under bed`、`over toilet`
- 纯房间：`bathroom`、`kitchen`
- 纯产品形态：`cabinet`、`bin`
- 纯材质：`plastic`

**示例**：

| 输入 | 产品使用场景 | 说明 |
|---|---|---|
| `shoe rack` | `shoe storage` | shoe 是对象，rack 是形态，场景是鞋收纳 |
| `lego display shelf` | `lego display` | display 是任务意图 |
| `under sink organizer` | `under sink organization` | under sink 既可作为细场地，也可形成场景 |
| `over toilet storage cabinet` | `toilet storage` | over toilet 是场地，toilet storage 是场景 |
| `storage bins with lids` | `` | 只有通用收纳形态，无明确对象或细场景 |

### 7.3 存储对象

**定义**：表示被收纳、整理、存储、展示、保护的对象。

**可以填**：

- `shoe`
- `pill`
- `toy`
- `lego`
- `makeup`
- `jewelry`
- `food`
- `pet food`
- `spice`
- `tool`
- `ornament`
- `christmas tree`
- `towel`
- `clothes`

**不可以填**：

- 产品形态：`rack`、`cabinet`
- 场地：`garage`、`bathroom`
- 材质：`plastic`
- 品牌词：`old spice` 中不能抽 `spice`

**边界说明**：

- `running shoes for men` 中的 `shoe` 是商品购买对象，不是收纳对象；整体应为 `not_storage`。
- `shoe rack` 中的 `shoe` 是被收纳对象，应填 `shoe`。
- `lego` 单独出现时不能自动认为是 `lego storage`，应为 `ambiguous` 或 `not_storage`。

### 7.4 产品材质

**定义**：表示产品本身的材质 canonical 值。

**可以填**：

- `plastic`
- `wood`
- `metal`
- `fabric`
- `glass`
- `acrylic`
- `bamboo`
- `wire`
- `canvas`

**不可以填**：

- 颜色：`white`、`black`
- 透明特征：`clear`，除非标签库将其定义为材质，否则应进入功能/特征或暂不打标
- 风格：`farmhouse`、`modern`
- 表面效果：`wood look` 不是 `wood`，需按规则单独处理

**多材质处理**：

v1 由于字段为单值字符串，默认只输出一个主材质：

1. 如果命中受控复合材质 canonical，例如 `metal+wood`，可输出复合值。
2. 否则按标题词序或规则优先级输出主材质。
3. 其余材质进入 `unmapped_phrases` 或 debug 字段，供后续决定是否扩展。

### 7.5 尺寸

**定义**：表示尺寸、容量或规格信息。

**可以填**：

- `small`
- `medium`
- `large`
- `12 inch`
- `24 inch`
- `50L`
- `3 tier`
- `4 cube`
- `10 drawer`

**不可以填**：

- 颜色
- 材质
- 功能
- 纯数量包装，如 `2 pack`，除非业务明确将 pack 数作为规格管理

**Final 决策**：

- 数字尺寸、容量、层数、格数属于 v1 尺寸/规格。
- `small/medium/large` 只有显式出现时才打，不做推断。
- `2 pack`、`4 pack` 默认不进入尺寸字段，先放入未映射或 debug；如后续产品开发认为 pack 数重要，再扩展为 `规格/包装数量`。

### 7.6 产品使用场地

**定义**：表示产品使用、安放或适配的物理空间位置。v1 优先记录**最细显式场地**。

**可以填**：

- `under bed`
- `over toilet`
- `under sink`
- `inside cabinet`
- `over door`
- `wall mounted`
- `closet`
- `pantry`
- `garage`
- `bathroom`
- `kitchen`
- `laundry room`
- `entryway`

**Final 修订说明：关于 bathroom/kitchen 等上层空间**

早期草稿中倾向于“不在产品使用场地写上层空间，如 bathroom”。Final v1.0 修订为：

1. **如果有细场地，必须写细场地**：
   - `over toilet storage cabinet` -> `产品使用场地 = over toilet`，`bathroom` 只作为 roll-up parent。
   - `under sink organizer` -> `产品使用场地 = under sink`，不直接降级为 `kitchen` 或 `bathroom`。
2. **如果只有上层空间被显式表达，可以写上层空间作为 fallback canonical**：
   - `bathroom organizer` -> `产品使用场地 = bathroom`
   - `garage storage` -> `产品使用场地 = garage`
3. **比较时通过 roll-up 解决细粒度与粗粒度不一致**：
   - keyword=`over toilet`，title=`bathroom` -> `rollup_match`，不是 `true_conflict`。

这样既保留产品开发所需的细颗粒度，也不会丢掉 keyword/title 中仅出现的上层空间信息。

### 7.7 产品功能

**定义**：表示功能性、结构性或使用特征。它不是“用途”字段，不应把所有 `storage/organization` 都写成产品功能。

**可以填**：

- `vacuum`
- `foldable`
- `collapsible`
- `stackable`
- `rolling`
- `wheeled`
- `with lid`
- `airtight`
- `waterproof`
- `dustproof`
- `lockable`
- `hanging`
- `wall mounted`
- `display`
- `rotating`

**不可以填**：

- 纯场景：`shoe storage`
- 纯对象：`shoe`
- 纯场地：`under bed`
- 纯产品形态：`cabinet`
- 纯材质：`plastic`

**边界说明**：

- `display` 在 `lego display shelf` 中可作为功能，同时 `lego display` 是场景。
- `wall mounted` 可同时具有放置方式和功能特征。v1 默认放在 `产品功能`；如果业务更关注物理安装位置，也可在标签库中配置为 `产品使用场地`，但同一短语不能在同一版本中双写。

---

## 8. 入域、出域与模糊边界

### 8.1 入域条件

满足以下任一条件，可进入收纳 taxonomy：

1. 明确包含收纳/整理/展示/保存/保护相关意图：
   - `storage`
   - `organizer`
   - `organization`
   - `holder`
   - `rack`
   - `shelf`
   - `cabinet`
   - `bin`
   - `basket`
   - `box`
   - `container`
   - `bag`
   - `caddy`
   - `display`
2. 明确是典型收纳产品词：
   - `shoe rack`
   - `storage bins`
   - `food storage containers`
   - `makeup organizer`
   - `spice rack`
3. 明确表达收纳场景：
   - `under bed storage`
   - `over toilet storage cabinet`
   - `under sink organizer`
   - `garage tool storage`

### 8.2 出域条件

以下情况应标记为 `not_storage`：

1. 纯商品购买，不表达收纳：
   - `running shoes for men`
   - `lego set`
   - `makeup remover wipes`
2. 品牌词误伤：
   - `old spice deodorant` 不能因为包含 `spice` 而进入香料收纳。
3. 相关空间但非收纳产品：
   - `under cabinet lighting`
   - `garage door opener`
4. 相关对象但非收纳需求：
   - `dog food`
   - `kids toys`
   - `christmas ornaments`

### 8.3 模糊条件

以下情况默认 `ambiguous`，除非有点击类目、标题或人工规则支持：

- `lego`
- `makeup`
- `shoe`
- `toy`
- `bathroom`
- `garage`
- `kitchen cabinet`
- `desk`

模糊词不能强行打细标签。v1 允许输出空 7 字段，并设置：

```text
mapping_status = ambiguous
```

---

## 9. Canonical 标签库合同

冷启动标签库建议使用本地 JSON/YAML。每个 canonical 值至少包含：

| 字段 | 必需 | 说明 |
|---|---|---|
| `axis` | 是 | 对应 7 字段之一 |
| `canonical_value` | 是 | 标准值 |
| `aliases` | 是 | 同义词、变体、拼写 |
| `rollup_parent` | 否 | 上层聚合值 |
| `status` | 是 | `active` / `deprecated` / `candidate` / `rejected` |
| `priority` | 是 | 规则冲突时的优先级 |
| `example_terms` | 是 | 正例 |
| `negative_examples` | 建议 | 负例 |
| `notes` | 否 | 边界说明 |

示例：

```json
{
  "axis": "产品使用场地",
  "canonical_value": "over toilet",
  "aliases": ["above toilet", "over the toilet", "toilet top"],
  "rollup_parent": "bathroom",
  "status": "active",
  "priority": 90,
  "example_terms": [
    "over toilet storage cabinet",
    "above toilet bathroom shelf"
  ],
  "negative_examples": [
    "toilet paper",
    "toilet brush"
  ],
  "notes": "表示马桶上方空间，不能降级写 bathroom。"
}
```

---

## 10. 抽取规则优先级

v1 抽取时按以下顺序执行：

1. **文本标准化**
   - 小写化
   - 去多余符号
   - 单复数归一
   - 常见拼写归一
   - phrase matching，如 `under sink`、`over toilet`
2. **负向规则优先**
   - 如 `old spice`、`under cabinet lighting`、`running shoes`
3. **入域判断**
   - 输出 `mapped` / `partial` / `ambiguous` / `not_storage`
4. **最长 alias 优先匹配**
   - `over the toilet` 优先于 `toilet`
   - `storage cabinet` 优先于 `cabinet`
5. **字段约束检查**
   - 防止对象写入场地、材质写入形态等
6. **canonical 归一**
   - alias -> canonical_value
7. **roll-up 关系记录**
   - 不覆盖 canonical 值，仅用于 diff 与运营聚合
8. **置信度与 unmapped phrase 记录**
   - 供人工复核和新值发现使用

---

## 11. 输出文件要求

### 11.1 kw.csv

每行一条搜索词。

必需字段：

```text
search_term
产品形态关键词
产品使用场景
存储对象
产品材质
尺寸
产品使用场地
产品功能
taxonomy_version
mapping_status
```

建议字段：

```text
confidence
matched_aliases
unmapped_phrases
evidence
```

### 11.2 st.csv

每行一条 Top ASIN title。

必需字段：

```text
search_term
asin
title
产品形态关键词
产品使用场景
存储对象
产品材质
尺寸
产品使用场地
产品功能
taxonomy_version
mapping_status
```

建议字段：

```text
asin_rank
confidence
matched_aliases
unmapped_phrases
evidence
```

### 11.3 diff.csv

每行是一组 keyword 与 ASIN title 在一个字段上的比较结果。

必需字段：

```text
search_term
asin
field_name
kw_value
st_value
diff_type
review_required
rollup_parent_if_any
resolution_note
```

建议字段：

```text
asin_rank
search_frequency_rank
review_priority
kw_mapping_status
st_mapping_status
taxonomy_version
```

---

## 12. Diff 分类规则

### 12.1 exact_match

两边 canonical 值完全一致。

示例：

| field | kw_value | st_value | diff_type |
|---|---|---|---|
| `存储对象` | `shoe` | `shoe` | `exact_match` |
| `产品材质` | `plastic` | `plastic` | `exact_match` |

### 12.2 rollup_match

两边不完全一样，但存在 alias、parent-child 或 roll-up 关系。

示例：

| field | kw_value | st_value | 关系 | diff_type |
|---|---|---|---|---|
| `产品使用场地` | `over toilet` | `bathroom` | `over toilet -> bathroom` | `rollup_match` |
| `产品使用场地` | `above toilet` | `over toilet` | alias 归一后相同 | `exact_match` 或 `rollup_match`，取决于是否已归一 |
| `存储对象` | `boot` | `shoe` | `boot -> shoe` | `rollup_match` |

Final 决策：

- 如果 alias 已在抽取阶段归一为同一 canonical 值，则 diff 为 `exact_match`。
- 如果两边 canonical 值不同但存在 roll-up 关系，则 diff 为 `rollup_match`。

### 12.3 missing_value

一边有值，一边为空。

示例：

| field | kw_value | st_value | diff_type | 说明 |
|---|---|---|---|---|
| `产品材质` | 空 | `plastic` | `missing_value` | title 信息更丰富，不必然是错 |
| `尺寸` | 空 | `3 tier` | `missing_value` | ASIN 标题补充规格 |
| `产品使用场地` | `under bed` | 空 | `missing_value` | 标题未表达该位置 |

Final 决策：

- `missing_value` 默认不等于错误。
- 只有高价值 missing 才进入人工队列。

高价值 missing 的默认判定：

1. `search_frequency_rank` 进入当前批次 Top 20%；或
2. 该 missing 模式出现频次进入 Top 20%；或
3. 涉及核心字段：`产品使用场景`、`存储对象`、`产品使用场地`；或
4. 人工指定某字段本轮重点审。

### 12.4 true_conflict

两边都非空，指向不同 canonical 语义，且不存在 alias 或 roll-up 关系。

示例：

| field | kw_value | st_value | diff_type | 说明 |
|---|---|---|---|---|
| `产品材质` | `glass` | `plastic` | `true_conflict` | 材质冲突 |
| `存储对象` | `shoe` | `toy` | `true_conflict` | 对象冲突 |
| `产品使用场地` | `under bed` | `over toilet` | `true_conflict` | 场地冲突 |
| `产品形态关键词` | `["rack"]` | `["cabinet"]` | `true_conflict` | 形态明显不同，且无父子关系 |

`true_conflict` 是 v1 人工复核和标签库迭代的核心对象。

---

## 13. 人工复核规则

### 13.1 复核队列来源

人工只审：

1. 所有 `true_conflict`。
2. 高价值 `missing_value`。
3. `mapping_status = ambiguous` 且搜索量或频次高的词。
4. 系统生成的 candidate canonical value。

不审或低优先级处理：

- 普通 `exact_match`
- 普通 `rollup_match`
- 低价值 `missing_value`
- 明确 `not_storage`

### 13.2 人工可执行动作

| 动作 | 说明 | 后续影响 |
|---|---|---|
| `accept_kw` | 以 keyword 侧为准 | 更新规则或 title 侧纠偏 |
| `accept_st` | 以 ASIN title 侧为准 | 更新规则或 keyword 侧纠偏 |
| `create_alias` | 将某个短语加入 alias | 下轮归一 |
| `create_rollup` | 建立 parent-child 关系 | 下轮 diff 降级为 rollup_match |
| `create_canonical` | 新增 canonical 值 | 标签库版本升级 |
| `reject_mapping` | 标记为误伤或出域 | 形成 negative rule |
| `mark_ambiguous` | 明确为模糊，不强制分类 | 降低无意义冲突 |

### 13.3 人审沉淀要求

每次人工修改标签库，必须记录：

```text
change_id
change_type
axis
old_value
new_value
reason
examples
taxonomy_version_before
taxonomy_version_after
reviewer
review_date
```

---

## 14. Rerun Loop

v1 执行回路：

```text
1. 初始化 taxonomy v0
2. 跑 keyword -> kw.csv
3. 跑 Top ASIN title -> st.csv
4. 生成 diff.csv
5. 人工审 true_conflict + 高价值 missing_value
6. 更新标签库、alias、roll-up、negative rules
7. 升级 taxonomy_version
8. rerun 第 2-6 步
9. 观察 true_conflict_rate 与 review_queue_size
```

### 14.1 停止条件

主指标：

```text
true_conflict_rate < 10%
```

定义：

```text
true_conflict_rate = 有任一字段 true_conflict 的 keyword-ASIN pair 数 / 可比较 keyword-ASIN pair 总数
```

辅指标：

```text
review_queue_size 连续两轮下降
```

v1 可用条件：

1. `true_conflict_rate < 10%`；
2. review queue 不再爆炸；
3. 无新增高频 canonical 值必须补入；
4. 产品开发认为 niche mapping 已能用于初步市场拆解。

---

## 15. 新标签发现与自学习边界

### 15.1 v1 的“自学习”定义

v1 的自学习不是模型自动上线标签，而是：

```text
未覆盖 / 低置信 / 高频冲突
  -> candidate canonical values
  -> 人工审核
  -> 标签库更新
  -> rerun
```

### 15.2 候选新值来源

1. `unmapped_phrases` 高频短语。
2. 高频 `missing_value` 模式。
3. 高频 `true_conflict` 模式。
4. `ambiguous` 中反复出现的词组。
5. 规则无法覆盖但在 title/keyword 中稳定共现的短语。

### 15.3 候选新值输出

建议输出 `candidate_values.csv`：

```text
candidate_value
axis
source_phrases
example_terms
frequency
search_volume_sum
suggested_aliases
suggested_rollup_parent
suggested_action
review_status
```

### 15.4 严格限制

- candidate 不能直接进入 active taxonomy。
- LLM 或聚类只能辅助命名、解释和归并。
- 上线前必须经过人工确认。
- 被拒绝的 candidate 要记录 negative examples，避免反复出现。

---

## 16. 关键争议边界与 Final 决策

### 16.1 `产品使用场景` vs `产品使用场地`

| 输入 | 产品使用场景 | 产品使用场地 | 说明 |
|---|---|---|---|
| `over toilet storage cabinet` | `toilet storage` | `over toilet` | 场景是任务，场地是物理位置 |
| `bathroom organizer` | `bathroom organization` | `bathroom` | 只有上层场地时可 fallback |
| `under sink organizer` | `under sink organization` | `under sink` | under sink 可同时形成场景和细场地，但字段语义不同 |
| `garage tool storage` | `garage tool storage` | `garage` | 对象=tool，场地=garage |

### 16.2 `产品形态关键词` vs `产品使用场景`

| 输入 | 产品形态关键词 | 产品使用场景 | 说明 |
|---|---|---|---|
| `shoe rack` | `["rack"]` | `shoe storage` | rack 是产品形态 |
| `shoe storage` | `[]` | `shoe storage` | 没有明确产品形态 |
| `shoe storage cabinet` | `["storage cabinet", "cabinet"]` | `shoe storage` | cabinet 是形态 |
| `lego display shelf` | `["display shelf", "shelf"]` | `lego display` | shelf 是形态，display 是场景/功能 |

### 16.3 `产品功能` vs 原先 Purpose 维度

上一版曾有 `Purpose`，如 storage、organization、display、dust protection。Final v1.0 不单独输出 Purpose 字段：

- `storage/organization` 通常进入 `产品使用场景`，如 `shoe storage`、`makeup organization`。
- `display` 可进入 `产品功能`，并与对象组合形成 `产品使用场景`，如 `lego display`。
- `dustproof`、`waterproof`、`airtight`、`with lid` 进入 `产品功能`。

### 16.4 `bathroom` 是否可以进入产品使用场地

Final 决策：可以，但仅作为 fallback。

- 有细位置时：写细位置，不写上层空间。
- 只有上层空间时：允许写上层空间。
- 细位置与上层空间对比时：通过 roll-up 归为 `rollup_match`。

### 16.5 `missing_value` 是否算错误

Final 决策：不默认算错误。

keyword 通常短，ASIN title 通常长。title 提供材质、尺寸、功能是正常现象。只有当 missing 涉及高价值字段或高频词时，才进入人工复核。

### 16.6 `Top ASIN title` 侧是否只看第一条

Final 决策：v1 不强制只看第一条。

- 系统按行处理 ASIN title。
- 如输入提供 Top N，则输出 Top N 的 `st.csv` 和逐行 `diff.csv`。
- 如业务只想看 Top 1，在输入预处理阶段过滤。

---

## 17. 示例打标结果

为避免 7 字段宽表在 Excel/Word 中阅读困难，本节按单条示例展示。实际输出仍以 `kw.csv` / `st.csv` 的 7 字段列为准。

### 17.1 `shoe rack`

```json
{
  "产品形态关键词": ["rack"],
  "产品使用场景": "shoe storage",
  "存储对象": "shoe",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "",
  "mapping_status": "mapped"
}
```

### 17.2 `under bed shoe storage`

```json
{
  "产品形态关键词": [],
  "产品使用场景": "shoe storage",
  "存储对象": "shoe",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "under bed",
  "产品功能": "",
  "mapping_status": "mapped"
}
```

### 17.3 `over toilet storage cabinet`

```json
{
  "产品形态关键词": ["storage cabinet", "cabinet"],
  "产品使用场景": "toilet storage",
  "存储对象": "",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "over toilet",
  "产品功能": "",
  "mapping_status": "mapped"
}
```

### 17.4 `food storage containers with lids`

```json
{
  "产品形态关键词": ["storage container", "container"],
  "产品使用场景": "food storage",
  "存储对象": "food",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "with lid",
  "mapping_status": "mapped"
}
```

### 17.5 `glass food storage containers with lids`

```json
{
  "产品形态关键词": ["storage container", "container"],
  "产品使用场景": "food storage",
  "存储对象": "food",
  "产品材质": "glass",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "with lid",
  "mapping_status": "mapped"
}
```

### 17.6 `old spice deodorant`

```json
{
  "产品形态关键词": [],
  "产品使用场景": "",
  "存储对象": "",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "",
  "mapping_status": "not_storage"
}
```

### 17.7 `lego`

```json
{
  "产品形态关键词": [],
  "产品使用场景": "",
  "存储对象": "",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "",
  "mapping_status": "ambiguous"
}
```

### 17.8 `lego display shelf`

```json
{
  "产品形态关键词": ["display shelf", "shelf"],
  "产品使用场景": "lego display",
  "存储对象": "lego",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "display",
  "mapping_status": "mapped"
}
```

### 17.9 `under cabinet lighting`

```json
{
  "产品形态关键词": [],
  "产品使用场景": "",
  "存储对象": "",
  "产品材质": "",
  "尺寸": "",
  "产品使用场地": "",
  "产品功能": "",
  "mapping_status": "not_storage"
}
```

---

## 18. 推荐项目目录

Final v1.0 建议目录结构：

```text
storage_taxonomy_workflow/
├── README.md
├── requirements.txt
├── pyproject.toml
├── config/
│   ├── taxonomy/
│   │   ├── canonical_values_v0.json
│   │   ├── aliases_v0.json
│   │   ├── rollups_v0.json
│   │   └── negative_rules_v0.json
│   ├── rules/
│   │   ├── extraction_rules_v0.yaml
│   │   ├── field_constraints_v0.yaml
│   │   └── thresholds.yaml
│   └── workflow_config.yaml
├── data/
│   ├── local/
│   │   ├── keyword_input.csv
│   │   └── top_asin_input.csv
│   └── golden/
│       ├── golden_keyword_100.csv
│       └── golden_title_100.csv
├── outputs/
│   ├── kw.csv
│   ├── st.csv
│   ├── diff.csv
│   └── candidate_values.csv
├── review/
│   ├── review_queue.csv
│   ├── taxonomy_change_log.csv
│   └── human_review_template.csv
├── docs/
│   ├── requirements_final_v1.md
│   ├── labeling_guideline_v1.md
│   ├── diff_policy_v1.md
│   └── rerun_sop_v1.md
├── scripts/
│   ├── run_workflow.py
│   ├── extract_kw.py
│   ├── extract_st.py
│   ├── generate_diff.py
│   ├── build_review_queue.py
│   └── discover_candidate_values.py
└── src/
    └── storage_taxonomy/
        ├── normalizer.py
        ├── domain_gate.py
        ├── taxonomy_registry.py
        ├── canonical_extractor.py
        ├── field_constraints.py
        ├── diff_engine.py
        ├── review_queue.py
        ├── candidate_discovery.py
        └── metrics.py
```

---

## 19. 核心程序模块需求

### 19.1 normalizer.py

负责文本清洗：

- lower case
- 标点清洗
- 空格归一
- 单复数归一
- 常见拼写变体归一
- phrase 标准化，如 `over the toilet` -> `over toilet`

### 19.2 domain_gate.py

负责判断：

```text
mapped / partial / ambiguous / not_storage
```

要求：

- 负向规则优先。
- 不因为出现对象词就直接入域。
- 不因为出现房间词就直接入域。

### 19.3 taxonomy_registry.py

负责加载和查询：

- canonical values
- aliases
- rollups
- negative rules
- status
- priority
- taxonomy_version

### 19.4 canonical_extractor.py

负责把 keyword/title 抽取为固定 7 字段。

要求：

- 输出字段类型稳定。
- 保留 evidence。
- 执行字段约束。
- 支持最长 alias 优先。
- 支持 unmapped phrase 输出。

### 19.5 diff_engine.py

负责生成字段级 diff。

要求：

- 支持 exact_match。
- 支持 rollup_match。
- 支持 missing_value。
- 支持 true_conflict。
- 支持数组字段 `产品形态关键词` 的集合比较。

### 19.6 review_queue.py

负责从 diff 中生成复核队列。

要求：

- 所有 true_conflict 必进。
- missing_value 按高价值规则筛选。
- review_priority 可配置。

### 19.7 candidate_discovery.py

负责从 unmapped / ambiguous / conflict 中生成候选 canonical 值。

v1 可先使用：

- 高频短语统计
- TF-IDF phrase extraction
- 简单聚类

后续可升级：

- embedding 聚类
- LLM 候选标签命名
- 主动学习

---

## 20. 指标与验收标准

### 20.1 数据产物验收

必须能稳定生成：

1. `kw.csv`
2. `st.csv`
3. `diff.csv`
4. `review_queue.csv`
5. `candidate_values.csv`

### 20.2 Schema 验收

1. 7 字段全部存在。
2. `产品形态关键词` 始终为数组或 CSV 中可解析数组字符串。
3. 其他 6 个字段始终为字符串。
4. 必须有 `taxonomy_version`。
5. 必须有 `mapping_status`。
6. diff 必须有 `diff_type` 与 `review_required`。

### 20.3 质量验收

MVP 初始可接受目标：

| 指标 | 目标 |
|---|---|
| `true_conflict_rate` | rerun 后低于 10% |
| `review_queue_size` | 连续两轮下降 |
| `not_storage` 误入率 | 金标样本中可控，目标低于 5%-10% |
| 核心字段准确性 | 金标样本中优先看 `产品使用场景`、`存储对象`、`产品使用场地` |
| 标签库变更可追踪 | 每次更新有 change log |

### 20.4 业务验收

产品开发认为：

1. 能用 canonical niche 值做市场拆解。
2. 能看出 keyword 与 title 的供需差异。
3. 不再需要逐条手填大部分重复标签。
4. 复核重点集中在真正冲突，而不是所有不一致。

---

## 21. 实施里程碑

### M0：金标样本与初始标签库

产出：

- 100 条 keyword 金标
- 100 条 Top ASIN title 金标
- 30-50 个 canonical 值
- alias 与 rollup 初稿
- negative examples 初稿

### M1：本地抽取 baseline

产出：

- `domain_gate.py`
- `taxonomy_registry.py`
- `canonical_extractor.py`
- `kw.csv`
- `st.csv`

### M2：分层 diff 与 review queue

产出：

- `diff_engine.py`
- `diff.csv`
- `review_queue.csv`
- diff policy 文档

### M3：rerun 闭环

产出：

- `taxonomy_change_log.csv`
- 标签库版本升级逻辑
- rerun SOP
- 第一轮 true_conflict_rate 报告

### M4：候选新值发现

产出：

- `candidate_values.csv`
- 高频 unmapped phrase 报告
- candidate 审核模板

### M5：扩大到真实批次

产出：

- 昨天那批真实数据跑通
- 对比人工工作量下降
- review queue 规模报告
- 是否进入下一阶段模型增强的决策

---

## 22. 风险与应对

### 风险 1：字段仍然重叠

表现：同一个值在多个字段里都“似乎合理”。

应对：

- 每个字段有正例、负例、禁止项。
- 抽取时做 field constraint。
- 人审发现重叠后先改字段定义，再 rerun。

### 风险 2：场地粒度不稳定

表现：有人写 `bathroom`，有人写 `over toilet`。

应对：

- canonical 优先细场地。
- 上层空间只作为 fallback。
- roll-up parent 处理细/粗不一致。

### 风险 3：missing_value 队列爆炸

表现：ASIN title 比 keyword 多很多材质、尺寸、功能。

应对：

- missing_value 默认不算错误。
- 只审高价值 missing。
- 可按字段配置 review_priority。

### 风险 4：品牌词和对象词误伤

表现：`old spice` 被识别成 `spice`，`running shoes` 被识别成鞋收纳。

应对：

- negative rules 优先。
- Domain Gate 必须先于字段抽取。
- 金标样本必须包含易混淆负例。

### 风险 5：candidate 标签过度膨胀

表现：系统不断生成过细、低价值标签。

应对：

- candidate 不自动上线。
- 上线必须满足频次、搜索量、业务价值、供给差异。
- rejected candidate 要记录，避免重复推荐。

### 风险 6：版本不可追踪

表现：rerun 后结果变了，但不知道为什么。

应对：

- 所有输出带 taxonomy_version。
- 每次标签库更新写 change log。
- 保留 deprecated -> canonical 映射。

---

## 23. 仍需业务确认的问题与默认方案

| 问题 | 默认方案 | 何时调整 |
|---|---|---|
| `产品形态关键词` 是否需要 primary form | v1 不新增字段，只输出数组 | 如果数组过多影响分析，再增加内部 `primary_form_factor` |
| 尺寸是否归一到 small/medium/large | 只在显式出现时归一；数字尺寸保留规范短语 | 如果产品开发需要尺寸段分析，再做 bucket |
| pack 数是否进入尺寸 | 默认不进入 | 如果 pack count 对选品重要，新增 `包装数量` 或并入尺寸 |
| Top ASIN 是否只取第一条 | v1 按输入行处理，可支持 Top N | 如果复盘只看 Top 1，则输入预过滤 |
| `bathroom` 是否能作为场地 | 仅无细场地时 fallback | 如果产品开发坚持只看细 niche，可把 room-level 只放 rollup，不进字段 |
| `clear` 放材质还是功能 | 默认不放材质，可作为功能/特征候选 | 如果 clear bins 是重点 niche，可加入产品功能 canonical |
| `wall mounted` 放场地还是功能 | v1 默认放产品功能 | 如果安装位置分析更重要，可配置到产品使用场地 |

---

## 24. Final 结论

Final v1.0 的核心设计原则是：

1. **先固定 canonical truth，再谈自动化。**
2. **产品开发优先，运营通过 roll-up 聚合。**
3. **7 字段语义必须单一，不能把团队分歧自动化。**
4. **keyword 与 Top ASIN title 使用同一套标签库。**
5. **所有不一致必须分层，不能一刀切当错误。**
6. **true_conflict 才是 v1 的核心复核对象。**
7. **missing_value 默认不是错，只审高价值部分。**
8. **新标签可以被发现，但不能自动上线。**
9. **每次变更必须记录版本，并通过 rerun 验证是否降低冲突。**

一句话概括：

> v1 要交付的不是“全自动分类器”，而是一套可重复运行、可解释、可治理的 canonical taxonomy workflow，让产品开发能稳定地把收纳市场拆成可复用的 niche，并把人工判断集中到真正值得判断的地方。
