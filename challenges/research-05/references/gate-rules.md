# 五门判定规则、词表与评分锚点（v1.0.0）

本文件是 `scripts/gates.py` 中规则的**人类可读版本**：脚本判什么、阈值多少、为什么这样判。
改判定口径时两处都要改（本文件 + `gates.check()`），否则文档与实现会漂移。

## 1. 五门与四类交付的映射

题面的四项交付不是四份并列文档，而是同一份判断的四个侧面；本 Skill 把它们压成五门：

| 门 | 名称 | 回答的问题 | 题面交付项 | 主要字段 |
|---|---|---|---|---|
| G1 | worth_doing | 值得做吗 | 研究问题定义 | `question.*` |
| G2 | nobody_done | 别人做到哪一步 | 已有工作比较 | `matrix[]` |
| G3 | can_do | 做得出来吗 | 可行性判断 | `assumptions[]` |
| G4 | not_old_wine | 不是旧方案吗 | 创新点识别 | `novelty[]` |
| G5 | downside | 失败会怎样 | 可行性判断（风险侧）+ 冲突证据 | `conflicts[]`、`gates[G5]` |

## 2. verdict 阈值（可执行口径）

| 门 | `go` 的充分条件 | 必须降级为 `conditional` 的情形 | `no_go` |
|---|---|---|---|
| G1 | 对象/变量/基线/预期四项齐 + ≥1 条可判定判伪条件 | 缺一项，或判伪条件不可观测 | 无法写出任何判伪条件 |
| G2 | 每条主张 ≥2 个可比工作，且最近工作已明确划界 | 对照行 <2、或存在 `not_comparable` 且未给原因 | 最近工作已完整覆盖且无剩余空间 |
| G3 | 全部前提 `state != unsupported`，每类至少 1 条 | 存在 `unsupported` 前提，或某类前提完全未登记 | 关键前提缺失且无法在窗口内补齐 |
| G4 | 每条主张 `verdict != undetermined` 且边界可写 | 存在 `undetermined`，或核心主张判 `covered` | 全部主张均 `covered` |
| G5 | 每门 kill criteria 可判定，反证已登记并取舍 | 存在未取舍的相反证据，或退出成本未评估 | 失败成本高于全部预期收益 |

脚本不做价值判断，只检查**结构约束与自相矛盾**；verdict 本身由 Agent 写，脚本负责抓“判 go 但前提 unsupported”这类不一致。

## 3. 错误码（`check` 的 ERROR，必须修完再 build）

| 码 | 触发条件 | 修法 |
|---|---|---|
| `E_G1_STATEMENT` / `E_G1_SPLIT` / `E_G1_FALSIFY` | 问题陈述缺失；四项拆解不全；判伪条件为空 | 补 `question` 四个字段与 ≥1 条判伪条件 |
| `E_G1_GO` | G1 判 go 但问题未拆全或无判伪条件 | 降级或补齐 |
| `E_G2_MATRIX` | `matrix` 为空 | 每条主张至少 1 行最近工作 |
| `E_G2_OVERLAP` / `E_G2_STATUS` / `E_G2_REASON` | 枚举值越界；`not_comparable` 无原因 | 用第 5 节枚举并写原因 |
| `E_G2_FAKE` | `source_id` 不在输入对象表 | 只用 `show` 里真实存在的编号；不得编造文献 |
| `E_G3_ASSUMPTIONS` / `E_G3_STATE` / `E_G3_KILL` | 前提 <3 条；状态越界；无 kill criteria | 按 `draft-schema.md` §6 补 |
| `E_G3_UNSOURCED` | 标 `source` 但无逐字证据/定位 | 补 quote，或改判 `assumed` |
| `E_G3_GO` | G3 判 go 但存在 `unsupported` | 降级为 conditional 并给条件 |
| `E_G4_NOVELTY` / `E_G4_TYPE` / `E_G4_VERDICT_ENUM` | 无创新判定；类型/判定越界 | 用第 5 节类型学 |
| `E_G4_COVERED_BY` / `E_G4_BOUNDARY` | 判 covered 无来源；判 novel 无边界 | 补 `covered_by` 或 `boundary` |
| `E_G4_FALSE_NOVEL` | 用“检索不到/无人研究”支撑 novel 且对照行 <2 | 改判 `undetermined` 或补足对照 |
| `E_CONFLICT_UNLOGGED` / `E_CONFLICT_SILENT` | 有 contradict 证据未登记；或既无冲突也无范围声明 | 登记冲突或写 `no_contrary_found` |
| `E_GAP_STATEMENT` / `E_GAP_GLOBAL` | 无空白陈述；`global_claim=true` | 限定范围表述 |
| `E_GATE_MISSING` / `E_GATE_VERDICT` / `E_GATE_NOEVID` / `E_GATE_BADEVID` | 缺门；判定越界；无证据；证据未解析到已验证条目 | 补 G1–G5 与可核验 `evidence_ids` |
| `E_G5_COND` / `E_G5_PIVOT` | conditional/no_go 无条件或无改法 | 补 `conditions` / `pivot_if_no_go` |
| `E_DECISION` / `E_DECISION_INCONSISTENT` / `E_DECISION_SUMMARY` | 总判定越界，或与各门矛盾，或无摘要 | 让总判定不高于最弱的一门 |

