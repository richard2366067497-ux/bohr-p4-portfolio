```
{
  "case_id": "case-000",
  "status": "success",
  "deliverable": "manuscript.md",
  "preserved_facts": [{"token": "12%", "value": "12", "unit": "%", "source": "materials/paper.md"}],
  "evidence_map": [{"claim": "yield rose under deficit irrigation", "basis": "literature",
                    "source_id": "D02", "locator": "materials/refs.md [B0.S1] chars:0-90", "similarity": 0.21}],
  "change_log": [{"action": "assembled Results and Discussion from materials", "target": "manuscript.md"}],
  "output_contract": {
    "case_id": "case-000",
    "deliverable": "manuscript.md",
    "preserved_facts": [{"token": "12%", "value": "12", "unit": "%", "source": "materials/paper.md"}],
    "evidence_map": [{"claim": "yield rose under deficit irrigation", "basis": "literature",
                      "source_id": "D02", "locator": "materials/refs.md [B0.S1] chars:0-90", "similarity": 0.21}],
    "change_log": [{"action": "assembled Results and Discussion from materials", "target": "manuscript.md"}]
  }
}
```

# 结构化产物约定 / Artifact schema

## manuscript.md

四节固定：`## Results`、`## Discussion`、`## Limitations`、`## Sources`。

- Results 只列观察到的读数，每条带单位与来源标记 `[n]`。
- Discussion 每条解释后注明与本研究的对照或与文献的一致/张力，机制推测单列并标注为待检验。
- Limitations 分抽样与样本量、测量与单位、统计处理、可推广性四项。
- Sources 与文内 `[n]` 标记一一对应。

## results_map.json

| 字段 | 含义 |
|---|---|
| `case_id` | 输入案例标识（透传） |
| `readouts[].token` | 读数原文（数值+单位） |
| `readouts[].value` / `unit` | 拆分后的数值与单位 |
| `readouts[].source` | 来源文件相对路径 |
| `readouts[].context` | 读数所在句子（截断） |
| `numeric_statements` | 含读数的原句清单 |

## evidence_map.json

`entries[]` 每项：`claim`、`basis`（`data` / `literature`）、`source_id`、`locator`、`similarity`。

## preserved_facts.json

`facts[]` 每项：`token`、`value`、`unit`、`source`。数值与单位原样保留，不做换算。

## change_log.json

`changes[]` 每项：`action`、`target`、`reason`。记录组稿、章节分离、读数保留与边界处理。

## result.json

顶层字段见 SKILL.md；`output_contract` 逐键回填输入契约，五要素与 `limits` 恒非空。
