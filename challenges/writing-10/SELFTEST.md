# SELFTEST — writing-10 (reviewer response and manuscript revision)

Validation performed with the packaged simulator `scripts/eval_sim.py` plus targeted
ad-hoc cases. All runs are offline, standard-library only.

## 1. Simulator runs (rich / boundary × single / agent)

Command shape:

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-10 --case work/p4/synth_cases/writing-10/<case> --mode <single|agent>
```

| case | mode | status | notes |
|---|---|---|---|
| rich | single | **PASS** | contract_echo 5/5, 8 artifacts, case_id passed through, placeholder_sweep clean |
| rich | agent | **PASS** | same, agent draft path adopted when a draft is present |
| boundary | single | **PASS** | no `output_contract` in case.json → canonical 5 keys echoed; 8 artifacts; exit 0 |
| boundary | agent | **PASS** | same |

No placeholder tokens (`TODO`, `TBD`, `null`, `N/A`, `pending`, `待补充`, …) in any output
file; `result.json` carries nested **and** top-level `output_contract` keys.

## 2. Behaviour checks (substantive, not just structural)

- **Real, locatable edits** — an English ad-hoc case (`Our treatment cures the disease in all
  patients and generalizes to every setting.` + 4 comments) produced:
  - `RC01 narrow → accept`: the sentence was softened/limited and tagged `[[C1]]`, and
    `revised_locator = revised_manuscript.md#C1` resolves to that marker.
  - `RC03 clarify → accept` with `[[C2]]`.
  - `RC02` (add references) with no anchor → **defer** (no invented citation).
  - `RC04` (unrelated disease) → **reject**, with the reason stated in the response letter.
  - `selfcheck.json`: `ok = true`, problems `[]`, `no_accept_without_change = true`.
- **Four-state decision** — `accept` / `partial` / `reject` / `defer` all reachable;
  `comment_ledger.json.decisions` reports the count of each.
- **Anchor threshold** — raised to `0.15` (cosine) with a CJK fallback (≥3 shared content
  characters and ≥20% coverage), so off-topic comments are not force-anchored; a short
  Chinese revision-plan case anchors only the two on-topic comments and defers the ethics one.
- **Language** — revision text follows the manuscript's language (material detection wins,
  `case.json.language` is the fallback), so an English paper gets English edits and a Chinese
  plan gets Chinese edits.
- **Consistency self-check** — response letter cites only change ids that exist in
  `change_locator.json` **and** whose `[[Cx]]` marker is present in the revised text.

## 3. Degenerate input

- Missing/empty input directory → `status = failed`, legal `result.json` with non-empty
  `limits`/`uncertainties`, **exit 0**.
- Unreadable/binary material → recorded in `degradations`, run continues.
- Non-writable output dir → falls back to `./output`.
