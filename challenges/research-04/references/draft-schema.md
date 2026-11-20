# `draft.json` 字段字典与错误码修法

工作稿是 Agent 唯一的写入口：`/app/work/draft.json`。`init` 会写一份骨架（含 `corpus` 与候选事件），你必须改写它，再 `check` → `build`。

## 1. 顶层结构

```jsonc
{
  "case_id": "从 case.json 原样复制",
  "research_question": "一句话，来自 task_instruction",
  "corpus": [ /* 来源登记，可留 init 生成值，年份/主题要核对 */ ],
  "events": [ /* 事件台账：本稿核心 */ ],
  "stage_division": [ /* 阶段，可为空→脚本给候选 */ ],
  "turning_points": [ /* 转折，可为空→脚本给候选 */ ],
  "gaps": [ /* 空白，可为空→脚本给候选（缺排除证据） */ ],
  "conclusions": [ /* 结论摘要，报告第 1 节直接用 */ ],
  "method_notes": { /* 口径说明，报告第 7 节直接用 */ },
  "uncertainties": ["..."],
  "pending_human": ["..."]
}
```

## 2. `corpus[]`（来源登记）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source_id` | string | 是 | `S01`…，与 `init` 输出一致，不要改 |
| `year` | int\|null | 是 | 主口径年份；缺失写 `null`，脚本不猜 |
| `year_source` | enum | 是 | `published`/`online`/`preprint`/`venue`/`unknown` |
| `year_alt` | int\|null | 否 | 备选年份（如 online 年），用于口径影响说明 |
| `venue` | string | 否 | 期刊/会议 |
| `themes` | string[] | 否 | 该文献涉及的主题 id |
| `has_fulltext` | bool | 否 | 仅摘要时应为 false，并进 `uncertainty` |

## 3. `events[]`（一等产物）

| 字段 | 类型 | 校验 | 说明 |
|---|---|---|---|
| `event_id` | string | 唯一 | `E01`…；脚本候选为 `C01`…，改写后建议改 `E` 编号 |
| `year` | int | `1800<=year<=2100` | 事件发生在该文献所报告的年份 |
| `year_source` | enum | 五值之一 | 见 typology §4 |
| `event_type` | enum | 八型之一 | 见 `references/event-typology.md` §2 |
| `statement` | string | 非空、无评价词 | 一句话**事实**陈述；不要写"重要/突破性" |
| `source_id` | string | 必须在 corpus | 事件出处 |
| `locator` | string | 必须存在 | `S03:P07`（由 `show` 打印），可写区段 `S03:P07-S03:P09` |
| `quote` | string | 逐字命中 | 允许空白/大小写/全半角差异；**不许改词、补字、翻译、跨段拼接** |
| `theme_id` | string | 建议 `T1`/`T2`… | 主题归并规则写进 `method_notes.theme_merge_rules` |
| `method` | string | 可空 | 方法名（用于 `no_transfer` 判定） |
| `object` | string | 可空 | 数据集/物种/尺度/任务 |
| `confidence` | enum | `high/medium/low` | 判定把握：句子直述=high；需推断=medium；综述句/单句歧义=low |
| `reviewed` | bool | 建议 true | `false` 会被 `check` 持续提示（脚本候选） |

## 4. `stage_division[]`

| 字段 | 类型 | 校验 |
|---|---|---|
| `stage_id` | string | 唯一，`G1`… |
| `label` | string | 简短可读 |
| `year_range` | `[int,int]` | 起止有序 |
| `basis_event_ids` | string[] | **至少 1 个存在的事件**（`STAGE_NO_BASIS`） |
| `lifecycle` | enum | `emerging/consolidating/maturing/declining` |
| `rationale` | string | 写清"因何变化"，不是"数据分两段" |

## 5. `turning_points[]`

```jsonc
{"turning_id":"P1","event_ids":["E02","E03"],"criteria_hit":"first_of_type",
 "why_turning":"method_introduced 首次出现，方法从概念变为可复用估计器"}
```

- `criteria_hit` 只能取 `first_of_type/type_shift/density_jump/theme_birth/theme_death`（也可给列表）。
- `why_turning` 必须说明**改变了什么**（口径、对象、方法选择），不是复述事件。

## 6. `gaps[]`

```jsonc
{"gap_id":"N1","gap_type":"unresolved_conflict","description":"...",
 "events_evidence":["E04","E08"],"search_scope":"在哪批材料/用哪些词检索",
 "exclusion_evidence":"为什么这不是检索遗漏"}
```

三件必备：`events_evidence`（存在的 id）、`search_scope`（非空）、`exclusion_evidence`（非空）。缺一即为错误。

