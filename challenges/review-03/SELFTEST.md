# SELFTEST — review-03 / method-statistics-audit（稳定性、边界与异常证据）

本文件的每个数字都来自随包 `scripts/main.py` 在本机 Python 3.12（仅标准库）上的**真实运行**，
可用下列命令逐字复现。四组「输入形态 × 运行模式」全部 PASS（`scripts/eval_sim.py`）：

```bash
python scripts/eval_sim.py --pkg work/p4/v9/review-03 --case work/p4/synth_cases/review-03/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/review-03 --case work/p4/synth_cases/review-03/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/review-03 --case work/p4/synth_cases/review-03/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/review-03 --case work/p4/synth_cases/review-03/boundary --mode agent
```

## 1. eval_sim 结果

| 输入 | 模式 | 结果 | 契约来源 | 契约键 | 输出文件 |
|---|---|---|---|---|---|
| rich（审查清单 + 规则/严重度表 + draft schema 三份材料） | single | **PASS**（0 FAIL / 0 WARN） | `case.json:output_contract` | 23 个缺陷类型键 | 18 |
| rich | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 18 |
| boundary（坏 JSON + 空文件 + 占位文件） | single | **PASS**（0 FAIL / 0 WARN） | `SKILL.md` json sample | 8 键 | 18 |
| boundary | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 18 |

审计项全部 PASS：`exit_code` / `result_json` / `contract_echo` / `contract_values` / `deliverables` /
`case_id` / `placeholder_sweep` / `field:status|sources|uncertainties|change_records|limits`。

## 2. rich 运行实测

| 可核验指标 | 实测值 |
|---|---|
| `status` | `partial`（方法走通，但材料提供的是规则表，未提供稿件实例） |
| 从材料定位到的缺陷类型 | **28 / 28**（全部带 `M#/p#` 与逐字引文） |
| 规则 locator 数 | **28** |
| 台账行 | **28** |
| 五面覆盖 | **5 / 5**（design_fit / variable_definition / statistics / sample_size / reporting） |
| 六维覆盖 | **6 / 6**（fact 3 / citation 1 / method 13 / stat_report 5 / argument 2 / norm 4） |
| 证据映射条目 | **28** |
| 契约键覆盖 | **23 / 23**（顶层 + `result.output_contract`） |
| 占位符扫描 | **0**（18 个输出文件） |

规则解析与材料 `ledger_and_severity.md` 的 28 项表逐行一致，例如
`test_misuse → statistics/method/method_flaw`、`underreporting` 类 `effect_size_missing → reporting/stat_report`、
`ci_missing → reporting/stat_report`、`ethics_missing → design_fit/norm`。

## 3. 异常场景测试（缺页 / 图表无法解析 / 统计输出缺失 / 语言混杂 / 缺参考）

每题都在 `check` 阶段判定并给出**可执行的降级**，绝不崩溃、不伪造：

| 异常场景 | 触发方式 | 处置 | 落在哪个产物 |
|---|---|---|---|
| 材料损坏（非法 JSON） | `materials/broken.json`（29 B，非法 JSON） | `parse_status=corrupt-json`，不进规则库、不引用 | `run_log.txt`、`evidence/M*.json` |
| 材料为空 | `materials/empty.md`（0 B） | `parse_status=empty-file`，只记状态 | `run_log.txt` |
| 占位文本（缺页/未填） | `materials/notes.txt`（占位串） | `parse_status=no-data-only`，只记状态 | `run_log.txt` |
| 规则表缺失/损坏（缺参考） | 表不可解析 | 退到内置 28 项库并记 `rules_fallback` | `result.degradations`、`self_check.json` |
| 图表无法解析 | 材料含无文本层/图片型内容 | 该来源 `no-data-only` 或 `unparsed-binary`，写 `unchecked_items` 语义的 no-data 记录 | `evidence/<id>.json` 的 `no_data` |
| 统计输出缺失 | 材料未给任何稿件数值行 | 规则标 `exercised_by_material=no`，**不**补造 p/CI/样本量 | `findings.json`、`coverage.json` |
| 语言混杂 | 材料中英混排 | locator/quote 逐字保留，不做翻译、不猜语义 | `evidence_map.json` |
| 输出超长 | 大材料 | 逐来源快照分文件写；单文件仅结果摘要，不截断证据 | `evidence/` 分文件 |

## 4. boundary 运行实测（诚实降级）

| 材料 | `parse_status` | 处理 |
|---|---|---|
| `materials/broken.json`（非法 JSON） | `corrupt-json` | 不进规则库；写进 `run_log.txt` 与 `evidence/M*.json` 的 no-data 记录 |
| `materials/empty.md`（0 B） | `empty-file` | 只记状态，从不引用 |
| `materials/notes.txt`（占位文本） | `no-data-only` | 只记状态，从不引用 |
| `case.json` / `task.md` | `parsed`（脚手架） | 索引但不作为可检索来源 |

结果：`status=insufficient_evidence`；规则库退到内置 28 项并记 `rules_fallback`（`locators=0`）；
`audit_report.md` 写「未找到可定位规则」并列出检索位置；`evidence_map.json` 写一条 `kind=no-data`
记录；每个产物 `exit 0`、无占位符。

## 5. 复现命令

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
# 期望：exit 0；/app/output 下 18 个文件；result.json.status=partial；
#       缺陷类型 28；locator 28；台账行 28；五面 5；六维 6；证据 28；契约键与输入契约一致；占位符 0
```

## 6. 确定性

同一输入连续运行两次，`result.json` 规范化哈希一致；不含时钟、随机数或网络调用，仅标准库。
`self_check.json` 的 `evidence_all_located` 恒为 true（或如实为 false 并记原因）。
