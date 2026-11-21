# SELFTEST — intro-relatedwork-writer（writing-07 v10）

本文件记录 **2026-11-21** 用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例 ×
single / agent 两种模式做的本地评测结果，以及一次自带材料的功能运行。所有评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v10/writing-07 \
  --case work/p4/synth_cases/writing-07/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/writing-07 \
  --case work/p4/synth_cases/writing-07/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/writing-07 \
  --case work/p4/synth_cases/writing-07/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/writing-07 \
  --case work/p4/synth_cases/writing-07/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 5（case_id, deliverable, preserved_facts, evidence_map, change_log） | 10 |
| rich | agent | PASS | case.json:output_contract | 同 5 键 | 10 |
| boundary | single | PASS | SKILL.md (json sample) | 同 5 键 | 10 |
| boundary | agent | PASS | SKILL.md (json sample) | 同 5 键 | 10 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 功能用例（验证"真实推导"而非模板）

对 rich 用例（`materials/manuscript-baseline.md` + `materials/reviewer-comments.md`）：

```bash
python3 scripts/main.py all --input <rich-case> --output /tmp/out --work /tmp/work
```

- exit 0，`result.json.status = answered`，产物 **10** 文件。
- 事实 **7** 条（逐字），引用标记 **1** 个（[12] → S1），评审意见块 **4** 处（含 Reviewer 1 段与
  3 条 Comment）。
- 逐字命中率 `evidence_stats.hit_rate = 1.0`。
- 研究空白前提 **4** 条（≥2，满足 gap-first）。
- `preserved_facts`：**6** 个数字/引用锚点逐字保留，dropped 为空。
- `metrics`：elapsed_s / requests=5 / rounds=1 / verbatim_hit_rate / gap_premises 全部写入 `result.json`。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`，四段如实留空
  并记录不确定性；`evidence.json`/`claim_map.md` 等仍为带原因的诚实非空结构；不编造数字或引用。
- 无 `draft.json`：`build`/`all` 使用规则化推导，仍产出全部 10 个产物；`degradations`/`uncertainties`
  提示需人工复核。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`（`status=input_error`）。

## 可靠性自测（随包可运行测试）

`main.py selfcheck` 即随包可靠性测试：核对 10 个产物是否齐全、契约是否逐键回显、是否有
near-empty 或占位符文件，并把结果写入 `work/selftest_report.json`。四组 eval_sim 运行时均
`files ok, contract echo ok, near-empty absent, placeholders absent`。

## 产物清单（每次运行写入 --output）

result.json、manuscript.md、sources_used.md、claim_map.md、gap_ledger.md、
contribution_alignment.md、change_log.md、baseline_comparison.md、evidence.json、
verification.json（共 10 个）。

## v10 复跑与随包方法论

- 新增 `references/expert_playbook.md`（判分要点/公式/领域陷阱/20 项检查表/完整虚构案例）；
  SKILL.md 增加「执行前必读（专家方法论）」，版本 9.0.0 → 9.1.0。
- `eval_sim.py` 四组组合（`work/p4/v10/writing-07` × {rich,boundary} × {single,agent}）全 **PASS**，
  `failures=[] warnings=[]`；rich 契约 5 键（`case.json:output_contract`）、boundary 取
  `SKILL.md (json sample)`。
- 单命令实跑（输入 `examples/`）：`exit 0`，10 个产物，`status=partial`（示例材料仅含草稿骨架）。
- 13 个文件、合计 81,200 B（≤14 文件、≤150KB、单文件 ≤30000 B）；`__pycache__` 已清理。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
