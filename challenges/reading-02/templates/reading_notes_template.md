# Figure reading — <figure_id> panel <panel>

- source image: <file>            <!-- locator: file name -->
- status: answered | partial | insufficient_evidence

## Axes

| axis | label | unit | scale | ticks | origin | interval |
|-|-|-|-|-|-|-|
| x | | | linear/log | | | |
| y | | | linear/log | | | |

Calibration used: `value = v0 + (px - px0) * (v1 - v0) / (px1 - px0)` (per axis; log folds via log10).

## Legend → series

| series | legend label | colour | digitize | tol |
|-|-|-|-|-|
| | | rgb(...) | yes/no | |

## Elements

| element | present | note |
|-|-|-|
| error bars | | |
| significance marks | | |
| scale bar | | |
| panel id | | |

## Claims  <!-- every claim: quote + locator + read_basis + verbatim -->

| claim_id | kind | readability | quote | quote_type | locator | read_basis | verbatim |
|-|-|-|-|-|-|-|-|
| c01 | table_cell | directly_read | | text | /tables/0/rows/0/1 | literal table cell | |

## Uncertainties / queued for human review

- 
