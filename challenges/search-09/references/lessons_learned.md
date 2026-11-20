# lessons_learned — a failure library for literature appraisal

Each entry is a failure seen when a generic summariser is asked to "appraise this paper against the
checklist", the wrong output it produces, and the rule in this package that prevents it. The rule ids
are the same ids that appear in `grading.json` and in `appraisal_rules.md`.

## F1 · judging an absent field as a pass  → rule `R_J1_ABSTAIN`

A summary sees no mention of blinding and writes "blinding: yes". This package grades a check point
with no keyword-family hit **`not_assessable`** and records the reason. An absent field is a gap, not
a pass — and the abstain ratio drives the overall verdict toward `insufficient_evidence`.

## F2 · one negative hit outweighed by a wall of text  → rule `R_J2_NEG`

A negative keyword ("not randomised", "no blinding") is buried under paragraphs of method prose. A
token-frequency summary counts the positive words and calls it compliant. This package gives the
negative family priority: a negative hit with fewer than two anchors grades **`not_met`** at a
`major` risk, regardless of how much prose surrounds it.

## F3 · a single mention promoted to "met"  → rule `R_J4_WEAK`

One sentence mentions the sample size, so a summary marks the sample-size check point "met". This
package requires at least two anchors for `met`; exactly one anchor is **`partial`** (`some` risk).
Evidence strength is the anchor count, not the presence of a word.

## F4 · a verbatim quote with no locator

A summary quotes a sentence but says only "from the paper". The quote cannot be checked. Every anchor
in this package carries a source id and a line locator (`M01/p37`) in `anchor_table.csv` and in
`result.json.evidence_map`; the per-material snapshot in `evidence/M##.json` holds the quoted lines.

## F5 · a threshold invented on the spot

A summary applies "more than half the items met → low risk" that exists in no rulebook. This package
reads the numbered thresholds from the material's own prose and echoes them in `grading.json`; if the
material states none, no threshold is invented.

## F6 · a missing rules block silently produces a blank report

A summariser handed a corpus with no parseable checklist returns prose. This package degrades
honestly: with no checklist it runs a minimal built-in checklist and records
`degradations: rules_fallback`; with no parsed material it still writes every artifact and names the
locations it searched, under `status: insufficient_evidence`.

## F7 · a dimension label that does not match the rule that produced it

A summary mixes DESIGN and STATSREP judgments. Every trace entry in `grading.json` keeps the
dimension, the check point, the rule id, the judgment, the risk and the anchor count together, so the
label can never drift from its rule.
