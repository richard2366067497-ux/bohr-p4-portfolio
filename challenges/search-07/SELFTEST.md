# SELFTEST — 检索覆盖与漏检闭环审计（search-07 v10）

本文件记录 **2026-11-21** 用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例 ×
single / agent 两种模式做的本地评测结果，以及一次自带 fixture 的功能运行。四组均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v10/search-07 \
  --case work/p4/synth_cases/search-07/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/search-07 \
  --case work/p4/synth_cases/search-07/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/search-07 \
  --case work/p4/synth_cases/search-07/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/search-07 \
  --case work/p4/synth_cases/search-07/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 15 | 12 |
| rich | agent | PASS | case.json:output_contract | 同 15 键 | 12 |
| boundary | single | PASS | SKILL.md (json sample) | 同 15 键 | 12 |
| boundary | agent | PASS | SKILL.md (json sample) | 同 15 键 | 12 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 功能用例（验证「真实推导」而非模板）

自带 fixture（`examples/case.json` + `examples/materials/{refset,queries,retrieved}.json`，
6 篇参考集 / 6 条池内记录 / 3 条查询）：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

- exit 0，`status = partial`。
- 冻结参考集 **6** 条，分母策略 `dedup_exclude_unavailable`，范围 **6** 条。
- 命中判定：`id_doi` 精确命中 **4** 条；R-004 因**快照内存在该记录但深度不足**判为未命中；
  R-006 标题词未进任何查询式 → 未命中。
- 初始覆盖率 = 4 / 6 = **0.6667**；遗漏率 0.3333。
- 漏检归因：R-004 → `ranking_depth`；R-006 → `query_term_missing`，各带 locator 与判定证据。
- 补检：S-01（`query_term_missing`）本地无可新增命中 → `no_gain`，触发停止规则；
  S-02（`ranking_depth`）从快照按深度重排恢复 **1** 条（R-004）。
- 补检后覆盖率 = 5 / 6 = **0.8333**；补检边际收益 = 1 / 2 = **50%**。
- `audit_trail.json` 复算 `coverage = |命中 ∩ 范围| / |范围|` 并与报告一致；
  `self_check.json` 六项全通过（含 `命中 + 遗漏 = 分母` 恒等式）。
- 12 个产物全部非空、无占位符。

## 边界行为核对

- `boundary`（空 `empty.md` + 坏 JSON + 10 字节 `notes.txt`）：无参考集文件 →
  `status = insufficient_evidence`，参考集 **0**、分母 **0**、覆盖率如实为 0；
  `degradations` 记载坏 JSON 与空文件；产物仍是**带原因的合法非空结构**（契约 15 键全部回填）。
- 无 `draft.json`：`all`/`build` 走规则抽取，仍产出全部 12 个文件。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写出带完整 `output_contract` 的 `result.json`。
- 重复运行同一输入：命中台账、覆盖率、补检计划逐字节一致（确定性；时间戳不参与判等）。

## 可靠性自测（随包可运行）

`python3 scripts/main.py selfcheck --output /app/output --work /app/work` 重新核对产物是否齐全、
`output_contract` 是否逐键回显、`命中 + 遗漏 = 分母` 是否成立、覆盖率是否可复算。四组 eval_sim
运行时均为 `files ok, contract ok`。

## 产物清单（每次运行写入 --output）

result.json、scope_card.md、hit_ledger.csv、gap_matrix.csv、gap_atlas.json、supplement_plan.md、
coverage_report.md、audit_trail.json、self_check.json、gain_report.md、gain_report.json、run_log.txt。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
