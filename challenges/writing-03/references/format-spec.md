# 版式规格、优先级与检查口径

本文件是 `scripts/core.py` 与 `scripts/adapter.py` 的规则说明书：规格项 id、取值来源、OOXML 换算与 C1–C8 检查口径
以本文为准；改阈值或规则时同步代码与本表。

## 1 规格项（固定 10 项）

| id | 含义 | 默认值 | OOXML 落点 |
|-|-|-|-|
| `page_size` | 纸张 | A4 (210 x 297 mm) | `w:pgSz` |
| `margin_vertical` | 上下页边距 | 2.54 cm | `w:pgMar@top/@bottom` |
| `margin_horizontal` | 左右页边距 | 3.17 cm | `w:pgMar@left/@right` |
| `body_font` | 正文字体 | Times New Roman | `w:rFonts@ascii/@hAnsi` |
| `body_font_size` | 正文字号 | 12 pt | `w:sz@val`（半磅） |
| `line_spacing` | 行距 | 1.5 | `w:spacing@line`（240 = 单倍） |
| `columns` | 栏数 | 1 | `w:cols@num` |
| `heading_numbering` | 标题编号 | 1 / 1.1 / 1.1.1 | 生成时写入标题文本 |
| `caption_position` | 题注位置 | 图下、表上 | 记录用，未自动排版 |
| `citation_style` | 引用样式 | numeric [n] | 记录用，正文编号原样保留 |

## 2 抽取与优先级

1. 模板：docx 读 `word/document.xml` 的 `w:pgMar`、`word/styles.xml` 的 `w:sz`；tex 读
   `documentclass`、`fontsize`、`geometry`。模板项 `source_kind=template`。
2. 格式要求：在关键词（font size/字号、line spacing/行距、margin/页边距、column/栏、citation/引用、
   heading/标题、paper/纸张）附近用正则取值。每条带 `source`、`locator`（`文件#L行号`）、逐字
   `quote`，并核验 quote 确在该文件中出现（`traceable`）。
3. 默认档：任何未被前两步定义的 id 用上表默认值，`inferred=true`、`traceable=false`。
4. 冲突：同一 id 多源不同值 → 按 `template > requirements > default` 取值，被丢弃值与来源写入
   `pending_human`，并计入 `result.json` 的 `errors` 之外的冲突通道（`degradations` 保持只列降级）。

## 3 重排规则

- 标题编号相对最小标题层级：最浅一级从 1 开始，下一级 `.1` 递增；已是数字开头的标题不改。
- 每条编号改动写入 `change_log`：`before` / `after` / `reason` / `locator="deliverable.md"`。
- 只含空壳标记（方括号内待写类词、单独省略号等）的行与重复段落不进入成稿，条数写入
  `pending_human`。
- 参考文献条目原样保留并追加到成稿末尾；正文引用编号不改号。

## 4 保真与证据

| 记录 | 口径 |
|-|-|
| `preserved_facts[kind=measure]` | 重排前后带单位量值计数；后 < 前 记 `missing` |
| `preserved_facts[kind=citation]` | 只统计正文行（排除以 `[n]` 开头的条目行）的引用计数 |
| `preserved_facts[kind=reference]` | 每条参考文献条目一条记录，带 locator |
| `evidence_map[].status` | `supported_by_source` / `reference_missing` / `source_not_found` / `overstated_in_source` / `overgeneralised_in_source` / `number_not_in_source` |

证据链：正文 `[n]` → 参考文献条目 → DOI → 包内 `source` 文件（`source` 角色优先于 `references`
文件，避免用条目自身当作证据）。

## 5 C1–C8 检查

| id | 检查 | 判定 |
|-|-|-|
| C1 | 正文字号 | 无论证冲突即 pass（值记录在 style_map） |
| C2 | 行距 | 同上 |
| C3 | 页边距 | 实际写入 docx sectPr |
| C4 | 标题编号 | 所有二级及以下标题（排除 References）均带编号才 pass |
| C5 | 引用一致性 | 正文引用编号集合 ⊆ 参考文献条目集合 |
| C6 | 摘要块 | 成稿含摘要标题才 pass，否则 skip |
| C7 | 参考文献 | 至少一条条目才 pass，否则 skip |
| C8 | 事实保真 | `preserved_facts` 无 `missing` 才 pass |

`skip` 不计失败，但必须在 `limits` 或 `pending_human` 中说明缺哪类材料。
