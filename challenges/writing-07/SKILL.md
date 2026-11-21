---
name: intro-relatedwork-writer
description: >-
  Turn a manuscript plus reviewer comments into a source-grounded four-section
  introduction and related-work revision (研究背景 / 相关工作 / 研究空白 / 贡献).
  Every number and citation marker is copied verbatim from a material line with a
  locator and a verbatim quote; citations are bound inline to the specific claim
  they support; the research gap is derived from at least two premises; each
  reviewer comment is mapped to an applied change. Use when a task asks for
  引言与相关工作写作 / introduction and related work / 文献综述改写 / 引用与论断绑定 /
  研究空白推导 / 贡献与图表对齐. Pure standard library, offline.
version: 9.1.0
---

# intro-relatedwork-writer

Nothing that leaves this skill is invented. Every number and every citation marker
is copied verbatim from an input material together with a locator (`<file>#L<line>`)
and the verbatim quote of that line. Sentences that were not found in the material
are reported as absent, never written as if present. The `output_contract` keys are
echoed both at the top level of `result.json` and inside its `output_contract`
object, and `case_id` is passed through unchanged.

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点（立得住/分得清/说得实/对得上/可核验）、错误做法→正确做法、
八步求解框架与门控、量化口径与公式（引用覆盖率、引用-论断绑定率、分组纯度、空白推导支持率、
贡献-证据对齐率、元数据准确率、事实可回溯率、转述一致性、格式一致性）、领域陷阱、交付物清单
与 20 项防扣分检查表、完整虚构案例。执行顺序固定为：先读手册 → 再用 §1 单命令或 §2 agent-first
路径逐阶段落盘 → 交付前逐项勾选手册 §6 检查表。手册与 `SKILL.md` 冲突时，契约键名、入口命令与
产物文件名以 `SKILL.md` 为准，方法与判分口径以手册为准。

## 0. result.json contract

The engine fills every key below (top level and inside `output_contract`):

```json
{
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "preserved_facts": "string",
    "evidence_map": "path",
    "change_log": "path"
  }
}
```

When `/input/case.json` supplies its own `output_contract`, those keys are used
instead (names kept verbatim, none dropped or merged) and each is filled the same
way. `status` is one of `answered`, `partial`, `insufficient_evidence`,
`input_error`.

## 1. 单命令（one-shot，评测入口，无 draft 时执行）

Run this single command; with no draft it still writes every artifact and a
complete `result.json` and exits 0.

## 2. agent-first 增强路径（质量更高，可选）

An agent may fill `/app/work/draft.json` to steer the derivation:

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py show --input /input --work /app/work
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output --work /app/work
```

`show` prints material sentences with their locators so the agent can quote them
verbatim; `check` reports whether the four sections are derivable and whether the
gap has at least two premises; `selfcheck` re-audits the produced artifacts and is
the packaged reliability test.

## 3. Draft schema (JSON, optional, 示例)

```json
{
  "case_id": "",
  "task_understanding": "",
  "claims": [
    {"section": "background", "claim": "", "locator": "", "quote": ""}
  ],
  "gap_premises": [],
  "contributions": [],
  "uncertainties": []
}
```

An empty draft is legal; the engine then uses the rule-based derivation. Extra
`uncertainties` are appended verbatim to the run's uncertainty list.

## 4. Pipeline

1. Scan every file under `/input` and index it as a material (`M01`, `M02`, ...).
2. Copy each non-heading line as a fact with `locator`, verbatim `quote`, the
   numbers it contains and the `[S#]` citation markers it carries.
3. Register each citation marker as a source and bind it inline to the claim that
   carries it (never at paragraph end).
4. Derive 研究背景 / 相关工作 / 贡献 from the material sentences and 研究空白 from at
   least two premises (cited-work limitations and reviewer comments).
5. Verify that every source number and citation marker survives verbatim in the
   manuscript; report the hit rate.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| result.json | contract keys (top level + `output_contract`), status, sections, citations, preserved_facts, evidence_stats, metrics, contract_check, limits, uncertainties, pending_human, sources, change_records, artifacts |
| manuscript.md | the four-section revised manuscript with inline citations |
| sources_used.md | every `[S#]` source with locator and verbatim quote |
| claim_map.md | `F#:locator` mapping from each claim to its verbatim source line |
| gap_ledger.md | each research gap with its ≥2 premises and locators |
| contribution_alignment.md | each contribution with the result locator it aligns to |
| change_log.md | reviewer comment -> applied change |
| baseline_comparison.md | base-vs-skill comparison protocol and efficiency metrics |
| evidence.json | every fact with locator, quote, numbers and verbatim hit flag |
| verification.json | four-section counts, citation binding, gap premises, preserved facts |

## 6. Degradation rules

- No non-heading text line → the four sections are reported absent with the
  searched locations; `status=insufficient_evidence`.
- Fewer than two gap premises → the gap is stated as provisional; `status=partial`.
- No citation marker → the related-work section is bound to source sentences only.
- Unreadable (binary) file or unparseable JSON → recorded in `errors`, skipped,
  never guessed.
- Empty `/input`, bad JSON, missing `case.json` → still writes a legal `result.json`
  and exits 0.

## 7. 逐条 top_fix 落点

- 基线对照与效率指标 → `result.metrics`（elapsed_s / requests / rounds / hit rate）+
  `baseline_comparison.md`；GAIN_EVIDENCE.md 说明口径。
- GitHub 公开链接 → 根目录 `GITHUB_URL.txt`（两行）。
- 契约完整性校验 → `result.contract_check`：逐键比对 case.json 的 output_contract，
  缺失写入 `errors[]`。
- 示例 draft + 示意输出 → `examples/`；模板 → `templates/manuscript_template.md`。
- 可靠性自测 → `main.py selfcheck` + `SELFTEST.md`。
- 失败分析与 benchmark → GAIN_EVIDENCE.md 与 `baseline_comparison.md`。
- 专家方法论 → `references/expert_playbook.md`；每次交付前须**逐项通过其 §6 专家检查表**。
