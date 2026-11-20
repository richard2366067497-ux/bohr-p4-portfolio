# Outputs and the compact evidence ledger

## Preserve the case schema

Read the real `output_contract` and keep its exact keys, nesting and types in
`result.json`. Fill inline content where it is requested instead of returning a
bare filename. Extra diagnostics belong in sidecars when extra top-level fields
are forbidden. Validate the JSON and every named file. Only when no schema is
supplied at all, fall back to this shape:

```json
{"case_id":"actual identifier","status":"partial","main_result":{"manuscript_path":"/app/output/manuscript.md"},"sources":{"ledger_path":"/app/output/evidence.json"},"uncertainty":[],"changes":[],"artifacts":[],"process":{"quality_gain":"not_measured","efficiency_gain":"not_measured"}}
```

An uncertainty entry names the affected passage, the issue type, what evidence
is missing or conflicting, the effect and the next action. `partial` means real
content plus explicit unmet requirements — not an empty success.

## Ledger v1

The sidecar supplements the official output fields. IDs are stable strings and
paths are absolute at runtime or relative to the ledger directory. Copy each
used extract into the artifacts (for example `extracts/S1.txt`) so a reviewer can
check a quote independently; keep the original path and the extraction method.
Never silently edit source text to force a quote to match.

```json
{
  "schema_version": "1.0",
  "case_id": "actual identifier",
  "sources": [
    {"id":"S1","input_path":"/input/paper.pdf","extracted_path":"extracts/S1.txt","kind":"prior_work","availability":"full_text","metadata":{"authors":[],"year":null,"title":null,"venue":null,"doi":null},"extraction":"tool and options actually used"}
  ],
  "evidence": [
    {"id":"E1","source_id":"S1","locator":"section 3, paragraph 2","line_start":120,"line_end":120,"quote":"Exact short span taken from those extracted lines."}
  ],
  "references": [
    {"id":"R1","source_id":"S1","citation":"Exact rendered token used in the manuscript","metadata_status":"verified_from_input"}
  ],
  "claims": [
    {"id":"C1","text":"Exact final manuscript clause including its citation token.","role":"related_work","assessment":"supported","evidence_ids":["E1"],"citation_ids":["R1"],"rationale":"Why the evidence entails this wording, and under which conditions."}
  ],
  "groups":[{"id":"G1","label":"Evidence-derived route","axis":"Actual comparison dimension","source_ids":["S1"],"claim_ids":["C1"]}],
  "gaps":[],"contributions":[],"uncertainty":[],"changes":[]
}
```

Claim roles: `background`, `related_work`, `gap`, `contribution`, `other`.
Assessments: `supported`, `inference`, `needs_confirmation`. An `inference`
needs settled premises and a rationale. A `needs_confirmation` claim must be
visibly qualified, omitted from the clean prose, or carry an exact draft marker
recorded in uncertainty — never asserted as established fact.

Each evidence item needs a locator and a verbatim quote inside an inclusive
1-based range of the extracted lines. For figures and tables keep the original
locator and a faithful transcription and record the visual check. A matched
quote proves traceability, not extraction correctness or entailment. Keep the
conditions present in short excerpts.

Own-contribution evidence must come from sources of kind `current_work` or
`experimental_record`. A prior paper can motivate a contribution but cannot
prove that this paper performed it. Metadata-only sources cannot substantiate a
method or a result; missing metadata stays `null` with a note.

Gap record:

```json
{"id":"H1","claim_id":"C5","premise_claim_ids":["C1","C3"],"derivation":"Bounded reasoning and counterevidence assessment","scope":"Studies and conditions actually checked"}
```

Contribution record:

```json
{"id":"K1","claim_id":"C6","own_evidence_ids":["E8"],"addresses_gap_ids":["H1"],"limits":"Regimes that were not validated"}
```

For a narrow task leave the inapplicable collections empty and explain the
scope. For a full introduction an empty collection needs explicit treatment as
missing evidence or a missing mapping.

## Audit interface

```sh
python scripts/audit.py --ledger /app/output/evidence.json --draft /app/output/manuscript.md --report /app/output/audit.json
```

Exit 0: no structural errors (warnings may remain); 1: the audit found errors;
2: input/parse/shape failure. The report contains errors, warnings, counts and
input hashes. The helper writes only its named report. It checks IDs and links,
local extracts, quote positions, final-claim and citation-token presence,
inference rationale and own-work provenance. It cannot judge entailment,
unrecorded claims, novelty, complete literature coverage or journal compliance.
Read the draft backwards even at exit 0, and never suppress a ledger error while
keeping the unsupported sentence.
