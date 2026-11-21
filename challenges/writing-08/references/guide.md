# guide.md — 工作稿 schema、模板与边界

本文件是 `scripts/` 的参考资料：Agent 写 `${WORK}/draft.json` 的字段定义，以及脚本渲染章节稿的模板
口径。**不含预生成答案**，所有取值来自 `/input` 材料。判分口径、指标公式与检查表见
`references/expert_playbook.md`；契约键名与入口命令见 `SKILL.md`。

## 1 工作稿 draft.json（Agent 写入 ${WORK}/draft.json）

```yaml
case_id: 与输入一致
language: zh | en
task_understanding: {genre, audience, language, scope, notes}
headings: {scope: 1 任务与范围}    # 可选：覆盖默认标题
facts:                            # 逐字事实；进入正文前必须通过逐字校验
  - {fact_id: F1, statement: 事实表述, value: "12.5", unit: mg/L, source_id: S1,
     locator: materials/paper.md#L5, quote: 材料原句, status: verified|unverified}
steps:                            # 有序、可执行步骤
  - {sid: P1, name, inputs, operation, params, output, branch, source_ids: [S1], locator}
settings:                         # 硬件、环境、软件版本、种子、重复次数
  - {area, text, source_ids: [S1], locator}
parameters:
  - {param, value: "0.001", unit, scope, source_id: S1, locator, status: verified|conflict|unsourced, conflict: false}
datasets:
  - {name, version, size, preprocess, split, usage, source_ids: [S1]}
baselines:
  - {name, version, budget_match: true, metric, stat, comparable: true, source_ids: [S1]}
evaluation: [{text: 指标与聚合方式, source_ids: [S1]}]
repro:
  - {item, value, source_ids: [S1], locator}
limitations:                      # 适用范围 + 具体失效场景 + 材料依据
  - {scope, failure_case, reason, source_ids: [S1]}
gaps:
  - {gid: G1, kind: MISSING_MATERIAL|CONFLICT|STEPS_MISSING|DATASET_MISSING, desc, impact,
     owner: author, section, question}
conflicts:                        # 材料间冲突（并列保留，不静默统一）
  - {cid: C1, item, desc, sources: [{source_id: S1, locator, value}], impact, resolution}
result_fields: {}                 # 可选：直接覆盖某契约字段取值
```

覆盖状态：`covered`（条目齐备且均有来源）/ `partial`（部分有源或有缺口条目）/ `unsourced` /
`gap`（材料未提供，已登记缺口）/ `missing`（完全未涉及）。

## 2 参数表模板（parameter_ledger.csv）

`param,value,unit,scope,source_id,locator,source_kind,conflict_flag`

`conflict_flag`：`no` / `yes_resolved`（工作稿已裁决）/ `unresolved_detected(...)`（脚本检测到但工作稿
未裁决 → 正文并列标注，交作者确认）。

## 3 追问模板（gaps.md）

```
## G1 · MISSING_MATERIAL
- 缺什么：<缺口内容>
- 影响：<对复现/可比性的影响>
- 需谁确认：author
- 涉及小节：params
- 追问：<一句可直接发给作者的问题>
```

英文场景（`language: en`）渲染为 `Missing / Impact / Owner / Section / Follow-up`。

## 4 使用边界与失败模式

- 只处理 `/input` 下材料；不联网、不引入外部文献，不补造数值与引用。
- 引文必须在来源文件中逐字命中；未命中只能在台账标 `unverified`，不得进入正文。
- 材料缺失、不可读、超限（>400KB/文件）或二进制：登记 `degradations` + 缺口，继续运行。
- 空/坏输入：`status = input_error` 或 `insufficient_evidence`，仍写合法 `result.json`，退出码恒为 0，
  并在 `limits` / `uncertainties` 说明未确认部分。
