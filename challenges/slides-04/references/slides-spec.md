# Reference: how slides-author turns material into pages

This note explains the mechanics the package enforces. It is documentation for a
reader, not machine input; the pipeline reads only the material under the input
root.

## 1. From a paper to a page plan

A paper is one continuous argument; a deck is a sequence of discrete pages. The
conversion is a structural rewrite, not a paragraph shuffle:

- the first material in the input root is the main source; its title becomes the
  deck title, its headings become the page skeleton;
- for every section the run keeps the **sentences** of that section (not just the
  heading) and turns the first substantive sentence into that page's claim and up
  to four of them into the page bullets;
- empty pages are never emitted: a section with no readable sentence is dropped,
  and a material with no usable prose produces a single honest
  "insufficient evidence" page instead of invented content.

## 2. Locators and verbatim evidence

Every page remembers where it came from:

- a locator of the form material id plus section index, e.g. a page taken from
  the first material's third section is anchored to that span;
- each bullet keeps the exact sentence it was taken from, so a reviewer can
  re-check it;
- numeric claims are re-located inside the source span before they reach a page;
  a number that cannot be found in the material is not printed.

## 3. Page roles

Roles are inferred from the section name and drive layout and note style:
title, outline, question, background, methods, results, discussion,
limitations, conclusion, thanks. A role only changes emphasis, not evidence; the
claim and the locator are recorded regardless.

## 4. Speaker notes

Each page carries a speaker note at least twenty characters long, written to be
different from the on-slide text (it tells the presenter what to emphasise and
which span to point at), so notes coverage is reported rather than assumed.

## 5. Figures

Image material found in the input is registered as an available figure. When no
usable figure is present the run records an exception saying so, rather than
placing a decorative stand-in.

## 6. Template inheritance

When a target presentation template is supplied, its theme and slide master are
reused for the written slides, and the reuse is recorded as a template
inheritance note. Without a template, a built-in Office theme is used.

## 7. Compliance the run checks on itself

The run writes a compliance record with one entry per check: every page has a
source locator; bullets are re-checked verbatim against the span; no number is
invented; the page count stays within budget; a vector preview is always
produced; the editable OOXML source parses; and the PDF export is written from
the same page plan. A failing check is reported as a warning entry, not hidden.

## 8. Degraded input

Unreadable, empty or malformed material never aborts the run. Each problem is
recorded as a degradation and as an exception entry, the status becomes
insufficient evidence when too little prose is available, and the process still
exits successfully with a legal result document.
