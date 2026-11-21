---
name: plan-forge-experiment
description: Turn a batch of experiment material into a reviewable, versioned experiment plan — six required elements (hypothesis and variables, controls, equipment and materials, time and cost, parameter ranges, risks and exceptions) extracted with locator and verbatim quote, three versioned candidate plans, six validation rules, an arithmetic ledger with self-checks, a rule-based revision pass, and a reproducible recommended setting with a tolerance band. Use when a task asks for an experiment plan, a protocol design, a candidate comparison, a cost or booking check, or a plan that must be derived item by item from the supplied material.
version: 2.6.0
---

# plan-forge-experiment

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§2 六步法（S1–S6）** 推进——假设与变量 → 变量操作定义 → 对照矩阵 → 步骤与排程
  → 参数规格 → 风险登记；前一步未冻结不进入下一步，并遵守其门控规则。
- **量化口径**：按其 **§3** 逐条复算——样本量 `n = 2×((z_{α/2}+z_β)/d)²`、时间用关键路径法
  （并行取 max，含 15% 缓冲）、预算 `单价×用量×(1+损耗)` + 机时 + 人工，写进 `arithmetic_ledger.json`
  并逐行自检。
- **判读标准**：按其 **§3.4 风险等级**（H>30% / M 5–30% / L<5%）与参数允许偏差（如恒温 ±1 °C、
  马弗炉 ±3 °C、时间 ±5%）给定判据、止损点与替代路径。
- **陷阱与单位**：按其 **§4 领域陷阱与单位**逐条排雷（SEM/TEM、XRD 晶相、ppm、rpm 与 RCF、sccm 与
  mL/min），所有数值标注来源类型（设备手册 > 文献 DOI > 预实验），不编造 DOI。
- **门控**：交付前逐项通过其 **§5 自查表（C01–C17）**，并用其 **§7 专家注意点**逐条排雷。

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, this package
default applies:

```json
{"output_contract": {"case_id": "string", "status": "string", "plan_report": "string",
 "plan_revised": "string", "validation_report": "string", "arithmetic_ledger": "string",
 "evidence": "string", "uncertainties": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is
written into any artifact.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan the input → extract the six elements with locator
and quote → pull domains, constraints, resources, plans, controls, risks and confirmations →
generate three versioned candidates when none were supplied → validate each against the six
rules → revise the failures → tot up the arithmetic ledger with self-checks → render the
artifacts → fill the contract → sweep empty-value tokens. It works with no draft present,
prints a one-line summary and exits 0. Empty input, malformed JSON and a missing `case.json`
still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
python3 scripts/main.py check       # map the draft's recommended settings onto the finite domains and flag anything out of range
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to
confirm every proposed setting sits inside its declared domain, then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case", "objective_weights": {"metric name": 0.5},
 "recommended": {"parameter name": 120},
 "constraints_added": ["free text rule the agent read from the prose"],
 "resource_notes": ["free text note about equipment or booking"],
 "uncertainties": ["what could not be read from the material"],
 "change_log": ["what the agent changed and why"],
 "hypothesis": "the testable statement the run is meant to settle",
 "control_design": "the control or baseline arm"}
```

`check` maps each `recommended` key onto a declared parameter domain (exact key first, then a
unique substring match) and reports `inside_domain` per entry plus any key that maps to
nothing. Out-of-range or unmapped settings must be fixed before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `plan_report.md` | status and reason, the six elements each with locator and quote, the recommendation with its tolerance band, every arithmetic check, limits and sources |
| `plan_revised.json` | candidate versions with their revisions (`from → to` plus the reason), the winner, the revision rules |
| `validation_report.json` | the six rules, per-plan violations/warnings/notes, before-revision state, totals |
| `arithmetic_ledger.json` | per version: formula, cost lines, duration lines, the input rows, and each self-check |
| `evidence.json` | every extracted item with source_id, locator, verbatim quote and a hit-rate |
| `version_diff.md` | one row per version (settings, cost, duration, violations, feasible, revised) and the locators |
| `reproduce.md` | the entry point, materials read, the recommended settings, ordered steps and the decision rules |
| `result.json` | the contract keys plus domains, constraints, resources, candidate versions, arithmetic, validation totals, evidence stats, limits, uncertainties, sources, change records and artifacts |

## 5. Six required elements

Every plan must carry all six, each traceable to the material: hypothesis and variables,
controls, equipment and materials, time and cost, parameter ranges, risks and exceptions. An
element that the material does not carry is reported as absent or proposed with the reason —
it is never replaced by an invented list.

## 6. Six validation rules

`param_domain` (inside the finite domain and on the step grid), `constraint_*` (stated le/ge/
lt/gt/eq/ne bounds and mutex pairs), `booking` (facilities reserved inside a declared window),
`budget` (total cost within the ceiling), `quantity` (consumption within stock), `control` (a
control arm exists), `unit` (each parameter and priced item has a unit).

## 7. Arithmetic and revision

Cost is `amount × unit price` per item, summed to a per-run cost, then `× replicates` for the
total; duration is the sum of serial step minutes plus one maximum per parallel group. Both
are written out line by line and re-checked (line totals vs per-run cost, per-run × replicates
vs total, budget ceiling, calendar fit). A failing plan is repaired by rule: clamp to the
nearest legal grid point, satisfy the stated bound, trim usage to stock, cut replicates to
`floor(budget / per_run_cost)`, or add a flagged reference control. Every action is recorded.

## 8. Boundaries

Standard library only, offline, no third-party dependency. No significance testing; with few
history rows the model is reported as a hint alongside its sample count. Missing budget or
domain is preserved as an open rule with a reason, never guessed. Nothing is fetched or
installed.

## 9. 交付前自检清单

- [ ] 六个要素齐全，每个元素带 `source_id` + `locator` + 逐字引文，缺失项以 abstain 记录、绝不编造
- [ ] 三个版本候选均落在声明的有限参数域内且在 step 网格上
- [ ] 六条校验规则逐条执行，违反项已按规则修订并记录 `from → to` 与理由
- [ ] 算术台账逐行可复算（行和 = 单次成本，单次 × 重复 = 总成本，不超预算）
- [ ] 结论中每个数字可回指具体材料行；`case_id` 原样透传；契约键逐键非空
- [ ] **专家检查表逐项通过**：交付前逐项通过 `references/expert_playbook.md` §5 的 C01–C17
  自查表，并用 §7 专家注意点逐条排雷；任一项未通过则修正后重出，不得静默提升 status
- [ ] 无静默修改：所有数据变更均有记录与理由；纯标准库、离线、无时钟读取

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（六步法/量化口径/风险等级/陷阱与单位/自查表 C01–C17/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + params.json），评审可直接复跑
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
