---
name: method-statistics-audit
version: 1.0.0
description: >-
  Turn a supplied review material set (checklist, rule table, severity anchors) into a reproducible
  research-method and statistics audit: parse the issue-type library and the nature-to-severity caps
  FROM the material, locate every rule with an M#/p# locator and a verbatim quote, build a ledger that
  keeps "not reported" apart from "done wrong", cover the five facets and six review dimensions, cap
  underreporting at major and acceptable-but-clarify at minor, and record the boundary honestly. Use
  when a task asks for 研究方法审查 / 统计审查 / 缺陷类型 / 严重度分级 / 审查台账 with a reproducible path.
  Degrades honestly to insufficient_evidence when the material is empty, corrupt or placeholder-only.
  Pure standard library, offline, deterministic, exit code 0.
---

# method-statistics-audit

An audit is only worth as much as its evidence. Here every rule carries the locator it came from and a
verbatim short quote; a rule in the table is never asserted as a manuscript defect; "the author did not
report X" is never written as "the author did X wrong"; and the severity of an underreporting item is
capped at major, so no missing report can be escalated to critical. No network, no clock, no third-party
package, no invented manuscript sentence.

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its `output_contract` object;
`case_id` is passed through unchanged. When the case supplies its own `output_contract`, those keys are
used instead and each is filled the same way (a delivery-like key resolves to the written artifact, an
issue-type key gets its located rule row, any other key gets a real derived value, never an empty shell).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "partial | insufficient_evidence | input_error",
    "deliverable": "audit_report.md",
    "findings": "findings.json",
    "ledger": "statistics_ledger.json",
    "coverage": "coverage.json",
    "evidence_map": "evidence_map.json",
    "change_log": "change_log.json"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with its own ledger rows and findings; `build` records whether a
draft was seen, and the deterministic pass still runs regardless, so a thin draft cannot turn an
unlocated rule into an asserted defect.

```json
{
  "case_id": "",
  "manuscript_meta": {"title": "", "design_type": "", "field": "", "target_guideline": "", "n_reported": ""},
  "statistics_ledger": [],
  "extra_findings": [],
  "unchecked_items": [],
  "uncertainties": [],
  "summary": ""
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete `result.json`, and
exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

List the material with locators, fill the draft above, then check it before `build` normalises it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints every quotable line with an `M02/p7` locator; `check` reports how many issue types,
locators and facets the material supports; `compare` writes a baseline-vs-skill contrast to
`/app/work/compare_report.json` and emits `gain_report.json` + `gain_report.md` into the output directory.

## 4. Pipeline

1. Index every file under `/input` with its kind, size, sha256 and parse status
   (`parsed` / `empty-file` / `no-data-only` / `corrupt-json` / `unparsed-binary`).
2. Split each parsed source into lines, each with an `M#/p#` locator. Task scaffolding
   (`case.json` / `task.md` / `README`) is indexed but never quoted as an audit source.
3. Parse the issue-type table and the nature-to-severity cap table from the material into the rule
   library; on failure fall back to the built-in 28-item library and record `rules_fallback`.
4. Locate every issue-type row with its locator and verbatim quote; build one finding and one ledger row
   per rule, each marked `not_exercised` (no manuscript row invoked it).
5. Apply the severity discipline: underreporting is capped at `major`, acceptable-but-clarify at `minor`;
   a cap rewrite is recorded in `change_log.json`.
6. Compute the five-facet and six-dimension coverage, the evidence map and the boundary entries, then
   write every artifact.

The engine lives in `scripts/auditlib.py`; `scripts/main.py` is the CLI entry that imports it.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, counts, sources, uncertainties, change records, limits |
| `audit_report.md` | the human-readable audit: rule library, facet and dimension coverage, severity discipline, boundary |
| `statistics_ledger.json` | one row per rule with its locator, quote, cell_status and severity discipline |
| `findings.json` | one finding per rule row, marked `not_exercised` and never escalated past its nature cap |
| `coverage.json` | the five-facet and six-dimension coverage and what was not audited |
| `evidence_map.json` | each rule with its source id, `M#/p#` locator and match status |
| `change_log.json` | the ordered build steps and their counts |
| `index.json` | the source index and the located rule locators |
| `self_check.json` | the grounding self-audit (rules located, contract keys) |
| `boundary_log.json` | the boundary entries by type and the gaps |
| `gain_report.json` | the measured skill metrics next to the simulated baseline metrics |
| `gain_report.md` | the same contrast in a readable table, with the honest baseline declaration |
| `run_log.txt` | per-material parse status and the stage counts |

Raw source extracts are also written under `evidence/` as one file per source id, so every rule can be
re-checked against the line it came from.

## 6. Degradation rules

- No locatable rule row and no quotable line -> `status=insufficient_evidence`; every artifact carries a
  structured no-data record naming the searched locations; exit 0.
- A corrupt JSON, an empty file or a no-data-only text is recorded with its parse status and is never
  quoted; it is listed in `run_log.txt` and in the matching `evidence/` snapshot.
- An issue-type table that cannot be parsed -> the built-in 28-item library is used and `rules_fallback`
  is recorded in `degradations`.
- No manuscript row -> every rule is `not_exercised`, and no defect severity is asserted.
- An underreporting item is capped at `major` and an acceptable-but-clarify item at `minor`; the cap is
  never silently dropped.
- No network, no clock, no third-party package, no invented manuscript sentence or severity.

## 7. Coverage duty (five facets, six dimensions)

`coverage.json` counts, item by item, the **five check facets** (`design_fit`, `variable_definition`,
`statistics`, `sample_size`, `reporting`) and the **six audit dimensions** (`fact`, `citation`,
`method`, `stat_report`, `argument`, `norm`). A facet with no located rule is written as
`not covered` rather than omitted, so citation support, factual verification and academic-norm items
can never be silently skipped: every case is required to carry at least a citation-support check and a
factual-verification check, and `scripts/main.py check` prints the facet and dimension coverage counts
into `work/check_report.json` so a gap is visible before `build`. The `natures` field of each issue type (in
`references/defect_types_and_severity.md`) is what maps a defect to its dimension, so a new issue type
cannot be added without naming the dimension it audits.

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
