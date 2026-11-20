# SELFTEST — reproducible single-command and agent-path runs

Everything below is offline and standard-library only. Run from the package root. The interpreter is
`python3` on the platform; on this workstation it was
`C:\Users\23660\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` (3.12).

## 1. Example run (walks the whole pipeline)

```bash
python3 scripts/main.py all --input examples --output /tmp/w15-out --work /tmp/w15-work
```

Measured result on 2026-11-21:

- exit code 0; `status=ok`
- 1 material parsed (`manuscript.md`, 1493 chars), 11 located blocks
- ledger rows: term 2, symbol 1, definition 2, numbering 3, citation 3, claim 3, unit 6 (20 total)
- findings 4: term expansion clash (high), missing caption list (low), citation `[5]` without an
  entry (high), opposite-polarity claim pair (high)
- 3 annotation blocks applied; `preserved_facts.json` total 11, not-preserved 0
- selfcheck: files ok, contract echo ok, placeholder sweep ok

Inspect `result.json` and the `output_contract` object; every contract key is non-empty and is
repeated inside `output_contract`.

## 2. Evaluator matrix (`scripts/eval_sim.py`)

The local evaluator installs the package as `/skills/weekly-skill`, copies the synthetic case into
`/input`, and runs either the single documented command or the agent subcommands. All four
combinations were run:

| case | mode | contract source | status | failures | warnings |
|-|-|-|-|-|-|
| rich | single | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| rich | agent | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| boundary | single | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |
| boundary | agent | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |

Reproduce with, for each pair of `case in {rich, boundary}` and `mode in {single, agent}`:

```bash
python scripts/eval_sim.py --pkg work/p4/v9/writing-15 \
  --case work/p4/synth_cases/writing-15/rich --mode single \
  --out /tmp/es-out --json-out /tmp/es.json
```

## 3. Boundary degradation (honest, not hidden)

The boundary case supplies an empty file, an invalid JSON file and a placeholder-only text. The run
still exits 0 and writes:

- `status=partial` (or `insufficient_evidence` when nothing is readable),
- `sources` with a per-file `status` (`empty-file`, `invalid-json`, `placeholder-only`),
- `uncertainties` naming each skipped file and the reason,
- a complete non-empty contract echo whose `term` … `unit` fields state "zero entry found",
- `revised_manuscript.md` with an explicit no-editable-chapter note rather than invented text.

## 4. Agent enhancement path

```bash
python3 scripts/main.py init   --input /input --output /app/output --work /app/work
python3 scripts/main.py show   --input /input --work /app/work --find FDM
python3 scripts/main.py check  --input /input --work /app/work
python3 scripts/main.py build  --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output
```

`init` writes `work/source_index.json` and `work/draft_template.json`. A draft annotation is accepted
only when its locator resolves and its quote is verbatim inside that block; rejected items land in
`work/check_report.json` and never modify the source. `build` is the deterministic path, so the
single-command and agent paths produce the same artifacts for the same input.

## 5. Failure-mode spot checks

```bash
# missing input: still a valid result.json, exit 0
python3 scripts/main.py all --input /tmp/does-not-exist --output /tmp/o --work /tmp/w

# no draft: deterministic ledgers and annotations are still produced
rm -f /tmp/w/draft.json && python3 scripts/main.py build --input examples --output /tmp/o --work /tmp/w

# tampered draft annotation (quote not verbatim): rejected, source unchanged
python3 scripts/main.py check --input examples --work /tmp/w
```

The full matrix (chapter types, oversized files, binary formats, NUL bytes, invalid JSON, Unicode
normalisation) is in `references/rules-and-failure-modes.md`.

## 6. Invariants checked by `selfcheck`

- `result.json` plus all nine named artifacts exist;
- `output_contract` is a non-empty object;
- no placeholder token survives in any artifact;
- the annotated manuscript keeps every source line; removing the `EA-` quote blocks restores the
  original text (`versions/rollback_check.json`).
