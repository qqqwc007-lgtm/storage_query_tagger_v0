# 01. v0 打标边界

## 1. 入域：storage_related

满足以下任一条件通常入域：

### A. 明确收纳/整理意图

```text
storage
organization
organizer
organizers
organize
display shelf
display case
```

示例：

```text
closet organizers and storage
bathroom organizers and storage
storage bins with lids
jewelry organizers and storage
lego display shelf
```

### B. 明确收纳产品形态

```text
rack
shelf / shelves
cabinet
bin
basket
box
container
drawer organizer
caddy
cart
hanger
hook
holder
divider
```

示例：

```text
shoe rack
spice rack
jewelry box
makeup organizer
under sink organizer
over the toilet storage cabinet
```

## 2. 出域：not_storage

### A. 单纯商品购买，不是收纳

```text
shoes for women
nike shoes men
toilet paper
paper towels
```

### B. 品牌或误伤词

```text
old spice deodorant
old spice body wash
```

### C. 非收纳用途的形态词

```text
under cabinet lighting
box cutter
xbox controller
basketball
trash bags
dog poop bags
crossbody bags for women
gym bag
beach bag
```

### D. v0 暂不纳入的邻近需求

```text
lunch box
lunch bag
diaper bag
ordinary tote bag
ordinary handbag
```

## 3. 模糊：ambiguous

没有明确收纳意图，但可能与收纳相关：

```text
lego
makeup
jewelry
shelf
box
basket
closet
garage
```

处理方式：

- v0 输出 `ambiguous`
- `needs_review = true`
- 后续结合点击商品、类目、Embedding 或人工审核判断

## 4. 显式优先

不要过度推断。

```text
food storage containers with lids
```

可标：

```text
obj_food
form_container
purpose_storage
attr_with_lid
```

不要高置信标：

```text
loc_kitchen
loc_pantry
```

除非 query 明确出现 kitchen / pantry。

## 5. Scenario 边界

Scenario 只收业务可运营复合需求：

```text
closet organization
bathroom organization
under-sink organization
entryway shoe organization
holiday storage
makeup organization
jewelry organization
garage tool storage
```

以下不做 Scenario，拆成原子标签：

```text
glass food storage containers with lids
```

拆成：

```text
target_object = food
product_form = container
purpose = storage
attribute = glass
attribute = with_lid
```
