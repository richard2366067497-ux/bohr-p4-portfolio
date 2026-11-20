---
name: evidence-linked-introductions
description: Draft or revise a scientific introduction and related-work section from the supplied research materials, binding every characterisation to a verbatim source span and recording research-gap and contribution derivations. Use for 写引言、整理相关工作、补引用、核对贡献 and bilingual academic drafting where sources must stay traceable.
---

# Evidence-linked introduction and related work

Produce an editable manuscript **and** a compact evidence ledger that a second
reader can audit. The ledger supports the prose; do not replace the requested
writing with a checklist. Every scientific statement must come from the actual
case materials, never from topic labels, this file, or prior knowledge.

## 1. Entry command (single command runs the whole job)

```bash
python3 scripts/build.py --input /input --out /app/output --work /app/work
```

This one call: discovers inputs → classifies sources (current work vs prior
work) → extracts verbatim evidence spans with 1-based line ranges → groups
related work → derives a bounded gap and a contribution → writes
`manuscript.md`, `evidence.json` (ledger), `review.md`, `audit.json` and
`result.json`. No draft and no second pass are required. Missing or corrupt
material degrades to an honest `partial`/`blocked` result and still exits 0.

Optional structural re-check after hand-editing the ledger or draft:

```bash
python3 scripts/audit.py --ledger /app/output/evidence.json \
    --draft /app/output/manuscript.md --report /app/output/audit.json
```

`audit.py` exits 0 when there are no structural errors, 1 when it found errors,
2 on an input/parse failure. It never judges entailment, novelty or completeness
— only that IDs, links, quote line ranges and own-work provenance are sound.

## 2. Output contract (frozen)

- `result.json` carries `case_id`, `status`, `status_reason`, `summary`,
  `main_result`, `sources`, `artifacts`, `uncertainty`, `changes`, `process`,
  `audit`, `ledger_summary`, `limits`, `inputs`, `runtime`, `output_contract`.
- The case's own `output_contract` keys are echoed **verbatim** at the top level;
  a key whose value we cannot model still gets an honest non-null placeholder and
  is listed in `unmapped_contract_keys`.
- Sidecars, written to the same directory: `manuscript.md`, `evidence.json`,
  `review.md`, `audit.json`, and `extracts/<source>.txt` for independent quote
  inspection.
- `status` ∈ `complete | partial | blocked`. `complete` requires a grouped
  related-work passage, a bounded gap derived from cited premises and a
  contribution aligned to current-work evidence.

## 3. Workflow (inside `build.py`)

1. **Manifest**: enumerate `--input`, record relative path, bytes and sha256,
   locate `case*.json` and `task.md`.
2. **Classify sources** by filename and content: `manuscript|draft|current|results`
   → `current_work`; `review|comment|referee` → `other` (instructions, not
   evidence); everything else → `prior_work`. Each source keeps a full verbatim
   extract so line ranges stay auditable.
3. **Evidence**: one entry per substantive sentence, with `line_start =
   line_end` pointing at the exact line and a verbatim `quote` (target 20–240
   characters). Nothing is paraphrased inside a quote.
4. **Related work**: group prior-work sentences by source; attach a citation
   (`[12]` or `(Author, 2024)`) only when that token literally occurs in the
   quoted sentence.
5. **Gap**: derive from the *cited* related-work claims, never from general
   knowledge. Mark it `assessment: inference` with a rationale and an explicit
   `scope` naming the material actually checked.
6. **Contribution**: anchor to a `current_work` sentence; a prior paper can
   motivate a contribution but cannot prove this work performed it.
7. **Assemble** `manuscript.md` (Background → Related work → Gap → Contributions;
   revision mode keeps the baseline facts and appends a change table), run the
   structural audit, then write `result.json`.

## 4. Honest status and failure handling

| Situation | Result |
|---|---|
| No readable material | `blocked`; empty ledger collections; `status_reason` names it |
| Only current-work material | `partial`; related-work grouping absent, recorded in `uncertainty` |
| Related work present, no explicit gap premises | `partial`; gap left unresolved rather than invented |
| Structural audit reports errors | downgrade `complete`→`partial`, copy errors into `uncertainty` |
| Bad `case.json` | log it, keep discovering materials, `case_id=null`, do not fabricate |
| Empty input directory | `blocked`, all required keys present, exit 0 |
| Any internal error | top-level guard prints to stderr and **always exits 0** |

## 5. Self-check

- [ ] Single command writes all five artifacts without a hand-written draft.
- [ ] Every `output_contract` key appears at the top level, `null` never dropped.
- [ ] Every claim's evidence line range resolves to its quoted span.
- [ ] No citation token appears without a matching reference entry.
- [ ] `status` follows the artifacts; nothing is asserted beyond the material.

## 6. File index

| File | Role |
|---|---|
| `scripts/build.py` | entry + orchestration: discovery, extraction, ledger, draft, audit, result |
| `scripts/audit.py` | standalone structural evidence audit (IDs, links, quote ranges, provenance) |
| `references/output-and-ledger.md` | ledger v1 schema, `result.json` fallback shape, audit interface |
| `references/writing-decisions.md` | grouping / gap / contribution rules and failure checks |