## 7. `conclusions[]`

```jsonc
{"text":"...","event_ids":["E01","E08"],"strength":"established|preliminary|hypothesis"}
```

- `small_sample=true` 时 `strength` 只能取 `preliminary`/`hypothesis`。
- 每条结论必须能追到事件 id；报告第 1 节按此渲染。

## 8. `method_notes`（缺省会被脚本填保守默认值并记降级）

`year_basis`、`theme_merge_rules`、`stage_basis`、`gap_criteria`、`small_sample_rule` 五项。写"口径如何影响结论"，而不是"用了什么方法"。

## 9. 错误码 → 修法

| 错误码 | 含义 | 修法（按顺序） |
|---|---|---|
| `EV_NO_ID` | 缺 `event_id` | 补 `E` 编号 |
| `EV_TYPE_INVALID` | 类型不在八型 | 按 typology §2 重判；判不了就换一条更清楚的句子 |
| `EV_YEAR_MISSING` | 事件无年份 | 从文献元数据/正文找；实在没有则不要登记为事件，改记 `uncertainty` |
| `YEAR_INVALID` | 年份越界 | 修数字（不要用 0/当前年占位） |
| `YEAR_SOURCE_INVALID` | 口径不在五值 | 用 `published/online/preprint/venue/unknown` |
| `SRC_NO_ID` | `source_id` 不在语料 | 用 `show --sources` 核对 |
| `EV_NO_QUOTE` / `EV_NO_LOCATOR` | 缺证据 | 用 `show --grep` 找到原句复制 |
| `LOC_MISS` | 段号不存在 | 换 `show` 打印的真实 locator |
| `QUOTE_MISS` | 未逐字命中 | 缩短引文到确定逐字的片段；**不要改原文** |
| `QUOTE_NOT_IN_LOCATOR` | 引文在别的段 | 把 locator 改成命中段 |
| `EV_EMPTY` | 台账为空 | 先读材料再写事件（不是跑 build 的理由） |
| `EV_STATEMENT_EVALUATIVE`（提示） | 陈述含评价 | 改成"谁对什么做了什么" |
| `NUM_UNSOURCED`（提示） | 陈述里的年份不在引文 | 确认来自同源材料或删除 |
| `CHRONO_CONFLICT`（提示） | 验证/反驳早于提出 | 标 `chronology_conflict` 并写 `uncertainty`，不改年份 |
| `STAGE_NO_BASIS` / `STAGE_YEAR_RANGE` / `STAGE_YEAR_ORDER` | 阶段缺依据或年份错 | 补 `basis_event_ids`，修正区间 |
| `STAGE_GAP`（提示） | 相邻阶段断年 | 在 `rationale` 说明或合并阶段 |
| `TURNING_EVENT_MISSING` / `TURNING_NO_CRITERIA` | 转折无事件/无 criteria | 补事件 id；criteria 取五值之一 |
| `REP_STAGE_UNCOVERED`（提示） | 阶段无转折 | 该阶段补一条转折，或接受 `stage_first_event` 兜底 |
| `GAP_TYPE_INVALID` / `GAP_NO_EVENT_EVIDENCE` / `GAP_NO_SCOPE` / `GAP_NO_EXCLUSION` | 空白不合规 | 补类型、事件证据、检索范围、排除证据 |
| `STAT_MISMATCH` / `STAT_DRIFT` | 统计与台账不一致 | 不要手写统计；重跑 `build`，统计永远由台账聚合 |
| `CLAIM_OVERREACH`（提示） | 小样本用了强断言 | 改成"提示性/初步"，删除"显著/证明" |
| `SMALL_LEDGER`（提示） | 事件 <8 | 继续读材料补齐各阶段事件 |

## 10. 最小可用工作稿（示例，非案例答案）

```jsonc
{
  "case_id": "DEMO",
  "research_question": "该方法在 2017–2023 年经历了哪些阶段？",
  "events": [
    {"event_id":"E01","year":2017,"year_source":"published","event_type":"proposal",
     "statement":"提出基于稀疏编码的因果父节点恢复框架。","source_id":"S01","locator":"S01:P02",
     "quote":"除此处外请填逐字原文","theme_id":"T1","confidence":"high","reviewed":true}
  ],
  "stage_division": [],
  "gaps": [],
  "method_notes": {"year_basis":"见刊年为主口径"},
  "uncertainties": ["材料仅 3 篇，结论为提示性"]
}
```

单条事件也可跑通 `check`/`build`（`status=partial`，提示 `SMALL_LEDGER`）。
