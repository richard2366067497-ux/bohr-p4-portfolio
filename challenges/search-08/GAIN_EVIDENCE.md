# Usage-gain evidence — screening-dedup-conflict-auditor (search-08)

## Honest declaration

The baseline below is a **deterministic simulation of the naive workflow**, not a measured
competitor. It is defined as: "read the materials, list the records, and stop." That approach
produces a list but no reason codes, no evidence locators, no count closure and no arbitration.
The contrast is therefore **structural**, computed over the same input, and is
**not an official benchmark score**.

## Structural contrast (same input, deterministic)

| Property | Naive baseline (simulated) | This skill |
|-|-|-|
| Count closure | none | `count_closure.md` asserts `input − merges = after_dedup = include + exclude + needs_review` |
| Reason codes | not produced | every screened row carries a dictionary code |
| Evidence | not produced | every row carries a locator and a title/abstract excerpt |
| Dedup | not produced | each pair keeps its basis; DOI mismatch is never merged |
| Conflicts | not produced | standard-based arbitration with a recorded basis, never majority vote |
| Standard version | none | `criteria-<hash>` frozen; every judgement records `standard_version` |
| Recomputable | no | `check` re-derives closure and coverage in `work/check_report.json` |
| Contract keys filled | 0 | every key echoed into `result.json.output_contract` |

## What is actually measurable here

- The identity `input − merges == after_dedup` and `after_dedup == include + exclude + needs_review`
  is asserted mechanically on every run and written to `count_closure.md`.
- `cohen_kappa` and `inter_reviewer_agreement` are recomputed from the two reviewer label sequences.
- Repeat runs on the same input produce byte-identical tables, so the numbers are stable.

## What is *not* claimed

- No live database search is performed, so no global recall claim is made.
- The reviewers are simulated and labelled as such; no human review is claimed.
- The simulated baseline is a stand-in used to make the contrast explicit; it is labelled as such
  wherever it appears (`gain_report.md`, `gain_report.json`).
