---
name: experiment-interpretation-dossier
description: Turn a batch of experimental readout material into a reviewable interpretation dossier — the five checkable conclusions (trend, anomaly point, candidate causes, recheck steps, next-round experiment) each tied to a locator and a verbatim quote, the screening rules R1-R9, the unit dictionary and the threshold constants indexed from the material, a definitional statistic ledger recomputed on a fixed fixture, and the anomalies bound to their sample, batch, channel or estimator-fold. Use when a task asks what a batch of readouts shows, which point is genuinely off and by how much, what may have caused it, what to recheck, or what to run next.
version: 2.6.0
---

# experiment-interpretation-dossier

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§2 求解框架（S1–S6）与门控**推进——材料解析 → 任务拆解 → 方案设计 → 数据解释
  → 风险审查 → 组装交付；前一步未冻结不进入下一步（每个数据文件标"已解析/失败/部分解析"，无对照
  标"置信度降级"）。
- **统计口径**：按其 **§3 逐条复算**——趋势按线性斜率 / R² / 拐点 / 平台期 / 偏离幅度（§3.1）；
  异常按 **§3.2 阈值体系**（Z-score \|Z\|>3.0、修正 Z `0.6745*(x-median)/MAD` 的 \|Z_MAD\|>3.5、
  IQR 1.5×/3× 栅栏、Grubbs）；重复数按 **§3.3 功效** `n=[(z_{α/2}+z_β)·σ/δ]²`；写进
  `recompute.json` 并在固定夹具上自检。
- **防幻觉与归因**：五段结论（趋势/异常/原因/复核/后续）逐条挂 locator 与逐字引文；原因候选按
  **§3.4 证据强度 A/B/C** 分级并写支持证据 + 排除证据；按 **§4 领域陷阱与单位**排雷（AU 量程、
  pH 对数标度、°C→K、R²≠因果、n=3 功效不足、precision≠accuracy），不编造 DOI 或数据。
- **风险与确认**：按手册标注 `[需专家确认]`，安全/伦理/设备/专家四维不缺项。
- **门控**：交付前逐项通过其 **§5 自查表（SC-01…SC-20）**，并用其 **§7 专家注意点**逐条排雷。

## 0. result.json contract

`result.json` carries every key of the case's `output_contract`, both at the top level and
inside a nested `output_contract` object. When the case does not declare one, the sample
below applies:

```json
{"output_contract": {"id": "string", "case_id": "string", "time_course": "string",
 "deviation": "string", "mechanism": "string", "dataset": "string", "parameter": "string",
 "limitation": "string", "answered": "string", "partial": "string",
 "insufficient_evidence": "string", "input_error": "string"}}
```

`case_id` is passed through unchanged. `status` is one of `answered`, `partial`,
`insufficient_evidence`, `input_error`. No key is ever empty and no empty-value token is
written into any artifact.

## 1. 单命令（one-shot，评测入口）

```
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

One command runs the whole pipeline: scan every input file → index the screening rules, the
unit dictionary and the threshold constants with a locator and a verbatim quote → recompute the
screening definitions on a fixed five-value fixture → screen any numeric column with the
modified-z, IQR-fence, duplicate and saturation rules → organise the five conclusions → render
the artifacts → fill the contract → sweep empty-value tokens. It works with no draft present,
prints a one-line summary and exits 0. Empty input, malformed JSON and a missing `case.json`
still produce a legal `result.json` and exit 0.

## 2. 五命令（agent 深读，质量更高）

```
python3 scripts/main.py init        # index the material, write a partial result.json + work/draft.skeleton.json
python3 scripts/main.py show        # print material paragraphs with locators (--grep, --mat)
# the agent reads the material and writes /app/work/draft.json (trends, dossiers, causes, result_fields)
python3 scripts/main.py check       # verify each dossier's rule_id exists and every judged dossier carries a basis
python3 scripts/main.py build       # render every artifact and the final result.json
python3 scripts/main.py selfcheck   # verify the artifacts exist and the contract echo is non-empty
```

The agent reads the material with `show`, writes `/app/work/draft.json`, runs `check` to confirm
every dossier points at an indexed rule and every judged dossier carries an attribution basis,
then `build` and `selfcheck`.

## 3. draft schema (`/app/work/draft.json`)

```json
{"case_id": "same id as the case",
 "task_understanding": "the checkable question this case answers",
 "dataset_note": "which artefact is the original, which is the summary, which is the control",
 "trends": [{"trend_id": "TR-01", "scope": "metric/group/interval",
             "statement": "direction, breakpoint or plateau, departure with its unit",
             "method": "interval, control and fitting rule", "locator": "f#L12",
             "quote": "verbatim source line", "strength": "A"}],
 "dossiers": [{"id": "A-001", "anomaly_type": "outlier", "target": "which sample/batch/channel/fold",
               "locator": "f#L20", "observed": "value with unit",
               "expected_or_rule": "rule and cited threshold", "rule_id": "R1",
               "severity": "high", "judged": true, "verdict": "confirmed",
               "attribution": "data_quality", "attribution_basis": "support plus exclusion",
               "evidence_quote": "verbatim line", "excluded_alternatives": ["what was ruled out"],
               "do_not_conclude": ["what must not be read into this"],
               "recheck_actions": ["object + action + decision condition"],
               "next_experiment": "the next change", "strength": "A"}],
 "causes": [{"candidate": "candidate cause", "support": "supporting evidence",
             "exclusion": "excluding evidence", "strength": "B"}],
 "uncertainties": ["what could not be read from the material"],
 "confirmations": ["items that need an expert or equipment owner"],
 "next_steps": ["work-draft level next experiment"],
 "result_fields": {"<an output_contract key>": "the value for that key"}}
