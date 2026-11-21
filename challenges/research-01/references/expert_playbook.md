# 深度研究文献综述 · 专家方法论手册

本手册描述「深度研究 / 文献综述」任务的判分口径、求解流水线、量化公式、错误模式、证据分级、自查表与案例。命令接口见 SKILL.md，方法论以下文为准。核心原则：**走完一条可复核的研究路径，每条结论都能指回原文的一段/一表/一图**。

## 1. 判分要点

任务不是写综述文章，而是走完可复核研究路径：把模糊问题拆为可独立检索的子问题，逐条取回证据，综合成带来源定位的结论。评委只看三件事：

1. **子问题拆解质量**——每个子问题能否独立检索并产出证据？
2. **结论回链率**——每条结论句能否精确指到某篇文献的某段/某表/某图？
3. **路径可复跑性**——他人按记录能否重走并得到可比结果？

### 六类必覆盖要点（缺一扣分）

| 序号 | 要点 | 最低交付 |
|---|---|---|
| P1 | 问题拆解 | 带依赖关系的子问题树（≥3 个子问题） |
| P2 | 检索覆盖 | 每个子问题 ≥1 条检索式 + 来源 + 命中数 |
| P3 | 证据回链 | 证据表每行有 `source_id` + `locator`（页/段/表号） |
| P4 | 冲突证据 | 显式列出 ≥1 对矛盾结论，标注双方来源 |
| P5 | 综合结论 | 每个子问题 ≥1 条结论句，引用 evidence_id |
| P6 | 研究空白 | 基于检索缺口的具体空白描述，非套话 |

## 2. 错误做法 → 正确做法

| # | 错误做法 | 正确做法 |
|---|---|---|
| F1 | 把原始问题直接当关键词搜索 | 拆成研究对象/机制/方法/范围/比较 5 维子问题 |
| F2 | 检索式只写一个宽泛 query | 每子问题写专用检索式，记录命中数与筛选理由 |
| F3 | 引用只写「某某等人研究表明」 | 写 `source_id=S03, p.4, Table 2` |
| F4 | 遇矛盾取一方或写「尚存争议」 | 列双方证据，分析差异来源（样本/方法/条件） |
| F5 | 研究空白写「尚需进一步研究」 | 写「子问题 Q3 在 XX 条件下仅命中 0 篇 RCT，证据不足」 |
| F6 | 工具调用不记参数和返回 | 每步记 `step_id, tool, params, status, output_ref` |
| F7 | 失败不标注、静默跳过 | 标 `status=failed`，写原因和替代策略 |
| F8 | 把检索结果直接当结论 | 从证据表推导，每条结论附 `evidence_ids` |
| F9 | PDF 解析失败后用编造内容填充 | 标 `parse_status=failed`，用摘要/元数据降级 |
| F10 | 一次检索覆盖所有子问题 | 按依赖顺序分批检索，前置结果指导后续 |

## 3. 五步流水线（每步冻结产物 + 门控）

`输入 → S1 问题拆解 → S2 检索规划 → S3 证据采集 → S4 证据综合 → S5 交付打包`。下一步只能基于上一步冻结产物推进。

**S1 问题拆解**：识别五维要素 Entity / Mechanism / Method / Scope / Comparison；按依赖生成子问题树，每项格式 `{"id":"Q1","text":"...","dims":[...],"depends_on":[],"priority":1}`。冻结 `subquestions.json`。门控：子问题 ≥3；每个可映射到 ≥1 检索动作；依赖图无环。

**S2 检索规划**：为每子问题生成中英文检索式，指定来源（paper/news/patent/web），每子问题纳入 3–15 篇；P1 先执行，其结果术语反馈后续。冻结 `search_plan.json`。门控：每子问题 ≥1 检索式；来源已指定；无完全重复检索式。

**S3 证据采集**：按优先级执行并记录 `{"step_id":"T01","tool":"web_run","params":{},"status":"ok","results_count":12,"output_ref":"R01"}`；逐篇提取证据行 `{"evidence_id":"E01","source_id":"S03","subquestion":"Q2","locator":"p.7, Table 3","claim":"...","evidence_type":"quantitative","direction":"supports","confidence":"high"}`；PDF 解析失败降级摘要，检索为空扩词并记录。冻结 `evidence_table.json` + `tool_trace.json`。门控：证据行 ≥ 子问题数×2；每行有 source_id+locator；tool_trace 无未处理 failed。