## 4. 警告码（WARN：可交付但要写进 degradations）

`W_QUOTE`（引文未逐字命中）、`W_G1_VAGUE`（模糊措辞未替换）、`W_G2_BOUNDARY`（缺边界说明）、
`W_G3_CATS`（前提类别 <3）、`W_G3_VALID`（缺最小验证实验）、`W_G4_NOMATRIX`（主张无对照行）、
`W_CONFLICT_PAIR` / `W_CONFLICT_RES`（冲突缺一侧原话或缺取舍）、`W_GAP_SCOPE` / `W_GAP_BASIS`（空白未限范围或无依据）、
`W_DECISION_NEXT`（缺下一步验证）、`W_SEARCH_QUERIES` / `W_SEARCH_WINDOW` / `W_SEARCH_SCREENED`（检索协议不完整）、
`W_NUMBER`（数字在材料中无同形文本：必须标“计划值”或补依据）。

## 5. 枚举词表（脚本只接受这些值）

- `overlap`：`method` 方法重叠 / `data` 数据重叠 / `scenario` 场景重叠 / `conclusion` 结论重叠 / `none` 无重叠
- `comparison_status`：`comparable` 可直接比较 / `not_comparable` 不可直接比较（须给原因）
- `novelty.type`：`method` / `data` / `scenario_transfer`（场景迁移，**不算**理论创新）/ `conclusion_correction`（结论修正）
- `novelty.verdict`：`covered` 已被覆盖 / `novel` 相对最近工作有边界 / `undetermined` 材料不足以判定
- `assumptions.state`：`source` 有出处 / `assumed` 假设 / `unsupported` 无支撑
- `assumptions.category`：`data` / `compute` / `experiment` / `time` / `people` / `ethics`
- `gate.verdict` / `decision.overall`：`go` / `conditional` / `no_go`

## 6. 模糊措辞词表（`W_G1_VAGUE`）

`显著提升｜大幅提升｜明显改善｜性能更好｜效果更好｜更有优势｜国际领先｜填补空白｜首创｜有效解决｜较好效果｜较高精度｜大幅降低｜state-of-the-art｜significantly better｜novel and effective`

处理方式三选一：给出可测量替换（写进 `vague_replaced`）、删除该说法、或明确列入 `untestable`。

## 7. “检索不到 ≠ 新颖”的判定方法

`E_G4_FALSE_NOVEL` 只在**肯定用法**上触发。带否定/免责语境的句子不算（例如“不代表全局无人研究”“不等同于尚无人做过”），
脚本以前 14 个字符内是否出现 `不代表/不等同/不等于/并非/不是/不得/不能/避免/禁止/而非` 判定。
允许的表达：“在本材料 3 篇来源、2020–2024 范围内未见该波段定量标定”；禁止的表达：“无人研究，因此新颖”。

## 8. 证据核验的三种匹配

| 匹配 | 含义 | 是否可作证据 |
|---|---|---|
| `exact` | 归一化空白后整句逐字命中某段 | 可 |
| `segments` | quote 用 `…` 省略了中间，各段均命中 | 可（须保留省略号，不补写） |
| `despaced` | 去掉全部空白后命中（PDF 换行/CJK 断行） | 可（定位可能跨行，须回 `show` 核对） |
| `quote_not_found` | 改写、跨段拼接、编号错、材料里没有 | 不可；只进附录 A 的未命中行与 `degradations` |

