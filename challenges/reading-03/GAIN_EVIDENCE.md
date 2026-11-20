# GAIN_EVIDENCE — 增益证据与对照口径（reading-03 v9）

回答三件事：**和谁比**、**用什么口径比**、**比出了什么数字**。数字都来自本包可复现的运行；不能自动化的部分明确标注。

## 1 对照双方与公平条件

| | 基线（基础 Agent，无 Skill） | 本 Skill |
|-|-|-|
| 输入 | 同一 `case.json` + `materials/` | 同一输入 |
| 交付形态 | 整篇翻译文本 | 段落级对照 + 术语表 + 核验记录（6 产物） |
| 术语口径 | 无外部术语表 | quote 逐字命中才 locked，全篇回填 |
| 可核验性 | 无法定位段/句，无机器可读结构 | 每段 locator + 逐字证据 + 核验结论 |

包内 `compare` 实现**可复现的下界基线**：把材料原文直接搬进 `target`（不切段、不建术语表、不核验）：

```bash
python scripts/main.py compare --input examples --output <out> --work <work>   # → work/compare_report.json
```

平台侧基线由平台用基础 Agent 跑同一案例生成；本包不伪造平台数字，只给口径与可复现下界。

## 2 指标口径（第三方可复算）

| 指标 | 定义 | 来源 |
|-|-|-|
| paragraphs_aligned / locators | 同时有 source+target 的段数 / locator 非空段数 | `paragraph_pairs.jsonl` |
| span_checks | 保护性 span 类别核验数（数字·单位/引用/图表编号/公式号） | `audit_report.json` |
| glossary_locked | 逐字命中并锁定的术语条数 | `glossary.json` |
| audit_checks | 机械核验项总数 | `audit_report.json` |
| deliverables | 声明产物个数 | `--output` 目录 |
| coverage_rate / glossary_consistency / span_retention | 段落覆盖率 / 术语一致率 / span 保留率 | `result.json.audit_summary.rates` |
| negation_rate / hedge_rate | 否定与限定关系保留率 | 同上 |
| seconds_per_segment | 机器耗时（切段→出产物）/ 段数 | `result.json.runtime.efficiency` |

## 3 实测对照（`examples/`：17 段、4 条锁定术语）

| 指标 | 基线（搬运） | 本 Skill |
|-|-|-|
| paragraphs_aligned | 0 | **17** |
| locators | 0 | **17** |
| span_checks | 0 | **4** |
| glossary_locked | 0 | **4** |
| audit_checks | 0 | **16**（全 pass，fail=0 warn=0） |
| deliverables | 1 | **6** |

同次运行指标率全为 **1.0**：`coverage_rate`、`glossary_consistency`、`span_retention`、`negation_rate`、`hedge_rate`、
`element_coverage`、`quote_verbatim`；要素覆盖 13/13（caption_figure=1 caption_table=1 formula=1 heading=5
reference=2 table_row=3）。

**"更准"的可复现证据**（不是自述）：按 `SELFTEST.md` §4 删掉 `S003` 译文里的 `[1]`、改掉 `S013` 的否定关系后，
核验器给出 `citations` + `protected_numbers`（同段 `S003`）与 `negation`（`S013`，定位到第 2 句）三项 fail，
`status` 自动从 `answered` 降为 `partial`。同一套指标能同时衡量基线与本 Skill 的产物质量。

## 4 效率口径与实测

`result.json.runtime` 记录真实计时（`timings.index/draft/check/build`、`total_seconds`），`runtime.efficiency` 给出
段数/行数、`seconds_per_segment`、`seconds_per_pair`、`manual_baseline_minutes_per_segment=3.0`（口径假设）与
`automated_minutes_estimate`。

实测（17 段）：机器总耗时 ≈ 0.012 s，`seconds_per_segment≈0.0006`；按 3 分钟/段的人工口径，人工约 51 分钟。
假设写在字段里，可复算。**注意**：省时只覆盖机械部分（切段、定位、查术语、一致性回扫、数字/引用比对、产物装配），
译文本身仍由 Agent/人产出，语义判断不可替代——不做夸大宣称。

## 5 开发期观察到的基线失败案例（可用 SELFTEST §4 复现）

标注：以下为开发期在同类材料上反复观察到的失败形态与包内复现，不是对某个具体模型运行结果的断言。

| 失败形态 | 后果 | 本包的拦截 |
|-|-|-|
| 把摘要概括成一段大意而非逐句对照 | 无法复核、丢信息 | 逐段对照 + `coverage` 必须逐段有译文 |
| `[1]`/`Fig. 1`/`(1)` 被省略或改成"文献1" | 引用不可追溯 | `citations`、`figure_table_refs`、`equation_tags` |
| 数字/单位被改写（`92.4 %`→`约 92%`） | 事实被篡改 | `protected_numbers`（少一个即 fail） |
| 否定/限定被抹平（"没有恢复"→"恢复了"，may→是） | 结论方向被改写 | `negation`（定位到句）、`hedge`（warn） |
| 同篇术语两种译名 | 术语不一致 | `glossary_lock`、`glossary_consistency` |
| 未译处写成"待补充/TBD" | 缺口被掩盖 | `placeholder_policy` + 产物占位符扫描 |

## 6 创新证据与价值边界

新增能力（有产物可查）：① 术语表强制约束与全篇回填（本次 4 条锁定 / 8 次出现 / 8 次命中）；② 跨页跨栏续段与
`bridged` 标记；③ 保护性 span 多重集比对；④ 否定/限定逐句核验；⑤ `selfcheck`（含降级场景）与 `compare`（可复现下界）。

价值边界：不判断译文好坏（只列 `human_review`）；不做 OCR（扫描件记降级，不产假正文）；不代译、不联网、不调模型
（无工作稿即 `insufficient_evidence`）；极端排版的切段会保守处理并记 `warnings`，需人工确认。