**S4 证据综合**：按子问题分组，识别一致/冲突/空白。冲突三步法：列双方证据对 → 分析差异来源（样本量/方法/条件/时间）→ 给有边界限制的判断（「X 条件下 A 成立，Y 条件下 B 成立」）。某子问题证据 <2 或全低置信度则标空白并说明。写综合结论，每条附 evidence_ids。冻结 `synthesis.json`。门控：每子问题 ≥1 结论句；每句 evidence_ids 非空；冲突 ≥1 对（若存在）；空白具体到子问题与条件。

**S5 交付打包**：组装 result.json（含全部必选字段），生成 Markdown 综述，逐条自查。冻结 `result.json` + `review.md` + 辅助文件。门控：result.json 通过 schema 验证。

## 4. 量化口径

| 指标 | 公式 | 目标 |
|---|---|---|
| 子问题拆解深度 D | 子问题总数 / 原始问题独立概念数 | D ≥ 1.5 |
| 证据回链率 R | 有 locator 的证据行数 / 总证据行数 × 100% | R ≥ 95% |
| 结论覆盖率 C | 有 evidence_ids 的结论句数 / 总结论句数 × 100% | C = 100% |
| 冲突识别率 F | 已标注冲突对数 / 实际存在冲突对数 | F ≥ 80% |
| 检索效率 η | 纳入文献数 / 总检索命中数 × 100% | 5% ≤ η ≤ 40% |
| 工具成功率 T | status=ok 步数 / 总步数 × 100% | T ≥ 85% |

**自洽示例**：4 个独立概念拆出 7 子问题 → D=7/4=1.75 ✓；7 条检索式命中 120 纳入 18 → η=15.0% ✓；证据 32 行 31 有 locator → R=96.9% ✓；12 结论全引用 → C=100% ✓；20 步 18 成功且 2 失败有降级 → T=90% ✓。

### 证据强度分级

| 等级 | 条件 | 权重 |
|---|---|---|
| high | 同行评审期刊 + 定量数据 + locator 精确到表/图 | 3 |
| medium | 同行评审期刊 + 定性描述 + locator 到段落 | 2 |
| low | 预印本/会议/网页 + locator 模糊 | 1 |

同方向加权求和：`score = Σ(weight_i × direction_i)`，direction 取 +1/-1/0。|score|≥4 为强结论，2–3 为弱结论，≤1 为证据不足。

## 5. 领域知识清单

| 错误类型 | 示例 | 正确做法 |
|---|---|---|
| 混淆相关与因果 | 「A 与 B 相关，因此 A 导致 B」 | 明确标注研究设计（观察性/实验性） |
| 忽略样本规模 | 引用 n=10 作强证据 | 记录样本量，纳入证据强度评估 |
| 时间错位 | 用 2010 数据答 2024 问题 | 标注文献年份，说明时效性 |
| 来源等级不分 | 博客与 Nature 等权 | 按证据强度分级 |
| 单位遗漏 | 「效率提升了 30」 | 写「30%」或「30 个百分点」 |
| 指标混淆 | conversion 当 selectivity | 核对原文定义，照录原始指标名 |

**文献依据**：定量结论必须引用原始论文（非二次引用）；冲突双方各 ≥1 独立来源；禁止以「个人通讯/未发表数据」作主要证据；优先 DOI 可解析文献；纳排标准含文献类型与语言。

**检索陷阱**：中英文检索词不等价（「深度学习」可能命中 deep learning / deep etching，须加领域限定词）；专利检索用 IPC/CPC 辅助；预印本未经同行评审，证据等级 low。

## 6. 防扣分自查表

- [ ] SC01 子问题树 ≥3 且每个可独立检索
- [ ] SC02 子问题依赖关系已标注且无循环
- [ ] SC03 每子问题 ≥1 检索式，记录来源类别与命中数
- [ ] SC04 证据表每行含 `source_id` 与 `locator`
- [ ] SC05 每条结论句引用 ≥1 `evidence_id`
- [ ] SC06 存在矛盾结论时显式列双方证据并分析差异来源
- [ ] SC07 研究空白具体到子问题编号与条件，非套话
- [ ] SC08 tool_trace 记录每步工具调用的参数与状态
- [ ] SC09 检索式按依赖顺序执行，非一次性全发
- [ ] SC10 工具调用失败有降级策略记录
- [ ] SC11 拆解策略含五维要素分析，超越关键词拆分
- [ ] SC12 冲突处理含差异来源分析
- [ ] SC13 status 如实反映完成度（completed/partial/failed）
- [ ] SC14 PDF 解析失败降级摘要/元数据，不编造
- [ ] SC15 检索 0 结果有扩大策略记录
- [ ] SC16 result.json 含完整 case_id 与全部 output_contract 字段
- [ ] SC17 change_log 记录流程调整决策与原因
- [ ] SC18 uncertainty 说明整体证据边界与未覆盖范围
- [ ] SC19 综述正文引用标记可追溯到 evidence_table 具体行
- [ ] SC20 所有文件路径有效，无硬编码个人路径

