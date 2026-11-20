# Writing decisions: grouping, gap and contributions

`build.py` implements these rules deterministically. Read them before editing
the draft by hand; the same rules explain every ledger record it emits.

## Source inventory

Assign stable IDs while reading. Record the real input path, the kind
(`prior_work`, `current_work`, `experimental_record`, `other`) and the access
level (full text, abstract only, bibliographic record only, missing,
unreadable). File names decide nothing about scientific content: a name is a
label, not evidence. Reviewer comments and referee reports are instructions, not
evidence, so they never become claims.

## Which sentences become claims

A sentence becomes a claim only when it is substantive: at least ~30
characters, contains real punctuation, starts no line that is a heading, bullet
or table row, and is not a duplicate of one already taken. The claim text is the
sentence verbatim, so it reappears word-for-word in `manuscript.md`; no
paraphrase is allowed in a quote.

Role follows the source and the content:

- current work containing a number or measurement -> `contribution`
- other current-work sentences -> `background`
- prior-work sentences -> `related_work`, with a citation id attached only when
  a literal token such as `[12]` or `(Author, 2024)` occurs in that sentence

## Related work grouping

Group prior work by source and compare on one shared axis (problem setting,
method route, or data and evaluation). Never turn a single heterogeneous source
into three invented traditions. A paragraph leads with the route or question,
synthesises the sources on the common axis, states the trade-off and moves to
the unresolved condition. Avoid paper-by-paper abstract concatenation and
decorative citation clusters.

## Gap derivation

Build the gap from settled premises only — cited related-work claims, or
background claims when no prior work was supplied. Test one plausible
counterexample against the supplied corpus before writing. Distinguish:

- **Explicit limitation** — a supplied source names an unresolved condition.
- **Bounded synthesis** — cited sources jointly imply an open condition. Mark it
  `assessment: inference`, give a rationale, and state the `scope` that was
  actually checked.
- **Corpus gap** — the material is silent. Write "the supplied studies do not
  establish …", never "no work has ever …".

Do not infer global novelty, universal superiority, causality or deployment
readiness from a small corpus. When novelty is unprovable, still write the
useful narrower motivation.

## Contribution alignment

Align every contribution with a real method subsection, result table, figure,
proof, dataset or released artifact of THIS work. "We evaluate …" needs a real
evaluation; a proposal supports "we propose …", not "we demonstrate …". No
measured result means no invented improvement. Keep percent versus percentage
points, mean versus best run, and association versus causation straight. Never
write "first", "state of the art", "significant" or "robust" without evidence at
exactly that strength and scope.

## Reverse audit

Read the finished draft against the original evidence, not against your notes.
Map each checkable clause to evidence; split a sentence that mixes facts or give
each clause its own evidence. Connective prose needs no artificial source. Run
the helper:

```sh
python scripts/audit.py --ledger /app/output/evidence.json --draft /app/output/manuscript.md --report /app/output/audit.json
```

Fix structural errors and dangling links, then inspect the warnings. The helper
cannot prove truth, entailment, literature completeness or journal compliance,
so its exit 0 is never a scientific correctness score.

## Honest status and failure handling

Use `complete` only when the requested work is delivered with supported claims,
`partial` when a substantive requirement is unmet, `blocked` only when no
meaningful main result is possible.

| Condition | Action |
|---|---|
| Empty bibliography | Draft from supplied factual evidence; mark citation-dependent claims unresolved; never invent references. |
| Unknown journal style | Use one documented provisional style; do not claim compliance. |
| Conflicting numbers | Check version, dataset and denominator; keep both qualified values if unresolved. |
| No own results | Write the supported proposal; mark result-dependent contributions pending. |
| Unreadable source | Try one alternative extractor, then keep a useful partial result. |
| Missing gap evidence | Narrow to the checked corpus or leave positioning unresolved. |
