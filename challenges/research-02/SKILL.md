---
name: outline-slot-review
description: 提纲驱动（outline-first）的文献综述生成 Skill。先冻结纳排标准并按两阶段筛选留痕，再把综述结构写成"节 → 论断槽位（slot）"提纲，用逐字引文逐槽位填充或显式标为证据缺口，最后只由已填槽位渲染带引用的草稿，并输出缺口报告与覆盖率。适用于给定一批真实文献（含仅有摘要、重复记录、结论冲突、元数据不全）产出可逐句回链、可独立复核的综述：每条实质论断指向具体文献的具体段落，冲突并列呈现，研究空白落到具体证据缺口。
version: 1.0.0
license: MIT
---

# 提纲驱动文献综述（outline-slot-review v1.0.0）

## 1. 用途与适用条件

**做什么**：把"文献综述"拆成四件可检查的事，并让每一步都留下可回查的产物：

1. **筛选**（L1）：纳排标准先写定，再逐条记录决策；重复、仅摘要、低相关分别处置。
2. **提纲**（L2）：把综述结构写成"节 → 槽位"骨架，槽位是"一句论断 + 需要什么证据"的最小单位。
3. **填充**（L3）：每个槽位要么用**逐字引文**填实（`filled`），要么明确标为缺口（`gap`）；不允许含糊段落。
4. **渲染**：草稿只由已填槽位生成，段末标注来源槽位，冲突证据并列成段，缺口单列一节。

**适用**：给定研究问题 + 一批文献材料（PDF / Markdown / TXT / DOCX / JSONL / CSV 题录），需要产出带引用、可复核的综述、系统筛选记录、证据表、缺口分析与覆盖统计。

**不适用**（本 Skill 明确不做，交给相邻课题）：单篇文献精读与全文翻译；语言润色；投稿选刊；联网核验文献真实性、DOI 与影响因子；从零检索（它读的是已给出的材料）；OCR 图像。

**三条硬纪律**（题面判定内核，也是本 Skill 的失败模式清单）：

| 纪律 | 违反时的表现 | 本 Skill 的拦截 |
|---|---|---|
| 标准先于写作，且一致执行 | 先有结论再补标准；排除项没有条款 | `S101`/`S103`/`S104` |
| 每条实质论断可指回具体文献的具体位置 | 引用与论断脱节；引文被改写 | `Q104`/`Q103`（逐字比对）+ 引文无法命中即转 gap |
| 主题与空白从这批文献里长出来 | 套"背景/方法/挑战/展望"；空白是套话 | `O105` + `G103` + `outline_basis` 必填 |

## 2. 五命令主路径（先读这一节，按顺序执行）

