# Usage-gain evidence — search-coverage-gap-auditor (search-07)

## Honest declaration

The baseline below is a **deterministic simulation of the naive workflow**, not a measured
competitor. It is defined as: "read the materials, quote the coverage number that the material
itself states, and stop." That approach produces a number but no auditable denominator and no
located misses. The contrast is therefore **structural**, computed over the same input, and is
**not an official benchmark score**.

## Structural contrast (same input, deterministic)

| Property | Naive baseline (simulated) | This skill |
|-|-|-|
| Coverage denominator | the number the material states, unverifiable | frozen reference set, `audit_trail.json` lists every `ref_id` |
| Numerator | none | hit ledger with match rule and certainty per row |
| Miss attribution | not produced | every miss mapped to one of six actionable classes with a locator |
| Supplement | not produced | planned per class with marginal yield and a stop rule |
| Recomputable | no | one formula in `audit_trail.json`; `self_check.json` re-derives it |
| Contract keys filled | 0 | every key echoed into `result.json.output_contract` |

## What is actually measurable here

- `audit_trail.json.recompute` re-derives the coverage from the numerator and denominator lists;
  `self_check.json` records whether it matches the reported figure.
- The identity `hits + misses == denominator` is asserted mechanically on every run.
- Repeat runs on the same input produce byte-identical ledgers, so the numbers are stable.

## What is *not* claimed

- No live remote search is performed, so no global recall claim is made.
- The simulated baseline is a stand-in used to make the contrast explicit; it is labelled as such
  wherever it appears (`gain_report.md`, `gain_report.json`).
