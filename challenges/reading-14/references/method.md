# How the builder reaches an answer

Five stages, one deterministic pass. Nothing is guessed into the graph: every
claim is welded to a paragraph excerpt that is checked by substring.

## 1. Ingest

Walk the input tree and pick up `case.json`, `task.md`, the corpus. Paragraph
bundles arrive in several shapes — `material.json`, `primary-material.json`,
`secondary-material.json`, a manifest, an index that points at more files, or
plain `.md`/`.txt`. The loader recurses through any JSON object looking for a
`paragraph_id` string beside a `text` string, remembering the nearest ancestor
`source_id`, and deduplicates by `(source_id, paragraph_id)`. The organiser's
`paragraph_id` is kept exactly as given. Unreadable JSON becomes a warning, not
a crash.

`work/corpus.json` preserves what was read: manifest papers, blocks and stats,
so the input can be audited independently.

## 2. Extraction (three tiers)

1. **Agent extraction** — if an `extraction.json` is present it wins; it carries
   nodes/edges already shaped to the schema.
2. **Candidate graph** — a `candidates.json` is a graph hypothesis. Types and
   relations are mapped onto the closed vocabularies (`dataset -> material`,
   `evaluated_on -> uses`, …). A candidate whose type or relation cannot be
   mapped is rejected and reported.
3. **Heuristic** — with neither file the builder pulls `Name (ABBR)` entities,
   `Label was <value>` metrics and sentence-level co-occurrences linked by a
   relation cue. This tier is explicitly marked `partial`: it is a scaffold, not
   a finished reading.

In all tiers a node or edge survives only if its quote resolves to a verbatim
excerpt of the cited paragraph. "You must find the sentence" — a quote that is
not literally present causes the candidate to be dropped, and the drop is logged
in `errors`. The heuristic never invents a quote.

## 3. Graph assembly

Degree is counted after all edges are kept. `source_ids` and `paragraph_ids` are
derived from the mentions; nothing is typed by hand.

## 4. Alignment and conflicts

Concepts are grouped by `(type, normalised surface/alias)`. A group spanning two
sources becomes an alignment record:

- `merge` only for the same measured quantity (the value still stays per paper);
- `undetermined` when the same surface appears in two independent papers but no
  sentence equates them — the honest default.

Conflicts are collected separately: two sources reporting different values for
the same metric become a conflict record, with the two locators and a handling
note that refuses to pool incomparable measurements.

## 5. Queries

The bundle's own `queries.json` drives execution when present (`find_surface`,
`outgoing`, `incoming`/`neighbours`, `conflicts`, bounded by `depth`). Otherwise
the builder generates at least three: an outgoing walk from the highest-degree
node, an alias lookup, a conflicts query, and a deliberate absent-surface probe
that must return `undetermined` rather than a guess. Each query returns the
subgraph, its verbatim evidence and its undetermined reasons.

## Honest status

- no readable blocks → `undetermined`, empty graph, reason recorded;
- readable material but zero verified nodes → `partial`;
- rejected candidates → `partial` (the valid graph is kept);
- no cross-paper alignment → `partial`;
- everything bound, aligned and queried → `success`.

The validator re-reads the emitted files and re-checks verbatim binding; a run
that calls itself `success` is downgraded to `partial` if its own self-check
fails.

## What this cannot do

A matching quote proves traceability, not entailment. The builder cannot read
for meaning, complete the literature, decide that two differently-named methods
are identical, or resolve a definitional clash hidden in the prose. Those stay
in `uncertainty` for a human to settle.
