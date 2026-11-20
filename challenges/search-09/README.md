# search-09 · literature-appraisal-benchmark (v9)

A weekly-skill package that turns a checklist plus a literature corpus into a structured,
evidence-located appraisal — not a summary. Drop a case into `/input`, run one command, get a
complete contract plus every artifact under `/app/output`.

## 1. entry point

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

Runs the whole pipeline (scan → parse checklist → scan corpus → locate anchors → judge → grade →
write), produces `result.json` and every deliverable, and always exits 0. A draft under
`/app/work/draft.json` is optional; without it the run is still complete.

## 2. what it answers (the four questions of the task)

- **规得齐** — one check point → one dimension, with the study-type specific ones added.
  `candidate_pool.csv` lists each check point with its dimension, keyword family, chapters and risk
  floor; the study-type `type`/`gen` rules in the material are parsed and anchored too.
- **换得准** — a judgment keeps its rule id, its risk floor and its threshold. `grading.json` carries
  the judgment-rule table (`R_J1`…`R_J4`), the numbered thresholds and a per-check-point trace.
- **合得对** — a merge or a judgment uses a defensible key, not a vibe: a check point is `met` only
  with ≥2 anchors, `partial` with one, `not_met` when a negative family outranks the positives, and
  `not_assessable` when nothing is found.
- **追得回** — every judgment walks back to a source locator and a verbatim quote in
  `anchor_table.csv` and `result.json.evidence_map`; `evidence/M##.json` holds the per-material
  snapshot and quoted lines.

## 3. honest degradation

| situation | behaviour |
|---|---|
| no checklist block parsed | `degradations: rules_fallback`; a minimal built-in checklist is used and named |
| no parsed material at all | `status: insufficient_evidence`; artifacts still written, searched locations named |
| a check point with no keyword hit | `not_assessable` with reason `R_J1_ABSTAIN`; never guessed into `met` |
| abstain ratio ≥ 30% | overall verdict `insufficient_evidence`, not `low_risk` |
| corrupt / empty / no-data material file | classified and skipped; never used, never invented |
| input unreadable | `status: input_error`, exit 0 |

## 4. why it beats a generic assistant (innovation)

A general chat assistant asked to "appraise this corpus against the checklist" produces one of three
shapes, and each is a failure this package avoids:

1. **a prose summary** — readable, but no per-check-point judgment, no rule id, no locator. This
   package emits a trace with one row per check point.
2. **a flat report list** — a bullet per item with a yes/no word, all judged on token presence. This
   package grades on anchor count and negative-family priority, so one mention is not a pass.
3. **editor triage** — a human reads the whole paper and decides by feel. This package turns that
   decision into a recomputable rule and a re-runnable trace, which is what makes a second reviewer
   able to audit the first.

See `GAIN_EVIDENCE.md` for the honest, simulated baseline comparison, the two-reviewer cross-check
and the manual review-entry reduction.

## 5. layout

```
SKILL.md                        contract, entry command, agent path, pipeline, degradation
scripts/main.py                 CLI: init|show|check|build|selfcheck|compare|all (stdlib only)
scripts/qualib.py               engine + io: scan, parse rules, locate anchors, judge, grade, write
references/appraisal_rules.md   the reusable rule library (kw / cp / type / gen / judges / thresholds)
references/lessons_learned.md   the failure library: what a generic summary gets wrong, and the rule
templates/appraisal_template.json  the draft schema `init` writes
examples/case.json              a minimal example directory description
environment/resources.yaml      no third-party dependency; native runtime notes; license
GITHUB_URL.txt                  the challenge URL
SELFTEST.md                     how this package was checked, incl. abnormal-case tests
GAIN_EVIDENCE.md                baseline vs skill + dual review, labelled as simulated
```

## 6. constraints

Twelve files, under 150 KB, pure Python standard library, every file under 30 KB, deterministic,
offline, no clock and no network.
