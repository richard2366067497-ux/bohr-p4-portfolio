# Reusable templates: glossary, citation ledger, chapter checklist

Copy a section into your own chapter folder and fill it. These templates are plain Markdown so a
human and an agent can read the same table.

## Template A — glossary and symbol table

| term / symbol | expansion or meaning | first locator | variant seen | decision | owner |
|-|-|-|-|-|-|
|  |  |  |  |  |  |

Rules:

1. One row per concept; put the preferred spelling in `term` and every other spelling in `variant`.
2. A symbol used with two meanings gets two rows and a note in `decision`.
3. `first locator` is `<file> §<section> <title> ¶<paragraph>`; do not leave it blank.
4. `owner` is `author` (scientific choice) or `editor` (house style).

## Template B — citation ledger

| citation | locator in body | reference-list entry | status | action |
|-|-|-|-|-|
| `[5]` |  |  | matched / missing-entry / no-reference-list |  |

Rules:

1. `status=missing-entry` requires the exact reference-list locator that was searched.
2. If there is no reference list, write `no-reference-list`; do not invent an entry.
3. Author-year citations are listed separately and are not fully cross-checked by the mechanical
   rules.

## Template C — chapter completeness checklist

| required element | present | locator | note |
|-|-|-|-|
| research question |  |  |  |
| method and conditions |  |  |  |
| results with units |  |  |  |
| discussion and limitations |  |  |  |
| figure/table captions |  |  |  |
| reference list |  |  |  |
| appendix (if claimed) |  |  |  |

Mark each row `yes`, `no` or `not-applicable`. A `no` row becomes a `pending_human.json` item; it
is not silently treated as done.

## Template D — review-response log

| comment id | reviewer comment | target locator | change made | evidence | done |
|-|-|-|-|-|-|
| R1 |  |  |  |  |  |

One comment per row. A change without a target locator is not accepted by `check`.
