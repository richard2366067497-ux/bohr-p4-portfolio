# GAIN_EVIDENCE

Every number below is produced by the package. The measurement is
`python3 scripts/main.py compare --input <case> --work <work>`: it loads the input twice, once as this skill does
it and once as a face-value baseline that indexes the files and calls one t test on the first two levels - no
facet coverage, no verbatim quote check, no severity, no revision, no locator.

Measured on the rich synthetic case (two documents, 96 readable units, contract of six keys):

| measure                     | baseline | this skill | delta |
|-----------------------------|---------:|-----------:|------:|
| contract keys echoed        |        0 |          6 |    +6 |
| deliverable files written   |        1 |          6 |    +5 |
| located claim rows          |       11 |        11 |     0 |
| verbatim quote checks       |        0 |         11 |   +11 |
| findings with severity      |        0 |          4 |    +4 |
| fields status/sources/...   |        0 |          5 |    +5 |
| material index rows         |        0 |          3 |    +3 |

The deltas that carry the task: a contract echo on every declared key so the result is machine-checkable; a
deliverable that resolves to a real file plus the annotated manuscript and the evidence stream; every quote
verified verbatim inside a single unit with unverified ones downgraded to pending review; typed findings with
severity, evidence and an executable revision; and a material index with `sha256_12` per source.
Deterministic simulated comparison, **not an official score**.