```

`check` reports, per dossier, whether the referenced `rule_id` exists in the indexed rule table
and whether a `judged` dossier carries a non-empty `attribution_basis`. A judged dossier without
a basis must be fixed before `build`.

## 4. What each artifact holds

| artifact | contents |
|-|-|
| `interpretation.md` | the eight sections: inventory, the five conclusions (trend, anomaly, causes, recheck, next), uncertainties and method |
| `dossier_index.json` | one entry per anomaly with its target, severity, verdict, attribution, strength, locator and its per-dossier `dossiers/anomaly-<id>.md` file, plus the per-entry issues |
| `inventory.json` | the per-file inventory with every table object, its columns and size, the numeric series and the unit groups |
| `recompute.json` | the fixed fixture, the recomputed definitions with their expected values, the per-series statistics, the rule candidates and the consistency checks |
| `thresholds.json` | every threshold constant with its locator, its quote and the conflicting constants kept side by side |
| `evidence.json` | every indexed item with source_id, locator, verbatim quote and a hit-rate |
| `uncertainties.json` | the uncertainty items, the confirmations that need a human and the recorded gaps |
| `method_notes.md` | parsing, statistics, criteria and the re-run command |
| `result.json` | the contract keys plus inventory, rule index, thresholds, units, the recomputed definitions, the dossiers, metrics, limits, uncertainties, sources, change records and artifacts |

## 5. The five checkable conclusions

Trend, anomaly point, candidate causes, recheck steps and next-round experiment. A trend is a
direction plus breakpoint or plateau plus a departure with a unit, never a restatement of the
readings. An anomaly is bound to the sample, batch, channel, well, time point or estimator-fold
it actually belongs to, with its severity and the rule that fired. Candidate causes are ranked
by evidence strength with the support and the exclusion written out, and the four attribution
values are `data_quality`, `method_artifact`, `source_ambiguity` and `undetermined`. A recheck
step names the object, the action and the decision condition; a step such as "check the data
quality" is not accepted. A next-round experiment follows from the cause candidates and the
evidence gaps.

## 6. Rules and statistics

The screening rules R1-R9 (modified z, IQR fence, recomputation deviation, calibration
back-calculation, unit inconsistency, duplicate rows, incomplete series, threshold conflict,
physical bounds, saturation plateau, cross-source inconsistency) are indexed from the material
with their trigger and their default severity. The statistics are the ones the material defines:
arithmetic mean, sample standard deviation with n-1, interpolated median, MAD, modified z
`0.6745*(x-median)/MAD`, the IQR fence, the least-squares fit and the relative deviation. Rules
only find a disagreement with a distribution or with another source; they never decide that it
is a fault. Conflicting units or thresholds are kept side by side and never silently reduced to
one value.

## 7. Boundaries

Standard library only, offline, no third-party dependency. No fabricated wet measurements, no
fabricated causes and no fabricated replicate counts. A structure the material does not carry is
reported as searched-but-absent with its searched locations. Nothing is fetched or installed.

## 8. 交付前自检清单

- [ ] 五段结论（趋势/异常/原因/复核/后续）逐条写出，每条带 `source_id` + `locator` + 逐字引文
- [ ] 每条趋势含方向/幅度/区间/拐点（非复述读数）；每异常有量化方法与具体阈值（Z/MAD/IQR/Grubbs）
- [ ] 每异常绑定具体维度（样本/批次/通道/孔位/时间点），并声明严重度与触发规则
- [ ] 原因候选 ≥2 个或说明为何仅 1 个，各含支持证据、排除证据与 A/B/C 强度；复核步骤具体可执行
- [ ] 复算口径与固定夹具自检一致（修正 z / IQR 栅栏 / 相对偏差）；单位一致、数值带单位
- [ ] 缺失/不适用内容显式声明，未编造数据、DOI 或结论；`case_id` 原样透传；契约键 12/12 非空
- [ ] **专家检查表逐项通过**：交付前逐项通过 `references/expert_playbook.md` §5 的 SC-01…SC-20
  自查表，并用 §7 专家注意点逐条排雷；任一项未通过则修正后重出，不得静默提升 status
- [ ] 纯标准库、离线、无时钟读取；安全/伦理/设备/专家确认项标 `[需专家确认]`

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（S1–S6 六步法/统计口径 §3/陷阱与单位 §4/自查表 SC-01…SC-20/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + notes.md + readout.csv），评审可直接复跑
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
