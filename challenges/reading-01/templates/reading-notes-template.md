# Reading notes template (aligned with the artifacts the skill writes)

Fill one row per item you accept from `work/draft_candidates.json`. The `locator` column is what makes
the note checkable: it must name a page object the skill printed, of the form
`<file> pN <object-id> <type>`. A row whose locator does not resolve is rejected by `check` and never
reaches the artifact; that is the point of the review step.

## 1. Document

| field | value | locator |
|-|-|-|
| title | | |
| authors | | |
| abstract | | |
| venue / year | | |

## 2. Reading order decisions

| page | decision | why |
|-|-|-|
| 1 | single column / two column / mixed | |
| 2 | | |
| running matter excluded | header / footer / none | |

## 3. Structure

| kind | label | locator | accepted? |
|-|-|-|-|
| section | | | |
| table | | | |
| formula | | | |
| caption | | | |
| reference | | | |

## 4. Unreadable items

| file | status | reason | follow-up |
|-|-|-|-|
| | | | |

## 5. Reviewer decision

- [ ] every accepted row has a locator that resolves in the source file
- [ ] no number, symbol or conclusion was changed by this review
- [ ] the unreadable list is complete for the material supplied

Reviewer: ______________  Date: __________
