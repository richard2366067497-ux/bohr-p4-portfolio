# guide.md — 工作稿 schema、要素清单、模板与契约样例

本文件是 `scripts/` 的参考资料：Agent 写 `${WORK}/draft.json` 时的字段定义，以及脚本渲染
章节稿时使用的模板口径。**不含任何预生成答案**；所有取值都必须来自 `/input` 的材料。

## 1. 契约样例（result.json 逐键回填）

```json
{
  "case_id": "输入 case.json 的 case_id 原样回填",
  "output_contract": {
    "case_id": "输入 case.json 的 case_id 原样回填",
    "deliverable": "可编辑的方法与实验章节稿（manuscript.md）",
    "preserved_facts": "材料中的数字、单位、引用与来源逐条保留并可回溯",
    "evidence_map": "每条要素到材料来源定位（文件#行号）的映射",
    "change_log": "逐条修改动作、原因与需人工确认项"
  }
}
```

`case.json` 提供了 `output_contract` 时以它为准（键名原样）；未提供时使用上面的五个默认键。
五个键在 `result.json` 的**顶层**与**嵌套 `output_contract`** 中同时出现，且不得为 null/空壳。
未映射到的字段会写成 `{"field": "...", "carried_by": "result.json 顶层信封字段..."}`，
而不是 null。

## 2. 工作稿 draft.json（Agent 写入 ${WORK}/draft.json）

```yaml
case_id: 与输入一致
language: zh | en            # 缺省按 case.json/材料检测
task_understanding:
  genre: 方法与实验章节
  audience: 论文读者/复现者
  language: zh
  scope: 本节覆盖的材料范围（不含未读材料）
  notes: 需要读者知道的口径说明
headings: {scope: 1 任务与范围}   # 可选：覆盖默认标题
facts:                        # 逐字事实（进入正文前必须通过逐字校验）
  - fact_id: F1
    statement: 该事实的文字表述
    value: "12.5"
    unit: mg/L
    source_id: S1             # 与 init 台账一致
    locator: materials/paper.md#L5
    quote: 材料中的原始句子（逐字）
    status: verified | unverified
steps:                        # 有序、可执行的步骤序列
  - sid: P1
    name: 步骤名
    inputs: 输入
    operation: 操作
    params: 参数
    output: 输出
    branch: 分支/判断条件
    source_ids: [S1]
    locator: materials/paper.md#L3
settings:                     # 实验设置（训练/验证/评测、硬件、环境、种子、重复）
  - area: 硬件与环境
    text: 设置描述
    source_ids: [S1]
    locator: materials/config.yaml#L12
parameters:                   # 参数与来源
  - param: learning_rate
    value: "0.001"
    unit: ""
    scope: 作用对象
    source_id: S1
    locator: materials/config.yaml#L7
    status: verified | conflict | unsourced
    conflict: false
datasets:                     # 数据集与划分
  - name: 数据集名称
    version: v1
    size: 规模
    preprocess: 预处理
    split: 划分与随机方式
    usage: 各子集用途
    source_ids: [S1]
baselines:                    # 基线对照与可比性
  - name: 基线名称
    version: 版本
    budget_match: true | false
    metric: 指标口径
    stat: 统计方式
    comparable: true | false
    source_ids: [S1]
evaluation:                   # 指标与统计
  - text: 指标与聚合方式
    source_ids: [S1]
repro:                        # 复现清单
  - item: 代码版本
    value: abc1234
    source_ids: [S1]
    locator: materials/commit.txt#L1
limitations:                  # 限制条件：适用范围 + 具体失效场景 + 材料依据
  - scope: 适用范围
    failure_case: 失效场景
    reason: 材料依据
    source_ids: [S1]
gaps:                         # 缺口与待作者确认项
  - gid: G1
    kind: MISSING_MATERIAL | CONFLICT | STEPS_MISSING | DATASET_MISSING | ...
    desc: 缺什么
    impact: 影响
    owner: author | agent
    section: params
    question: 追问句
conflicts:                    # 材料间冲突（并列保留）
  - cid: C1
    item: learning_rate
    desc: 描述
    sources: [{source_id: S1, locator: config.yaml#L7, value: "0.001"}]
    impact: 正文无法给出唯一取值
    resolution: 待作者裁决，正文并列标注
result_fields: {}             # 可选：直接覆盖某契约字段的取值
```

## 3. 要素清单（六类，渲染与覆盖矩阵共用）

| 要素 | 覆盖要求 |
|---|---|
| 步骤 steps | 每步给输入、操作、参数、输出、判断条件；不把多步压成一句 |
| 实验设置 settings | 训练/验证/评测分开；硬件、软件版本、环境、随机种子、重复次数 |
| 参数 parameters | 名称、取值、单位、作用对象、来源；正文数值与台账一致 |
| 数据集 datasets | 名称、版本、规模、预处理、划分比例与随机方式、子集用途 |
| 基线 baselines | 基线对象与版本、是否同预算、指标口径、统计方式、可比性 |
| 复现与限制 repro/limitations | 代码版本、环境、命令、数据获取；限制指向具体失效场景 |

覆盖状态：`covered`（条目齐备且均有来源）/ `partial`（部分有源或有缺口条目）/
`unsourced` / `gap`（材料未提供，已登记缺口）/ `missing`（完全未涉及）。

## 4. 参数表模板（parameter_ledger.csv）

`param,value,unit,scope,source_id,locator,source_kind,conflict_flag`

`conflict_flag` 取值：`no` / `yes_resolved`（工作稿已裁决）/ `unresolved_detected(...)`
（脚本自动检测到但工作稿未裁决 → 正文并列标注，交作者确认）。

## 5. 追问模板（gaps.md）

```
## G1 · MISSING_MATERIAL
- 缺什么：<缺口内容>
- 影响：<对复现/可比性的影响>
- 需谁确认：author
- 涉及小节：params
- 追问：<一句可直接发给作者的问题>
```

英文场景（`language: en`）会渲染为 `Missing / Impact / Owner / Section / Follow-up`。

## 6. 使用边界与失败模式

- 只处理 `/input` 下的材料；不联网、不引入外部文献，不补造数值与引用。
- 引文必须在来源文件中逐字命中；未命中只能在台账标 `unverified`，不得进入正文。
- 材料缺失、不可读、超限（>400KB/文件）或二进制：登记 `degradations` + 缺口，继续运行。
- 空/坏输入：`status = input_error` 或 `insufficient_evidence`，仍写出合法 `result.json`，
  退出码恒为 0，并在 `limits` / `uncertainties` 中说明未确认部分。
