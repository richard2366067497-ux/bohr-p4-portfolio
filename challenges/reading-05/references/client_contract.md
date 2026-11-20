# client_contract — 契约键、locator 与状态口径

本文件冻结 `result.json` 的键语义和阅读闭环的判定口径。键名一旦发布不再改名；
新增字段走次版本，阈值与文案走修订号。

## 1. 顶层键

| 键 | 类型 | 语义 | 空值规则 |
|-|-|-|-|
| `case_id` | string | 原样透传输入 `case.json` 的 `case_id`；缺失时退回目录名 | 不允许空 |
| `status` | string | `answered` / `partial` / `insufficient_evidence` / `input_error` | 由产物推导 |
| `summary` | string | 一句话结果摘要（文档数 / 段落数 / 跨度数 / 质检） | 不允许空 |
| `output_contract` | object | 输入契约逐键回填；无契约时回填标准五键 | 每键必须非空 |
| `result` | object | 结构化主结果（见 §2） | 非空对象 |
| `claims` | array | 断言列表，每条带 `evidence[]`（quote + locator） | 至少一条 |
| `sources` | array | 材料来源清单；`task.md` 项始终带一条逐字引文与 locator | 至少一条 |
| `uncertainties` | array | 未报告 / 无法判断 / 冲突项；同时镜像为 `uncertainty` | 至少一条（scope） |
| `change_records` | array | 本次变更轨迹；同时镜像为 `changes` | 至少一条 |
| `errors` | array | 结构性错误（引文/定位/解析） | 允许为空数组 |
| `degradations` | array | 降级说明（编码、引擎、shell 过滤） | 允许为空数组 |
| `pending_human` | array | 需要人复核的点（由 degradations 派生） | 允许为空数组 |
| `limits` | array | 本次交付的边界声明 | 至少一条 |
| `counts` | object | 计数快照（documents/paragraphs/selections/claims/sources） | 非空 |
| `runtime` | object | skill / version / seconds / 通过率 | 非空 |

`output_contract` 的取值顺序（只认 case 真给的键，不改名、不合并）：

1. `case.json:output_contract` 的键集合（权威）；值为计算出的真实内容；
2. 契约缺失或为 null 时使用标准五键 `case_id/status/result/claims/uncertainties`；
3. `output_contract` 里出现未识别的键时，回填 `{key, summary, documents, evidence_spans}`
   这一结构化对象，绝不写 `string`/`object` 这样的类型词。

## 2. `result` 子结构

| 键 | 内容 |
|-|-|
| `question` | 本次阅读的问题；无 case 指令时用包内默认问法，并在 `task_source` 标注 |
| `task_source` | `case.json:task_instruction` 或 `package-default` |
| `documents[]` | 每份材料的 id / 文件名 / 类型 / 引擎 / sha1 / 字节数 / 段落数 / 质量 |
| `closed_loop` | 七步（open/locate/select/ask/save/review/export）的状态、说明、完成数 |
| `selections[]` | 选中的证据跨度：`span_id / document_id / locator / quote / char_start / char_end / score` |
| `annotations` | 批注计数与类型（highlight） |
| `anchor_precision_counts` | 段落数 / 带字符区间数 / 唯一 locator 数 |
| `context_design` | 窗口大小、locator 方案、偏移方案 |
| `export` | 导出的记录与阅读器路径 |
| `efficiency` | 材料数、复用锚点数、秒数 |
| `method_notes` | 方法声明（确定性、逐字、无网络） |
| `artifacts` | 本次写出的产物清单 |

## 3. locator 方案

- 形式：`p{页}#para{序}`，例如 `p1#para4`。
- 页号：`1 + char_start // 1600`；同一页内 `序` 从 1 递增。
- 字符区间：`char_start` / `char_end` 为规范化文本中的绝对偏移。
- 唯一性：质检要求 `len(locators) == len(set(locators))`。
- 报告与 HTML 中一律使用 `(p1#para4)` 形式，不使用尖括号包裹 locator。

## 4. 选句与 shell 过滤

1. 段落按空行切分，超长段按 ~1600 字符再切（尽量在空格处断开）。
2. 句子按 `[.!?]` 后空白切分；只保留长度 ≥20 的句子。
3. 只选含数字或百分号的句子；段落首行以 `Results` / `Findings` / `Conclusion`
   开头时加权；无百分号的句子仍可入选，但排序靠后。
4. 每份材料最多 3 条，跨文档不合并。
5. 整段只有未填写模板标记（方括号待写、TBD、NOT_EXTRACTED 等）的段落直接跳过，
   并写入 `degradations`；跳过的段落不进入 anchors，也不进入任何自产产物。

## 5. 状态推导

| status | 条件 |
|-|-|
| `input_error` | `--input` 不存在，或发现不到任何材料文件 |
| `insufficient_evidence` | 有材料文件，但没有任何段落可锚定 |
| `partial` | 有锚点，但没有选出任何量化证据跨度 |
| `answered` | 至少一条证据跨度，且其引文逐字命中所在段落 |

质检闸门：`quote_is_verbatim` 与 `locator_is_unique` 必须通过；否则仍如实交付，
但把失败项写进 `degradations` 与 `self_check.json`，不允许静默通过。

## 6. 不变量

- 任何答案都必须能切回某一段落的原文；不接受改写句充当引文。
- 不补写材料里没有的数字、单位、条件或因果。
- 材料重复时按 sha1 去重，保留先出现的那份，并在 `change_records` 记明。
- 输出件中不出现未填写的模板标记；所有列表若不是“真的为空”，就必须带结构化解释。
