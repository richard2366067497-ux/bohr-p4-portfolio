# SELFTEST — systematic-review（research-03 v6）

> **验证状态（诚实声明）**：本包创作所在的 Windows 主机没有可用的 Python 解释器（仅有 Windows Store
> 占位别名，无 WSL 发行版、无 Node），因此**未能在本机实际执行** `eval_sim.py`。下表“预期”是按
> `eval_sim.py` 的入口抽取 / 契约解析 / 审计规则逐条静态推演得到的，请在 Linux `python3.10` 上按下列
> 命令实跑确认（预期全部 PASS）。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/research-03 \
  --case work/p4/synth_cases/research-03/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/research-03 \
  --case work/p4/synth_cases/research-03/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/research-03 \
  --case work/p4/synth_cases/research-03/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/research-03 \
  --case work/p4/synth_cases/research-03/boundary --mode agent
```

## 预期结果（静态推演）

| 用例 | 模式 | 预期状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 17（design_fit, risk_of_bias, sample_or_data_adequacy, reporting_completeness, directness, identified, screened_title_abstract, excluded_title_abstract, exclude, full_text_assessed, excluded_full_text, included, include, excluded, unresolved, not_screened, excluded_by_reason） | 6 |
| rich | agent | PASS | case.json:output_contract | 同上 17 键 | 6 |
| boundary | single | PASS | SKILL.md (json sample) | 25（17 + records, screening, appraisal, criteria, summary, report, case_id, status） | 6 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 25 键 | 6 |

逐项检查（预期均 PASS）：

- `exit_code`：`all`（agent 模式 `all → init → check → build → selfcheck`）均 exit 0。
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键。
- `contract_echo`：rich 17 键 / boundary 25 键均覆盖（回填取 `case` 键 ∪ 内置规范键的并集）。
- `contract_values`：5 个评价维为含 `assessed/status/note` 的非空 dict；`identified/included/…` 为非负整数；
  `excluded_by_reason` 恒非空（无排除时回退 `{"no_excluded_records": 0}`）；`records`/`screening` 为非空 list
  （无题录时含一条 `status` 占位记录结构、非空字符串）；`report`→真实 `report.md`。无 empty/placeholder/missing-file。
- `deliverables`：`prisma_flow.json`、`screening_ledger.jsonl`、`appraisal.json`、`criteria.json`、`report.md`、
  `result.json` 均存在且 >40 字节（至少一个契约交付物命中）。
- `case_id`：`synth-rich-research-03` / `synth-boundary-research-03` 原样透传。
- `placeholder_sweep`：文本产物无占位符标记；`.jsonl` 不在扫描范围，仍按清洗后写出。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为

- boundary（`output_contract=null`）：契约回退到 `SKILL.md` 的 JSON 样例（25 键），照常逐键回填。
- 空 `/input` / 无题录：`identified=0`、`status=insufficient_evidence`，`degradations` 记录原因，exit 0。
- 坏 JSON / 缺 `case.json`：忽略并以材料自建，exit 0。
- 全文不可解析：保守排除写入 `excluded_by_reason`，`uncertainties` 说明。

## 产物清单

`result.json`、`prisma_flow.json`、`screening_ledger.jsonl`、`appraisal.json`、`criteria.json`、
`report.md`（共 6 个）。

> 以上为按源码推演的预期结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
