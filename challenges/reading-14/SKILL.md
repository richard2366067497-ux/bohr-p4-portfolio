---
name: reading-14
description: Build an evidence-bound literature knowledge graph from a small multi-paper corpus — nodes, typed edges, cross-paper alignment, conflicts, executed queries and a validated result.json — in one deterministic command.
---

# Reading-14 — evidence-bound literature knowledge graph

Turn a small corpus (primary and secondary papers, a manifest, optional query
bundle and candidate graph) into a knowledge graph whose every node and edge is
welded to a verbatim paragraph excerpt, with cross-paper identity decisions
stated rather than assumed.

## 1. Run it

The one required command produces the complete `output_contract` and all
artifacts:

```sh
python3 scripts/graph_build.py --input /input --out /app/output
```

`--work` defaults to `<out>/work`; pass `--work /app/work` to separate scratch
files. Standard library only, no network. It always exits 0 and always writes a
valid `result.json`, including for empty or corrupt input.

Optional follow-up on an already-built graph (not required for the contract):

```sh
python3 scripts/graph_query.py --graph /app/output/graph.json --type outgoing --surface WideNet
```

## 2. What it writes

`/app/output/`

| file | content |
|---|---|
| `result.json` | the full contract: case_id, status, graph, queries, alignment, conflicts, uncertainty, artifacts, sources, merges, change_records, validation, runtime_notes, output_contract |
| `graph.json` | validated nodes/edges with mentions, stats, alignment, conflicts |
| `nodes.csv` | `node_id,type,label,aliases,source_ids,paragraph_ids,degree` |
| `edges.csv` | `edge_id,type,source,target,conditions,source_ids,quote` |
| `query_results.json` | every executed query with subgraph and evidence |
| `validation.json` | self-check: checks_total / checks_failed / checks / errors |
| `work/corpus.json` | ingested blocks, papers, stats (audit trail) |
| `work/extraction.json` | what was extracted, in which mode, what was rejected |

`result.json` top-level keys are always present even when empty. Every key of
the supplied `output_contract` is echoed at the top level (a contract `case_id`
never overwrites the real one).

## 3. Input discovery

Picked up automatically from anywhere under `--input`: `case.json` (case_id and
`output_contract`), the corpus (`material.json`, `primary-material.json`,
`secondary-material.json`, a manifest, an index pointing at more files, or plain
`.md`/`.txt`), `queries.json`, and either an agent `extraction.json` (highest
priority) or a `candidates.json` graph hypothesis. `task.md` is read for
context, not treated as evidence.

`paragraph_id` is the organiser's JATS identifier — **never** a PDF page number.

## 4. Vocabulary (closed)

Node types: `researcher | material | method | task | metric | conclusion`.
Relations: `uses | compares | outperforms | supports | contradicts`.
Alignment decisions: `merge | keep_distinct | undetermined`.
Status: `success | partial | undetermined | refused`.

A type or relation outside these sets is a build error, never silently kept.

## 5. Evidence rule

Every node and edge needs at least one excerpt that is a verbatim substring of
the paragraph it cites. If the quote cannot be found the candidate is dropped
and the drop is logged; nothing is invented to fill the gap. See
`references/schema.md` for the full record shapes and `references/method.md` for
the extraction and query procedure.

## 6. Two independent papers

Keep both papers' nodes, edges and sources; do not collapse them into one. Record
a `merge` only where identity is genuinely established; otherwise record
`keep_distinct` or `undetermined` with a basis. A shared generic term is not proof
of a shared sample, dataset or condition. Unreported facts and intra-source
conflicts are preserved, not resolved by averaging.

## 7. Status and failure handling

| Condition | Status / action |
|---|---|
| No readable paragraph block | `undetermined`, empty graph, reason recorded |
| Material read, no node bound to an excerpt | `partial` |
| Some candidates rejected | `partial`, valid graph kept, drops logged |
| No cross-paper alignment | `partial` |
| Graph + alignment + conflicts + ≥3 queries | `success` |
| Self-check fails after a would-be `success` | downgraded to `partial` |
| Corrupt / missing JSON | warning, continue on what is readable, exit 0 |

## 8. Files

```
SKILL.md
scripts/graph_build.py      entry: ingest → extract → align → query → validate → write
scripts/graph_query.py      optional single-query wrapper over graph.json
scripts/graph_support.py    shared JSON/CSV helpers, query engine, delivery self-check
references/schema.md        closed vocabularies, record shapes, result contract
references/method.md        extraction tiers, alignment/conflict policy, status logic
```
