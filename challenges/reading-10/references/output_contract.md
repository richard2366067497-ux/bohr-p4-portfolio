# result.json 契约与字段规则

本文件是 `result.json` 的字段字典：信封字段、`output_contract` 回填规则、状态枚举。
`SKILL.md` §5 是摘要，冲突时以本文件为准，脚本行为以 `scripts/build.py` 为准。

## 1. 顶层结构

```json
{
  "case_id": "<case.json 的 case_id，原样>",
  "status": "ok | partial | insufficient_evidence | input_error",

  "<output_contract 的每个字段名>": "...",

  "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
  "degradations": [], "changes": [], "runtime": {},

  "summary": "...", "generated_at": "...", "scope_text": "...", "scope": {},
  "paper": {}, "materials": [], "coverage": {}, "environment": {},
  "tolerance_plan": {}, "tolerance": [], "params": [], "plan": [],
  "runs": [], "comparison": [], "attributions": [], "claims": [], "evidence": [],
  "verdict": {}, "checklist": [], "gaps": [], "counts": {}, "artifacts": {}
}
```

## 2. `output_contract` 回填（硬性）

1. **字段名一个不改、一个不漏**：契约是 `{"a": ...}` 就产出 `{"a": ...}`；嵌套对象逐层同名保留。
2. 契约是字段清单 `[{"name": "comparison_table", "type": "array"}]` 时，按 `name` 展开为顶层键。
3. 值按语义映射（见 §3）；映射不到 → 保留 `null`（列表型保留 `[]`），并写
   `degradations: ["contract_field_unmapped:<字段名>"]`。
4. 信封字段永远存在，且不会被契约字段覆盖（同名时信封字段优先）。
5. 契约字段的值与产物同源：`comparison_table` 与 `comparison.csv` 同数据，
   `reproduction_record` 与 `repro_record.json` 同为完整记录。

## 3. 语义映射表（键名 → 载荷）

| 契约键名里含 | 填入 |
|---|---|
| `toler` / `容差` / `band` | `tolerance`（事前容差表，含 resolve 后的 abs/rel） |
| `attribut` / `归因` / `cause` | `attributions` |
| `compar` / `diff` / `对比` / `差异` / `vs` | `comparison`（逐 run × 逐指标的行） |
| `repro` / `复现` / `replicat` | `reproduction_record`（完整记录） |
| `environment` / `环境` / `snapshot` | `environment` |
| `param` / `参数` / `hyper` / `超参` | `params` |
| `run` / `exec` / `运行` / `log` / `command` | `runs` |
| `checklist` / `material` / `source` / `来源` / `licen` / `dependency` | `checklist` |
| `evid` / `证据` / `quote` / `locator` / `citation` | `evidence` |
| `verdict` / `conclusion` / `结论` / `tier` / `grade` | `verdict` |
| `uncert` / `不确定` / `unknown` / `ambigu` | `uncertainty` |
| `pending` / `human` / `人工` / `handover` | `pending_human` |
| `gap` / `missing` / `缺失` / `缺口` | `gaps` |
| `plan` / `step` / `流程` / `procedure` | `plan` |
| `claim` / `finding` / `结论点` | `claims` |
| `report` / `报告` / `markdown` / `narrative` | `report_markdown`（`repro_report.md` 全文） |
| `csv` / `table` / `表` | `comparison_csv`（路径） |
| `summary` / `摘要` / `answer` / `答案` / `abstract` | `summary`（一句话结论） |
| `status` / `状态` | `status` |

匹配按下表从上到下取第一条命中的规则，所以 `tolerance` 先于 `table`、`attribution` 先于 `comparison`。
新增契约字段名且语义不明时，**不要猜**：留 `null` + `contract_field_unmapped`，并在
`uncertainty` 写一句"契约字段 X 语义未识别，已留空"。

## 4. `status` 枚举

| 值 | 含义 | 典型触发 |
|---|---|---|
| `ok` | 闭环完整：材料、环境、参数、运行、对比、归因、结论都在，无缺口 | 全部方法跑通、有报告值、材料类齐全 |
| `partial` | 有交付但存在显式缺口 | 无工作稿、某份方法失败、某材料类缺失或需申请、PDF 无文本层、容差被放宽 |
| `insufficient_evidence` | 没有可判定的证据 | 无候选方法、所有方法失败、无任何报告值 |
| `input_error` | 输入本身不可用 | `case.json` 缺失或坏 JSON、材料目录为空 |

