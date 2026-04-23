# 03. 人工标注指南

## 标注顺序

1. domain
2. location
3. target_object
4. product_form
5. purpose
6. attribute
7. scenario
8. 备注和新标签建议

## 原则

### 负例优先

`old spice deodorant` 命中 spice，但应标 `not_storage`。

### 有证据才标

`shoe rack` 可标 shoes 和 rack，不要标 entryway。
`shoe rack for entryway` 才标 entryway。

### 单独物品不入域

`lego`、`makeup`、`shoes` 没有明确 storage/organizer/display 证据，标 ambiguous 或 not_storage。

### 不要推断隐含地点

`spice rack` 不强推 kitchen。
`food storage containers` 不强推 kitchen。
