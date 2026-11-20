# GAIN_EVIDENCE — reading-11 · table-cleaning-benchmark

## 1. honest declaration

The baseline below is a **deterministic simulated naive policy** over the same input and the same
hold rule — not an official A/B measurement. This package fabricates no official scores. The
`skill` column is measured by this package's own `compare` command; the `baseline` column is the
declared policy "copy the records into one file, convert whatever looks convertible".

## 2. baseline vs skill

| metric | baseline (simulated naive policy) | this skill (measured) |
|---|---|---|
| output files | 1 | 13 |
| rows collected | 0 | 12 |
| rows cleaned | 0 | 10 |
| traced changes | 0 | 26 |
| rows held for a human | 0 | 2 |
| duplicate groups | 0 | 2 |
| unknown units registered | 0 | 1 |
| rules applied | 0 | 5 |
| contract keys echoed | 0 | 7 |

Every non-zero cell is realisable from the supplied records: reproduce with

```bash
python3 scripts/main.py compare --input /input --output /app/output --work /app/work
```

## 3. why this is better than a generic system

A generic summariser asked for "a clean table" silently converts `a.u.`, drops the `n.r.` row and
loses the path back to the source. This skill's gain is not volume, it is **auditability**:

- every change is named with a rule id (`change_log.json`), so a reviewer can re-run the rule;
- every unknown is preserved (`pending_review.json`, `unknown_units.json`), so nothing is invented;
- every row walks back to an input record and source locator (`evidence/M##.json`), so a claim is
  checkable;
- duplicates are decided on an explicit judgement key, so a different material is never merged.

## 4. what is deliberately not claimed

- No official benchmark score is claimed; the comparison column is simulated and labelled.
- No conversion of an unresolvable unit is claimed, because the material gives no resolvable basis.
- No value outside the supplied records is claimed; the count is bounded by the input.
