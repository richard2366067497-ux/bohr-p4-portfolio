# stats-decision-ledger — analysis-02 (v10)

One messy table in, one auditable statistics package out: descriptive statistics, the gated inference, an
effect size with a 95% interval, and a ledger binding every number to a locator and a verbatim quote.

> **执行前必读** `references/expert_playbook.md`；产出前逐项过其 §6 的 19 项自查表，未过即 `status=partial`。

## Run

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One shot, no draft needed, exit 0. The agent path (`init` / `build` / `selfcheck` / `compare`, plus `show`
and `check`) runs the same engine step by step. Paths default to `/input`, `/app/output`, `/app/work` and
are also flags.

## Input and output

`case.json` (or `challenge.json`) carries `case_id`, `language`, `materials_root` and the authoritative
`output_contract`. Materials: CSV, TSV, JSON, JSONL, SQLite, Markdown or text; anything else is snapshotted
and named; a draft is optional and never wins over the gates. Example: put such a case beside
`examples/sample_data.csv` and run `all` → 6 questions, 15 ledger rows, 25 evidence rows, 5 figures,
`status: ok`. One pass writes `result.json`, the ledger + CSV projection, `cleaned_data.csv`,
`evidence.json`, `decision_log.json`, the manifests, `report.md`/`report.pdf` and `self_check.json`.

The gate order is printed with every verdict (sample size, normality ≥8 obs, equal variance, independence,
multiplicity); one method per question; losing candidates are kept marked not selected with the reason.
No causal claim, no p without effect size+interval, no silent row removal, no non-selected method as the
finding. With no analysable data: `status: insufficient_evidence`, every key `computed: false` with a
reason, the ledger empty rather than padded.
