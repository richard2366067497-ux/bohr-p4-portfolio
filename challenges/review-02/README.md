# citation-fact-audit — review-02 (v10)

One manuscript plus its materials in, one auditable review package out: every checkable claim located verbatim,
the citation support verdict the rubric allows, typed findings with severity and an executable revision, an
annotated manuscript, and an evidence stream where each row carries a locator.

> **执行前必读** `references/expert_playbook.md`；产出前逐项过其 §8 的 18 项自查表，未过即 `status=partial`。

## Run

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command, no draft needed, exit 0. The agent path (`init` / `show` / `check` / `build` / `selfcheck`) runs the
same engine step by step; `compare` measures a no-gate baseline. Paths default to `/input`, `/app/output`,
`/app/work` and are also flags.

## Input and output

`case.json` (or `challenge.json`) carries `case_id`, `language` and the authoritative `output_contract`; materials
may be Markdown, text, JSON, CSV or PDF. No contract is invented: without one the package declares the six
standard keys (`case_id`, `deliverable`, `evidence_map`, `change_log`, `coverage`, `status`) and echoes them.

One pass writes `result.json` (contract echo plus `status` / `sources` / `uncertainties` / `change_records` /
`limits`), `citation_report.md`, `manuscript.md`, `evidence.jsonl`, `index.json`, `run_manifest.json`.

## Method and gates

Six facets (citation, fact, statistics, logic, method, compliance) each carry a checked state; the verdict order
is fixed - marker pairing, then direction / numeric / scope, then severity. `full_support` requires all three
elements true, otherwise the run downgrades it and records the change. Verdicts are S/P/N/U; severities
critical/major/minor/suggestion. Quotes are checked NFKC- and whitespace-normalised inside a single unit; a quote
that does not hit verbatim drops to pending review.
