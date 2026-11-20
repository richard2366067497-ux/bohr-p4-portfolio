# claim-graph-auditor — v6 repair package (review-04)

Claim/evidence graph auditor for the Bohr P4 challenge **review-04**
(论文逻辑与论证审查). Offline, pure standard library, and produces the full
deliverable set from a single command even with no draft, no case file, or no
readable material.

## Entry

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

Agent-first path (optional): `init` → `show` → write `work/draft.json` → `check` → `build` → `selfcheck`.

## Deliverables

`result.json` (contract echoed key-by-key at top level and under `output_contract`),
`logic_report.md`, `claim_graph.json`, `claim_evidence_matrix.csv`, `check_report.json`,
`run_manifest.json`, `sources.json`, `uncertainty.json`; `selfcheck` adds `verify_report.json`.

## Guarantees

- Text is parsed into located units; nodes and edges are materialised deterministically.
- Every finding carries a verbatim quote, a locator, a severity in
  `critical|major|minor|suggestion`, a facet in the six checked families, and an
  executable recommendation; unconfirmable items go to `review_pending`.
- Long material is reported as `truncated` instead of being claimed as fully audited.
- Empty or broken input still exits 0 with a legal `result.json` and honest limits.
- No placeholders: every output file is sanitised at the end of a run.

## Layout

```
SKILL.md                          entry contract, method, degradation, self-check
scripts/main.py                   CLI and pipeline (all/init/show/check/build/selfcheck)
scripts/audit_core.py             units, nodes, edges, findings, cleaning, sanitise
references/review_checklist.md    six facets, severity criteria, false-positive guards
README.md                         this file
SELFTEST.md                       reproduction steps and expected observations
GITHUB_URL.txt                    submission repository URL and challenge path
```
