# Contract reference — scientific-figure-parser

冻结本 Skill 的契约语义、定标/数字化口径与证据类型。实现改动不得改变这里的键名。

## 1. result.json 顶层键

| 键 | 类型 | 含义 |
|-|-|-|
| `case_id` | string | 逐字透传 `case.json.case_id`；缺失时退回输入目录名 |
| `status` | string | `answered` / `partial` / `insufficient_evidence` / `input_error` |
| `summary` | string | 一句话摘要（图数、表数、结论数、数字化点数、错误/降级数） |
| `output_contract` | object | `case.json.output_contract` 逐键回填，每个键给真实值 |
| `result` | object | 主载荷：paper_title、来源文件名、figures、tables、digitization、elements、materials |
| `claims` | array | 每条结论带 `evidence{quote, quote_type, source_id, location, read_basis}` |
| `sources` | array | 每份材料 `{file, extension, bytes, role}` |
| `uncertainties` | array | 不确定项；镜像为 `uncertainty` |
| `figure_tables_digest` | object | 图表摘要：`figure_count/table_count/claim_count/digitized_points/figures[]/tables[]` |
| `change_records` | array | 处理步骤；镜像为 `changes` |
| `errors` | array | error 级缺陷（坏 JSON、引文不在材料、表不存在…） |
| `degradations` | array | 抽取降级（解码失败、刻度不足、颜色零命中、重复副本） |
| `pending_human` | array | 需人工确认的事项 |
| `limits` | array | 非阻断性局限 |
| `counts` | object | `figures/tables/claims/digitized_points/errors/degradations` |
| `runtime` | object | `skill/version/seconds/figures/tables/claims/digitized_points` |

**回填规则**：case 给几个 `output_contract` 键就回填几个，并把每个键浅拷贝到顶层（不覆盖已有
`case_id`/`status`/`result`/`claims`/`uncertainties`/`figure_tables_digest`）。未定义的键也给结构化
非空值。**任何路径都不写 JSON `null`**：写盘前统一走 `denull()`，`None` → `""`，`NaN/Inf` → `""`。

## 2. 定标与数字化口径

- 定标：`value = a·px + b`，由 `tick_px`/`tick_labels` 做最小二乘；`scale: log` 时先 `log10`
  拟合、输出时还原。**可用刻度 < 2 → 放弃数字化**并记 `degradation`。
- 命中：像素与序列 `rgb` 的逐通道差都 ≤ `tol` 才命中（默认 60）。
- 取点：每个命中像素列输出一个点（该列命中像素 y 的均值），同时保留 `px/py` 与 `x/y`。
- 零命中 → `status: no_pixels`，不得外推或填补。

## 3. 证据类型（`claims[].evidence.quote_type`）

| 类型 | 校验方式 |
|-|-|
| `text` | 归一化后在**任一材料文本**中能逐字找到（精确或去空格一致） |
| `json` | `location.table_id` 必须存在于本次读到的表集合 |
| `visual` | `source_id` 必须对得上本次读到的某张图（文件名或 figure_id） |

## 4. 序列状态

| status | 含义 |
|-|-|
| `digitized` | 定标成功且找到像素，`n_points > 0` |
| `no_pixels` | 定标成功但容差内无像素（记 `degradation`） |
| `not_digitized` | 配置 `digitize: false`，或轴刻度不可用 |

## 5. status 推导

| status | 条件 |
|-|-|
| `answered` | 有图表/表格，且无 `error`、无 `degradation` |
| `partial` | 读到了内容，但存在 `error` 级缺陷或抽取降级 |
| `insufficient_evidence` | 材料可读但无任何图表/表格/结论 |
| `input_error` | `--input` 不可读或无语料，交付缺口报告 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。
