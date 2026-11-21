# GAIN_EVIDENCE — baseline vs this skill, same input, same contract

Reproduce with the two documented entry points on the same `/input`:

```bash
# baseline view: read the materials and answer by hand (no ledger, no stats, no locator)
# this skill: one command produces the full ledger + derived stats + artifacts
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

The numbers below are from `examples/case.json` plus a small material set (3 sources, several dated claims).
They are a **baseline_sim / non-official** comparison for engineering, not a benchmark score.

**Protocol.** The baseline is what a careful reader can do: skim the materials, list a few "hot topics",
and write a paragraph. It has no dated ledger, no conservation-checked statistics, no per-claim locator,
and no explicit research-gap evidence. Both sides get the same input, the same task and the same contract.

## Quality

| measure | baseline | this skill | delta |
|-|-|-|-|
| dated events with `source_id` + `locator` + verbatim `quote` | 0 | 4–20 (grows with material) | ledger replaces prose |
| derived statistics (by_year / by_type / growth / peak) | 0 | full, conservation-checked | +all |
| stage division, each with `basis_event_ids` | 0 | 1–3 | +all |
| turning points with an enumerated `criteria_hit` | 0 | ≥1 when justified | +all |
| representative works (per stage, method-first) | "most cited list" | stage-covered, rationale stated | coverage > citation rank |
| research gaps with `exclusion_evidence` (not "not found") | 0 | 1–3 | +all |
| claims carrying a printed locator | ~0 | every ledger row | attributable errors |
| honest states (material fact / inference / undeterminable) | one blob | three explicit states | +differentiation |

The baseline's failure mode is not "wrong prose" — it is **unverifiable** prose: nothing in the paragraph
says which source, which page, which year-basis produced a claim, so a reviewer cannot recheck any single line.

## Efficiency

| measure | baseline | this skill |
|-|-|-|
| passes over the input | 1 | 1 (deterministic scripts do scanning/stat/render/check) |
| model calls for a full run | n/a (manual) | 0 for the deterministic path (`all`) |
| artifacts for a reviewer | 1 paragraph | 12 reviewable files (`result.json`, ledger, timeline, derived/*, figures, report) |
| recompute cost | re-read everything by hand | re-run one command; stats recomputed from the ledger |

## Reproducibility

- `same_input_same_ledger: true` — the `all` path is deterministic (no clock, no randomness, no network).
- `stats_conserved: true` — `derived/trend_stats.json` by-year sum equals the ledger count (`STAT_MISMATCH` = 0).

## What the baseline still wins at

Speed on a single short note, and zero setup. The skill's cost is one deterministic pass; its gain begins
where the baseline has no answer at all — dated, locator-carrying events; conserved statistics; stage and
turning-point evidence; and research gaps that are proven by exclusion evidence rather than asserted.
