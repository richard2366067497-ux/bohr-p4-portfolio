# 最小调用示例（示例，非正式案例结果）

> 本文件是一组**示意**输入与输出，用来说明接口与完整流程。
> 它不是任何正式案例的评分结果，也不代表平台分数。

## 1. 输入

`/input/case.json`

```json
{"case_id": "demo-slides", "language": "en", "materials_root": "materials",
 "output_contract": {"editable_source": null, "export_artifact": null,
                     "content_map": null, "compliance_checks": null, "exceptions": null}}
```

`/input/materials/paper.md`（节选）

```markdown
# A short demo paper
## Method
Samples were annealed at 500 C for 2 h in air before measurement.
## Results
The conversion reached 94.7 % after 120 min of irradiation.
```

## 2. 调用（一条命令）

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. 示意输出

`/app/output/result.json`（节选）

```json
{"case_id": "demo-slides",
 "status": "ok",
 "editable_source": "deck.pptx",
 "export_artifact": "deck.pdf",
 "coverage": {"slides": 3, "quotes_checked": 1, "quotes_matched": 1},
 "summary": "3 slides built; every page keeps a locator back to the material"}
```

`/app/output/content_map.json`（节选）

```json
{"slides": [{"index": 2, "title": "Method", "kind": "section", "source": "M01#s1"}]}
```

同一目录下另有 `deck.md`、`deck.pptx`、`deck.html`、`deck.pdf`、`preview.svg`、
`slide_plan.json`、`compliance_checks.json`、`report.md`。

## 4. 结果说明

- 页面只使用材料中的实质句子；`Method` 页的来源定位是 `M01#s1`；
- `94.7 %` 这类数字要点会在原文 span 中重新定位后才上页；
- 即使 `/input` 为空，运行仍 `exit 0`，结果是带原因的 `insufficient_evidence` 结构。
