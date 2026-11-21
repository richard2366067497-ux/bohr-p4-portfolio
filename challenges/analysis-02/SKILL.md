---
name: stats-decision-ledger
description: Turn one messy research table into a reproducible statistics package - reads the real file, cleans it while counting every step, runs the fixed gate order, picks exactly one method per question, publishes rejected alternatives, binds every number to a locator plus a verbatim quote, and writes a ledger, a report, a PDF preview and figures. Degrades honestly when the input carries no analysable data.
license: MIT
---

# Statistical analysis and result interpretation

Turn one messy research table into an auditable answer: descriptive statistics with units, the
inferential test the design and the gates allow, an effect size with a 95% interval, and a usable
interpretation, reported as an association (never a cause) because the data are observational.

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按它组织全部产出：

- **流程**：按其 §2 六步门控（解析→清洗→描述→推断→效应量与CI→解读）推进；前一步未冻结不进入下一步。
- **选方法**：按其 §2 的 Q1–Q4 决策树为每个问题选**唯一**方法，并附正态性/方差齐性依据链。
- **口径**：按其 §3 公式与容差核算效应量与 CI；按其 §4 领域陷阱逐条排雷。
- **可追溯**：按其 §5 locator 规则，报告里每个数字回到 `{文件}→{字段/行号}→{公式}`。
- **门控**：交付前逐项通过其 §6 自查表（19 项）；未过项记 `partial` 并写入不确定性，不静默提升为 `ok`。

## Output contract

Every key of `case.json -> output_contract` is echoed in `result.output_contract` and at the top level,
carrying the block this run produced or the reason it could not run:

```json
{"output_contract": {"student_t": "block or reason", "mann_whitney_u": "block or reason", "kruskal_wallis": "block or reason", "wilcoxon_signed_rank": "block or reason", "spearman_rho": "block or reason", "ols_slope": "block or reason", "fisher_exact": "block or reason", "descriptive": "block or reason"}}
```

## Draft shape (the only file an agent writes)

An agent may write `work/draft.json` before running; every decision is recomputed and any disagreement is
kept as a change record.

```json
{"case_id": "example-analysis-02", "data_plan": {"missing": {"policy": "mark_only", "columns": ["mass_g"]}, "duplicates": {"policy": "drop_exact", "keys": []}, "outliers": {"policy": "flag", "rule": "tukey_1.5iqr", "columns": ["mass_g"]}, "units": {"mass_g": "g"}}, "items": [{"decision_id": "D-02", "question_id": "Q2", "design": "two_independent_groups", "variables": {"outcome": "mass_g", "group": "group"}, "candidates": [{"method": "mann_whitney_u"}], "chosen_method": "mann_whitney_u", "multiple_comparison_family": "primary", "correction": "holm"}]}
```

Policies: `missing: listwise|pairwise|mark_only`, `duplicates: drop_exact|keep|flag_only`,
`outliers: keep|flag|winsorize|exclude`. An unknown policy or a missing column is rejected into change
records; an unknown question id or unresolvable method is skipped and counted. Without a draft: keep the
empty cell and count it, drop exact repeats, flag Tukey outliers.

## Single command entry (one shot, no draft needed)

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command reads the case, cleans the table, runs the gates, fills every contract key, writes all
deliverables and exits 0. Paths default to `/input`, `/app/output`, `/app/work` and are also flags.

## Agent path (same engine, plus a draft)

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare --input /input --work /app/work
```

`init` suggests candidate questions; `build` is `all`; `selfcheck` re-reads the written artifacts and
fails if a number drifted; `compare` measures a no-gate baseline against this run.

## Input, method and gates

`case.json` (or `challenge.json`) carries `case_id`, `language`, `materials_root` and the authoritative
`output_contract` (keys are never invented). Materials may be CSV, TSV, JSON, JSONL, SQLite, Markdown or
text; anything else is snapshotted and named. Questions follow the columns present; pairing is never
invented and a group is never manufactured by splitting a numeric column. Gate order: sample size,
normality (Jarque-Bera, >=8 obs), equal variance (Brown-Forsythe), independence, multiplicity. One method
per question, alternatives kept marked not selected, Holm within family, every p two-sided, every
interval 95%.

## Honest degradation and limits

Triggers are recorded, never hidden: missing/invalid draft (defaults), no decisions, unresolved variable
(skipped), empty groups, a draft that disagrees with the recomputed gate (recomputed wins), internal test
failure, uncomputable effect size, auto-generated interpretation, no analysable data (empty ledger), a
failed write (partial `result.json` still written). Status is `ok`, `partial` or `insufficient_evidence`.
It will not claim a cause, report a p without its effect size and interval, remove a row without counting
it, present a non-selected method as the finding, split a numeric column into groups, or pair columns that
do not declare a pairing. Standard library only, no network, no clock, seed 20240517, deterministic.
