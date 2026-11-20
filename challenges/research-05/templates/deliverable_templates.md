# 交付物骨架模板（templates/deliverable_templates.md）

本文件给出两份可复用的骨架：对齐矩阵长表与证据表。用法：把表头连同示例行复制成 `.csv`，
再把示例行替换成本次材料的真实行——**每一行都要带 `locator` 与逐字 `quote`**，
材料未给就写「材料未给」，不要留空、不要改写原话。

## A 对齐矩阵长表（对应 `prior_art_alignment_matrix.csv`）

一行一主张，与最近的一份工作并排写；不可比时必须给原因，边界差别必须陈述。

```csv
claim_id,source_id,source_locator,task,method,data,evaluation,overlap,comparison_status,cannot_compare_reason,boundary_note,row_basis
"C1","S1","M1/p2","一行一主张：把该主张与最近的一份工作并排写","四维比较字段，材料未给就写材料未给","材料未给","材料未给","no-overlap","not_comparable","not_comparable 必填原因：为何无法直接比较","边界差别：本设想与那项工作到底差在哪","framework row; 文献级比较需要候选文献材料"
```

## B 证据表（对应 `evidence_index.jsonl`）

每条证据必须能回到材料逐字复核；改写过、找不到的句子会被判 `quote_not_found` 并失去证据资格。

```csv
evidence_id,source_id,locator,quote,match,verified,kind,note
"EV1","M1","M1/p2","逐字抄写材料里的那一句（含标点）","exact","true","claim-support","改写过的句子会成为 quote_not_found 并失去证据资格"
```

## C 使用要点

- `match` 取值：`exact`（逐字）/ `despaced`（去空白后一致，记降级）/ `quote_not_found`（不可用）。
- `overlap` 取值：`no-overlap` / `partial` / `full`；`comparison_status` 取值：`not_comparable` / `comparable`。
- 骨架里的「材料未给」「材料未给」原样保留，表示该字段在本材料中没有依据，而非占位符。
