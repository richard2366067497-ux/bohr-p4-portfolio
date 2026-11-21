---
name: patent-search-dossier
version: 1.0.0
description: >-
  Turn a supplied patent/literature material set into a reproducible search dossier: locate every
  quotable line, normalise publication/application/grant/priority numbers with a traced rule chain,
  record legal status with its source kind and an as-of date, grade every source with a green/yellow/red
  licence gate, keep a family graph that never claims exhaustiveness, log boundaries and gaps, keep the
  raw evidence snapshot behind every number and label, and render a figure. Use when a task asks for
  专利检索 / 技术文献检索 / 号码规范化 / 同族归并 / 法律状态核验 / 许可分级 with a reproducible path.
  Degrades honestly to insufficient_evidence when the material is empty, corrupt or placeholder-only.
  Pure standard library, offline, deterministic, exit code 0.
---

# patent-search-dossier

A patent search is only worth as much as its provenance. Here every number, label and boundary carries
the locator it came from and a verbatim short quote; a legal status is never inferred from a re-posting
page; a keyword hit is never promoted into a family link; and a source whose licence is not declared is
handled as the yellow tier, so only conclusions and locators leave the dossier. No network, no clock,
no third-party package, no invented literature or numbers.

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **协议先行**：按其 **§2 七步框架（含门控）** 推进——盘点材料 → 冻结检索协议 → 来源授权分级
  → 执行查询并存证 → 抽取规范化定位 → 筛选归并状态核验 → 尽早输出增量完善；前一步未冻结不进入下一步。
- **授权闸门**：按其 **§3 绿/黄/红分级**处理每份来源，许可未声明按黄色并进 `gaps`。
- **口径与公式**：按其 **§4** 计算精确率/召回率/正确率/覆盖率/可追溯率；召回率无完整参考范围时
  报 `not_estimable`，不得宣称 100%。
- **事实边界**：按其 **§5 领域事实清单** 逐条排雷；号码规范化不等于存在性证明，授权种类代码
  不等于当前有效。
- **门控**：交付前逐项通过其 **§8 防扣分自查表（26 项）**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties` / `boundary_log.json`，绝不静默提升为完整成功。

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its `output_contract` object;
`case_id` is passed through unchanged. When the case supplies its own `output_contract`, those keys are
used instead and each is filled the same way (a delivery-like key resolves to the written artifact, any
other key gets a real derived value, never an empty shell).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "partial | insufficient_evidence | input_error",
    "deliverable": "dossiers.md",
    "evidence_map": "evidence_map.json",
    "change_log": "change_log.json",
    "coverage": "coverage.json"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with its own number decisions, patent objects, family edges,
status entries and licence decisions; `build` records whether a draft was seen, and the deterministic
pass still runs regardless, so a thin draft cannot turn an unlocated number into a located patent.

```json
{
  "case_id": "",
  "query": {"kind": "number | topic | both", "statement": "", "targets": [], "scope": "", "excluded": []},
  "number_decisions": [],
  "patent_objects": [],
  "field_extraction": [],
  "family_edges": [],
  "status_entries": [],
  "claims_versions": [],
  "technical_papers": [],
  "license_decisions": [],
  "boundaries": [],
  "conflicts": [],
  "gaps": [],
  "status_note": ""
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete `result.json`, and
exits 0:

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

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

`show` prints every quotable line with an `M02/p7` locator; `check` reports how many numbers, status rows
and boundaries the material supports; `compare` writes a baseline-vs-skill contrast to
`/app/work/compare_report.json` and emits `gain_report.json` + `gain_report.md` into the output directory.

## 4. Pipeline

1. Index every file under `/input` with its kind, size, sha256 and parse status
   (`parsed` / `empty-file` / `no-data-only` / `corrupt-json` / `unparsed-binary`).
2. Split each parsed source into lines, each with an `M#/p#` locator. Task scaffolding
   (`case.json` / `task.md` / `README`) is indexed but never quoted as a searchable source.
3. Find every patent-number shape in the quotable lines and normalise it:
   `strip_separators` -> country prefix -> trailing kind code -> digit-count type -> inferred country.
4. Record legal status provenance per number: value, as-of date, source kind, confidence and the
   `needs_official_verification` flag. With no official register page the value stays unknown.
5. Grade every source with the licence gate and write the degrade plan for the tier it lands in.
6. Write the boundaries, the gaps, the evidence map and one raw evidence snapshot per source, then
   render the family figure.

The engine lives in `scripts/kglib.py`; `scripts/main.py` is the CLI entry that imports it.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, counts, sources, uncertainties, change records, limits |
| `dossiers.md` | the human-readable dossier: lanes, number registry, status table, licence gate, boundaries, evidence map |
| `number_registry.json` | the normalised number entries with their rule chain and locators |
| `family_graph.json` | family nodes, observed edges, the not-exhaustive note and the figure legend |
| `family_graph.png` | the rendered family figure (plain png from zlib+struct, no third-party library) |
| `status_provenance.csv` | one row per number: value, as_of, query date, source kind, locator, confidence, verify flag |
| `license_gate.md` | the green/yellow/red grading table with the degrade plan for each source |
| `boundary_log.json` | the boundary entries by type, the conflicts and the gaps |
| `evidence_map.json` | each claim with its source id, `M#/p#` locator and match status |
| `change_log.json` | the ordered build steps and their counts |
| `coverage.json` | the facet coverage, counts and the summary reliability note |
| `self_check.json` | the grounding self-audit (every claim located, contract keys, figure present) |
| `gain_report.json` | the measured skill metrics next to the simulated baseline metrics |
| `gain_report.md` | the same contrast in a readable table, with the honest baseline declaration |
| `run_log.txt` | per-material parse status and the stage counts |

Raw source extracts are also written under `evidence/` as one file per source id, so every number and
label can be re-checked against the line it came from.

## 6. Degradation rules

- No locatable number and no quotable line -> `status=insufficient_evidence`; every artifact carries a
  structured no-data record naming the searched locations; exit 0.
- A corrupt JSON, an empty file or a no-data-only text is recorded with its parse status and is never
  quoted; it is listed in `run_log.txt` and in the matching `evidence/` snapshot.
- No official register page -> the legal status stays unknown and is never written as granted or lapsed.
- No family link observed -> the graph carries isolated nodes and exhaustiveness is never claimed.
- A source whose licence is not declared -> the yellow tier; only conclusions, field names and locators
  leave the dossier.
- No network, no clock, no third-party package, no invented literature, numbers or legal status.

## 7. 专家门控（交付前硬性）

**专家检查表逐项通过**是交付前的硬门控：每件交付物必须先通过
`references/expert_playbook.md` §8 的 26 项防扣分自查表。任一项未通过，`status` 记为 `partial`
并把未决项写入 `uncertainties` 与 `boundary_log.json`，绝不静默提升为完整成功。
