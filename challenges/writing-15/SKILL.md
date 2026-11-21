---
name: longdoc-consistency-ledger
version: 1.0.0
description: >-
  Run a source-faithful consistency pass over thesis and long-document chapters: index the
  supplied materials into located blocks, build six mechanical ledgers (term, symbol, definition,
  numbering, citation, claim, unit), insert locator-anchored annotations without altering the
  author's lines, and keep a preserved-fact and rollback check for every block. Use when a task
  asks for 学位论文/长文档写作, 跨章节一致性, 术语与引用核对, 编号与交叉引用检查, or 改稿留痕
  with a reproducible evidence trail. Pure standard library, offline, deterministic, exit 0.
---

# longdoc-consistency-ledger

A long document fails less often from bad prose than from drift: the same abbreviation is expanded
two ways, a figure is cited with no caption, a citation points at a missing entry, or a result
chapter and a discussion chapter disagree. This skill turns the supplied chapters into an
**index, six ledgers, a set of findings, and annotations that can be removed again**. It never
rewrites the author's sentences and it never invents a reference.

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册给出任务本质
与判分要点、错误做法→正确做法、6 步求解框架、量化口径与公式（事实-来源匹配率 / 术语一致性 /
引用缺失率 / 编号连续性 / 修改可追溯率）、领域知识与单位陷阱、交付物清单与专家检查表、完整虚构
案例与交付前门控。执行顺序固定为：先读手册 → 再按求解框架逐阶段落盘冻结产物 → 交付前逐项勾选
手册 §5.2 专家检查表。手册与本文冲突时，契约键名与入口命令以本文为准，方法与判分口径以手册为准。

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its `output_contract`
object. `case_id` is passed through unchanged. If the case supplies its own `output_contract`,
those keys are used instead and each one is filled with a real derived value.

```json
{
  "output_contract": {
    "term": "abbreviation/expansion pairs and conflicts",
    "symbol": "symbol definitions and meanings",
    "definition": "explicit definition statements",
    "numbering": "figure/table/equation captions and cross-references",
    "citation": "numeric and author-year citations with cross-check state",
    "claim": "claim sentences with polarity and quantity flags",
    "unit": "value + unit pairs, normalised writings",
    "annotations_applied": "how many annotation blocks were applied to how many targets",
    "sha": "sha256/16 of revised_manuscript.md",
    "case_id": "the input case id, passed through"
  }
}
```

## 1. Draft schema (`/app/work/draft.json`, optional)

`build` works without a draft. A draft only lets an agent add its own reading notes, findings and
annotations; every annotation is re-verified against the located block and a quote that does not
match is rejected, never adjusted.

