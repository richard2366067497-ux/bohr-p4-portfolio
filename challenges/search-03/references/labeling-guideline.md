# 标签体系与判定规则（R1–R12）

判定顺序固定，**不得跳步**：硬排除 → 重复/版本合并 → 主题门控 → 对象/方法/时间/类型 → 证据可用性与
元数据 → 定层与置信度。脚本 `scripts/analyze.py:judge` 与本文档必须一致；不一致时改脚本。

## 1. 三层标签

| 标签 | 定义 | 判定条件（全满足） | 典型反例 |
|---|---|---|---|
| `keep` | 纳入：直接支撑研究问题 | 主题命中（R1）＋至少 2 条实质条件（R2/R3/R4/R5）＋无 R8 违反＋有可引用证据（R6） | 主题对上但对象不对；只有综述 |
| `maybe` | 待定：证据或元数据不足，人工看一眼即可定 | 主题命中但实质条件 1 条或缺失；摘要缺失/截断（R11）；双通道判定不一致（R12）；同研究多篇报道（R10） | 题名很相关但无摘要 |
| `exclude` | 排除：不相关、硬排除或重复 | 命中 R8；主题完全不命中（R1）；重复/版本变体（R9）；被明确排除的文献类型 | 综述被排除但用户其实要综述 → 说明口径 |

相关性层级（与标签正交，供排序与解释使用）：

- `direct`：研究对象＋方法＋问题三者都对上，摘要给出该问题的结果或数据。
- `indirect`：方法参考、邻近人群/体系、背景或机制综述、只能部分迁移的结论。
- `none`：主题或对象不匹配，或硬排除。

**边界约定**（必须按此处理，不得临场改口径）：

1. 主题对上、摘要缺失 → `maybe` + `indirect` + `R11`，不许按"看起来相关"给 `keep`。
2. 预印本与正式版同题 → 合并为一条，预印本 `exclude` + `duplicate_of`（R9），不重复计数。
3. 同一研究多篇报道（不同结局指标/不同随访）→ **不合并**，全部保留，标 `same_study_group`，升级人工（R10）。
4. 综述在"原始研究为主"的问题里 → `exclude`（R5/R8），但在 `rationale` 写明"可作背景资料"。
5. 撤稿、勘误、社论、征稿、纯广告 → 一律 `exclude`（R8），无论主题多贴合。
6. 摘要语言与问题语言不同 → 允许判 `keep`，但 `confidence` 不超过 `medium`，并在 `flags` 写 `cross_language`。
7. 同分不靠"感觉"：排序键见 `scoring-and-ranking.md`，同分进 `tie_groups`。

## 2. 规则表（机器只认这 12 个 ID）

| ID | 名称 | 判定条件 | 触发证据 | 违反时的处置 |
|---|---|---|---|---|
| R1 | 主题匹配 | 题名/摘要命中研究问题核心概念族（≥1 个实质词，且不是泛词） | 命中的词 + 原句 | 判 `exclude`/`none` |
| R2 | 研究对象/人群匹配 | 物种、材料体系、疾病、人群、样本与问题一致 | 对象关键词 | 判 `indirect` 或 `exclude` |
| R3 | 方法匹配 | 干预/表征/模型/统计方法与问题要求一致 | 方法关键词 | 降为 `indirect` |
| R4 | 时间窗匹配 | 发表年份落在给定窗口（缺失年份按最旧处理） | 年份字段 | 标注违反，通常 `maybe` |
| R5 | 文献类型匹配 | 类型符合要求（原始研究/综述/预印本/RCT/队列） | 类型与载体 | 类型被明确排除 → `exclude` |
| R6 | 结果/证据可用 | 摘要含结果陈述、效应量、数值或明确结论 | 结果句 | 只算 `indirect` |
| R7 | 元数据完整 | 题名＋摘要＋年份＋标识符基本齐全 | 字段计数 | 置信度降级 |
| R8 | 硬排除 | 撤稿/勘误/社论/征稿/广告；命中排除条款；主题完全无关 | 类型词、排除词 | 直接 `exclude` |
| R9 | 重复/版本合并 | 同 DOI；题名规范化相同；题名相似度 ≥0.90；预印本-正式版成对 | DOI、题名、载体 | 合并，`duplicate_of` |
| R10 | 同一研究多篇报道 | 同第一作者＋题名相似度 ≥0.72＋年份差 ≤2，且 DOI 不同 | 作者、题名、年份 | 不合并，升级人工 |
| R11 | 摘要不足 | 摘要为空或 <40 字符 | 摘要长度 | 至少 `maybe`，置信度 `low` |
| R12 | 标注分歧/输入冲突 | fixture 意见冲突；题面与 case 冲突；双通道判定不一致 | 冲突来源定位 | `maybe` + `pending_human` |

