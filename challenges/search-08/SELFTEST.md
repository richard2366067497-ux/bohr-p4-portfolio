# SELFTEST — 筛选去重与冲突仲裁闭环审计（search-08 v10）

本文件记录 **2026-11-21** 用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例 ×
single / agent 两种模式做的本地评测结果，以及一次自带 fixture 的功能运行。四组均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v10/search-08 \
  --case work/p4/synth_cases/search-08/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/search-08 \
  --case work/p4/synth_cases/search-08/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/search-08 \
  --case work/p4/synth_cases/search-08/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/search-08 \
  --case work/p4/synth_cases/search-08/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 6 | 12 |
| rich | agent | PASS | case.json:output_contract | 同 6 键 | 12 |
| boundary | single | PASS | SKILL.md (json sample) | 同 6 键 | 12 |
| boundary | agent | PASS | SKILL.md (json sample) | 同 6 键 | 12 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 功能用例（验证「真实推导」而非模板）

自带 fixture（`examples/case.json` + `examples/materials/records.json`，
8 条题录含 1 对预印本/正式版、1 条设计排除、1 条语言排除、1 条动物排除、1 条缺摘要、1 处方分歧）：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

- exit 0，`status = partial`。
- 去重：输入 **8** 条，合并 **1** 对（预印本 `REC-002` 与正式版 `REC-003`，依据 `preprint_of_same_study`），
  去重后 **7** 条；去重合并率 = 1/8 = **0.125**。
- 筛选：纳入 **2**、排除 **3**（设计 / 语言 / 人群）、待裁决 **2**（缺摘要 1、仅摘要纳入需全文 1）。
- 双人独立判断 7 条，冲突 **1** 处，经标准仲裁（非多数投票）；一致率 = **0.8571**，Cohen's kappa = **0.7812**。
- 理由码覆盖率 = **1.0**；证据片段覆盖率 = **1.0**；计数闭合 = **True**；审计链完整率 = **1.0**。
- `count_closure.md` 复算 `8 − 1 = 7` 且 `7 = 2 + 3 + 2`，与报告一致；`self_check.json` 八项全通过。
- 12 个产物全部非空、无占位符。

## 边界行为核对

- `boundary`（空 `empty.md` + 坏 JSON `broken.json` + 10 字节 `notes.txt`）：无题录 →
  `status = insufficient_evidence`，计数如实为空，`degradations` 记载坏 JSON 与空文件；
  产物仍是**带原因的合法非空结构**（契约 6 键全部回填）。
- 无 `draft.json`：`all`/`build` 走规则抽取，仍产出全部 12 个文件。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写出带完整 `output_contract` 的 `result.json`。
- 重复运行同一输入：筛选表、去重报告、冲突报告、指标逐字节一致（确定性；时间戳不参与判等）。

## 可靠性自测（随包可运行）

`python3 scripts/main.py selfcheck --output /app/output --work /app/work` 重新核对产物是否齐全、
`output_contract` 是否逐键回显、计数是否闭合。四组 eval_sim 运行时均为 `files ok, contract ok`。

## 产物清单（每次运行写入 --output）

result.json、screening_table.csv、dedup_report.json、conflict_report.json、audit_log.jsonl、
criteria.json、search_protocol.json、count_closure.md、self_check.json、gain_report.md、
gain_report.json、run_log.txt。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
