# 创新证据：与通用 Agent / 商用库 / 人工查新的差异与价值边界

配套 `patent-search-dossier` v1.0.0。本文件说明本 Skill 相对**已有方案**的具体改进、可验证的规则依据，
以及**不做什么**（价值边界）。所有对材料内容的引用都带 `M#/p#` 定位符；不引用未在材料中出现的数字或文献。

## 1. 比较对象与口径

| 比较对象 | 它通常怎么做 | 本 Skill 的差异 |
|---|---|---|
| 通用检索 Agent | 把技术主题丢进通用搜索，从网页摘要拼答案 | 号码规范化 + 状态分级 + 族口径显式化 + 许可闸门，全部可复核 |
| 商用专利数据库 | 字段齐全、但不告诉你「结论从哪一行来」 | 每条结论带 `M#/p#` locator 与逐字引文，且不抓取受限库 |
| 人工查新流程 | 依赖个人经验，口径散落在各人笔记 | 规则链、状态三字段、许可分级、边界类型全部落在文件里，可复跑 |

任务原文把通用 Agent 的典型失败写得很具体：「公开号与授权号混用，优先权和申请日混为一谈，关键词命中的几件
不同专利被当成同一族，法律状态引用的是几年前的转载页面」（`M02` = task.md，见其 §1 段落）。本 Skill 的每条
规则都直接对着这些失败点设防。

## 2. 新增能力（基础 Agent 不易稳定实现）

1. **规则链号码规范化**（`number_registry.json` 的 `rules[]`）
   链：`strip_separators → cc:*（国别前缀）→ kind:*（尾部 kind code）→ 位数判型 → inferred_country:*`。
   规则来自材料 §2 的规范表（`M03/p28` 起，字段字典 §2），例如
   `US 2017/0123456 A1 → US20170123456A1 (us_publication)`、
   `PCT/US2018/012345 → WO2018012345 (pct_application)`、
   `10,123,456 → US10123456 (us_grant, parse_status=ambiguous)`。
   通用 Agent 常直接照抄原串或在号码间混用文书类型；本 Skill 把每一步决策写进 `rules`，可逐条复核。
2. **同族归并口径显式化**（`family_graph.json`）
   只陈述**观察到**的链接；`not_exhaustive` 恒记；关键词命中不等于同族。材料纪律句「关键词命中 ≠ 同族」见
   `M03` 字段字典 §4。无链接时输出孤立节点并写 `no_data`，绝不编造族边。
3. **法律状态三字段纪律**（`status_provenance.csv`）
   每条状态强制 `as_of` + `source_kind` + `needs_official_verification`；非官方来源恒 true。材料纪律句
   「材料没有官方登记 → value=unknown，不得推断"已授权/已失效"」见 `M03` 字段字典 §3。本包在无登记页时
   `status_value` 全为 `unknown`，并额外写入 `source_kind=not-declared` 说明它落在四类枚举之外及原因。
4. **许可绿黄红闸门**（`license_gate.md`）
   许可未声明 → 按 `yellow` 处理并进 `gaps`；`red` 来源只登记不引用。判据来自材料 §5（`M03` 字段字典 §5）。
5. **证据快照**（`evidence/<id>.json`）
   每个来源一份原始行快照，任何号码或标签都能回到它出现的那一行。材料缺少官方登记页时，快照本身即「检索了
   哪些位置、为什么没有结果」的证据。

## 3. 方法改进的可验证证据

| 规则 | 可验证产物 | 实测（rich 材料集） |
|---|---|---|
| 号码规范化 + 规则链 | `number_registry.json:entries[].rules[]` | 12 个号码，规范化结果与材料 §2 表逐行一致 |
| 状态三字段纪律 | `status_provenance.csv` | 12 行，全部 `unknown` + `needs_official_verification=true` |
| 族口径显式化 | `family_graph.json:not_exhaustive` + `no_data` | 0 族边，明确不声称穷尽 |
| 许可闸门 | `license_gate.md` | 4 行全部 `yellow`，附降级方案 |
| 证据留存 | `evidence_map.json` + `evidence/<id>.json` | 17 条证据映射，可回看原文行 |

以上数字来自 `SELFTEST.md` 的真实运行，可用 `python3 scripts/main.py all --input /input --output /app/output --work /app/work` 逐字复现。

## 4. 价值边界（不做什么）

- 不伪造文献、专利号、法律状态或软件状态；材料没有的就不写，改为 `boundaries` 与 `gaps`。
- 不做侵权判定、自由实施（FTO）分析与专利价值评估；不替代专利律师或法律意见。
- 不绕过付费墙，不上传受限数据，不对外展示受限库原文；未声明许可的来源只给结论与定位。
- 同名或同关键词**不等同**同一族或同一权利要求范围；本 Skill 只按可见证据陈述。
- 无官方登记页时状态保持 `unknown`；影印件上的授权公告日期不等于现行有效性。
- 语言/国别覆盖以材料实际出现为准；材料未出现的国别不作推断性结论（`country` 为空即如实为空）。

## 5. 与「只要文字自述即可」的差别

本文件的每个数字都能在 `SELFTEST.md` 与随包 `scripts/` 的运行中找到来源；对照的基线一栏在
`GAIN_EVIDENCE.md` 中明确标注为**模拟**而非官方对照。文字自述不构成证据，产物与可复现命令才构成证据。
