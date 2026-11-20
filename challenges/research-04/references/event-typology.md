# 事件类型学与判据手册（可跨领域复用）

本文件是本 Skill 的**判定规则源**。`scripts/core.py` 的 `CUES`/`EVENT_TYPES` 只是候选线索；**最终类型由 Agent 按本手册判定**，并给出原文依据。

## 1. 为什么用事件而不直接数文献

按年数文献只能回答"多少"，回答不了"变了什么"。同一篇文献可包含多个事件（提出一个假设、验证其中一条、否定另一条），事件的年份与类型可分别检验，因此：

- 统计成为**派生视图**：`derived/trend_stats.json` 永远由 `events/event_ledger.jsonl` 聚合，可复算；
- 代表作有**口径**：命中转折 criteria 的事件所在文献，而非总被引排序；
- 空白有**结构**：某类事件在某主题上缺席，而不是"我没搜到"。

## 2. 事件八型（固定枚举）

| 类型 | 判据（缺一不可） | 不算事件的情形 |
|---|---|---|
| `proposal` | 文献自身提出主张/框架/假说/问题，且该主张后续可被检验 | 引用他人主张；仅陈述领域背景 |
| `validation` | 有数据/实验/证明**支持**某具体主张，且指明对象或条件 | "已有研究表明"式转述；无对象与条件的泛泛结论 |
| `refutation` | 未能复现、给出反例、否定先前结论，或明确指出冲突结果 | 仅指出"仍需研究"；把他人方法说成"有局限"但不否定其结论 |
| `method_introduced` | 首次引入方法/工具/数据集/指标，且文中可识别其做法 | 使用已有方法；把已有方法换个名字 |
| `merged` | 两条主题线/方法线被显式结合成一条路线（"combine/integrate"） | 同一文献并列讨论两个主题但未结合 |
| `split` | 一个主题显式分化出子类/子族，或引入区分性划分 | 文献结构上的"分节"；把不同领域的工作并排罗列 |
| `declined` | 某方法/主题被显式判定为不足、被替代、退出使用 | 仅说"未来可改进"；作者自谦式局限声明（记为 medium/low） |
| `application_transfer` | 方法被迁移到**新对象/新尺度/新数据模态/新领域**并有实际结果 | 声称"可用于"但无结果；在同一数据集上换指标 |

判定顺序（减少误判）：
1. 先定位**动词**（propose/confirm/contradict/introduce/combine/split/no longer/apply）；
2. 再看**作用对象**是否具体（数据集、物种、尺度、任务）；
3. 最后看**是否改变领域状态**——只改作者自己的措辞不算。

## 3. 线索词表（双语，仅用于候选召回）

| 类型 | 英文线索 | 中文线索 |
|---|---|---|
| proposal | propose, hypothesize, we suggest, we argue, posit | 提出、设想、假设、我们认为 |
| validation | demonstrate, confirm, we show, validate, verify, reproduce | 验证、证实、支持了、复现 |
| refutation | fail to, cannot reproduce, contradict, refute, challenge | 未能、无法复现、反驳、不一致、相反 |
| method_introduced | we introduce, novel method, new framework/dataset, first ... method | 首次提出、新方法、新框架、构建了数据集 |
| merged | combine, integrate, unify, merge, bridge | 结合、融合、统一、打通 |
| split | distinguish, split into, two families/classes, diverge | 分为、分化、区分、两类 |
| declined | superseded, no longer, obsolete, abandoned, fall out of use | 被取代、不再适用、逐渐减少、降温 |
| application_transfer | applied to, extend to, transfer, deploy, scale to | 应用于、推广到、迁移到、扩展到 |

> 线索词只用于 `init` 生成候选（`auto=true`、`confidence=low`）。**未复核的候选不得直接进入结论**；`check` 会对 `reviewed=false` 的条目持续提示。

## 4. 年份归一决策表

| 情形 | 处理 | 记录字段 |
|---|---|---|
| 记录/元数据给 `year` | 直接用 | `year`, `year_source=published`（若记录标明 online/preprint 则用其值） |
| 同时有 online 与 published | published 为主口径 | `year`, `year_alt`（online） |
| 只有预印本 | 用预印本年 | `year_source=preprint` |
| 从正文检出 `(2019)`、`Published: 2019` | 采用并标来源 | `year_source=published` |
| 只能从卷期推断 | 采用，标 `venue` | `year_source=venue` |
| 找不到任何年份 | **不猜**（不用当前年、不用邻近年插值） | `year=null`, `year_source=unknown`，该来源不参与年度统计 |
| 两处年份矛盾且无 alt 说明 | 双值都记，统计用主口径 | `year_alt` + `uncertainty` 条目 |

