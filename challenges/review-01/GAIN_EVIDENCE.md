# GAIN_EVIDENCE — baseline vs this skill, same input, same contract

Reproduce with the documented entry points on the same `/input`:

```bash
python3 /skills/weekly-skill/scripts/main.py init      # index + legal partial result.json
#   reviewing agent reads materials, writes /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py build     # final deliverable, unconditional finalize
```

Numbers below come from a small manuscript (one doc, conflicting participant counts) and are a
**baseline_sim / non-official** comparison for engineering, not a benchmark score.

**Protocol.** The baseline is what a careful reader can do: read the paper, list "things that look off",
and write a paragraph. It has no per-item locator, no verbatim-quote check, no typed verdict, and no
coverage ledger. Both sides get the same input, the same task and the same contract.

## Quality

| measure | baseline | this skill | delta |
|-|-|-|-|
| findings, each with a paragraph-level locator + verbatim quote | 0 (prose) | every candidate rising to a finding | attributable errors |
| quote verified against the material (NFKC + whitespace) | no | yes, per finding (`quote_verified`) | +a machine check |
| typed verdict (error / insufficient / compliance / suggestion / pending) | no | yes | +classification |
| cross-section numeric conflicts detected | by eye | rule `CO-01/02` on repeated numbers | +systematic |
| citation-vs-reference mismatch | by eye | rules `CI-01..05` | +systematic |
| coverage ledger over 7 facets, explicitly `checked`/not | no | yes, with `unchecked_items` | +honesty |
| severity not flat (critical / major / minor) | one tone | anchored, each with `severity_reason` | +graded |

The baseline's failure mode is not "wrong prose" — it is **non-actionable** prose: nothing says which
sentence, which page, or which check facet produced a complaint, so an author cannot act on it and a
reviewer cannot recheck it.

## Efficiency

| measure | baseline | this skill |
|-|-|-|
| passes over the input | 1 (manual read) | 1 (rules scan + the agent's read are one pass; `build` finalizes) |
| artifacts for a reviewer | 1 paragraph | 5 reviewable files (`result.json`, `audit_report.md`, `evidence.jsonl`, `candidates.json`, `run_manifest.json`) |
| recheck cost | re-read by hand | `show --seg <locator>`, or re-run `check` |

## Reproducibility

- `same_input_same_result: true` — `result.json` is byte-identical across runs; only `run_manifest.json`
  timing differs (no clock, randomness or traversal-order dependence in the pipeline).
- `contract_keys_echoed: true` — every `output_contract` key is echoed to the top level and inside
  `output_contract`, with a real non-null value.

## What the baseline still wins at

Speed on a single obvious typo, and zero setup. The skill's cost is one deterministic pass; its gain
begins where the baseline has no answer at all — per-item locators and verbatim quotes, typed verdicts,
systematic cross-section checks, a coverage ledger, and an honest list of what was not checked.
