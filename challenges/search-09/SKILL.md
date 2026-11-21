---
name: literature-appraisal-benchmark
version: 1.0.0
description: Appraise a literature corpus against a checklist of dimensions, check points, judgment rules and grading thresholds. Parse the checklist, scan the corpus for each check point's keyword and negative-keyword family, locate every anchor with a source locator and verbatim quote, apply the judgment rules and thresholds, and emit a candidate pool, an anchor table, a grading trace and a report. Standard library only, offline, deterministic.
license: MIT
---

# literature-appraisal-benchmark

Turn a checklist plus a corpus into a structured, evidence-located appraisal — not a summary.

Four questions drive the design, and each is answered by an artifact:

| question | meaning | artifact |
|---|---|---|
| 规得齐 | one check point → one dimension, with the study-type specific ones added | `candidate_pool.csv` |
| 换得准 | a judgment keeps its rule id, its risk floor and its threshold | `grading.json` (`trace`) |
| 合得对 | a merge/judgment uses a defensible key, not a vibe | judgment rules `R_J1`…`R_J4` |
| 追得回 | every judgment walks back to a source locator and a verbatim quote | `anchor_table.csv` |

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 0. result.json contract

The entry command writes `/app/output/result.json` and echoes every field of the caller's
`output_contract` verbatim, both at top level and inside `output_contract`:

```json
{
  "case_id": "synth-rich-search-09",
  "status": "partial",
  "deliverable": "candidate_pool.csv",
  "page": "M01 p1-p126",
  "anchor_table": "anchor_table.csv",
  "some": "some=B3,C1,D3; major=Z3",
  "low_risk": "high_risk",
  "dimensions": {"DESIGN": "some", "SAMPLE": "low", "STATSREP": "some", "BIAS": "major"},
  "counts": {"check_points": 46, "kw_families": 45, "types": 11, "anchors": 109, "corpus_lines": 126},
  "evidence_map": [{"label": "A001", "locator": "M01/p18", "match": "verbatim", "kind": "kw"}],
  "check_report": "check_report.json",
  "self_check": "self_check.json",
  "sources": [{"id": "M01", "name": "appraisal_rules.md", "parse_status": "parsed"}],
  "uncertainties": ["12 check point(s) are not assessable on this corpus (abstained, not guessed)"],
  "change_records": [{"step": 1, "action": "scan material"}],
  "limits": ["a check point with no keyword hit abstains, it is never guessed"],
  "gaps": [{"item": "corpus text for the abstaining check points"}],
  "output_contract": {
    "page": "M01 p1-p126",
    "anchor_table": "anchor_table.csv",
    "some": "some=B3,C1,D3; major=Z3",
    "low_risk": "high_risk"
  }
}
```

`status` is `partial` (checklist parsed and graded), `insufficient_evidence` (no checklist found) or
`input_error`.

## 1. agent draft

An agent may pre-write `/app/work/draft.json`; every field is optional and the build step fills what
is missing:

```json
{
  "case_id": "synth-rich-search-09",
  "notes": "free-text triage note from the agent",
  "dimension_overrides": {},
  "abstain_policy": "abstain, never guess, when a keyword family has no hit"
}
```

## 2. 单命令（等价入口，评测入口，one-shot）

This is the single-command equivalent and the evaluation entry point. With **no** draft present it
still produces the complete contract, every deliverable and `result.json`, and exits 0.
The command block is the first code block at the top of this file.

Optional arguments: `--input` (default `/input`), `--output` (default `/app/output`),
`--work` (default `/app/work`). Deterministic, offline, standard library only.

## 3. agent 增强路径 (multi-step)

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints the parsed checklist without writing anything. Every subcommand exits 0.

## 4. pipeline

1. **scan** every material file and class it `parsed` / `empty-file` / `no-data-only` / `corrupt-json`
   / `unparsed-binary`, with byte size and content hash.
2. **parse** the ` ```rules ` block: keyword families (`kw`), check points (`cp`), study types
   (`type`) and generators (`gen`); parse the judgment-rule table (`R_J1_ABSTAIN`…`R_J4_WEAK`) and the
   numbered grading thresholds from the surrounding prose.
3. **scan** the corpus for each check point's keyword family and negative-keyword family; keep every
   hit as an anchor with its source locator and the verbatim line.
4. **judge** each check point with the material's own rules: no hit → `not_assessable`; a negative
   hit with <2 anchors → `not_met`; ≥2 anchors → `met` at the check point's risk floor; exactly one
   anchor → `partial`.
5. **grade** per dimension (worst risk wins; no valid judgment → `insufficient`) and overall by the
   material's thresholds (abstain ≥30% → `insufficient_evidence`; DESIGN/SAMPLE/BIAS `major` →
   `high_risk`; any `some` → `some_concerns`; else `low_risk`).
6. **write** the candidate pool, the anchor table, the grading trace, the report, the check report,
   the self check, the run log, the gain report and the per-material evidence snapshots.

## 5. artifacts under /app/output

- `result.json` — the contract echo plus sources, uncertainty, change records and limits.
- `candidate_pool.csv` — one row per check point: `cp_id, dimension, question, keyword_family,
  negative_family, chapters, risk_floor, study_type, locator`.
- `anchor_table.csv` — the evidence locator table: `anchor_id, kind, ref, locator, quote`.
- `grading.json` — dimensions, overall verdict, thresholds, judgment rules and the per-check-point trace.
- `appraisal_report.md` — counts, dimension risk, candidate pool, trace and the first 20 anchors.
- `check_report.json`, `self_check.json`, `run_log.txt` — the machine check, the self check and the trace.
- `gain_report.json` / `gain_report.md` — baseline vs skill, honestly labelled.
- `evidence/M##.json` — one snapshot per material with parse status and quoted lines.

## 6. degradation and robustness

- No checklist block → `status: insufficient_evidence`; every artifact is still written and the
  searched locations are named.
- A corrupt / empty / no-data material file → classified and skipped, never used, never invented.
- A check point whose keyword family has no hit → `not_assessable` with reason `R_J1_ABSTAIN`; it is
  never guessed into `met`. The abstain ratio drives the overall verdict.
- A rule block that cannot be parsed → falls back to a minimal built-in checklist and records
  `degradations: rules_fallback`.
- No network, no clock, no third-party package; the run is deterministic and reproducible.

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
