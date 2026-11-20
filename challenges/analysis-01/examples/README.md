# 最小可跑示例

一组最小输入、调用方式与示意输出，用于核对五类处理与账本/对账是否闭环。

## 1. 准备输入

```text
/input/case.json
{"case_id": "demo-clean-01"}

/input/rules.json
{"missing_tokens": ["", "na", "-999"], "units": {"mg/l": ["mass_conc", 0.001, 0.0]},
 "unit_aliases": {"μg/l": "ug/l"}, "qc_invariants": ["raw_rows == kept_rows + marked_rows + quarantined_rows"]}

/input/metrics.md
| 字段 | 单位 | 范围 | 类型 | 释义 |
|---|---|---|---|---|
| removal | % | 0-100 | numeric | 平衡去除率 |

/input/table.csv
sample,removal,ph
S1,95,3
S2,NA,9
S3,61,n/a
```

## 2. 调用

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 3. 示意输出（`/app/output/cleaned_table.csv`）

```csv
record_id,__src_row,__row_status,__flags,sample,removal,ph
1,2,kept,,S1,95,3
2,3,quarantined,removal:MISSING_CODE; ph:MISSING_CODE,S2,NA,n/a
3,4,marked,removal:NON_NUMERIC,S3,61,n/a
```

`NA` / `n/a` 原值保留，仅写 `__flags`；`transform_ledger.jsonl` 记录每个动作与 locator；
`reconciliation.json` 给出 `raw_rows == kept+marked+quarantined` 的守恒核对。

## 4. 边界示例

材料只有空文件或坏 JSON 时：`cleaned_table.csv` 写「无源表」状态行，`status=partial`/`input_error`，
退出码仍为 0。
