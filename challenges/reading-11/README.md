# reading-11 · table-cleaning-benchmark (v9)

A weekly-skill package that cleans a batch of real literature extraction records into one
standardised, source-traceable table. Drop a case into `/input`, run one command, get a complete
contract plus every artifact under `/app/output`.

## 1. entry point

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

Runs the whole pipeline (scan → collect → normalise → hold → duplicate-detect → write), produces
`result.json` and every deliverable, and always exits 0. A draft under `/app/work/draft.json` is
optional; without it the run is still complete.

## 2. what it answers (the four questions of the task)

- **规得齐** — one indicator → one field name. `Band gap (eV)`, `bandgap`, `bank gap` all collapse to
  `band gap`; the change is recorded with rule `R_IND`.
- **换得准** — a conversion keeps the original, shows the precision and never breaks a range. This
  package holds any unit it cannot resolve rather than inventing a factor (`R010`, the declared rule).
- **合得对** — duplicate detection uses the judgement key `material | indicator | value | unit`, so
  `TiO2` and `titanium dioxide` merge but two different materials never do, and a held row is never
  merged.
- **追得回** — every changed value carries the `rule_id` that caused it and walks back to its input
  row; `evidence/M##.json` holds the per-material snapshot and quoted lines.

## 3. honest degradation

| situation | behaviour |
|---|---|
| no record row in the material | `status: insufficient_evidence`; artifacts still written, the searched locations are named |
| corrupt / empty / no-data material file | classified and skipped; never used, never invented |
| arbitrary unit (e.g. `a.u.`) or unreported value (`n.r.`) | held for a human, listed in `pending_review.json`, never converted |
| input unreadable | `status: input_error`, exit 0 |

## 4. why it beats a generic assistant

A general chat assistant asked to clean a table will silently convert `a.u.` to something, drop the
unreported rows and lose the trace. This package does the opposite: it makes every judgement explicit
in `change_log.json`, keeps every unknown in `pending_review.json`, and ties every row back to an
input record and a source locator. See `GAIN_EVIDENCE.md` for the honest, simulated baseline
comparison.

## 5. layout

```
SKILL.md                        contract, entry command, agent path, pipeline, degradation
scripts/main.py                 CLI: init|show|check|build|selfcheck|compare|all (stdlib only)
scripts/cleanlib.py             engine + io: scan, collect, normalise, hold, dedupe, write
references/cleaning_guide.md    the rule chain and the hold discipline, in prose
references/rules_library.json   the machine-readable rule library used by the engine
templates/cleaning_draft.json   the draft schema `init` writes
examples/case.json              a minimal example directory description
environment/resources.yaml      no third-party dependency; native runtime notes; license
GITHUB_URL.txt                  the challenge URL
SELFTEST.md                     how this package was checked
GAIN_EVIDENCE.md                baseline vs skill, labelled as simulated
```

## 6. constraints

Twelve files, under 150 KB, pure Python standard library, every file under 30 KB, deterministic,
offline, no clock and no network.
