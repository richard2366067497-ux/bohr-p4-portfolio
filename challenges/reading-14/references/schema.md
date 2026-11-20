# Schema: extraction, graph and delivery contract

Everything below is closed-vocabulary. Values outside these sets are a build
error on purpose — the graph never silently accepts a type or relation it does
not understand.

## Node vocabulary (closed)

| type | means | typical fields |
|---|---|---|
| `researcher` | a named person or group attached to a study | label, affiliation |
| `material` | a physical substance, dataset, corpus or sample | label, conditions |
| `method` | a technique, model, architecture or protocol | label, conditions |
| `task` | an objective the paper states | label |
| `metric` | a measured quantity | label, value |
| `conclusion` | a stated finding or claim | label |

IDs are stable strings, one per concept instance; labels keep the paper's own
surface form and aliases keep its abbreviations.

## Relation vocabulary (closed)

`uses`, `compares`, `outperforms`, `supports`, `contradicts`.

Direction conventions (do not reverse them):

- `task -> method` : uses
- `method -> material | metric` : uses
- `material -> material` : compares / outperforms, control as the target
- `metric | researcher -> conclusion` : supports
- `conclusion <-> conclusion` : contradicts

An edge that does not fit these directions is a modelling mistake, not a new
relation.

## Graph record

`graph.json`

```json
{
  "schema_version": "graph/v1",
  "case_id": "…",
  "nodes": [
    {"node_id":"met.widenet","type":"method","label":"WideNet","aliases":["WN"],
     "description":"","conditions":"","attributes":{},
     "mentions":[{"source_id":"primary","paragraph_id":"p1","section":"methods",
                  "quote":"We trained WideNet (WN) on ToySet (TS)","strength":"direct","role":"self"}],
     "source_ids":["primary"],"paragraph_ids":["p1"],"degree":1}
  ],
  "edges": [
    {"edge_id":"e1","type":"uses","source":"met.widenet","target":"mat.toyset",
     "conditions":"","evidence":[{"source_id":"primary","paragraph_id":"p1",
     "section":"methods","quote":"We trained WideNet (WN) on ToySet (TS)","strength":"direct","role":"self"}],
     "source_ids":["primary"]}
  ],
  "alignment":[…],"conflicts":[…],
  "stats":{"nodes":0,"edges":0,"node_types":{},"relation_types":{},"sources":[],"evidence":0},
  "validation":{"errors":[],"warnings":[]}
}
```

Every node and edge carries at least one `mention`/`evidence` entry whose
`quote` is a verbatim slice of the paragraph named by `source_id` +
`paragraph_id`. `paragraph_id` is the organiser's JATS identifier, never a PDF
page number. `strength` is one of `direct | indirect | review`; `role` is
`self` (this paper's own result) or `other` (someone else's, reported).

## Cross-paper alignment

```json
{"concept_a":"WideNet, primary","concept_b":"WideNet, secondary",
 "decision":"undetermined","basis":"same surface form, no shared instance stated",
 "node_ids":["met.widenet","met.widenet2"],"conditions_note":"same term, unproven identity"}
```

`decision` is `merge | keep_distinct | undetermined`. Merge only when identity is
actually established; `undetermined` is the correct answer whenever no supplied
sentence compares the two objects. A generic term recurring in two independent
papers is not evidence that they share a sample, dataset or condition.

## Conflicts

```json
{"topic":"…","node_ids":[…],"source_a":"primary/p1","source_b":"secondary/p1",
 "detail":"Values metric.score=0.91, metric.score2=0.80 …",
 "handling":"both kept under their own conditions; no average invented"}
```

A condition difference is not a conflict; record it and keep both statements
under their own scopes. Never average incompatible measurements into one value.

## Queries

```json
{"query_id":"q1","question":"What does WideNet connect to?","answer":{…},
 "status":"answered","start_nodes":["met.widenet"],
 "subgraph":{"nodes":[…],"edges":[…]},"claims":[],"evidence":[…],"undetermined":[]}
```

At least three queries are executed, each with the excerpt evidence it used.
A miss is `status: "undetermined"` with a reason — never a fabricated answer.

## result.json contract

Required top-level fields: `case_id`, `status`, `graph`, `queries`, `alignment`,
`conflicts`, `uncertainty`, `artifacts`. Also carried: `summary`, `sources`,
`merges`, `change_records`, `validation`, `runtime_notes`, `output_contract`.

`status` is `success | partial | undetermined | refused`:

- `success` — graph, alignment, conflicts and ≥3 queries all produced.
- `partial` — real graph plus a known unmet piece (rejected candidates, no alignment).
- `undetermined` — no readable material at all.
- `refused` — reserved for a request that cannot be answered honestly.

Sidecars: `graph.json`, `nodes.csv`, `edges.csv`, `query_results.json`,
`validation.json`, `work/corpus.json`, `work/extraction.json`.

## validation.json

`{"result":"result.json","pass":bool,"checks_total":N,"checks_failed":M,
  "errors":[…],"checks":[{"check":"…","pass":bool,"detail":"…"}]}`

It proves structure and verbatim binding, not entailment, coverage or truth.
