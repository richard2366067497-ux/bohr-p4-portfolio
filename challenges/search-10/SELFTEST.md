# SELFTEST — 跨语种 known-item 检索（search-10 v9）

本文件记录 **2026-11-21** 用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例 ×
single / agent 两种模式做的本地评测结果，以及一次自带材料的功能运行。所有评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v9/search-10 \
  --case work/p4/synth_cases/search-10/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/search-10 \
  --case work/p4/synth_cases/search-10/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/search-10 \
  --case work/p4/synth_cases/search-10/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/search-10 \
  --case work/p4/synth_cases/search-10/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 6（case_id, deliverable, evidence_map, change_log, coverage, status） | 10 |
| rich | agent | PASS | case.json:output_contract | 同 6 键 | 10 |
| boundary | single | PASS | SKILL.md (json sample) | 同 6 键 | 10 |
| boundary | agent | PASS | SKILL.md (json sample) | 同 6 键 | 10 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 功能用例（验证「真实推导」而非模板）

对 rich 用例（`materials/glossary.md` + `materials/draft-schema.md`）：

```bash
python3 scripts/main.py all --input <rich-case> --output /tmp/out --work /tmp/work
```

- exit 0，`result.json.status = partial`（材料是术语表与 schema，**没有视图**，因此不产生命中卡——
  如实留空，不伪造命中）。
- 解析内置术语表 **60** 个概念 × **5** 个语种（pt/en/es/fr/de）。
- 概念锚点 **300** 条（60 概念 × 5 语种），全部来自材料**逐字出现**的术语行；
  逐字证据 **94** 条，`evidence_stats = {total: 94, verbatim_hits: 94, hit_rate: 1.0}`。
- 逐语种查询式 **300** 条、`query_languages = [de, en, es, fr, pt]`；无效语种查询 **0**。
- 跨语种术语对齐 **217** 条成对证据，全部可回查术语表行（`term_alignment_accuracy = 1.0`）。
- `views_total = 0`、`distinct_works = 0`、`duplicates = 0`（材料未提供视图文件）。
- 契约回填 **6/6**（顶层 + 嵌套 `result.output_contract`），`contract_check.missing` 为空。
- `gain_metrics`：非英语语种 4、翻译服务调用 **0** 次、人工核对 1 条、逐字命中率 1.0。
- `check_report.json.status = ok`（D0–D8 / K1–K4 全通过）。
- 10 个产物全部非空、无占位符。

## 边界行为核对

- `boundary`（空 `empty.md` + 坏 JSON + 6 字节 `notes.txt`）：`status = insufficient_evidence`，
  术语表概念 **0**、查询 **0**、视图 **0**；`coverage` 各项如实为 0，`degradations` 写明
  「材料没有术语表 / 没有视图 / 没有题面」；产物仍是**带原因的合法非空结构**。
- 无 `draft.json`：`build`/`all` 走术语表驱动抽取，仍产出全部 10 个文件。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写出带完整 `output_contract` 的 `result.json`
  （`status=input_error`）。
- 重复运行同一输入：查询计划、术语对齐、命中卡逐字节一致（确定性；`selfcheck` 记录 `repeatable`）。

## 可靠性自测（随包可运行测试）

`python3 scripts/main.py selfcheck --output /app/output --work /app/work` 即随包可靠性测试：
核对 10 个产物是否齐全、`output_contract` 是否逐键回显、是否有 near-empty 文件，
结果写入 `work/selftest_report.json`。四组 eval_sim 运行时均为
`files ok, contract echo ok, near-empty absent`。

## 产物清单（每次运行写入 --output）

result.json、search_report.md、lang_queries.md、query_plan.json、glossary_index.json、
answer_cards.json、reconciliation.md、check_report.json、evidence.json、baseline_comparison.md
（共 10 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