## 7. 完整虚构案例（LLZO vs LGPS）

> 虚构演示，说明流程与数字自洽。

**研究问题**：对比 LLZO（Li₇La₃Zr₂O₁₂）与 LGPS（Li₁₀GeP₂S₁₂）在全固态锂电池中的离子电导率、电化学稳定性与界面阻抗，评估适用场景。约束：2015–2024，英文，同行评审优先。

**S1**：五维要素 Entity=LLZO/LGPS、Mechanism=电导率/稳定性/界面阻抗、Method=EIS/DFT、Scope=全固态锂电池 2015–2024、Comparison=LLZO vs LGPS；独立概念 5，拆 7 子问题（Q1 LLZO 电导率、Q2 LGPS 电导率、Q3 LLZO 稳定窗口、Q4 LGPS 稳定窗口、Q5 LLZO 界面阻抗、Q6 LGPS 界面阻抗、Q7 综合对比）；Q3 依赖 Q1、Q5 依赖 Q3、Q7 依赖 Q5/Q6。D=7/5=1.40，接近阈值可接受。

**S2 节选**：Q1 检 `LLZO Li7La3Zr2O12 ionic conductivity solid electrolyte`（paper，2015–2024，min3/max10）、`LLZO garnet ionic conductivity doping temperature`；Q3 检 `LLZO electrochemical stability window voltage`。

**S3 证据节选**：E01 S01 p.3 Table 1「Ta-doped LLZO 6.1×10⁻⁴ S/cm@25°C」high supports；E02 S02 p.5 Fig.3「Undoped cubic 2.4×10⁻⁴；Al-doped 4.0×10⁻⁴」high；E03 S03 p.2 Table 1「LGPS 1.2×10⁻² S/cm，高约两数量级」high；E04 S04 p.8 §3.2「LLZO 稳定至 6 V」high；E05 S05 p.4 Fig.5「LGPS >2.5 V 分解」high opposes；E06 S06 p.6 Table 2「LGPS 窗口 1.7–2.1 V（DFT），碳包覆可扩展」medium。检索总命中 105、纳入 16，η=15.2%。

**S4 结论/冲突/空白**：结论 Q7「LGPS 室温电导率(~10⁻²) 比 LLZO(~10⁻⁴) 高约 2 个量级」evidence [E01,E02,E03] strong；「LLZO 窗口(至 6 V) 显著宽于 LGPS(~2.5 V)」[E04,E05,E06] strong；「LGPS 高压稳定性可经界面工程改善但长期循环数据不足」[E06] weak。冲突 [E05,E06] 主题 LGPS 稳定窗口上限，差异来源 LSV 实验 vs DFT 与界面改性条件，结论「未改性上限 2.1–2.5 V，界面工程可扩展需具体条件」。空白 Q5「LLZO/高镍正极长期循环(>500 圈)仅 1 篇」、Q6「LGPS 干法电极界面无文献」。

**指标**：D=1.40、R=28/28=100%、C=8/8=100%、η=16/105=15.2%、T=14/15=93.3%（1 次 PDF 解析失败已降级摘要）。

**result.json 最小 schema**：

```json
{"case_id": "string", "status": "completed|partial|failed",
 "subquestions": [{"id": "Q1", "text": "...", "depends_on": []}],
 "search_summary": {"total_hits": 0, "included": 0, "subquestion_coverage": {}},
 "evidence_table": [{"evidence_id": "E01", "source_id": "S01", "subquestion": "Q1", "locator": "...", "claim": "...", "confidence": "high", "direction": "supports"}],
 "conclusions": [{"subquestion": "Q1", "text": "...", "evidence_ids": ["E01"], "strength": "strong"}],
 "conflicts": [{"pair": ["E02", "E05"], "topic": "...", "resolution": "..."}],
 "gaps": [{"subquestion": "Q3", "reason": "...", "evidence_count": 0}],
 "tool_trace": [{"step_id": "T01", "tool": "web_run", "params": {}, "status": "ok", "output_ref": "..."}],
 "uncertainty": "...", "change_log": [{"step": "S3", "action": "...", "reason": "..."}]}
```

**时间预算（900 秒内）**：S1 60–90s、S2 30–60s、S3 360–480s、S4 120–180s、S5 60–90s、缓冲 60s。先存 status=partial 的基础 result.json，再迭代完善，确保超时也有可用交付。
