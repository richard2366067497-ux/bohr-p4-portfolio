# Self-check — C1 … C24

`result.json.self_check` is computed from the written artifacts, not from
intentions. Shape:

```json
{
  "ready_to_submit": true,
  "weighted_score": 0.98,
  "blocking_failures": [],
  "checks": [{"id": "C1", "name": "...", "blocking": true, "weight": 2.0, "pass": true, "detail": ""}]
}
```

`ready_to_submit` is true exactly when no blocking check fails.
`weighted_score` is the weighted pass rate over all 24 checks.
The same report is copied to `work/selfcheck.json`; `check --result ...` can
re-run it on an existing `result.json` using the stored `work/text` pages.

| id | check | blocking | weight | threshold / reading |
|---|---|---|---|---|
| C1 | case_id and status present | yes | 2.0 | both non-empty |
| C2 | case_id copied from the case | yes | 1.5 | non-empty |
| C3 | status is one of four honest states | yes | 1.5 | `success/partial/unable_to_determine/refused` |
| C4 | every output_contract field is filled | yes | 3.0 | no contract key empty except `not_reported`/`uncertainties` |
| C5 | evidence anchors resolve against the source text | yes | 3.5 | every `quote` is a substring of its cited page |
| C6 | notes carry verified anchors | yes (only when > limit) | 2.5 | unanchored notes ≤ max(2, 10% of notes) |
| C7 | numbers in a claim appear on the cited page | no | 2.0 | each numeric token on the page |
| C8 | section notes follow the paper's own headings | no | 2.0 | ≥ 60% of detected headings have notes |
| C9 | uncertainty and not_reported are recorded | no | 1.5 | both keys present |
| C10 | no placeholder text left behind | yes | 1.5 | no `todo/tbd/待补充/待写/placeholder/原文摘录` |
| C11 | sources point at real parsed inputs | no | 1.0 | every source doc_id is in `documents` |
| C12 | each anchor falls inside the section it cites | no | 1.5 | page within the note's page span |
| C13 | notes are written, not just extracted | yes | 2.5 | ≤ 30% of fields are pure quotes |
| C14 | notes have substance | no | 2.0 | purposes ≥ 20 chars, ≥ 6 KPs, ≥ 4 distinct card texts, ≥ 50% unique transitions, ≤ 20% purpose-only notes |
| C15 | numbers in a claim also appear inside its quote | yes | 2.5 | each digit in `claim` is in the quote |
| C16 | extraction matches the document's page count | conditional | 2.5 | every anchor page ≤ page count |
| C17 | each note's prose is supported by the text it cites | no | 2.0 | ≥ 60% of notes share tokens with their quotes |
| C18 | the paper card carries all seven fields | no | 1.5 | ≥ 6 of 7 filled |
| C19 | anchor quotes are short enough to check by eye | no | 1.5 | each quote ≤ 400 chars |
| C20 | every knowledge point carries a synonym | no | 1.5 | a synonym different from the term |
| C21 | each transition describes how this section follows the last | no | 1.5 | ≥ 50% unique transitions |
| C22 | each answer states its content, not where to find it | no | 2.0 | ≥ 60 Latin chars or ≥ 20 CJK chars, not a pointer |
| C23 | conditions and limitations carry the reader's own reading | no | 2.0 | conditions ≥ 4 items, limitations ≥ 3 items (`;`/`；`/`、` separated) |
| C24 | a restated formula is anchored to the formula | no | 2.0 | passes when no display formula is detected |

## Reading a failure

- **C4 / C5 / C10 / C13 / C15** are contract-level: if any fails, the result is
  downgraded to `partial` and `status_reason` names the ids. Fix the input or
  the extraction, do not relax the check.
- **C6** blocks only once more than 10% (floor 2) of notes lack anchors — a
  short paper with two sections may legitimately have two unanchored notes.
- **C14 / C18 / C23** signal thin reading: few knowledge points, repeated card
  text, or a conditions list that just repeats a sentence. They are non-blocking
  because the material may genuinely be thin; the reason is still visible.
- **C16** is blocking only when material is missing entirely; otherwise a page
  beyond the document is reported but does not veto the result.
- **C22** rejects "see §3" style answers: the reader must state the content.

Blocking ids: C1, C2, C3, C4, C5, C6 (over limit), C10, C13, C15, C16 (material
missing). All others lower the score and appear in `checks` with a detail string.
