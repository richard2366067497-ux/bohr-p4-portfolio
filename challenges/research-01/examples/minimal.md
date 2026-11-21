# 最小调用示例（示例，非正式结果）

> 以下为**示例**，用来说明调用方式与产物形态，不冒充任何正式案例结果。

## 输入

`/input/case.json`（示例）：

```json
{"case_id": "demo-0001", "materials_root": "materials"}
```

`/input/materials/` 放入若干待处理文件。任务规则写在 `/input/task.md`。

## 调用

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

## 预期产物

research_plan.json、evidence_matrix.csv、synthesis.json、coverage.json、report.md、result.json。

`result.json`（示例骨架，实际值由运行生成）：

```json
{
  "case_id": "demo-0001",
  "status": "completed",
  "output_contract": {
    "case_id": "demo-0001",
    "deliverable": "<产物文件>",
    "evidence_map": ["<产物文件>"],
    "change_log": ["<操作记录>"],
    "coverage": {"files_expected": 0, "files_processed": 0},
    "status": "completed"
  }
}
```

## 判定

- 退出码 0；`result.json` 可被 `python -m json.tool` 解析。
- 契约键齐全且非空；路径键指向真实产物。
- 材料缺失/损坏时 `status` 为 `partial`，并列出限制。
