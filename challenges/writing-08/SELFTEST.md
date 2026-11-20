# SELFTEST — writing-08 (methods and experiments section writer)

Validation with the packaged simulator `scripts/eval_sim.py` plus targeted ad-hoc cases.
All runs offline, pure standard library (`python3 >= 3.8`).

## 1. Simulator runs (rich / boundary × single / agent)

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-08 \
    --case work/p4/synth_cases/writing-08/<rich|boundary> --mode <single|agent>
```

| case | mode | status | notes |
|---|---|---|---|
| rich | single | **PASS** | contract source `case.json:output_contract`; contract_echo 5/5; 7 artifacts; exit 0 |
| rich | agent | **PASS** | same contract; the documented `init→check/build/selfcheck` path plus the injected draft step produce the same artifacts |
| boundary | single | **PASS** | `output_contract: null` → resolver falls back to `SKILL.md (result schema table)`; 5/5 keys echoed at top level **and** in the nested `output_contract` |
| boundary | agent | **PASS** | same; `status = insufficient_evidence` with honest limits/uncertainties, exit 0 |

Zero failures **and zero warnings** in all four runs: no placeholder tokens in any output
file, `result.json` carries all five contract keys nested, `case_id` is passed through,
`deliverables` are all present and non-empty, and the envelope fields
`status / sources / uncertainties / change_records / limits` are non-empty.

## 2. Behaviour checks (substantive, not just structural)

- **Language is no longer hardcoded** — English case (`language: "en"`, English materials)
  renders an English manuscript (`# Methods and Experiments`, `## 3 Method steps`,
  `| Dataset | Version | ...`); a Chinese ad-hoc case (`language: "zh"`, config.yaml +
  run.log) renders Chinese (`# 方法与实验`, `## 5 参数与来源`, `〔待补：…〕`). Detection order:
  `case.json.language` → CJK ratio of `task.md` + materials.
- **Real extraction, not templates** — the rich case yields 7 parameters with locators
  (`initial concentration = 12.5 mg/L @ materials/paper.md#L5`, `pH = 3`, `n = 3
  replicates`, `reaction duration = 60 min`, `degradation phenol = 92.4 %`), 8 ordered
  steps, settings/limits/repro items, each carrying `[S#]` + `文件#行号`.
- **Six-element coverage is honest** — rich = 4/6 `covered` (steps, settings, parameters,
  repro_limits); `datasets` and `baselines` are `gap` because the material never names
  them: they are registered in `gaps.md` and rendered as `[needs input: …]` in the
  manuscripts, never invented. Boundary = 0/6 with all six registered as gaps.
- **No fabricated sources** — `init` extracted 0 candidates from the boundary material
  (the notes file contains only a placeholder token from the *input*), so no fact entered
  the manuscript; contract values fall back to an honest material inventory (with sha1).
- **Conflicts** — same-key/same-source-values are grouped by `three_source`; a differing
  value across sources is kept side by side (`conflicts.md`) and flagged in
  `parameter_ledger.csv` as `unresolved_detected(...)`, never silently unified.

## 3. Degenerate input

- Missing/empty input dir → `status = input_error` (or `insufficient_evidence` when
  materials exist but no element is extractable), legal `result.json` with non-empty
  `limits` / `uncertainties` / `sources`, **exit 0**.
- Empty `draft.json` (`{}`) from an agent path is treated as *missing*, so the
  deterministic extractor runs instead of rendering a shell.
- Unreadable/binary/oversized (>400KB) material → recorded in `degradations` and as gaps;
  the run continues.
- Non-writable output dir → falls back to `./output`; unhandled exception → minimal valid
  `result.json` including every contract key (never `null`), exit 0.