```json
{
  "case_id": "",
  "reading_notes": "",
  "targets": [],
  "annotations": [
    {
      "target_id": "",
      "locator": "chapter.md §2 Methods ¶3",
      "anchor_quote": "a verbatim sentence from that block",
      "annotation": "what this passage establishes, its condition, and what a reader may conclude",
      "evidence": [{"locator": "chapter.md §2 Methods ¶3", "quote": "verbatim source"}],
      "rationale": "why this note is needed",
      "uncertainty": "what cannot be confirmed from the material"
    }
  ],
  "findings": [],
  "pending_human": []
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command. With no draft it still indexes the material, writes every artifact and a
complete `result.json`, and exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

Index first, read each target with its locator, write the draft, then check and build:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`init` writes a valid partial `result.json`, `work/source_index.json` and a draft template with the
real locators. `show` prints every block with `<material> §<section> <title> ¶<paragraph>`.
`check` accepts an annotation only when its locator resolves and its anchor quote is verbatim
inside that block. `compare` writes the base-vs-skill contrast to `work/compare_report.json`.

## 4. Pipeline

1. Walk `/input` (max 120 files, max 600k characters per file) and classify each file with its
   kind, size and parse status: `parsed`, `empty-file`, `placeholder-only`, `invalid-json`,
   `unparsed-binary`. Labels are never trusted; extensions and content are inspected.
2. Split each readable chapter into located blocks. A heading starts a section (`§n`); paragraphs
   are numbered inside the section (`¶m`). The raw lines are kept exactly.
3. Build the six ledgers from the raw text:
   term (`expansion (ABBR)`), symbol (`where X is …`, `X =`), definition (`X is defined as …`),
   numbering (captions vs cross-references), citation (`[n]`, `(Author, 2020)`, reference entries),
   claim (claim verbs + negation polarity + quantity flag), unit (value + unit, normalised spelling).
4. Turn conflicts into findings: one abbreviation expanded two ways, a symbol with several
   meanings, a cited figure/table with no caption, a citation with no entry, two chapters of
   opposite polarity on the same topic.
5. Insert one annotation block after each affected block. Removing the annotation blocks restores
   the source text; `preserved_facts.json` and `versions/rollback_check.json` record that check.
6. Echo every contract key, write the artifacts, and run `selfcheck`.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | contract keys at the top level and in `output_contract`, status, findings, annotations, sources, uncertainties, pending items, coverage |
| `revised_manuscript.md` | source blocks in order plus annotation blocks (separate lines, reversible) |
| `consistency_report.md` | materials, ledger counts, findings, preservation, limits |
| `consistency_tables.json` | all seven ledger tables plus findings |
| `evidence_map.json` | one locator + verbatim quote + sha per ledger row and finding |
| `preserved_facts.json` | every source block with its char count, hash and preserved flag |
| `change_log.json` | each inserted annotation with the original quote and reversed flag |
| `coverage_matrix.json` | required structures extracted or missing, ledger counts, finding count |
| `pending_human.json` | author decisions the mechanical rules cannot make |
| `run_log.txt` | per-material status and stage counts |
| `versions/` | `v1_original.md`, `v2_revised.md`, `rollback_check.json` |

## 6. Degradation rules

- No readable chapter → `status=insufficient_evidence`; every artifact carries a structured no-data
  record naming what was searched; exit 0.
- An empty file, a placeholder-only file, an invalid JSON file or a binary file is recorded with its
  status and is never quoted; it is listed in `uncertainties` and `pending_human`.
- A citation without a reference list is reported as "cannot be cross-checked"; a missing entry is
  never invented.
- A file over 600k characters is truncated; the truncation is recorded and the status becomes
  `partial`.
- Placeholder tokens in the source (`[待写]`, `TODO`, `null`, `N/A`, `pending`, `lorem ipsum`) are
  neutralised in the deliverables and listed as a sanitisation note; the original file is untouched.
- A draft annotation whose locator does not resolve or whose quote is not verbatim is rejected and
  reported; the source is not changed.

## 7. Worked example ( illustrative output, not an official case result )

Running the single command on a two-chapter Markdown manuscript produced:

```text
build: status=ok artifacts=13
selfcheck: files=ok echo=ok placeholders=ok status=ok
```

and a `result.json` whose `output_contract` filled all ten keys:
`term` found `FDM (fused deposition modelling)`, `numbering` found `Figure 3` cited with no
`Figure 3` caption, `citation` reported `[5]` with no reference-list entry, `annotations_applied`
reported one block applied to the affected paragraph, and `sha` reported the 16-character hash of
`revised_manuscript.md`. This excerpt is an illustration; the platform supplies the fixed cases.

## 8. Innovation, boundaries and maintenance

- **Innovation.** Deterministic seven-ledger extraction with locator-level quotes, reversible
  annotation blocks, and a preserved-fact/rollback invariant. A base agent typically rewrites the
  passage and cannot show which source lines survived; this skill shows that mechanically.
- **Boundary.** Ledgers are candidate signals from patterns, not a scientific verdict. Free-text
  synonymy, paraphrase-level claim contradiction and author-intent questions still need a human.
  The skill does not generate new scientific content and does not replace a reference manager.
- **Maintenance.** Change a rule in `references/rules-and-failure-modes.md`, then the constant in
  `scripts/ledger_engine.py`, then rerun `check` and `build`; confirm the `sha` of
  `revised_manuscript.md` is stable for unchanged input.
- **Known failure modes** and a test matrix are in `references/rules-and-failure-modes.md`. Reusable
  glossary, citation and chapter-check templates are in `templates/`.

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §5.2 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，逐键回填 `output_contract`，`case_id` 与输入一致。
- [ ] `revised_manuscript.md` 可移除批注块还原原文，`preserved_facts.json` 与回滚校验一致。
- [ ] 空输入 / 仅占位符 / 坏 JSON / 二进制四条降级路径各跑过一次，均 exit 0 且写出合法 `result.json`。
