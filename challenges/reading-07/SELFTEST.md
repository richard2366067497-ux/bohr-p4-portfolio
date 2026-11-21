# SELFTEST — claim-evidence-verifier v3.0.0

自测日期 2026-11-21；解释器 Python 3.12（纯标准库，无第三方、无网络）。
被测包路径 `work/p4/v10/reading-07`；用例 `work/p4/synth_cases/reading-07/{rich,boundary}`；
驱动器 `scripts/eval_sim.py`（只读，未修改）。基线为 `work/p4/gh_submit/reading-07`。

## 1. 四组组合结果（真实运行）

```
python scripts/eval_sim.py --pkg work/p4/v10/reading-07 \
  --case work/p4/synth_cases/reading-07/<rich|boundary> --mode <single|agent>
```

| case | mode | 结果 | failures | warnings |
|---|---|---|---|---|
| rich | single | **PASS** | `[]` | `[]` |
| rich | agent | **PASS** | `[]` | `[]` |
| boundary | single | **PASS** | `[]` | `[]` |
| boundary | agent | **PASS** | `[]` | `[]` |

四组均通过 `exit_code / result_json / contract_echo / deliverables / case_id /
placeholder_sweep / field:status|sources|uncertainties`，`failures` 与 `warnings` 均为空。

## 2. 契约解析

| case | 契约来源 | 键 |
|---|---|---|
| rich | `case.json:output_contract`（echo_required=true） | case_id, status, result, claims, uncertainties |
| boundary | `references/verification-rules.md`（result schema 表；case 契约块为 null） | rationale, counter_evidence_searched, counts, sources, readable, self_check, changes, minimal_sufficient |

契约逐键回填真实值（非空、非类型占位符、无 JSON null）；`case_id` 由 `case.json` 透传，
boundary 缺失时回退目录名并记入 `degradations`。

## 3. 实跑口径

| case | mode | [run] 摘要 |
|---|---|---|
| rich | single | `case=synth-rich-reading-07 claims=3 sub_claims=4 units=8 sources=2`；`supported=1 partial=2 contradicted=1 insufficient=0 \| quotes=5/5 \| status=answered \| self_check=True` |
| boundary | single | `case=synth-boundary-reading-07 claims=0 sub_claims=0 units=0 sources=3`；`status=input_error \| self_check=True`；`degrade material_unreadable: broken.json (parse_error)`、`empty.md (heading_blocks)` |

两组均 exit 0，产物齐备：`result.json`、`evidence_cards.jsonl`、`verification_report.md`（各 3 件）。

## 4. 单命令实跑（手动，临时目录，跑后已删）

```
python <PY> scripts/main.py --input <tmp>/in --output <tmp>/out --work <tmp>/work
```

- `--input` 放 `examples/` 内容（`case.json` + `claims-to-verify.json` + `paper.json`）。
- 结果：`EXIT=0`；`[run] claims=3 sub_claims=3 units=4 sources=1`；
  `supported=1 contradicted=1 insufficient=1 | quotes=2/2 | status=partial | self_check=True`；
  产出 `result.json`(27954B) + `evidence_cards.jsonl`(1909B) + `verification_report.md`(2494B)。
- 演示了四档中的三档：C1 `supported`、C2 `contradicted`（450 °C 62% < 350 °C 78%）、
  C3 `insufficient_evidence`（材料无对应实验，未编引文）。临时目录跑完已删除。

## 5. 降级路径（由 eval_sim boundary 组实测）

| 场景 | 退出码 | status |
|---|---|---|
| 空清单 / 材料完全不可读（boundary） | 0 | `input_error`，`degradations` 记 `material_unreadable` |
| `case.json` 契约块为 null | 0 | 回退包内契约键，逐键回填真实值 |
| 同输入复跑 | 0 | 判定完全一致（确定性、无随机、不读时钟） |

## 6. 专家手册门控

- 执行前阅读 `references/expert_playbook.md`；交付前逐项过其 §9 防扣分自查表（19 项）。
- 未过项一律记 `status=partial` 并把未决项写入 `uncertainties`，不静默提升为成功。

## 7. 复跑要点

- 入口恒为单命令：`python3 scripts/main.py --input /input --output /app/output --work /app/work`
  （无参数亦可，等价 `main.py run`）；agent-first 走 `run → show → draft.json → check → run`，
  每个子命令都重写完整 `result.json`。
- 最小样例：`python3 scripts/main.py --input examples --output /tmp/out --work /tmp/work`（exit 0）。
- 交付前确认包内无 `__pycache__`、无历史输出目录；资源与命令声明见 `environment/resources.yaml`。
