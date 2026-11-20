# SELFTEST — formula-verification v3.0.0

自测日期 2026-11-20；解释器 Python 3.12.14（标准库，无第三方、无网络）。
被测包路径 `work/p4/v6/reading-08`；用例 `work/p4/synth_cases/reading-08/{rich,boundary}`；
驱动器 `scripts/eval_sim.py`（只读，未修改）。

## 1. 四组组合结果

命令模板：

```
python scripts/eval_sim.py --pkg work/p4/v6/reading-08 \
  --case work/p4/synth_cases/reading-08/<rich|boundary> --mode <single|agent>
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
| rich | `case.json:output_contract` | formulas, variables, derivations, numeric_checks, indicator_checks, notes |
| boundary | `SKILL.md` 契约样例（case 无契约块） | case_id, status, result, claims, uncertainties |

两组的 `output_contract` 逐键回填真实值（无类型占位符、无空值、无 JSON null），
并逐一浅拷贝到顶层；`case_id` 透传为 `synth-rich-reading-08` / `synth-boundary-reading-08`。

## 3. 产物清单（rich/single 实跑）

| 产物 | 字节 | 说明 |
|-|-|-|
| `result.json` | 37148 | 契约回填 + formulas/variables/derivations/numeric_checks/indicator_checks/coverage/missing_objects/notes/method |
| `formulas.tex` | 202 | `equation` 环境 + 注释行 |
| `symbol_table.csv` | 500 | 符号台账（含 `definition_source`） |
| `verification.md` | 2561 | 人读核验报告 |
| `run.log` | 142 | 运行摘要 |
| `work/index.json` | 7219 | 公式/符号/推导/指标/覆盖快照 |

rich 实跑口径：`status=partial formulas=2 symbols=7 checks=2 indicators=5`；
`fd-1 → N_{0}^{2}=e^{kt}`、`fd-2 → \frac{\alpha+\beta}{\sqrt{\gamma}}`；
`k`（0.35 1/h）与 `t`（6 h）为 `paper_defined` 并参与 `computed` 代入；
其余符号 `common_knowledge` 且判 `not_computable`，`missing_symbols` 逐条列出。

## 4. 降级路径实跑

| 场景 | 命令 | 退出码 | status |
|-|-|-|-|
| `--input` 指向空目录（out/work 在输入之外） | `main.py --input EMPTY_DIR --output OUT_DIR --work WORK_DIR` | 0 | `input_error` |
| `case.json` 为坏 JSON | 同上（输入含坏 `case.json`） | 0 | `input_error`，`degradations` 记一条 |
| boundary 用例（有文件但无公式无指标） | `main.py --input BOUNDARY_DIR --output OUT_DIR --work WORK_DIR` | 0 | `partial` + `missing_objects[]` |

三条路径都写出合法 `result.json`，`output_contract` 均为标准五键且无空值。

## 5. 复跑要点

- 入口恒为单命令：`python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work`；
  agent-first 走 `build → check → selfcheck`，四个子命令各自都重写完整 `result.json`。
- 复跑前确认包内无 `__pycache__`、无历史 `_t/` 输出目录（交付件应恰为 8 个文件）。

## 6. 已知边界

- `mtable` 嵌套与自定义语义走通用拼接，排版可能不理想（`references/formula_contract.md` §2 已声明）。
- 不做符号代数、不做单位换算；印的值原样带入。
- 只要材料里没有汉字级模板标记即可；含未填模板标记的文件会被跳过并记入 `degradations`。
