---
name: research-topic-innovation-eval
version: 1.1.0
description: >-
  Turn a research-topic dossier into a checkable five-gate judgement: read the gate rules and the
  field dictionary out of the supplied materials, carry every rule, threshold and quote with its own
  material locator (M#/p#), fold a supplied draft into the scorecard, refuse to invent references or
  numbers, log contrary evidence instead of smoothing it over, and degrade honestly when the material
  cannot be parsed. Use when a task asks for 科研选题与创新性评估 / 立项评审 / 已有工作比较 +
  可行性判断 + 创新点识别 with a reproducible path. Pure standard library, offline, deterministic.
---

# research-topic-innovation-eval

A verdict is only worth as much as the rules it was checked against. This package reads those rules
out of the material at run time — the five gates, their `go`/`conditional`/`no_go` thresholds, the
error and warning codes, the controlled vocabularies, the three evidence-matching modes — and carries
each one with the locator it came from and the sentence that supports it. A statement that cannot be
matched verbatim in the material is reported in `uncertainty.json` rather than used, and a claim that
the rules forbid (a `novel` verdict resting on "nobody researched this") is refused, not written.

## 单命令入口（评测入口，先看这里）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

**Four deliverables ↔ five gates.** The task's four deliverables are not four parallel documents;
they are four sides of one judgement, and this Skill compresses them into five gates:

| 门 | 名称 | 回答的问题 | 题面交付项 | 本包产物 |
|-|-|-|-|-|
| G1 | worth_doing | 值得做吗 | 研究问题定义 | `decision_brief.md` 第 1–2 节 |
| G2 | nobody_done | 别人做到哪一步 | 已有工作比较 | `prior_art_alignment_matrix.csv` |
| G3 | can_do | 做得出来吗 | 可行性判断 | `assumption_register.json` |
| G4 | not_old_wine | 不是旧方案吗 | 创新点识别 | `gate_scorecard.json` 的 G4 条目 |
| G5 | downside | 失败会怎样 | 可行性判断（风险侧）+ 冲突证据 | `conflicts.json` |

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 八步框架（S0–S7）与门控** 推进——读取输入与资源 → 研究问题定义 → 检索与筛选
  → 证据矩阵 → 创新边界 → 可行性 → 综合与不确定性 → 输出与自检；前一步未冻结不进入下一步。
- **量化口径**：按其 **§3 量化口径与公式** 逐条复算 EC / VR / CRR / NRR / FSR / SR；逐字命中率
  <80% → `partial`，`ok` 还要求零 ERROR；总体判定不得高于最弱一门。
- **陷阱与单位**：按其 **§4 领域陷阱与单位** 逐条排雷（`mAh/g` 与 `mAh/cm²`、`mA/g` 与 `mA/cm²`、
  `°C`/`K`、`Pa`/`bar`、`mol/L`/`wt%`、TOF/TON），「检索不到」不得写成「尚无人研究」。
- **交付与核验**：按其 **§5 交付物与可核验方式** 逐件核对，locator 一律 `M#/p#`，逐字引文可回原文。
- **门控**：交付前逐项通过其 **§7 防扣分自查表（C01–C20）**；任一项未过则修正后重出，
  `status` 不得静默提升。

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its `output_contract`
object; `case_id` is passed through unchanged. When the case supplies its own `output_contract`, those
keys are used instead and each is filled the same way (an artifact-like key resolves to the written
file, any other key gets a real derived value).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "ok | partial | insufficient_evidence | input_error",
    "deliverable": "decision_brief.md",
    "evidence_map": "evidence_index.jsonl",
    "change_log": "change_log.json",
    "coverage": "coverage.json"
  }
}
```

## 1. Draft schema (JSON, optional but expected)

The Agent writes `/app/work/draft.json`; the engine only reads it. Merge the material's field
dictionary with your own judgement, then run `check` before `build` — the engine refuses the
`E_*` conflicts it is told to catch (a `go` gate over an `unsupported` assumption, a `covered` verdict
with no `covered_by`, a `novel` verdict with no boundary, an overall verdict stronger than the weakest
gate) and reports them instead of publishing them.

```json
{
  "case_id": "",
  "question": {"problem_statement": "", "object": "", "variables": [], "baseline": "", "expected": "", "falsification": []},
  "search_protocol": {"queries": [], "windows": "", "inclusion": [], "exclusion": [], "screened": 0},
  "gates": [{"gate_id": "G1", "verdict": "conditional", "conditions": [], "evidence_ids": [], "rationale": ""}],
  "matrix": [], "novelty": [], "assumptions": [], "claims": [], "conflicts": [],
  "research_gap": {"statement": "", "scope": "", "basis": [], "global_claim": false},
  "decision": {"overall": "conditional", "summary": "", "conditions": [], "next_validation": []},
  "change_log": []
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete `result.json`,
and exits 0:


见文首「单命令入口（评测入口）」——同一条命令，评测环境只跑这一条也能过。

## 3. agent-first 增强路径（可选，质量更高）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M#/p# 定位符读材料，按 §1 填 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints every material line with its `M#/p#` locator; `check` prints the grounded gate count,
the verdict rate and the `E_*` codes still open; `compare` writes a base-vs-skill contrast to
`/app/work/compare_report.json`.

## 4. Pipeline

1. Index every file under `/input` with its kind, size and parse status (`parsed` / `skipped` /
   `empty-file` / `placeholder-only` / `parse_error` / `unparsed-binary`).
2. Read the case, then extract the rules from each parsed material: the five gates and their
   deliverable mapping, the `verdict` thresholds, the `E_*` / `W_*` codes, the controlled
   vocabularies, the vague-phrase list, the evidence-matching modes, the number units, the object-table
   reconciliation steps, the rubric map and the out-of-scope boundaries.
3. Build the source/record object table: aliases fold onto their `M#` id, records sharing a content
   hash are marked `duplicate_of`, and `retract|预印本|修订版`-style tags are kept — an unresolved
   record is listed, never guessed onto a source.
4. Ground every rule and every draft quote: the quote must be found verbatim at its locator
   (`exact` / `despaced`); otherwise it is rejected with the reason and only appears in
   `uncertainty.json` and appendix A.
5. Score G1–G5 against the extracted thresholds, fold in the Agent's draft verdicts, and run the
   structural checks — the engine does not make value judgements, it catches self-contradiction.
6. Write every artifact, the coverage counts, the change log and `result.json`.

The code is split by responsibility across four deterministic files so no single file exceeds 30KB:
`scripts/main.py` (CLI + orchestration), `scripts/kglib.py` (scan / material resolution / gates /
conflicts / evidence / contract echo), `scripts/extract.py` (section-by-section rule extraction with
locators) and `scripts/render.py` (artifact writers and the pipeline). Pure standard library, offline.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, counts, decision, sources, uncertainties, change_records |
| `decision_brief.md` | the judgement: four deliverables ↔ five gates, per-gate verdict with its threshold, matrix, assumptions, conflicts, scoped gap, overall verdict, appendices A–C |
| `gate_scorecard.json` | G1–G5 with verdict, conditions, evidence ids, residual risks, pivot, and the rule/threshold quotes behind each row |
| `prior_art_alignment_matrix.csv` | the long table: one claim × one comparison row, with `材料未给` where the material is silent |
| `assumption_register.json` | feasibility preconditions with `source`/`assumed`/`unsupported` state and kill criteria |
| `evidence_index.jsonl` | one line per quote: locator, verbatim quote, match mode, verified flag |
| `conflicts.json` | contrary evidence with both sides quoted, plus the scope statement when none was found |
| `coverage.json` | the six coverage checks, counts and verdict tally |
| `self_check.json` | artifact presence, contract echo, evidence rate and open `E_*` codes |
| `change_log.json` | the ordered build steps, including the verdict downgrades |
| `search_log.json` | the deterministic query/probe log with hit locations and the screening standard |
| `uncertainty.json` | what could not be grounded, the unparsed records and the undetermined areas |
| `gain_evidence.json` | this run's own measurable gain, with the baseline stated as simulated |
| `run_log.txt` | per-material parse status and the stage counts |
| `evidence/sources_snapshot.json` | the object table with aliases, duplicates and version tags |

## 6. Degradation rules

- No material can be parsed as text → `status=insufficient_evidence`; every artifact carries a
  structured no-data record naming the searched locations; exit 0.
- A draft quote that is not verbatim at its locator → rejected with the reason, listed in
  `uncertainty.json`, never counted as verified evidence.
- A gate citing a claim with no verified evidence → `E_GATE_NOEVID`, reported rather than published.
- Contradictory evidence → both sides kept with their locators; no conflict found → a scoped
  `no_contrary_found` statement, which is not the same as "no conflict exists".
- Empty / binary / placeholder-only file → recorded with its parse status, never quoted.
- No network, no third-party package, no invented literature, numbers or legal status.

## 7. 交付前自查清单

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无占位符。
- [ ] 15 件产物齐全且非空，`evidence_index.jsonl` 每条带 `M#/p#` 与逐字引文。
- [ ] 五门 G1–G5 逐门有 verdict、conditions、证据与阈值原话，总体判定不高于最弱一门。
- [ ] 冲突两侧原话、`no_contrary_found` 的范围限定、`uncertainty.json` 的未命中项均已登记。
- [ ] 空 / 坏 / 占位输入走 `insufficient_evidence` 且 exit 0；rich 与 boundary 四组均 PASS。
- [ ] **专家检查表逐项通过**：references/expert_playbook.md §7 全项通过；未过则修正后重出，不得静默提升 status。
- [ ] 纯标准库、离线、确定性；包内无 `__pycache__` / `*.pyc`，文件数与字节数在上限内。
