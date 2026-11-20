# 清洗指南 / cleaning guide

This is the human-readable companion to `rules_library.json`. It states, in prose, the rule chain
the engine applies and the discipline it never breaks. It is a reusable checklist: ask of every row
"is the field name standardised, is the conversion shown, is the merge defensible, can I trace it
back?".

## 1. the rule chain (applied in order)

| rule | applies to | condition | transform | failure mode it avoids |
|---|---|---|---|---|
| `R_ALIAS` | material | the name is a known alias (`TiO2`, `SiO2`, `ZnO`) | map to the canonical name | the same material entered twice under two names |
| `R_IND` | indicator | the spelling is a variant (`bandgap`, `bank gap`, `Band gap (eV)`) | map to the canonical indicator | the same indicator split across field names |
| `R_VAL` | value | the value has trailing zeros (`3.20`) | strip trailing zeros, keep ranges verbatim | a spurious precision difference hiding a real one |
| `R_UNIT` | unit | the token is a known unit (`ev`, `nm`) | map to the canonical form (`eV`, `nm`) | a case difference read as a different unit |
| `R010` | unit | the token is arbitrary or unresolvable (`a.u.`) | **hold the row for a human; never convert** | an invented conversion |

`R010` is supplied by the case as a declared rule with `human_gate: true`. The engine honours the
gate: a held row is written to `pending_review.json`, its value is left empty in the cleaned table,
and no factor is ever applied.

## 2. the hold discipline

A row is held when either:

- the value is an unreported marker (`n.r.`, `n.d.`, `na`, `-`), so no number exists to clean; or
- the unit is arbitrary or unresolvable, so no conversion is licensed.

A held row is **never** converted, **never** filled with a guess, and **never** merged into a
duplicate group. It is listed with its reason so a human can decide. This is the difference between
"clean" and "quietly wrong".

## 3. duplicate detection

The judgement key is `material | indicator | value | unit` **after** normalisation. Two rows merge
only when all four agree. Consequences:

- `TiO2` and `titanium dioxide` with the same value merge (alias resolved first);
- two different materials never merge, even with the same value;
- an unreported value never merges, because it was held.

The merged group is reported (never silently dropped), keeping both `row_id`s so the reviewer can
compare the sources.

## 4. traceability

Every changed field is written to `change_log.json` as `{row_id, field, from, to, rule_id}`. Because
each rule id maps back to a row in this guide, any reviewer can re-run the rule and check the result.
`evidence/M##.json` holds a per-material snapshot (parse status, byte size, content hash, quoted
lines) so the source is never just a label.

## 5. degradation

- A material file that is empty, corrupt or contains only placeholder text is classified
  (`empty-file` / `corrupt-json` / `no-data-only`), skipped, and named in `run_log.txt`.
- When no record row exists at all, `status` becomes `insufficient_evidence`; every artifact is still
  written, and the cleaned table carries one explicit no-data row naming the searched locations.
- Nothing outside the supplied records is ever written.