命中率 = 已验证条数 / 总条数。`<80%` → `status=partial`；`status=ok` 还要求零 ERROR。

## 9. 数字溯源（`W_NUMBER`）

工作稿里形如 `数字+单位`（`%｜个月｜月｜年｜周｜天｜小时｜h｜例｜名｜人｜次｜万｜亿｜GB｜TB｜GPU｜核｜token`）的片段，
若在材料全文中找不到同形文本，列入提醒。**计划值**（如“目标 ≥300 h”）属于合法用法，只要在正文里标明“计划值/目标”，
或在 `assumption.kill_criteria` 语义下使用；不要为了让提醒消失而删掉关键阈值。

## 10. 输入对象表：别名与版本和解

`init` 会建 source/record 两级对象表并做三步机械消解：

1. **别名解析**：记录引用 `Zhang2021`/`demo_ir` 这类别名时，按 source 的 `aliases` 归并到 `S#`。
2. **重复检测**：多条记录指向同一 `S#` → 后者标 `duplicate_of`，不计入独立文献数。
3. **版本标记**：`note/status/version` 命中 `retract|撤稿|withdrawn`、`corrigend|erratum|勘误`、`preprint|预印本`、
   `supersed|取代`、`v2/v3|修订版` 时打标，写进 `result.coverage.objects` 与不确定性。

未解析记录**不猜归属**，只列进 `unresolved_records` 与 `degradations`；覆盖判定时应把它们算作“未能纳入”。

## 11. 评分维度 → 本包实现/检查项

| 评分点 | 本包对应实现 |
|---|---|
| 任务完成度 15 | 五门全覆盖（`E_GATE_MISSING`）+ 四项交付映射（§1）+ 六类覆盖统计 `coverage.six_checks` |
| 结果正确性 15 | `E_G2_FAKE` 防编造文献；`E_G4_COVERED_BY` 防“声称新颖无对照”；`E_G3_UNSOURCED` 防无出处前提；`E_G4_GO`/`E_G3_GO` 抓判 go 的自相矛盾 |
| 结果完整性 5 | 附录 A–C 显式列出未命中引文、缺口与不确定性；`status`/`degradations` 不掩盖 |
| 结果可核验性 5 | 每条证据带 `source_id + locator + quote`；`evidence_index.jsonl` 可逐行复核；`show --grep` 回看原文 |
| 质量增益 15 | 问题拆解、逐条划界、前提三分、条件式结论——基础 Agent 通常缺失的形式化结构 |
| 效率 5 | 索引/对象表/矩阵 CSV/记分卡一次生成；`counts` 给出覆盖统计 |
| 增益可验证 5 | 同一输入复跑结果一致（脚本确定性）；`selfcheck` 输出契约/证据/产物三项检查 |
| 新增能力 5 | 五门记分卡 + 对齐矩阵长表 + assumption register（kill criteria） |
| 方法改进 5 | 反证强制登记 + 版本/别名和解 + 数字溯源 |
| 创新证据 5 | 每条创新判定必须给 `covered_by` 或 `boundary`，边界可回链原文 |
| 调用易用性 3 | 五命令主路径；`SKILL.md` 与 `draft-schema.md` 给出可复制模板 |
| 运行稳定性 4 | 恒 exit 0；单材料解析失败只降级该材料；索引缺失自动重建 |
| 异常处理 3 | 空输入/坏 JSON/无文本层 PDF/缺工作稿四条路径都有明确 status 与 degradations |
| 文档完整性 3 | 本文件 + `draft-schema.md` + SKILL.md 的输入输出契约与限制 |
| 资源可复用 4 | 矩阵 CSV/记分卡/证据 jsonl 是通用表结构，换领域只需换材料 |
| 分享推广价值 3 | 五问结构可直接用于立项评审、投稿前自查 |

## 12. 不适用的场景（明确边界）

- 需要**在线检索**新文献：本 Skill 不联网，只处理输入材料；材料不足时输出 `partial` 并明说。
- 需要**实验数据统计推断**：只做证据登记与判断，不做显著性检验。
- 需要**替作者决定是否投稿**：输出的是带条件的判定与 kill criteria，决策权仍在人。
- 材料为扫描图片或无文本层 PDF 且无 OCR 工具：不转写像素，记 `no_ocr` 并降级。