`status` 与 `verdict.tier` 是两件事：`status` 描述**交付完整性**，`tier` 描述**复现结论**。
可以出现 `status=partial` + `tier=partially_reproduced`（最常见），
但不应出现 `status=ok` 而 `gaps` 非空。

## 5. 字段细节

| 字段 | 形态 | 说明 |
|---|---|---|
| `sources[]` | `{id, rel, kind, bytes, sha1}` | 每个输入材料一行，`sha1` 前 12 位，供他人核对同一份材料 |
| `materials[]` | `{id, rel, path, kind, bytes, units, quality, notes, sha1}` | 索引记录；`quality` ∈ `ok/low_text/unparsed/no_ocr/unsupported/skipped` |
| `coverage{}` | `{code,data,param,dependency,license,eval_script}` → `{found, objects, requested, status}` | 六类必需对象；`status` ∈ `available/needs_request/missing` |
| `environment{}` | `{python, platform, packages, seed, hardware_note, source}` | `source` ∈ `draft+host` / `host_only` |
| `tolerance_plan{}` | `{declared_step, declared_at, before_any_run, source, entries, plan_sha256, materialized}` | 见 `method_rules.md` §2 |
| `tolerance[]` | `entry + {metric}` | 摊平后的容差表，便于 `output_contract` 直接吃 |
| `params[]` | `{name, value, class, source, locator, quote, conflict_note, verified, check}` | `class` ∈ `paper/code_inferred/self_set` |
| `runs[]` | `{run_id, name, argv, cwd, started_at, exit_code, duration_ms, metrics, metric_evidence, stdout_tail, stderr_tail, log_path, source_sha1, source_file, tolerance_plan_sha256, error}` | 一次真实执行一行；`log_path` 指向 `output/runs/<run>.log` |
| `comparison[]` | `{metric, run, observed, observed_raw, reported, abs_tol, rel_tol, tolerance_basis, abs_dev, rel_dev, within_tolerance, verdict, reported_locator, reported_quote, reported_basis, scale_adjusted, metric_evidence, run_log}` | 一个 run × 一个指标一行 |
| `attributions[]` | `{metric, cause, confidence, evidence, detail}` | `cause` 见 `method_rules.md` §4 |
| `claims[]` | `{id, kind, text, confidence, evidence[]}` | `evidence` 每条含 `{source_id, locator, quote, verified, check}` |
| `evidence[]` | 同上 + `claim` | 只收 `verified=true` 的条目 |
| `verdict{}` | `{tier, rationale, caps, missing_objects, agent_tier, verdict_conflict, rule}` | 见 `method_rules.md` §5 |
| `checklist[]` | 材料/对象清单 | `{item, kind, status, locator, sha1, note}` |
| `counts{}` | 计数 | `materials/runs/runs_ok/comparison_rows/in_tolerance/out_of_tolerance/no_reported_value/evidence_verified/params/attributions` |
| `artifacts{}` | 路径 | 全部产物绝对路径 |
| `changes[]` | `{at, change}` | 变更记录：init 锁定容差、build 前摊平容差、build 执行与定稿 |
| `runtime{}` | `{started_at, finished_at, elapsed_s, budget_s, deadline_hit, python, platform}` | 运行信息，不写分数 |

## 6. 最小合法样例（截断）

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "summary": "verdict partially_reproduced; 2 run(s), 4 comparison row(s) (in 1 / out 3 / n.a. 0)",
  "reproduction_record": {"verdict": {"tier": "partially_reproduced"}},
  "comparison_table": [{"metric": "mae", "run": "method_a", "observed": 0.187,
                        "reported": 0.184, "abs_tol": 0.00092, "rel_tol": 0.02,
                        "within_tolerance": true, "verdict": "in_tolerance"}],
  "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
  "degradations": [], "changes": [], "runtime": {}
}
```

## 7. 不要做的事

- 不要为了"看起来完整"把 `null` 换成 `0`、`"unknown"`、`"N/A"`。
- 不要把 `verdict` 写成 `reproduced` 来美化结论（会被封顶规则覆盖并记 `verdict_conflict`）。
- 不要把 `comparison.csv` 的手抄数值当成 `observed`：`observed` 必须来自 runs 的 stdout。
- 不要漏掉 `case_id`：它是平台把结果对回案例的唯一键。