```bash
python3 scripts/main.py init     # ① 建索引：解析 case.json / output_contract / task.md / 材料 / 题录，
                                 #   建来源清单与对象表，先写出合法的 partial result.json 与 draft.json 脚手架
python3 scripts/main.py show     # ② 打印带 locator 的材料清单；用 --source Sxx 逐篇读，--grep 检索候选引文
#   ③ 你（Agent）亲自读材料，把判断写进工作稿 /app/work/draft.json（schema 见第 5 节与 references/）
python3 scripts/main.py check    # ④ 机械校验：契约字段、标准先行、引文逐字命中、槽位覆盖、冲突对称、降级项
python3 scripts/main.py build    # ⑤ 由工作稿生成主产物 draft.md 与全部结构化产物，并 finalize result.json
python3 scripts/main.py selfcheck # ⑥ 可选：独立复检（重新回材料核验引文、回链、契约完整性）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

这条约束是硬性的，原因很实际：脚本只做确定性重活（解析、切分、定位、逐字比对、去重、统计、渲染、落盘），
**"这批文献该怎么筛选、怎么分节、哪句能支撑哪条论断、冲突怎么并列、缺什么"必须由你在 `draft.json` 里写出来**。
只跑 `build` 的后果是：只能得到一份"全缺口"的降级交付（`status=partial`，`filled_ratio=0`），它诚实但几乎没有信息量。

**典型节奏**（预算紧时的最小充分路径）：`init` → `show`（先清单，再逐篇）→ 写 `draft.json` 的
`criteria`/`screening`/`outline` → `show --grep` 找引文并填 `slots` → `check` → 按 FIX 修 → `build` → `selfcheck`。
若时间只够一部分：**先保证 `criteria`+`screening`+`outline`+每节至少 1 个 filled 槽位**，其余槽位写 gap，
这样 `build` 产出的是"结构完整、部分填实、缺口显式"的综述，而不是空的。

## 3. 调用方式与参数

```bash
python3 scripts/main.py <子命令> [--input DIR] [--output DIR] [--work DIR]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--input` | `/input`，回退 `./input`、`/app/input` | 案例输入目录（`case.json`、`task.md`、材料） |
| `--output` | `/app/output` | 产物目录；不可写时退到 CWD 下 `output/` |
| `--work` | `/app/work` | 工作稿目录；不可写时退到 CWD 下 `work/` |

`show` 的附加参数：

| 参数 | 作用 |
|---|---|
| `show` | 材料清单：source_id、路径、类型、读取方式、字节、句数、是否仅摘要、标题 |
| `show --source S01` | 该来源的块-句全文，每句带 locator（逐字复制的唯一可信来源） |
| `show --source S01 --max 200` | 放大显示条数（默认 60 句） |
| `show --grep "primary outcome" --max 20` | 在全材料中按正则检索，返回命中句 + locator |
| `show --records` | 题录表：record_id、链接到的 source_id、年、DOI、标题、重复标记 |
| `show --task` | 打印 `task.md` 与 case 指令 |

- 装载位置无关：脚本用 `Path(__file__).resolve().parent` 定位自身资源，装在 `/skills/weekly-skill` 或任意目录都可运行，不依赖 CWD。
- `--help`、`--version`、非法参数均退出码 0（顶层捕获 `SystemExit`）。
- 全部子命令退出码恒 0；磁盘上任何时刻都存在合法 `result.json`。

## 4. 输入契约与输入发现

`/input/case.json`（必需，缺失也能跑）：

| 字段 | 用途 |
|---|---|
| `case_id` / `id` | 原样回填到 `result.json.case_id` |
| `output_contract`（或 `outputs` / `deliverables`） | 需**逐键原样回填**的字段表；可为映射（键→说明）或列表（键名） |
| `task_instruction` / `instruction` / `task` / `prompt` / `goal` | 任务要求，用于语言判定与信息提取 |
| `research_question` / `question` / `topic` / `title` | 研究问题；缺失时取 `task.md` 首个标题 |
| `records` / `items` / `studies` / `literature` / `papers` / `documents` | 题录列表（也可放在 `records.jsonl` / `*.csv` / 非 case 的 `*.json`） |

材料发现顺序（每一步的恢复动作都写进 `degradations`）：

1. case.json 里出现的文件线索 → 2. `/input` 全树递归（排除 `case.json`/`task.md`/`*.pyc`/`__pycache__`）→ 3. 题录文件与材料互链。

按文件名与内容分类，并分配稳定 id：

| 前缀 | 类型 | 判据 |
|---|---|---|
| `S` | 文献 | 默认；PDF/docx/xlsx/pptx/md/txt/html 均可解析 |
| `P` | 方案 | 文件名含 protocol/prisma/search-strategy/检索式/纳排 |
| `L` | 题录 | `*.jsonl` 或文件名含 records/题录/文献表/corpus |
| `X` | 其他 | readme/license 等 |

读取方式与降级：`pdftotext` → `pypdf/PyPDF2` → 内置流解压（标 `std-miniz`，提示引文需回原文复核）→ 无文本层则标 `none` 并提示 OCR。
`abstract_only` 判定：文件名含 abstract、或文本 <3200 字符且含 Abstract/摘要 而无方法/结果段、或自述"仅摘要"。**该来源支撑的槽位强度封顶 `moderate`。**

**题录处理**：同一 DOI 或标题相似度 ≥0.94 判为重复（`duplicate_of`），重复项应在筛选里以"重复条款"排除；
题录与文献文件按 DOI 命中、标题相似度 ≥0.62、或文件名词根匹配互链；链不上的题录会在 `note` 里写明"未定位到文献文件"，不猜测。

## 5. 工作稿 `draft.json`（你写的那份）

完整字段字典见 **`references/workbook_schema.md`**；这里给出最小可跑形状：

```json
{
  "case_id": "原样",
  "research_question": "一句话",
  "outline_basis": "为什么这样分节（基于文献分布的哪条事实）",
  "criteria":  [{"criterion_id": "IC1", "type": "include", "statement": "...", "judge_rule": "...", "priority": 1, "stage": "title_abstract"}],
  "screening": [{"record_id": "R01", "source_id": "S01", "stage": "title_abstract", "decision": "include",
                 "criterion_ids": ["IC1"], "reason": "...", "locator": "sources/x.md#B5S1@455-588"}],
  "outline":   [{"sec_id": "SEC1", "heading": "...", "purpose": "...", "section_label": "benefit",
                 "lead": "可选导语", "lead_slot_ids": ["SL1"],
                 "slots": [{"slot_id": "SL1", "claim_prompt": "要产出的论断", "required_evidence": "需要什么证据"}]}],
  "slots":     [{"slot_id": "SL1", "state": "filled", "claim": "一句论断", "strength": "moderate",
                 "polarity": "supports", "conflicts_with": [],
                 "evidence_refs": [{"source_id": "S01", "locator": "sources/x.md#B5S1@455-588", "quote": "逐字原句"}]},
                {"slot_id": "SL4", "state": "gap", "gap_reason": "...", "gap_type": "retrieval_gap",
                 "search_scope": "数据库+检索式+年份", "missing_evidence": "具体缺什么"}]
}
```

- `init` 会在该路径先放一份脚手架（`_scaffold: true`，筛选项已按题录列好、`decision=pending`）。**覆盖它**并删除 `_scaffold` 键表示已填写。
- id 可自起；脚本按出现顺序归一（`SL1..`），重复 id 会自动改名并在 `check` 里提示。
- 只写你能核验的内容：`quote` 必须是 `show` 输出里的原文（含标点、单位、数字），改写/翻译/拼接都会在 `check` 里报 `Q103`/`Q104`。

## 6. 方法：三层（L1 筛选 → L2 提纲与槽位 → L3 填充与渲染）

细则与错误码处置见 **`references/method_and_error_codes.md`**；这里是判定要点。

### L1 筛选：标准先行 + 两阶段留痕

- 先 `criteria` 后 `screening`；条款写"对象 + 结局 + 设计"这类可机械判定的形式，`judge_rule` 要能落到文本。
- `exclude`/`pending` 必须挂 `criterion_ids` 与 `reason`；排除项没有条款 → `S104`（FIX）。
- 两阶段：`title_abstract` → `full_text`；全文阶段行必须能追到题录行（`S107`）。
- 重复记录（同 DOI/同标题）用重复条款排除；仅摘要可纳入但强度封顶；元数据缺失照抄不补造。
- 中途调整条款：不改已写的判定，在 `protocol.amendments` 追加时间+原因+受影响记录。
- 产物：`screening/criteria.json`、`screening/screening_log.jsonl`。

### L2 提纲：结构从文献分布里长出来

- `outline_basis` 必写：分节依据来自"结局方向""设计分布""对象/方法差异"中的哪条事实。
- 禁止默认套"背景/方法/挑战/展望"或"introduction/methods/results/discussion"；材料确实如此分布时必须说明（否则 `O105`）。
- 一槽位 = 一句论断 + 一组证据，禁止"整节一个槽位"；每节写 `purpose`，每槽位写 `claim_prompt` + `required_evidence`。
- 主题靠 `section_label` 归并，合并依据写进 `method_notes.theme_rule`；不允许两节重复同批证据讲同一件事。
- 产物：`outline/skeleton.json`。

### L3 填充与渲染：每句可回链

- `filled` 的必要条件：非空 `claim` + ≥1 条证据（`source_id` + 逐字 `quote`）；缺一即为 `Q101`（FIX）。
- 引文必须逐字命中；仅差空白/标点 → `Q103`；找不到 → `Q104`。`build` 会尝试改用最近原句（记 `changes`），找不到就丢弃证据并把槽位转 gap（记 `degradations`）。
- 强度受判据约束（见 `references/workbook_schema.md` §3）：自评高于判据 → `Q107`，`build` 自动下调并留痕；仅摘要文献 → 封顶 `moderate`（`Q106`）。
- 结论相反的证据各自成槽位（`polarity=counter` + `conflicts_with` 互指），草稿中以"与此相反"另起段并列；`X102` 单向声明由 build 补对称。
- 无证据就写 gap：`gap_reason` + `search_scope` + `missing_evidence` + `gap_type`（四类之一）齐全，缺项 `G101`，类型非法 `G102`。
- 草稿只由 filled 槽位渲染：段末 `[SLx]` 回链、句中 `[Sxx]` 引文；gap 不写正文，集中到"证据缺口"一节；研究空白由缺口字段三步推导（槽位→缺什么→检索范围），套话 `G103`。
- 产物：`draft.md`、`slots/filled.jsonl`、`slots/gaps.jsonl`、`gap_report.json`、`coverage.json`、`changes.json`。

## 7. 输出契约与 `result.json` 回填

产物清单（`/app/output`）：`draft.md`（主产物）、`outline/skeleton.json`、`slots/filled.jsonl`、`slots/gaps.jsonl`、
`screening/criteria.json`、`screening/screening_log.jsonl`、`screening/check_report.json`、`gap_report.json`、
`coverage.json`、`changes.json`、`selfcheck.json`、`result.json`。

`result.json` 三条规则：

1. **`output_contract` 的每个键原样出现**（不改名、不删除、不合并）。值按语义回填：散文类键→`draft.md` 全文；
   表类键（evidence/screening/criteria/slots/gaps）→对应行列表；统计类→`coverage` 对象；状态类→`status`；`case_id` 原样。
2. 命中不了任何语义的键：保留键名、值 `null`，并记 `degradations.type=unmapped_field`（不猜、不编）。
3. 信封字段补齐：`case_id`、`status`(`ok`/`partial`/`input_error`)、`skill`、`skill_version`、`contract_map`（契约键→产物路径）、
   `artifacts`、`sources`（含 sha256 前 16 位、读取方式、是否仅摘要）、`metrics`（同 `coverage.json`）、`uncertainty`、
   `changes`、`degradations`、`errors`、`runtime`（版本、Python、耗时、`network: disabled`）。

`status` 判定：无文献材料 → `input_error`；工作稿缺失/脚手架/修复期丢过证据/覆盖率 <0.5/存在输入错误 → `partial`；否则 `ok`。
**不存在"空 result.json"**：`init` 第一步就写合法 partial，`build` 第一行再写一次，最后才 finalize。

## 8. 校验项与错误码

`check` 把完整清单写到 `/app/work/check_report.json`（`build` 另存一份到 `/app/output/screening/check_report.json`），
并打印 `FIX`/`WARN` 计数与修复建议。`FIX` 必须修；`WARN` 由 build 自动处置或记降级。

| 组 | 码 | 检查内容 |
|---|---|---|
| 筛选 | `S101` `S103` `S104` | 标准是否存在 / 引用未知条款 / 排除未挂条款与理由 |
| | `S102` `S105` `S106` `S107` | 筛选为空 / 记录未覆盖 / 重复未标 / 阶段顺序 |
| 提纲 | `O101` `O103` | 提纲为空 / 槽位未声明 |
| | `O102` `O105` | 节缺 heading/purpose / 疑似通用模板 |
| 证据 | `Q101` `Q102` `Q103` `Q104` | 缺证据 / 未知来源 / 引文非逐字 / 引文找不到 |
| | `Q105` `Q106` `Q107` `Q108` | 引用被排除文献 / 仅摘要越级 / 强度越级 / DOI 不在材料里 |
| 缺口 | `G101` `G102` `G103` | 字段不全 / 类型非法 / 套话 |
| 草稿 | `D101` | 节首导语无槽位回链 |
| 工作稿 | `C101` `C102` `C103` | 缺失或脚手架 / 非法 JSON / case_id 不一致 |
| 冲突 | `X101` `X102` | 指向不存在的槽位 / 关系单向 |

## 9. 边界与限制

- **离线**：不联网，不核验文献是否真实存在、DOI 是否正确、期刊年份是否准确；只做材料内一致性与逐字比对。所有参考文献均标"材料转录，未联网核验"。
- **只处理已给材料**：不做新的数据库检索；材料之外的知识不进入产物。
- **不做 OCR**：扫描件/图像标 `no_text` 并提示人工转录，不猜内容。
- **近似抽取有风险**：PDF 在缺失 `pdftotext`/`pypdf` 时走内置流解压（`std-miniz`），版式与连字不可靠；这类来源的引文需回原文复核，`degradations` 会标出。
- **不做语义判断**：脚本不判断"这两篇是否真冲突""这个结论是否成立"，它只检查你写下的判断是否有逐字证据支撑、是否与强度判据一致。判断质量取决于工作稿。
- **语言**：中英混排可用；渲染语言由材料与指令自动判定（`zh`/`en`）。
- **规模**：以 5–50 篇量级为目标；数百篇时 `show` 输出需分页（`--source`/`--grep`/`--max`）读取。

## 10. 失败处理与降级

| 情况 | 行为 | 结果 |
|---|---|---|
| 缺 `case.json` | `case_id=UNKNOWN`、空契约继续；`errors` 记 `no_case_json` | `input_error`，仍产出全部产物与合法 `result.json` |
| `case.json` 非 JSON | 同上，`errors.type=case_json_invalid` | `partial` |
| 无任何材料 | 提纲全 gap；草稿只写边界与缺口清单 | `input_error`，退出码 0 |
| 工作稿缺失 / 坏 JSON / 仍是脚手架 | 兜底：2 节骨架 + 全 gap + 文献清单表（材料转录，**不作论断**）+ 参考来源 | `partial`，`degradations.type=work_draft_missing` |
| 引文找不到 | 丢弃该证据；无剩余证据则槽位转 gap | `degradations.type=quote_dropped` + `changes.action=slot_to_gap` |
| 强度越级 | 下调到判据档位 | `changes.action=strength_downgraded` |
| PDF 无文本层 / 不支持的格式 | 标注 + 提示 OCR/转格式；不猜内容 | `degradations` |
| 目录不可写 | 退到 CWD 下 `output/`、`work/` | `errors` 记录 |
| 任意未捕获异常 | 顶层捕获，仍写合法 partial `result.json` | 退出码恒 0 |

任何情况下都不会出现：空目录、非法 JSON、缺契约键、非 0 退出码。**降级是显式的**：缺什么写在 `degradations`，不确定写在 `uncertainty`。

## 11. 自查清单（`selfcheck`）

`selfcheck` 重新读输入、重新核验产物（不采信 `build` 自报），逐项打印 PASS/FAIL 并写 `/app/output/selfcheck.json`：

- [ ] `result.json` 可解析，`output_contract` 全部键存在，`case_id` 原样
- [ ] 信封字段齐全：`status`、`errors`、`degradations`、`sources`
- [ ] 八个核心产物存在：`draft.md`、`outline/skeleton.json`、`screening/criteria.json`、`screening/screening_log.jsonl`、`slots/filled.jsonl`、`slots/gaps.jsonl`、`gap_report.json`、`coverage.json`
- [ ] 已填槽位的每条引文都能重新在材料中逐字命中
- [ ] `outline` 声明的槽位 = 产物里的槽位（filled ∪ gaps），无悬空、无遗漏
- [ ] 草稿段落标记 `[SLx]` 都在声明范围内；`[Sxx]` 引文都能解析到来源
- [ ] 每个缺口都有合法 `gap_type` 与 `search_scope`
- [ ] `gap_report.json` 无套话（`G103` 词表）
- [ ] `coverage.json` 的计数与产物文件行数一致

人工再确认三件事（脚本判不了）：分节是否真的来自这批文献；每条 `claim` 是否就是引文所支持的那句话；冲突是否被并列而不是被选择性引用掩盖。

## 12. 评分维度 → 实现映射

| 维度（分值） | 评分点 | 本 Skill 的落点 |
|---|---|---|
| 实际效果（40） | 完成度 15 | 筛选→提纲→填充→缺口→草稿闭环；每层都有产物文件，不是一段散文 |
| | 正确性 15 | 逐字引文比对（`Q103`/`Q104`）+ 强度判据复算（`Q106`/`Q107`）+ 冲突并列 + DOI 反查（`Q108`） |
| | 完整性 5 | 槽位全覆盖（filled ∪ gap = outline 槽位）；排除项有条款与理由；未处理项写明原因 |
| | 可核验性 5 | 每个证据行带 `locator` + 逐字 `quote`；`changes.json` 记录每处修补；`selfcheck.json` 独立复检 |
| 使用增益（25） | 质量增益 15 | 结构（提纲+槽位）替代"摘要拼接"；回链率与冲突并列可直接对比；兜底保证不空手 |
| | 效率增益 5 | `show` 一次给出清单/locator/检索命中，免去逐文件翻找；`check` 给出可执行的修复项；`coverage.json` 提供 `{sections, slots, evidence, filled_ratio}` 计数 |
| | 增益可验证 5 | `metrics` 与 `coverage` 全部可复算；`method_notes` 记录强度判据/渲染规则/主题归并依据 |
| 创新增益（15） | 新增能力 5 | 提纲-槽位填充范式 + 槽位级缺口 + 段末回链标记，三者在产物中互相可验 |
| | 方法改进 5 | 引文无法逐字命中时**降级为缺口而不是改写引文**；强度越级自动下调并留痕 |
| | 创新证据 5 | `references/` 给出字段字典与错误码表；同一套码在 `check`/`build`/`selfcheck` 一致复用 |
| 可靠体验（10） | 调用易用 3 | 五命令主路径 + `--help`/`--version`；默认路径可用，无需参数 |
| | 运行稳定 4 | 纯标准库、离线、不依赖 CWD；PDF 三级回退；重跑结果一致 |
| | 异常处理 3 | 9 类降级路径全部 exit 0 且 `result.json` 合法；`degradations`/`errors` 分开记 |
| 生态贡献（10） | 文档完整 3 | 本文件 + `references/` 三份（schema、方法与错误码、调用示例） |
| | 可复用 4 | 换材料即可复用：契约按语义匹配、题录自动去重、错误码可扩展；`FIELDS`/`DES`/`CODES` 三处集中可改 |
| | 分享价值 3 | 提纲模板、槽位 schema、错误码表可直接作为他人综述流程的检查清单 |

## 13. 最小调用示例（示例，非正式案例结果）

输入（示例）：

```
/input/case.json          {"case_id":"DEMO-1","research_question":"...","output_contract":{"review_draft":"...","screening_log":"...","evidence_table":"...","gap_report":"...","coverage":"..."}}
/input/sources/S01.md     试验类材料，报告指标下降
/input/sources/S02.md     一项队列，报告无差异
/input/records.jsonl      两条题录（含 1 条重复）
```

调用：

```bash
python3 scripts/main.py init            # 材料 3 个（source 2 / records 2）契约字段 5 个
python3 scripts/main.py show --source S01
# → 从输出里逐字复制原句到 slots[].evidence_refs[].quote（不要改写、不要翻译）
# → 同时复制该句的 locator，例如 "sources/S01.md#B5S1@<start>-<end>"
python3 scripts/main.py check           # check: 0 FIX / 1 WARN -> 就绪，可 build
python3 scripts/main.py build           # build: status=ok 章节=2 槽位=2 已填=2 缺口=0 覆盖率=100% 引文=2
python3 scripts/main.py selfcheck       # selfcheck PASS  12/12 项通过
```

示意输出（**示例，非正式案例结果**）：

```markdown
## <章节标题>
<可选导语> [SL1]
现有研究提示，<来自 S01 的逐字证据所支持的论断>[S01]。 [SL1]

