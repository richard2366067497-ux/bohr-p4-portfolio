# 评分口径到检查项的映射（references/rubric.md）

把平台对"结果与讨论章节写作"的验收口径，逐条映射到本包的**可复算检查项**。每一行都能用
`scripts/main.py` 或 `--selftest` 重跑出来，避免"自评式得分"。

## 1 口径 → 检查项

- **交付完整**：8 件产物齐全（成稿 + 预览 + 4 张表 + 指标 + 结果 JSON），均存在且非空 → 看 outputs 里的字节数。
- **结果只写观察**：解释句不落在 Results 节，节内无因果/机制措辞 → 看 manuscript.md 的分节。
- **数值与单位保真**：读数逐字保留、不换算 → 看 metrics.json.baseline_checks[0]。
- **每条论断有来源**：文献论断带定位 → 看 metrics.json.baseline_checks[1]。
- **因果边界**：关联不写成因果 → 看 metrics.json.baseline_checks[2]。
- **必保留项落点**：读数进 preserved_facts → 看 metrics.json.baseline_checks[3]。
- **契约回填**：顶层 + 嵌套逐键，case_id 透传 → 看结果 JSON 与自测项 contract_filled。
- **诚实降级**：坏文件/位图/扫描 PDF 均入 degradations，并给出 human_review 项 → 看结果 JSON。
- **占位符清洁**：无空壳 token → 看自测项 no_placeholder_tokens。
- **可复算**：指标可由第三方重跑 → 看 metrics.json 的 note 字段。

## 2 判定优先级

1. 先看 `status` 与 `metrics.json.pass`——这是机器判定部分；
2. 再看 human_review——这些项**机器无法判定**（位图读数、扫描件数字、文献可得性）；
3. 最后看成稿的语义质量——本包不作声称，由人工/平台对照。

## 3 不声称的部分

- 不判断结论在科学上是否成立；
- 不声称文笔优于基线；
- metrics.json 的阈值是**本包自设的守卫线**，不是平台分数。
