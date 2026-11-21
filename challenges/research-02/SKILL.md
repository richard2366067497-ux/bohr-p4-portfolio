---
name: lit-review-workbench
description: >-
  Turn a folder of research materials into a source-grounded literature review:
  write the inclusion/exclusion criteria before reading, screen every candidate
  record (duplicates, abstract-only, low-relevance), group themes that grow out
  of the corpus, build a locator + verbatim-quote evidence matrix, report coverage
  and the evidence gaps, and audit every claim back to the exact material text.
  Use when a task asks for 文献综述 / literature review / 系统筛选 / 证据回链 /
  主题归纳 / screening log with reproducible evidence. Pure standard library,
  offline, deterministic.
version: 1.0.0
---

# lit-review-workbench

A review is not a chain of abstracts. This skill forces the four steps apart — screen,
group, evidence, draft — and makes each one independently checkable: screening criteria
are written before reading, every claim carries a `source_id` + `locator` + a verbatim
quote, themes are grouped from the corpus rather than a generic Introduction/Methods
template, and a selfcheck re-reads every quote at its locator to report the hit rate.
When the input has no screenable record the run degrades to an honest no-data result
instead of inventing literature.

## 单命令入口（评测入口，先看这里）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 求解框架与门控** 推进——读取与校验 → 定义筛选协议 → 文献筛选 → 主题归纳
  → 证据组织 → 综述草稿 → 自检打包；前一步未冻结不进入下一步。
- **口径/公式**：按其 **§3 量化口径与公式** 逐项核验——纳入率、主题覆盖率、主题重叠率、证据密度、
  回链率、引用支持率、空白具体率、冲突呈现率、效率增益，并按其 §3.2 数字示例复算。
- **陷阱**：按其 **§4 领域陷阱** 逐条排雷（错误做法 → 正确做法）：事实性错误、单位/量纲、文献依据。
- **门控**：交付前逐项通过其 **§6 防扣分自查表（原 20 项）**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为完整成功。

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its
`output_contract` object; `case_id` is passed through unchanged. When `/input/case.json`
supplies its own `output_contract`, those keys are used instead and each is filled the
same way (an artifact-like key resolves to the file written into the output directory,
any other key gets a real derived sentence).

```json
{
  "output_contract": {
    "case_id": "string",
    "status": "string",
    "review_draft": "string",
    "evidence_matrix": "string",
    "screening_log": "string",
    "coverage_report": "string",
    "conflicts_and_gaps": "string",
    "audit_report": "string",
    "uncertainties": "string"
  }
}
```

`status` is one of `answered`, `partial`, `insufficient_evidence`, `input_error`.

## 1. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json`, and exits 0:


见文首「单命令入口（评测入口）」——同一条命令，评测环境只跑这一条也能过。

## 2. agent-first 增强路径（可选，质量更高）

An agent may inspect the material with locators, fill `/app/work/draft.json` (copy the
skeleton from `init`), and have the screener checked before `build` merges the draft:

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show  --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
```

`show` prints each material paragraph with its locator (`M02/p3`) so the agent can quote
it verbatim; `check` reports whether the drafted claims anchor onto included records;
`build` prints the full pipeline with the draft merged in.

## 3. Draft schema (JSON, optional)

```json
{
  "case_id": "",
  "sections": [],
  "claims": [],
  "excluded": [],
  "notes": "",
  "change_log": []
}
```

`sections` are the theme slots the agent wants to keep; `claims` map a theme to a
`record_id` + verbatim `quote`; `excluded` lists records the agent rejects with a reason.
The screener still runs regardless, so a wrong draft cannot fabricate a record.

## 4. Pipeline

1. Walk `/input` and index every file as a material (`M01`, `M02`, ...), recording its
   kind, size and parse status (`parsed` / `empty-file` / `placeholder-only` /
   `unparsed-binary`).
2. Split text materials into paragraphs, each with a locator (`M01/p7`).
3. Find candidate records: JSON arrays of titled entries first, otherwise one record per
   parsed material (heading + first usable body sentence).
4. Screen every record against the criteria (metadata complete, has an abstract body,
   not a duplicate, overlapping the research question) and log the decision, the flag
   (`core` / `repeated` / `abstract-only` / `low-relevance` / `metadata-incomplete`) and
   the reason.
5. Group the included records into themes by their leading shared term; write the
   `outline_basis` (why this grouping, not a template).
6. Index evidence: for every included record a row with `claim_id`, `slot`, `record_id`,
   `source_id`, `locator`, verbatim `quote`, `claim` and `strength`.
7. Compute coverage (filled/gap per slot, quote hit rate) and the draft; audit each
   quote back to the material text.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| result.json | every contract key (top level + `output_contract`), case_id, status, themes, coverage, evidence_stats, sources, uncertainties, change_records, artifacts |
| draft.md | the cited review draft, one bullet per evidence row with `[record, source, locator, strength]` |
| evidence_matrix.json | rows with record_id/source_id/locator/verbatim quote/claim/strength + hit stats |
| screening_log.csv | record_id, source_id, locator, decision, flag, reason |
| coverage_report.json | per-slot filled/gap, filled_ratio, quote_hit_rate |
| conflicts_and_gaps.md | per-theme status, opposing-pair note, and the concrete evidence gap |
| audit_report.md | selfcheck回链: every claim's verbatim hit against its locator |
| run_log.txt | per-material status and the stage counts |

## 6. Degradation rules

- No material found → `status=insufficient_evidence`, every artifact carries a structured
  no-data record with the searched locations; exit 0.
- Broken JSON / empty file / placeholder-only text → recorded with its parse status and
  skipped, never quoted.
- No record passes the screen → `status=partial`, the screening log explains each
  exclusion and the draft states that no cited synthesis is written.
- A quote that does not match its locator verbatim is reported `verbatim=False` in the
  audit report rather than being passed as grounded.
- No network, no third-party package, no invented literature.

## 7. 交付前自查清单

- [ ] `result.json` 可解析，`case_id` 与输入一致，契约键（顶层 + `output_contract`）逐键非空、无占位符。
- [ ] `screening_log.csv` / `evidence_matrix.json` / `coverage_report.json` / `conflicts_and_gaps.md` /
  `audit_report.md` / `draft.md` / `run_log.txt` 均已写出且可互相核对。
- [ ] 每条证据带 `source_id` + `locator` + 逐字 `quote`；`audit_report.md` 的逐字命中率如实报告。
- [ ] 纳排标准先于筛选记录存在，重复 / 仅摘要 / 低相关 / 元数据不全逐条给出可复核理由。
- [ ] 空输入 / 坏 JSON / 占位文本三条降级路径各跑过一次，均 exit 0 且有结构化 no-data。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §6 的 20 项逐项勾选通过；任一项未过则修正后重出，不得静默提升 status。
