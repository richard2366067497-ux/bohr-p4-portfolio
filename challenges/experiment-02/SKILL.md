---
name: plan-feasibility-review
description: Turn a batch of experiment material into a reviewable, source-grounded feasibility review — the seven categories (equipment, material, time, sample, ethics and safety, parameter ranges, risks and exceptions) checked item by item against versioned candidate plans, with locator and verbatim quote, a line-level duration and cost ledger with self-checks, the four-state resource mapping, blocked categories, and the confirmations that must be closed before approval. Use when a task asks whether a plan can actually be run, what a plan did not declare, which version is feasible, or what must be confirmed first.
version: 2.6.0
---

# plan-feasibility-review

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, the sample below
applies:

```json
{"output_contract": {"case": "string", "case_id": "string", "plan": "string",
 "equipment": "string", "material": "string", "booking": "string", "budget": "string",
 "domains": "string", "approval": "string", "source": "string", "task": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is written
into any artifact.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan the input → index the material with locators → pull
resource rows, price and booking contracts, finite parameter domains and stated bounds → build
the seven-category verdict for every candidate version → derive the serial duration and the
per-run cost line by line → rank the versions → collect the confirmations and degradations →
render the artifacts → fill the contract → sweep empty-value tokens. It works with no draft
present, prints a one-line summary and exits 0. Empty input, malformed JSON and a missing
`case.json` still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
# the agent reads the material and writes /app/work/draft.json (chosen_version + recommended values)
python3 scripts/main.py check       # map the draft's recommended values onto the extracted domains and bounds
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to confirm
every proposed setting sits inside its declared domain, then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case", "chosen_version": "the version under review",
 "recommended": {"parameter name": 120},
 "resource_notes": ["free text note about a resource that the material leaves implicit"],
 "constraints_added": ["free text rule the agent read from the prose"],
 "uncertainties": ["what could not be read from the material"],
 "change_log": ["what the agent changed and why"]}
```

`check` maps each `recommended` key onto a declared parameter domain (exact key first, then a
unique substring match), reports `inside_domain` per entry plus any key that maps to nothing, and
reports the constraint violations of the mapped values. Out-of-range settings must be fixed
before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `feasibility_review.md` | status and reason, the seven-category table per version, the line-level duration and cost, the domains and bounds each with locator and quote, the risks, the confirmations, the arithmetic ledger and the degradations |
| `checks.json` | the per-version × per-category state ledger, the ranked order and the winner, the parameter domains with evidence, the rule index and the evidence hit-rate |
| `estimate.json` | the duration and cost formula, the per-version estimate with its step lines and cost lines, the budget, the evidence for the ceiling and every arithmetic self-check |
| `risks.json` | the risk items per version, every stated bound with its evidence, and the unavailable resources |
| `confirmations.json` | the confirmations that must be closed before approval, the approval items and the budget state |
| `evidence.json` | every extracted item with source_id, locator, verbatim quote and a hit-rate |
| `version_diff.md` | one row per version (settings, blocked count, per-run cost, budget share, feasible, locator) and the winner |
| `result.json` | the contract keys plus resources, domains, constraints, versions, the arithmetic checks, the confirmations, limits, uncertainties, sources, change records and artifacts |

## 5. Seven categories

Every candidate version is reviewed across equipment, material, time, sample, ethics and safety,
parameter range, and risks and exceptions. Each category resolves to one of `ready`,
`conditional`, `blocked` or `unknown`, and every `blocked` is quoted back to the material line
that produced it. Equipment, material and booking rows map by the four-state wording the material
uses (already in place / can be outsourced / must be procured / unavailable). A category the
material does not carry is reported as not-declared — never silently treated as satisfied.

## 6. Arithmetic and revision

Duration is the sum of serial step minutes plus one maximum per parallel group; cost is
`amount × unit price` per priced item (consumables plus booking days), summed to a per-run cost.
Both are written out line by line and re-checked (step-line sum vs duration, cost-line total vs
per-run cost, budget ceiling, version count, winner feasibility). A version is feasible only when
no category is blocked and the per-run cost stays inside the declared ceiling. Versions are ranked
by feasibility, then blocked-category count, then per-run cost.

## 7. Boundaries

Standard library only, offline, no third-party dependency. No significance testing. Missing
budget, domain, sample plan or approval is preserved as an open item with a reason — never
guessed. Nothing is fetched or installed.
