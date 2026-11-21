# Contract reference — multi-doc-comparison

冻结本 Skill 的契约语义、locator 方案与字段字典。实现改动不得改变这里的键名。

## 1. result.json 顶层键

| 键 | 类型 | 含义 |
|-|-|-|
| `case_id` | string | 逐字透传 `case.json.case_id`；缺失时退回输入目录名 |
| `status` | string | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `summary` | string | 一句话摘要（文档数、字段数、报告格子数、覆盖率、一致性裁决） |
| `output_contract` | object | `case.json.output_contract` 逐键回填，每个键给真实值 |
| `result` | object | 主载荷：问题、维度、字段、文档、矩阵预览、可比性、一致性、计数 |
| `claims` | array | 逐字段比较结论，每条带 `evidence[{source_document_id, quote, locator}]` |
| `sources` | array | 每份语料的 `file/kind/engine/locator_scheme` |
| `uncertainties` | array | 不确定项；同时镜像为 `uncertainty` |
| `change_records` | array | 处理步骤记录；同时镜像为 `changes` |
| `errors` | array | `error` 级缺陷（引文不在原文、重复格子、未知文档/字段…） |
| `degradations` | array | 抽取降级说明（PDF 无页码、低质量文本、重复副本…） |
| `pending_human` | array | 需要作者确认的事项 |
| `limits` | array | 非阻断性局限 |
| `counts` | object | `documents/fields/cells/reported/unreported/coverage/quote_pass_rate` |
| `runtime` | object | `skill/version/seconds/documents/fields/cells/reported/quote_pass_rate` |

**回填规则**：case 给几个 `output_contract` 键就回填几个，并把每个键浅拷贝到顶层（不覆盖
已有的 `case_id`/`status`/`result`/`claims`/`uncertainties`）。未定义的键也给结构化非空值——
契约键名与语义的对应见 `contract_value()`。**任何路径都不写 JSON `null`**：写入前统一走
`denull()`，`None` → `""`，`NaN/Inf` → `""`。

## 2. locator 方案

- 文本/PDF/DOCX 统一形如 `<page>#para<n>`，页码用 `p1` 起（PDF/DOCX 只有 `p1`，因为纯标准库
  不做版面分页；此时在 `degradations` 里声明“页号非权威”）。
- 段落 = 空行切块；块内若整体 > 600 字符按句拼接再切；< 40 字符的碎块并入上一段。
- 反引号包裹的数字/单位/引用/DOI/URL 一律原样保留，locator 指向承载它们的整段。

## 3. 字段字典（缺省八维）

工单未给字段时按此表建矩阵；工单给了就以工单为准。

| field_id | 名称 | 单位 | 取值口径 |
|-|-|-|-|
| `task` | 任务类型 | - | 降解/吸附/转化等原文表述 |
| `dataset` | 数据集 | - | 语料/批次标识 |
| `sample` | 样本 | - | 样本编号或数量 |
| `material` | 材料/催化剂 | - | 原文命名（优先化学式，如 `TiO2`/`ZnO`） |
| `method` | 方法 | - | 光源/温度/时间等条件 |
| `metric` | 指标 | - | 去除率/转化率/选择性等 |
| `unit` | 单位 | - | 指标的单位 |
| `budget` | 资源/预算 | - | 用量、负载、能耗 |

材料/染料/统计常用中英对齐：光催化剂 catalyst、目标染料 pollutant / dye、去除率 removal
efficiency、转化率 conversion、选择性 selectivity、产率 yield、比表面积 SSA、初始浓度
initial concentration、载气流速 flow rate、动力学 kinetics。

## 4. 可比性口径

1. 维度取自工单 `comparison_dimensions`（缺省八维）。
2. 某维度上若各文档都报告了值：归一后完全一致 → `comparable: true`；有差异 → `false`，并在
   `basis` 说明差异，矩阵**分层保留**，不给合并值。
3. 只有一篇报告 → 不构成比较，记 `insufficient`。
4. 命中 `forbidden_pooling`（如“不同染料”“不同催化剂”）时，即使数值接近也**禁止合并**。
5. 冲突裁决 `conflicting` 必须归因到 `condition` / `system` / `unresolved` 之一；
   `unresolved` 的冲突记为 `error`，status 降为 `partial`。

## 5. status 推导

| status | 条件 |
|-|-|
| `ok` | 至少一个 `reported` 格子，且无 `error`、无 `degradation` |
| `partial` | 有 `reported` 格子，但存在 `error` 级缺陷或抽取降级 |
| `insufficient_evidence` | 语料可读但一个值都锚不出来 |
| `input_error` | `--input` 不可读或无语料，交付缺口报告 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。
