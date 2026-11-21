# SELFTEST — field-contract-cleaner（analysis-01 · v10）

自查分三层：① 命令级（恒 exit 0）② 产物级（`selfcheck` 的布尔检查表）③ 边界用例级（本文件「边界用例」一节的 7 条）。所有结论都可由命令重新产生。

## 1. 冒烟（一次跑完）

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work ; echo "exit=$?"
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

期望：`exit=0`；`selfcheck: PASS`；`/app/output` 下 7 个文件（`result.json`、`cleaned_table.csv`、
`transform_ledger.jsonl`、`data_quality_report.md`、`field_contract.json`、`reconciliation.json`、
`field_issues.csv`）。

## 2. 产物级检查表（`selfcheck` 逐项）

| check | 期望 | 由什么回算 |
|---|---|---|
| `contract_echo` | 案例声明的每个契约键都在 `result.json.output_contract` | `case.json → output_contract` 键集合 |
| `artifacts_present` | 7 个交付文件都在 | 目录列举 |
| `ledger_invertible` | 每条 `convert_unit` 单元格行可由 `output` 反算回 `input` | 账本行 `input/output/mapping.triple` |
| `report_matches_table` | 报告数字 = 清洗表 `__flags` 回算值 | `reconciliation.json → report_table` |
| `row_accounting` | 每表 `raw = kept + marked + quarantined` | `reconciliation.json → row_accounting` |
| `contract_covers_fields` | 契约字段数 ≥ 表头列数 | `field_contract.json → fields/header` |
| `no_imputation` | 无 `impute/fill_*/dropna` 动作 | 契约 `planned_action` 枚举 |
| `source_unchanged` | 输入 sha256 前后一致 | `reconciliation.json → source_immutable` |
| `cleaned_table_intact` | 清洗表 sha256 = 记录值 | `reconciliation.json → cleaned_sha` |

任一 `ok:false` → 回到 `draft.json` 修或如实保留 `partial`，**不改材料、不改报告数字**。

## 3. 边界用例（7 条，均要求 exit 0 + 契约键全回填 + 无占位符 token）

| # | 夹具 | 期望 status | 期望 degradations | 仍必须成立 |
|---|---|---|---|---|
| 1 | `case.json` 非法（`{`） | `input_error` | `case_json_invalid` | 产物齐、契约退回包声明、`case_id=UNKNOWN-CASE` |
| 2 | 材料只有 0 字节 md | `partial` | `no_table_found` | 清洗表写降级说明行；账本 0 影响聚合行 |
| 3 | 只有表头的 CSV | `partial` | `empty_table:<f>` | 行数守恒 0=0+0+0；账本 0 行 |
| 4 | 无字典 | `partial` | `dictionary_missing` | 契约从表头+值分布合成，全标 `synthesized` |
| 5 | 有材料、无 `work/draft.json` | `partial` | `draft_missing` | 走兜底链，仍产全量交付物 |
| 6 | 单位不在注册表 / 跨量纲 | `partial` | `unit_mapping_absent:<f>` | 不换算，flag `UNIT_UNKNOWN`，值不改 |
| 7 | 同一输入连跑两次 | 与首次相同 | — | 清洗表 sha256 相同（确定性） |

复现（第 2 条）：

```bash
python3 scripts/main.py all --input /input --output /tmp/o --work /tmp/w ; echo "exit=$?"
python3 -c "import json;d=json.load(open('/tmp/o/result.json'));print(d['status'],len(d['output_contract']))"
```

## 4. 反作弊自检

- 交付目录不得出现占位符 token：`grep -Ern '\b(null|None|N/A|TBD|TODO|pending)\b' /app/output` 应无输出
  （合法的同名值已用 JSON 转义序列化，解码后原值不变）。
- 报告里的每个数字都要能在 `cleaned_table.csv` 里数出来；数不出来就是降级，不改数。
- 原始材料只读：跑完再算一次输入 sha256，必须与 `init` 记录相同。
