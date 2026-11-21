---
name: plan-feasibility-review
description: Turn a batch of experiment material into a reviewable, source-grounded feasibility review — the seven categories (equipment, material, time, sample, ethics and safety, parameter ranges, risks and exceptions) checked item by item against versioned candidate plans, with locator and verbatim quote, a line-level duration and cost ledger with self-checks, the four-state resource mapping, blocked categories, and the confirmations that must be closed before approval. Use when a task asks whether a plan can actually be run, what a plan did not declare, which version is feasible, or what must be confirmed first.
version: 2.6.0
---

# plan-feasibility-review

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§2 求解框架 Step 1–5** 推进——材料解析与结构化提取 → 七类约束逐项审查 →
  交叉核验与冲突检测 → 结论综合与条件清单 → 输出组装与自核验；前一步未冻结不进入下一步。
- **量化口径**：按其 **§3** 计算时间（`T_total = Σ(T_setup_i + T_run_i×N_batch_i + T_wait_i + T_QC_i) + T_procurement + T_approval`，
  `N_batch = ceil(样本量/单批)`）与样本量（功效法 `n = 2((Z_{α/2}+Z_β)/δ)²σ²`）；设备匹配按
  §3.3（量程 ×1.2 / 精度）判 PASS/CONDITIONAL/FAIL；风险按 §3.4 分级、伦理按其 §3.5 周期表。
- **成本/时长口径**：时长与成本**逐行**写出（步骤行之和 = 单次时长；成本行之和 = 单次成本），
  每行标注来源（设备手册/SOP/组织方约束），可独立复算。
- **证据定位**：按其 **§5 定位符格式**给每条判断加 locator（`[方案 section X.Y, 表N, 行R]` /
  `[资源清单 equipment.row.field]` / `[组织方约束 constraints.key]`），避免 F6/F7 类失分。
- **门控**：交付前逐项通过其 **§6 专家检查表（S01–S18）**；`MISSING_INFO` 不得默认为 PASS，
  所有 `CONFLICT` 必须在结论中被显式处理。

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, the sample below
applies:

```json
{"output_contract": {"case": "string", "case_id": "string", "plan": "string",
 "equipment": "string", "material": "string", "booking": "string", "budget": "string",
 "domains": "string", "approval": "string", "source": "string", "task": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is written
into any artifact.

## 1. 单命令（one-shot，评测入口，无 draft 时执行）

**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan the input → index the material with locators → pull
resource rows, price and booking contracts, finite parameter domains and stated bounds → build
the seven-category verdict for every candidate version → derive the serial duration and the
per-run cost line by line → rank the versions → collect the confirmations and degradations →
render the artifacts → fill the contract → sweep empty-value tokens. It works with no draft
present, prints a one-line summary and exits 0. Empty input, malformed JSON and a missing
`case.json` still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
# the agent reads the material and writes /app/work/draft.json (chosen_version + recommended values)
python3 scripts/main.py check       # map the draft's recommended values onto the extracted domains and bounds
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to confirm
every proposed setting sits inside its declared domain, then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case", "chosen_version": "the version under review",
 "recommended": {"parameter name": 120},
 "resource_notes": ["free text note about a resource that the material leaves implicit"],
 "constraints_added": ["free text rule the agent read from the prose"],
 "uncertainties": ["what could not be read from the material"],
 "change_log": ["what the agent changed and why"]}
```

`check` maps each `recommended` key onto a declared parameter domain (exact key first, then a
unique substring match), reports `inside_domain` per entry plus any key that maps to nothing, and
reports the constraint violations of the mapped values. Out-of-range settings must be fixed
before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `feasibility_review.md` | status and reason, the seven-category table per version, the line-level duration and cost, the domains and bounds each with locator and quote, the risks, the confirmations, the arithmetic ledger and the degradations |
| `checks.json` | the per-version × per-category state ledger, the ranked order and the winner, the parameter domains with evidence, the rule index and the evidence hit-rate |
| `estimate.json` | the duration and cost formula, the per-version estimate with its step lines and cost lines, the budget, the evidence for the ceiling and every arithmetic self-check |
| `risks.json` | the risk items per version, every stated bound with its evidence, and the unavailable resources |
| `confirmations.json` | the confirmations that must be closed before approval, the approval items and the budget state |
| `evidence.json` | every extracted item with source_id, locator, verbatim quote and a hit-rate |
| `version_diff.md` | one row per version (settings, blocked count, per-run cost, budget share, feasible, locator) and the winner |
| `result.json` | the contract keys plus resources, domains, constraints, versions, the arithmetic checks, the confirmations, limits, uncertainties, sources, change records and artifacts |

**专家检查表逐项通过**：以上每件交付物在写入前，都要通过 `references/expert_playbook.md` §6
的专家检查表（S01–S18）逐项核验——每条判断带 locator（S01）、`MISSING_INFO` 不当作 PASS（S02/S16）、
所有 `CONFLICT` 被显式处理（S03）、时长按步骤拆分且每参数有来源（S04/S05）、样本量有统计依据（S06）、
设备区分四态（S07）、风险含触发/概率/降级（S08）、伦理含审批类型/材料/周期（S09）、参数给具体区间
（S10）、对照组给类型/样本量/功效（S11）、未声明信息显式标注（S12）、有条件可行时条件清单完整（S13）、
单位统一（S17）、方案内部矛盾被标记（S18）。任一项不通过则修正后重出。

## 5. Seven categories

Every candidate version is reviewed across equipment, material, time, sample, ethics and safety,
parameter range, and risks and exceptions. Each category resolves to one of `ready`,
`conditional`, `blocked` or `unknown`, and every `blocked` is quoted back to the material line
that produced it. Equipment, material and booking rows map by the four-state wording the material
uses (already in place / can be outsourced / must be procured / unavailable). A category the
material does not carry is reported as not-declared — never silently treated as satisfied.

## 6. Arithmetic and revision

Duration is the sum of serial step minutes plus one maximum per parallel group; cost is
`amount × unit price` per priced item (consumables plus booking days), summed to a per-run cost.
Both are written out line by line and re-checked (step-line sum vs duration, cost-line total vs
per-run cost, budget ceiling, version count, winner feasibility). A version is feasible only when
no category is blocked and the per-run cost stays inside the declared ceiling. Versions are ranked
by feasibility, then blocked-category count, then per-run cost.

## 7. Boundaries

Standard library only, offline, no third-party dependency. No significance testing. Missing
budget, domain, sample plan or approval is preserved as an open item with a reason — never
guessed. Nothing is fetched or installed.

## 8. 自检（selfcheck）与专家门控

`selfcheck` verifies the artifact set exists and the contract echo is non-empty; the run also
performs the arithmetic self-checks (step-line sum vs duration, cost-line total vs per-run cost,
budget ceiling, version count, winner feasibility). On top of that, **专家检查表逐项通过** is a
required gate: every deliverable must pass `references/expert_playbook.md` §6 (S01–S18) before it
is considered done, and `selfcheck` reports the expert-checklist status next to the file/contract
status. A run whose checklist still has an open item is reported `partial` with the item in
`confirmations` — never silently upgraded to `answered`.