`criteria_hit` 只能写上表 ID；写别的 ID 会被 `check` 判 `bad_rule_id`。

## 3. 决策树（可直接执行）

```
命中 R8（撤稿/勘误/社论/排除条款/主题完全无关）?
  └─ 是 -> exclude / none / confidence high
  └─ 否 -> 是某条已判定记录的同 DOI / 同题 / 预印本-正式版?
            └─ 是 -> exclude（duplicate_of=保留条目, R9）
            └─ 否 -> 主题命中?
                      └─ 否 -> exclude / none（R1 违反）
                      └─ 是 -> 摘要可用?
                                └─ 否 -> maybe / indirect（R11）
                                └─ 是 -> 对象+方法+时间+类型 至少 2 条满足?
                                          └─ 是 -> keep / (三者全满足 ? direct : indirect)
                                          └─ 否 -> maybe / indirect
疑似同一研究多篇报道（R10）-> 不合并，keep/maybe 均可，附 same_study_group
双通道（规则 vs 工作稿）差 ≥1 层且引证未通过校验 -> 降 maybe（R12）
```

## 4. 去重与版本链

判定重复的充分条件（任一）：

1. DOI 规范化后相同（去 `https://doi.org/`、转小写、去尾随标点）。
2. 题名规范化（小写、去标点与空格）后完全相同。
3. 题名相似度（词集 Jaccard）≥0.90。
4. 一侧带预印本标识（arXiv/bioRxiv/medRxiv/SSRN/Research Square/preprint）且相似度 ≥0.75。

保留方向：**正式发表版 > 有 DOI 版 > 年份较新 > 元数据更全 > 输入顺序靠前**。
被合并条目在产物中仍占一行（`label=exclude`、`duplicate_of=<保留 id>`），`merge_evidence` 写：
`reasons`（same_doi / same_title / title_similarity>=0.90 / preprint_vs_published / input_fixture）、
`kept_locator`、`merged_locator`、两侧 DOI。

合并前后计数必须在 `coverage.json` 对账：`total_candidates = unique_after_merge + merged_duplicates`。

## 5. 冲突与升级人工

| 冲突类型 | 来源 | 处置 | 产物字段 |
|---|---|---|---|
| 版本/重复 | 同 DOI、同题、预印本 | 合并，保留正式版 | `conflicts.duplicate_clusters[]` |
| 同一研究多报道 | 同作者+近似题名 | **不合并**，升级人工 | `conflicts.same_study_groups[]` |
| 标注意见分歧 | `conflicting_opinions*` fixture | 只作证据，不采纳为标签 | `conflicts.conflicting_opinion_fixtures[]` |
| 双通道不一致 | 规则 vs 工作稿 | 记录；引证未过校验则降 `maybe` | `conflicts.agent_rule_disagreements[]` |
| 引证不可核验 | quote 不在原文 | 降 `maybe`、`score≤0.5`、置信度 `low` | `conflicts.quote_unverified[]` |
| 输入冲突 | case.json 与 task.md 口径不一致 | 以 case.json 为准并记录 | `conflicts.input_conflicts[]` |

原则：**宁可待定，不造假阳性**。任何"看起来相关但无法引证"的记录进 `maybe`，并在 `pending_human` 写
"缺什么 + 人工下一步"。