## <章节标题>
与此相反，初步证据提示，<来自 S02 的反向论断>[S02]。 [SL2]
```

（`<…>` 为占位符：正式运行时必须换成你在 `draft.json` 里写的真实论断与材料逐字引文。）

完整示例（含字段、`check` 报错样例、兜底输出样例）见 **`references/usage_example.md`**。

## 14. 文件清单、版本与维护

| 文件 | 作用 | 大小 |
|---|---|---|
| `SKILL.md` | 本说明（入口） | ~17 KB |
| `scripts/main.py` | 五命令 CLI：init / show / check / build / selfcheck | ~21 KB |
| `scripts/rules.py` | 规则层：工作稿模型化、校验、修补、渲染、契约回填 | ~29 KB |
| `scripts/kit.py` | 文本层：环境与输入发现、解析、定位切分、引文校验、强度判据、错误码目录 | ~29 KB |
| `references/workbook_schema.md` | `draft.json` 字段字典、locator 规范、强度判据、产物与契约回填表 | ~8 KB |
| `references/method_and_error_codes.md` | 三层方法论细则、错误码表、降级表、维护入口 | ~8 KB |
| `references/usage_example.md` | 最小调用示例（标注示例）、产物片段、套用新案例的改动点 | ~7 KB |

版本 1.0.0；Python ≥3.8；仅标准库；无网络；无第三方依赖；`scripts/` 内无第三方导入、无 `__pycache__` 依赖。
若需扩展：改强度阈值→`kit.strength_hint()`；改设计分档→`kit.DES`；加错误码→`kit.CODES`；改契约映射→`rules.FIELDS`，
四处改动都必须同步 `references/` 对应表格（见 `method_and_error_codes.md` §7）。
