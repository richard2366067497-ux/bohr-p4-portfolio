# SELFTEST — writing-10 (reviewer response and manuscript revision)

Validation performed with the packaged simulator `scripts/eval_sim.py` plus targeted
ad-hoc cases. All runs are offline, standard-library only.

## 1. Simulator runs (rich / boundary × single / agent)

Command shape:

```bash
python3 scripts/eval_sim.py --pkg work/p4/v9/writing-10 --case work/p4/synth_cases/writing-10/<case> --mode <single|agent>
```

| case | mode | status | notes |
|---|---|---|---|
| rich | single | **PASS** | contract_echo 5/5, 9 artifacts, case_id passed through, placeholder_sweep clean |
| rich | agent | **PASS** | same, agent draft path adopted when a draft is present |
| boundary | single | **PASS** | no `output_contract` in case.json → canonical 5 keys echoed; 9 artifacts; exit 0 |
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

## 4. v8 复跑与关键数字（examples/）

新增随包最小样例 `examples/`（`case.json` + `manuscript.md` 含过度声称句 + `comments.md` 4 条意见），
可被评审直接复跑：

```bash
python3 scripts/main.py --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = success`，产物 **8** 文件。
- `metrics = {comments: 4, changes: 3, decisions: {accept: 2, partial: 1, reject: 0, defer: 1}}`；
  `evidence_map` 4 条；`selfcheck.ok = true`；契约键 **5/5**；占位符 0。
- 裁决落点：①收窄 → accept(C1)；②补引用 → defer（记 `evidence_pending.md`）；③新增 500 例 → partial；
  ④澄清请求 → accept(C3)。
- 规范化哈希（`result.json` 删除 `runtime.seconds` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`36eb9043b58dfc37`**。
- `scripts/eval_sim.py` rich/boundary × single/agent 四项全 **PASS**（契约键 5/5）。


## 5. v9 addition: quality metrics + honest baseline contrast

scripts/main.py now also writes /app/output/quality_metrics.json and folds the same numbers into

esult.json.metrics, so the gain claim is recomputable from a single input:

- comment_coverage - share of parsed comments given an explicit disposition.
- locator_verifiable_rate - share of changes applied verbatim at a baseline anchor.
- evidence_completeness - share of comments answered without deferral.
- 	one_compliance - 1.0 when no adversarial/defensive phrase appears in the response letter.
- aseline_vs_skill - a deterministic self-assessment on the same input, explicitly labelled
  **not an official A/B result**.

Reproduction on the packaged sample (examples/, 4 comments / 2 documents):

`ash
python3 scripts/main.py --input examples --output /tmp/out --work /tmp/work
# exit 0; status=success; 9 output files
# comment_coverage=0.75, locator_verifiable_rate=0.667, tone_compliance=1.0
`
