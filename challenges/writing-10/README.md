# writing-10 — Reviewer response and manuscript revision (审稿回复与论文修改)

Offline, pure-standard-library skill that turns a baseline manuscript plus a set of
reviewer comments into: a **really revised** manuscript (each adopted comment edits a
locatable sentence, tagged with a unique `[[Cx]]` anchor), a point-by-point response
letter, a change locator table, an evidence to-do list, and a self-consistency report.

## Install

No installation and no third-party packages. Copy this package to `/skills/weekly-skill`
(or anywhere) and run it with `python3` (>= 3.8).

## Usage

Single command — full pipeline:

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

Agent-first: drop a `draft.json` in `--work`/`--input` (or pass `--draft FILE`) with
per-comment `decision` / `kind` / `revised_text`; those are adopted verbatim. Without a
draft the deterministic extractor produces the same shape. See `references/usage.md`.

## Inputs

```
/input/case.json                 # optional: {case_id, language, output_contract}
/input/materials/manuscript.md   # the baseline manuscript (largest baseline-like file wins)
/input/materials/comments.md     # reviewer comments (numbered or bulleted)
```

## Outputs

`revised_manuscript.md`, `response_letter.md`, `comment_ledger.json`, `change_locator.json`,
`evidence_pending.md`, `version_notes.md`, `selfcheck.json`, `result.json`.

## Decisions

`accept` (anchored, no new material), `partial` (anchored but needs new material),
`defer` (no anchor / needs new material), `reject` (out of scope or a misreading).
Anchor threshold is `0.15`, so off-topic comments are never forcefully "accepted".

## Limits

Offline; no external data or literature is consulted. Revisions are in-text wording/scope
edits (or marked citation slots) — never fabricated experiments or data. Unanchored
comments are deferred or returned as not adopted, and reported honestly in `limits`.

## Maintenance & versioning

Single-file logic in `scripts/main.py` + helpers in `scripts/core.py`; no state on disk
besides the outputs. Version is reported in `result.json.runtime.version` and follows
semver; the response/ledger/locator contract is frozen by `references/usage.md` and
guarded by `selfcheck.json`.
