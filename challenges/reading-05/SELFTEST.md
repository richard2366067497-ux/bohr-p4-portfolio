# SELFTEST — reading-client v3.0.0

自测日期 2026-11-20；解释器 Python 3.12.14（纯标准库，无第三方、无网络）。
被测包路径 `work/p4/v6/reading-05`；用例 `work/p4/synth_cases/reading-05/{rich,boundary}`；
驱动器 `scripts/eval_sim.py`（只读，未修改）。

## 1. 四组组合结果

```
python scripts/eval_sim.py --pkg work/p4/v6/reading-05 \
  --case work/p4/synth_cases/reading-05/<rich|boundary> --mode <single|agent>
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
`case_id` 由 `case.json` 透传，缺失时退回目录名并记入 `degradations`。

## 3. 产物清单（rich/single 实跑）

| 产物 | 字节 | 说明 |
|-|-|-|
| `reading_record.md` | 1063 | 阅读记录（段落锚点 + 证据 + 结论） |
| `golden_standard.json` | 977 | 金标准抽取结果 |
| `diff_report.md` | 533 | 与金标准的差异 |
| `version_history.md` | 344 | 版本与变更历史 |
| `self_check.json` | 1105 | 自查（锚点/引文/计数） |
| `run.log` | 152 | 运行摘要 |
| `reader/index.html` | 1497 | 人读页面 |
| `reader/anchors.json` | 3750 | 段落锚点与 locator |
| `reader/annotations.json` | 547 | 批注 |
| `reader/qa_log.json` | 804 | 质检日志 |
| `reader/reading_state.json` | 267 | 阅读状态 |
| `result.json` | 12409 | 契约回填 + 结构化结果 |

rich 实跑口径：`status=answered docs=1 paragraphs=12 selections=2 claims=2`；
boundary 实跑：`status=partial docs=3 paragraphs=1 selections=0 claims=1`（证据不足走降级）。

## 4. 降级路径实跑

| 场景 | 退出码 | status |
|-|-|-|
| `--input` 为空目录 | 0 | `input_error` |
| `case.json` 为坏 JSON | 0 | `input_error`，`degradations` 记一条 |
| 材料里含未填模板标记（`[待写]` 类） | 0 | 该文件被跳过并在 `degradations` 说明，其余照常 |

三条路径都写出合法 `result.json`，`output_contract` 为标准五键且无空值。

## 5. 复跑要点

- 入口恒为单命令：`python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work`；
  agent-first 走 `build → check → selfcheck`，每个子命令都重写完整 `result.json`。
- 顶层 `--input/--output/--work` 与子命令共用同一组参数（`parents=[common]`），
  因此扁平入口与子命令入口的退出码都为 0；仅 argparse 用法错误返回 2。
- 复跑前确认包内无 `__pycache__`、无历史 `_t/` 输出目录（交付件应恰为 8 个文件）。

## 6. 已知边界

- HTML 页面每个开标签都带显式属性，材质文件里的裸标签不会被原样复制到产物。
- 不做语义改写：段落锚点与引文按材料原文逐字保留（仅去空白）。
- 只读材料本身，不联网、不调用外部模型。
