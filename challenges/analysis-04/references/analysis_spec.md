# 规格表（可编辑）· analysis-04 analysis-codegen-execute

本文件是包内**可编辑**的规格来源；`scripts/codelib.py:parse_spec` 会从材料（同结构 Markdown 表）
解析 draft 字段、校验项、降级矩阵、契约键语义与算子枚举，`scripts/engine.py` 据此生成代码、
执行、重算与回填。评测输入自带的规格材料优先级相同（同名键合并）。

## 1. 工作稿 `draft.json` 字段

| 字段 | 类型 | 必填 | 约束 |
|-|-|-|-|
| `case_id` | str | ○ | 与 `case.json` 一致 |
| `column_map` | list | ✔ | `{field, column, role, unit, locator, meaning}`；role ∈ numeric/group/id/target/time |
| `cleaning_policy` | obj | ○ | `{missing: skip\|drop_row, dedup, exclude_out_of_range}`，显式优先 |
| `analysis` | list | ✔ | `{id, kind, table, columns, group_by, why, locator}`；kind ∈ describe/missing/dedup/groupby/corr/ttest/sql/freq |
| `claims` | list | ✔ | `{id, statement, metric, table, column, y, where, value, unit}`；metric ∈ mean/median/stdev/min/max/sum/count/q1/q3/r |
| `verification` | list | ✔ | `{check, expected, observed, pass, method}`，≥3 条 |

## 2. 校验项规格（`verification[]`）

| category | 代表 check | 失败级别 | 说明 |
|-|-|-|-|
| input | `materials_and_tables_present` | high | 无表即 `input_error` |
| integrity | `row_conservation`、`rows_used_positive` | high | `n_in - 去重 == n_out` |
| cleaning | `duplicate_rows_accounted`、`missing_values_accounted` | medium | 有重复/缺失须写明策略 |
| claim | `claim_<id>_recompute` | high | 容差 `max(1e-6, 5e-4·|值|)` |
| silent_error | `claim_<id>_variant_attribution` | high | 声明值等于错误变体即判算错 |
| chart | `chart_points_vs_rows`、`chart_axis_unit` | medium | 点数 ≤ 源结果行数；轴标签含单位 |
| query | `sql_<id>_rowcount` | high | 行数 > 主表且无聚合 → JOIN 膨胀 |
| types | `type_coercion_<col>` | high | 数值列不可解析值 |
| execution | `code_executed`、`results_written` | high | 退出码与产物 |
| gold | `gold_standard_overlap` | high | 仅在提供金标准时出现 |

静默错误变体（`variant_hits[].variant`）：`missing_as_zero`、`dedup_applied`、
`outlier_retained`、`unit_scaled_x1000`、`unit_scaled_div1000`。

## 3. 异常与降级矩阵

| 触发 | 识别 | 处置 | 记录 |
|-|-|-|-|
| case.json 坏 JSON | 解析异常 | 保留原文，继续扫材料 | `errors[].stage=case` |
| 契约缺失 | 非 dict/list | 推断键兜底 | `coverage.contract_fields_total=0` |
| 缺列 | 字典有表无 | 标 `unmatched`，跳过该列断言 | `degradations` |
| 类型不符 | `to_num` 失败 | 计 `n_coercion_failed` + 样例 locator | `verification` |
| 依赖缺失 | 纯标准库 | 声明可选依赖 | `environment.fallbacks` |
| 空查询/空表 | 0 行 | 空集 + note，不编数值 | `verification`+`uncertainties` |
| 除零/空集合 | 统计量 None | 标 `insufficient_data` | `verification` |
| 超时 300s | `TimeoutExpired` | 留现场 → 包内重算 | `errors[].stage=execute` |
| code 非 0 退出 | returncode | 留 stdout/stderr → 重算 | `errors` |
| 无分类列 | 0 个 2–12 级列 | 跳过图表 | `degradations: chart_skipped` |

## 4. `output_contract` 键语义

| 键名模式 | 回填 |
|-|-|
| code/script/代码 | `code`（入口、文件、行数、sha256、复跑命令） |
| result/metric/stat/value/结果 | `results`（`key_numbers` + 每算子行） |
| verif/check/校验 | `verification` + `verification_summary` |
| log/日志 | `run_log`（命令、CWD、退出码、流摘要） |
| env/depend/version/环境 | `environment` |
| chart/figure/plot/图 | `chart`（路径、类型、点数、轴标签） |
| sql/query/查询 | `query` |
| clean/table/data/清洗 | `cleaning`（策略、行数账、规则） |
| report/analysis/报告 | `report`（路径、字节数） |
| repro/seed/command/复现 | `reproducibility` |
| error / uncertain / source | 对应列表 |
| 其他 | `{"available": [...], "note": "no semantic match"}` |

## 5. 复用

- 生成代码自足复跑：`python3 code/analysis.py --input <材料> --output <结果>`（纯标准库）。
- `results/summary.json` 是唯一结果来源，报告与 `key_numbers` 由它派生并由引擎独立重算比对。
- 新增算子：生成模板的算子分支 + 本表 §1 + `SKILL.md` §3 枚举同步。

## 6. locator 约定

文本行 `<file>#L<n>`；表 `<file>#L<起>..L<止>`；列 `<file>#col:<name>`；case 键 `case.json#<key>`。
