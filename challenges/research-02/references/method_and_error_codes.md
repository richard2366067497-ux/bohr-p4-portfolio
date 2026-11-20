# 方法与校验规则（outline-slot-review v1.0.0）

三层结构：**L1 筛选（标准先行）→ L2 提纲与槽位（结构骨架）→ L3 填充与渲染（证据回链）**。
每层都有"判定规则 + 产物 + 错误码"，错误码清单见 §5，降级处置见 §6。

## 1. L1 筛选：标准先于筛选，两阶段留痕

**判定规则**

1. 先写 `criteria`，再写 `screening`。任何"先看结果再补标准"的写法会在 `check` 中暴露为"排除行没有 criterion_id"。
2. 每条形如"对象 + 结局 + 设计"的可机械判定条款；`judge_rule` 必须能落到材料文本（出现什么词、报告什么结局）。
3. `exclude` 只在命中条款时使用；重复文献、仅摘要、元数据缺失按下面处置，不要混为一条"质量差"。
4. 两阶段：`title_abstract`（题录/摘要能否判）→ `full_text`（全文是否支持纳入）。全文阶段行必须能追到题录阶段行（`S107`）。
5. 中途改条款：不改动已写的判定，改为在 `protocol.amendments` 追加一条（时间 + 原因 + 受影响记录），保持"筛选留痕"。

**常见情形的处置口径**

| 情形 | 处置 |
|---|---|
| 重复记录（同 DOI/同标题） | 保留一条，其余 `exclude` + `criterion_id=EC*`（重复条款），`reason` 写清与哪条同源 |
| 仅有摘要 | 可纳入，但该来源支撑的槽位强度封顶 `moderate`（`Q106`）；在 `reason` 注明"仅摘要" |
| 元数据不全（缺年/DOI） | 照材料转录，缺项留空并写进 `degradations`；**不补造** |
| 低相关 | `exclude` 并给出条款与理由，不静默丢弃 |
| 检索为空 | 不写正文；`screening` 保留空结构，`status=partial`，在 `uncertainty` 说明 |

## 2. L2 提纲与槽位：结构从文献里长出来

**判定规则**

1. 分节依据必须写进 `outline_basis`：来自"结局方向分布""设计分布""对象/方法差异"中的哪条事实。
2. 禁止默认套用"背景/方法/挑战/展望"或"introduction/methods/results/discussion"。若材料确实如此分布，必须在 `outline_basis` 说明，否则 `O105`。
3. 每节写 `purpose`（这一节回答研究问题的哪一面）；每槽位写 `claim_prompt`（要产出的论断）+ `required_evidence`（什么样的证据才够）。
4. 槽位是**最小可判定单位**：一个槽位 = 一句论断 + 一组证据。禁止"整节一个槽位"。
5. 冲突独立成槽位：结论相反的两条证据不要塞进同一槽位，各自 `polarity=supports/counter` 并互指 `conflicts_with`。
6. 主题重叠用 `section_label` 标记并在 `method_notes.theme_rule` 说明合并依据；不允许两节重复同一批证据讲同一件事。

## 3. L3 填充与渲染：每句可回链

**判定规则**

1. `state=filled` 的必要条件：非空 `claim` + ≥1 条 `evidence_refs`（`source_id` + 逐字 `quote`）。
2. `quote` 必须从材料**逐字复制**（含标点、单位、数字）。改写、翻译、拼接、跨句缝合都不算命中（`Q103`/`Q104`）。
3. 证据不足 → `state=gap`，写 `gap_reason` + `search_scope` + `missing_evidence` + `gap_type`。**不允许"写一句像结论的话"来占位**。
4. 强度与证据匹配（见 `workbook_schema.md` §3）：单篇 RCT=moderate；仅摘要封顶 moderate；有冲突再降一档。
5. 草稿渲染：段落只由 filled 槽位生成，段末 `[SLx]` 回链；`counter` 槽位以"与此相反"另起段；gap 不写正文，集中在"证据缺口"一节。
6. 研究空白由缺口字段推导：`槽位 → 缺什么 → 在什么检索范围内补`。三段缺一不可，禁止"未来研究应进一步探索"式收尾（`G103`）。

## 4. 构建期自动修补（写入 `changes.json` 与 `degradations`）

| 触发 | 处置 | 记录 |
|---|---|---|
| `quote` 仅差空白/标点 | 替换为材料中的逐字原句 | `changes.action=quote_replaced`（human_confirm=false） |
| `quote` 高度相似但非逐字（≥0.86） | 替换为最近原句 | `changes.action=quote_replaced`（human_confirm=true，需人工确认语义） |
| `quote` 找不到 | 丢弃该证据行；若无剩余证据 → 槽位转 gap | `degradations.type=quote_dropped` + `changes.action=slot_to_gap` |
| 自评强度 > 判据 | 下调到判据档位 | `changes.action=strength_downgraded` |
| 冲突单向声明 | 自动补对称 | `coverage.conflict_pairs` 计数；`repairs.sym` |
| 工作稿缺失/脚手架/坏 JSON | 走兜底最小交付 | `degradations.type=work_draft_missing` |

