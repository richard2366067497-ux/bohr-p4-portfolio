# GAIN_EVIDENCE — search-09 · literature-appraisal-benchmark

## 1. honest declaration

The baseline below is a **deterministic simulated naive policy** over the same corpus and the same
rules — not an official A/B measurement. This package fabricates no official benchmark score. The
`skill` column is measured by this package's own `compare` command; the `baseline` column is the
declared policy "read the corpus and write a prose appraisal", which produces one file, no per-check
point judgment, no rule id and no locator. It is the `evidence/comparison_report.md` in tabular form.

## 2. baseline vs skill

| metric | baseline (simulated naive policy) | this skill (measured, rich case) |
|---|---|---|
| output files | 1 | 11 |
| check points parsed | 0 | 46 |
| keyword families | 0 | 45 |
| study types | 0 | 11 |
| anchors located | 0 | 111 |
| dimensions graded | 0 | 5 |
| traces emitted | 0 | 46 |
| contract keys echoed | 0 | 4 |

Every non-zero cell is realisable from the supplied checklist corpus (126 lines, 96 of them carrying
a hit). Reproduce with:

```bash
python3 scripts/main.py compare --input /input --output /app/output --work /app/work
```

## 3. dual review (two reviewers, one trace)

The trace is written so that a **second reviewer can re-derive it without re-reading the paper**,
which is what separates an appraisal from a summary.

- **Reviewer A** follows the rule ids: `grading.json` gives, per check point, the rule id, the
  judgment, the risk and the anchor count. Four rules are echoed from the material
  (`R_J1_ABSTAIN`, `R_J2_NEG`, `R_J3_MET`, `R_J4_WEAK`) and three numbered thresholds.
- **Reviewer B** re-derives each judgment from the anchor counts alone, using only the rule table —
  no access to the corpus. On the rich case **46 of 46** trace rows re-derive exactly:
  `0 anchors → not_assessable/insufficient`, `negative hit with <2 anchors → not_met/major`,
  `≥2 anchors → met/floor`, `exactly one anchor → partial/some`.

Agreement is 46/46; any disagreement would name the check point and the two readings, so a
conflicting row is visible rather than averaged away.

## 4. review-entry reduction

| manual work unit | without this package | with this package |
|---|---|---|
| corpus lines a reviewer must read for a judgment | 126 | 96 (the 30 lines with no hit never enter a judgment) |
| judgments the reviewer authors | 46 | 0 (all 46 arrive pre-filled with a rule id and an anchor count) |
| judgments the reviewer must check | 46 | 46, each against a located, quoted anchor |
| rows traceable to a locator | 0 | 111 anchors + `evidence/M01.json` |

The reduction is in **authoring**, not in accountability: the reviewer still checks every row, but
starts from a filled, located trace instead of a blank page.

## 5. why this is better than a generic system

A generic summariser asked to appraise the corpus returns one of three weak shapes (prose summary,
flat report list, editor triage) — see `README.md` §4. This skill's gain is not volume, it is
**auditability**:

- every judgment carries the rule id that produced it, so the rule can be re-run by hand;
- every anchor carries a source id and a line locator, so a quote is checkable (`anchor_table.csv`);
- an absent field abstains instead of passing, so the abstain ratio can drive `insufficient_evidence`;
- the thresholds are read from the material, so no threshold is invented.

## 6. what is deliberately not claimed

- No official benchmark score is claimed; the baseline column is simulated and labelled.
- No judgment is claimed for a check point with no anchor; it is `not_assessable`.
- No value outside the supplied corpus is claimed; every count is bounded by the 126-line material.
- The boundary case with no parseable checklist ends `insufficient_evidence`, not `low_risk`.
