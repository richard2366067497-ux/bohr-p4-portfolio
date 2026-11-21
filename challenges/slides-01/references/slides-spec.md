# Reference: how slides-author turns material into pages (v9)

This note explains the mechanics the package enforces. It is documentation for a
reader, not machine input; the pipeline reads only the material under the input root.

## 1. From a paper to a page plan

A paper is one continuous argument; a deck is a sequence of discrete pages. The
conversion is a structural rewrite, not a paragraph shuffle:

- the first material in the input root is the main source; its title becomes the deck
  title and its headings become the page skeleton;
- every section keeps its **sentences** (not just the heading): the first substantive
  sentence becomes the page claim, up to four become the page bullets. Sentence
  splitting happens on end punctuation followed by whitespace, so decimals such as
  `4.7 µm` and `12.5%` are never cut in half;
- caption-only lines (`Figure N. …`, `Table N. …`) are not used as bullets; their
  numbers are captured as `figure_refs` when the surrounding prose refers to them;
- empty pages are never emitted: a section with no readable sentence is dropped, and a
  material with no usable prose produces a single honest "insufficient evidence" page.

## 2. Locators and verbatim evidence

- a locator is `material id + section index`, e.g. `M01#s4`;
- every bullet keeps the exact sentence it was taken from, so a reviewer can re-check it;
  `content_map.json` marks each bullet `verified` only when it is found verbatim;
- numeric claims are re-located inside the source span before they reach a page; a
  number that cannot be found in the material is not printed;
- `page_gold.json` states, per page, the elements a reviewer can check (main-line claim,
  source locator, evidence quote, figure reference, speaker note).

## 3. Page roles

Roles are inferred from the section name and drive layout and note style: title, outline,
question, background, methods, results, discussion, limitations, conclusion, thanks. A
role only changes emphasis, not evidence; the claim and the locator are recorded regardless.

## 4. Speaker notes

Each page carries a speaker note of at least twenty characters, written to be different
from the on-slide text (it tells the presenter what to emphasise and which span to point
at), so notes coverage is reported rather than assumed.

## 5. Figures

Image material found in the input is registered as an available figure; figure / table
numbers mentioned on a page are recorded as its `figure_refs`. When no figure is present
the run records an exception saying so, rather than placing a decorative stand-in.

## 6. Template inheritance

When a target presentation template is supplied, its theme and slide master are reused for
the written slides and the reuse is recorded as a template-inheritance note. Without a
template, a built-in Office theme is used. `version_log.json` records the theme source and a
sha256 of the theme XML actually embedded, so the inheritance can be checked.

## 7. Agent path and the human draft

`init` writes a `work/draft.json` skeleton. A human (or the Skill Agent) may replace the
`sections` with hand-picked page claims; `build` keeps only entries whose `quote` is found
**verbatim** in the material and drops the rest, recording each drop in `exceptions`. This
is how the Skill improves on mechanical extraction without ever inventing content.

## 8. Compliance the run checks on itself

The run writes a compliance record with one entry per check: every page has a source
locator; bullets re-check verbatim; no number is invented; the page count stays within
budget; a vector preview is always produced; the OOXML source parses; the PDF export is
written from the same page plan. A failing check is reported as a warning entry, not hidden.

## 9. Degraded input

Unreadable, empty or malformed material never aborts the run. Each problem is recorded as a
degradation and an exception entry, the status becomes `insufficient_evidence` when too
little prose is available, and the process still exits successfully with a legal result
document and the full artifact set.