修补的**唯一目的是不把不可核验的内容留在产物里**；任何改写都在 `changes` 里保留 before/after。

## 5. 校验错误码

`check` 输出到 `/app/work/check_report.json`，`build` 把同一份清单写到 `/app/output/screening/check_report.json`。
`FIX` 必须修；`WARN` 由 build 自动处置或已记入 `degradations`。

| 码 | 含义 | 级别 | 处置 |
|---|---|---|---|
| S101 | 纳排标准缺失 / 无 include 条款 | FIX | 补条款 |
| S102 | 筛选记录为空 | WARN | 逐条给 decision |
| S103 | 引用不存在的 criterion_id | FIX | 改用已声明条款 |
| S104 | 排除/待定未挂条款或未给理由 | FIX | 补 criterion_ids + reason |
| S105 | 输入记录未出现在筛选记录 | WARN | 补该行 |
| S106 | 重复记录未排除 | WARN | 标 duplicate_of 并排除 |
| S107 | 全文阶段行缺题录阶段行 | WARN | 补两阶段记录 |
| O101 | 提纲为空（<2 节或无槽位） | FIX | 写提纲 |
| O102 | 节缺 heading/purpose | WARN | 补字段 |
| O103 | 槽位未在 outline 声明 | FIX | 删或并入 |
| O105 | 提纲疑似通用模板 | WARN | 补 outline_basis |
| Q101 | filled 但缺 claim/证据 | FIX | 补证据或改 gap |
| Q102 | 未知 source_id | FIX | 改用输入中的来源 |
| Q103 | 引文仅差异于空白/标点 | FIX | 用逐字原句 |
| Q104 | 引文找不到 | FIX | 重取或改 gap |
| Q105 | 引用被排除/待定文献 | WARN | 换来源或说明 |
| Q106 | 仅摘要文献支撑 strong | WARN | 封顶 moderate |
| Q107 | 自评强度高于判据 | WARN | 下调 |
| Q108 | 文本中的 DOI 不在材料里 | WARN | 删除（疑似编造） |
| G101 | 缺口字段不全 | FIX | 补三字段 |
| G102 | gap_type 非法 | FIX | 用四类之一 |
| G103 | 缺口/空白用套话 | WARN | 落到具体缺口 id |
| D101 | 节首导语无槽位回链 | WARN | 补 lead_slot_ids 或删 lead |
| C101 | 工作稿缺失/仍为脚手架 | FIX | 按 schema 填写 |
| C102 | 工作稿不是合法 JSON | FIX | 修语法 |
| C103 | case_id 与输入不一致 | WARN | 对齐 |
| X101 | conflicts_with 指向不存在的槽位 | WARN | 删除 |
| X102 | 冲突关系单向 | WARN | build 自动补对称 |

## 6. 降级与失败处置

| 输入/运行状况 | 行为 | 结果 |
|---|---|---|
| 缺 `case.json` | 用 `case_id=UNKNOWN`、空契约继续；`errors` 记录 `no_case_json` | `status=input_error`，仍产出全部产物 |
| `case.json` 非 JSON | 同上，`errors.type=case_json_invalid` | `status=partial` |
| 无任何材料 | 提纲全 gap，草稿只写边界与缺口 | `status=input_error`，退出码 0 |
| 工作稿缺失/坏 JSON/脚手架 | 兜底：2 节骨架 + 全 gap + 文献清单表（材料转录，不作论断） | `status=partial`，`degradations` 说明缺失项 |
| PDF 无文本层 | `method=none` + 提示 OCR；`degradations.type=no_text` | 该来源不可引用，不猜内容 |
| PDF 无 pdftotext/pypdf | 内置流解压近似抽取，标 `std-miniz` 并提示引文需回原文复核 | 可读但需复核 |
| 图像/xlsx/pptx 等 | 明确标注不支持或按 OOXML 抽文本 | `degradations` 记录 |
| 目录不可写 | 退到 CWD 下 `output`/`work` | `errors` 记录；退出码 0 |
| 任意未捕获异常 | 顶层捕获，仍写合法 partial `result.json` | 退出码恒 0 |

## 7. 复现与维护

- **改强度阈值**：`scripts/kit.py` 的 `strength_hint()`，同时更新 `workbook_schema.md` §3 与本文件 §3。
- **改设计分档**：`scripts/kit.py` 的 `DES` 表（正则 → 名称 → 分值），同步文档。
- **加错误码**：`scripts/kit.py` 的 `CODES`，并在本文件 §5 增行（码必须唯一）。
- **改契约映射**：`scripts/rules.py` 的 `FIELDS`（先专有后通用，顺序敏感），同步 `workbook_schema.md` §5。
- **回归**：`init → show → check → build → selfcheck` 全链，要求 `selfcheck` PASS 且 `result.json` 契约字段齐全。