口径影响必须写成一句话，例如：*"若改用 online 年，2019/2020 各迁移 1 篇，阶段边界从 2020 移到 2019，事件类型构成不变。"*——写不出影响就不要声称口径无关。

## 5. 阶段划分判据

阶段不是"按年份等分"，而是**边界有事件依据**。可用依据（至少一条，写进 `basis_event_ids`）：

| 依据 | 表述模板 | 该切/不该切 |
|---|---|---|
| 类型构成反转 | "G1 仅 proposal/method_introduced；G2 起出现 validation 与 refutation" | 该切 |
| 主题首现 | "T2 首现于 2020（E05），标志分化" | 该切 |
| 密度突变 | "相邻年事件数 2→5（n≥8）" | 该切；样本 <8 不切 |
| 对象/尺度迁移 | "2023 起事件对象由模拟系统变为基因调控数据" | 该切 |
| 仅有年份空白 | "2018–2019 无事件" | **不切**（多为材料缺口，记为 `stalled_theme` 候选或 retrieval_gap） |

阶段字段：`stage_id`、`label`、`year_range`、`basis_event_ids`、`lifecycle`（emerging/consolidating/maturing/declining）、`rationale`。

## 6. 转折事件 criteria（只能取这 5 个）

| criteria | 触发条件 | 说明 |
|---|---|---|
| `first_of_type` | 某 `event_type` 首次出现 | 最稳的转折证据，样本小也可用 |
| `type_shift` | 类型构成反转（如 refutation 首次压过 validation） | 需给出前后计数 |
| `density_jump` | 相邻年事件数翻倍/腰斩且总事件 ≥8 | 样本不足时禁用 |
| `theme_birth` | 新主题首现 | 与 `split` 事件常同时出现 |
| `theme_death` | 主题此后（≥2 年）无事件 | 需与检索范围一起写，否则是 retrieval_gap |

代表作 = 命中 criteria 的事件所在文献；每阶段至少 1 篇。**阶段内无转折事件**时用 `stage_first_event` 兜底并在 `why` 说明，不能默默用高被引补位。

## 7. 空白五类判据

| gap_type | 必要条件 | 必须写 |
|---|---|---|
| `missing_validation` | 存在 `proposal`，同主题无 `validation`/`refutation` | 提出事件 id；检索过的验证类词 |
| `stalled_theme` | 主题最后事件后 ≥2 年无事件，且时间窗在材料范围内 | 最后事件 id；窗口年份 |
| `no_transfer` | 方法存在且已在 ≥1 对象上使用，但目标对象无 `application_transfer` | 方法事件 id；检索过的对象词 |
| `unresolved_conflict` | 同主题 `validation` 与 `refutation` 指向同一主张 | 双方事件 id；为何无法裁决 |
| `retrieval_gap` | 材料本身不足（缺全文/缺年份/仅摘要/篇数极少） | 缺什么；补检索建议 |

`exclusion_evidence` 写法要求（否则 `GAP_NO_EXCLUSION`）：
- 写"我检索了什么"（词、范围、时间窗），不是"我没找到"；
- 写"为什么这属于材料边界"（例如 0 命中源于材料仅 3 篇）；
- 结论动词降级：`retrieval_gap` 只能说"待查方向"，不能说"领域空白"。

## 8. 小样本与结论强度

| 条件 | 标记 | 允许的表述 | 禁止的表述 |
|---|---|---|---|
| 事件 ≤20 或来源 ≤10 | `small_sample=true` | "提示性""初步""在本批材料内""与…一致" | "显著上升""证明""确立了""必然" |
| 事件 >20 且来源 >10 | `small_sample=false` | 可描述增长/回落，但仍不外推 | 未经检验的因果或显著性断言 |

`check` 会在 `CLAIM_OVERREACH` 提示里列出命中的断言词；`status` 仍可为 `ok`，但报告口径必须改。

## 9. 反模式（评审最常扣分的做法）

1. 把检索结果前 N 条当"前沿"——没有年份分布与类型构成。
2. 把关键词热度当"趋势"——热度不是事件。
3. 术语换说法当"新兴主题"——需 `theme_birth` 事件 + 首现年份。
4. 高被引当"代表作"——代表作必须命中转折 criteria。
5. "没检索到"当"研究空白"——必须是 `retrieval_gap` 且写明排除证据。
6. 统计手写、与台账不一致——`STAT_MISMATCH`/`STAT_DRIFT` 会直接暴露。
7. 为通过校验改写原文 quote——禁止；只能换更短的真实片段或改 locator。
