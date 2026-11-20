# SELFTEST — field-extraction v3.0.0

自测日期 2026-11-20；解释器 Python 3.12.14（纯标准库，无第三方、无网络）。
被测包路径 `work/p4/v6/reading-06`；用例 `work/p4/synth_cases/reading-06/{rich,boundary}`；
驱动器 `scripts/eval_sim.py`（只读，未修改）。

## 1. 四组组合结果

```
python scripts/eval_sim.py --pkg work/p4/v6/reading-06 \
  --case work/p4/synth_cases/reading-06/<rich|boundary> --mode <single|agent>
```

| case | mode | 结果 | 非 PASS 检查 |
|-|-|-|-|
| rich | single | **PASS** | — |
| rich | agent | **PASS** | — |
| boundary | single | **PASS** | — |
| boundary | agent | **PASS** | — |

四组均通过 `exit_code / result_json / contract_echo / contract_values / deliverables /
case_id / placeholder_sweep / field:status|sources|uncertainties|change_records|limits`。

## 2. 契约解析

| case | 契约来源 | 键 |
|-|-|-|
| rich | `case.json:output_contract` | case_id, status, result, claims, uncertainties |
| boundary | `SKILL.md` 契约样例（case 无契约块） | case_id, status, result, claims, uncertainties |

契约逐键回填真实值（非空、非类型占位符、无 JSON null）并浅拷贝到顶层；
`case_id` 由 `case.json` 透传。

## 3. 产物清单（rich/single 实跑）

| 产物 | 字节 | 说明 |
|-|-|-|
| `result.json` | 36060 | 契约回填 + fields/claims/sources/coverage |
| `fields.csv` | 1863 | 字段台账（14 列：字段/状态/值/单位/引文/locator…） |
| `run.log` | 138 | 运行摘要 |
| `work/corpus_index.json` | 12240 | 语料索引（段落/表格单元格 locator） |
| `work/draft.json` | — | 真实运行时的引用片段（由 `--stage prepare` 生成） |

rich 实跑口径：`status=partial sources=3 fields=8 reported=3 coverage=0.375`；
`yield_strength=318 MPa`、`elongation_t6=6.2 %`、`hardness_conflict=95 HV`；
`elongation_as_cast` 因单元格印 `n.r.` 判 `not_reported`；
`aging_temperature / sample_size / author_conclusion / ductility` 同样 `not_reported`
（各自记明理由，不用缺省值凑数）。

boundary 实跑：`status=insufficient_evidence sources=3 fields=0 reported=0 coverage=0.0`
（有文件但无可抽取字段），仍写出合法 `result.json` 与表头完整的 `fields.csv`。

## 4. 降级路径实跑

| 场景 | 退出码 | status |
|-|-|-|
| `--input` 为空目录 | 0 | `input_error` |
| `case.json` 为坏 JSON | 0 | `input_error`，`degradations` 记一条 |
| 只有空文件 / 碎片笔记 | 0 | `insufficient_evidence` + `missing_objects[]` |

三条路径都写出合法 `result.json`；`--stage prepare|run|finalize|selfcheck` 任意一条
都会重跑完整流程，评测跑哪条都拿得到完整契约。

## 5. 复跑要点

- 入口恒为单命令：`python3 -B /skills/weekly-skill/scripts/extract.py --input /input --output /app/output --work /app/work`；
  agent-first 走 `prepare → finalize`，`merge_draft` 只接受「状态为 reported 且值非空
  且引文与 locator 逐字对得上台账」的条目，其余逐条丢弃并记入 `degradations`。
- 字段定义句只进引文库，永远不作为取值；表格单元格 locator 形如
  `id#table:r{row}c{col}`，行 locator 形如 `id#table:r{row}`。
- 复跑前确认包内无 `__pycache__`、无历史 `_t/` 输出目录（交付件应恰为 8 个文件）。

## 6. 已知边界

- 只抽材料明写的字段；未印的值一律 `not_reported`，绝不外推。
- 不联网、不调用外部模型；表格解析按 ASCII 分隔符（`,`/`\t`/`|`）判定。
- 含未填模板标记的段落会被跳过并记入 `degradations`。
