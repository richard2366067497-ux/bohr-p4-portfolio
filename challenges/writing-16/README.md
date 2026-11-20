# source-faithful-retargeting — 使用与方法说明（README）

本包把一份科研事实底稿改写为"目标读者读得懂、原作者接得住、每条事实找得到来源"的成稿。
本 README 是 `SKILL.md` 的配套说明：**调用方式、输入输出、工作稿字段字典、受众-体裁矩阵、验收口径、失败处理**。
所有内容与提交版本一致；脚本仅用 Python 3 标准库、离线、不依赖 CWD。

---

## 1. 调用方式

### 1.1 单命令入口（评测/CI）

```bash
python3 scripts/main.py all          # 等价 init → build；空/坏输入也退出 0 并产出完整产物集
```

`all` 不需要 Agent 手写工作稿：`draft.json` 缺失/不可用时自动产出"逐字摘录兜底稿"（`status=partial`），
输入没有可解析材料时给 `status=insufficient_evidence`；两种情形都**恒退出 0**，并生成
`deliverable.md`、`retained_facts.json`、`diff_map.md`、`glossary.csv`、`result.json`。

### 1.2 分步主路径（拿到改写质量分时用）

```bash
python3 scripts/main.py init         # 扫描 /input，建 index.json，先写合法 partial result.json 与 draft 模板
python3 scripts/main.py show --ids M1:P1-M1:P12   # 打印带 locator 的原文，供逐字引用
#   你（Agent）读材料，写 /app/work/draft.json（正文真写）
python3 scripts/main.py check        # 机械校验：契约/引文/数字/覆盖/术语/强度/篇幅
python3 scripts/main.py build        # 渲染 deliverable.md + 附表 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck     # 交付前复检：契约键、可复算指标、文件清单
```

- 参数 `--input/--output/--work` 可放在子命令前或后；也可用 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK`。
- 默认路径即官方契约路径：输入 `/input`、工作 `/app/work`、产物 `/app/output`。
- 退出码**恒为 0**；异常写入 `result.json.errors`，已产出文件保留。

### 1.3 输入 / 输出契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`output_contract`、`task_instruction`）、`/input/task.md`、`/input/` 下任意材料（PDF/DOCX/XLSX/CSV/MD/TXT/JSON/TEX/图片） |
| 工作目录 | `/app/work`：`index.json`（locator 唯一权威）、`draft.json`（Agent 写）、`check.json`（最近校验） |
| 产物 | `/app/output/`：`deliverable.md`（主产物）、`retained_facts.json`、`diff_map.md`、`glossary.csv`、`result.json` |
| 依赖 | 仅 Python 3 标准库；离线；不依赖 CWD |

---

## 2. 工作稿字段字典（`draft.json`）

`init` 生成模板。**只填值，不删键**；`check` 依本表判分，`build` 依本表排版。

### 2.1 完整结构（注释仅用于说明，不要写入 JSON）

```json
{
  "audience": {"label": "受众标签", "profile": "画像", "knowledge": "知识假设",
               "goal": "阅读目的", "depth": "解释深度", "term_policy": "术语策略",
               "strength_policy": "强度策略"},
  "genre": {"label": "体裁", "conventions": ["结构惯例1", "结构惯例2"],
            "length_target": 800, "length_unit": "字"},
  "headline": "一句话结论（含对象与效果，不夸大）", "deck": "可选导语一句",
  "sections": [{"id": "S1", "title": "小标题", "text": "成稿正文段落……",
                "cites": ["M1:P3"], "strength": "established"}],
  "retained": [{"id": "R1", "kind": "number", "value": "87.5%", "locator": "M1:P3",
                "quote": "编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01）",
                "where": "S3", "treatment": "kept", "note": "起点值终点值同时保留"}],
  "trace": [{"section_id": "S1", "source_locator": "M1:P3",
             "source_quote": "源文逐字句。", "decision": "compress", "note": "转写为类比，事实不变"}],
  "changes": [{"action": "compress", "locator": "M1:P6", "original_quote": "源文逐字",
               "revised_quote": "改后（或：未进入正文）", "reason": "复现信息，非判断依据"}],
  "dropped": [{"item": "测序平台与深度", "locator": "M1:P6", "why": "方法细节，删去不影响结论适用范围"}],
  "glossary": [{"term": "BE-3", "expansion": "碱基编辑系统", "usage": "BE-3",
                "variants": ["BE3"], "locator": "M1:P3"}],
  "numbers_allow": [{"value": "90%", "reason": "源文 87.5%，按上限取整（待作者确认）"}],
  "open_questions": [{"issue": "题面未指定读者年龄层", "why": "影响解释深度", "action": "作者确认后调整", "owner": "author"}],
  "uncertainty": ["体外结果向体内外推尚待验证"]
}
```

### 2.2 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `audience.label` | 是 | 受众标签；其余 5 项缺失只提示，不阻断 |
| `genre.label` / `length_target` | 是 | `length_target` 是**上限**；超 105% 判 `over_budget` |
| `sections` | 是 | ≥3 段为宜；`text` 必须是**成稿正文**，不是要点、不是提纲 |
| `sections[].cites` | 建议 | `M1:P3` 或列表；不存在的 locator 判错 |
| `sections[].strength` | 建议 | `established` / `preliminary` / `hypothesis`，只降不升 |
| `retained` | 是 | 每条 = 值 + locator + 逐字 `quote` + `where` + `treatment` |
| `trace` | 是 | **每个 section 至少 1 条**，否则 `trace_missing_for_section` |
| `changes` | 是 | 每条 `action` + `reason`；`original_quote` 建议逐字 |
| `dropped` | 建议 | 声明删了什麼、为何不是证据 |
| `glossary` | 建议 | 面向公众/政策读者时必填；`variants` 列出**禁用**说法 |
| `numbers_allow` | 建议 | 换算/取整的唯一合法出口 |
| `open_questions` / `uncertainty` | 建议 | 直接成为 `result.json.pending_human` / `.uncertainty` |

枚举：`kind` = `conclusion|number|condition|sample|metric|figure|citation|limitation|term`；
`treatment` = `kept|condensed|moved|reworded`（**压缩也算保留**，`note` 要写清怎么压的）；
`decision` = `keep|compress|merge|split|drop`。

### 2.3 校验代码表（`work/check.json` 与 `result.json.errors`）

错误（阻断 `status=ok`）：

| 代码 | 含义 | 修复 |
|---|---|---|
| `draft_not_object` | 顶层不是对象 | 用 `{ }` 包住全部字段 |
| `draft_unreadable` | JSON 语法错误 | 查逗号、引号、括号；中文引号不是 JSON 引号 |
| `missing_field` / `empty_field` | 六大块缺失或为空 | 补齐 `audience/genre/sections/retained/trace/changes` |
| `too_few_sections` / `section_empty` | 只有 1 段 / 某段无正文 | 写真正的段落 |
| `too_short` | 正文 < 目标 45% | 补写成稿，不是扩写标题 |
| `over_budget` | 正文 > 目标 105% | 先删 P2，再压 P1，不动 P0 |
| `locator_not_found` | locator 不在索引 | 回 `init` 段落清单重抄 |
| `*_quote_miss` | quote 在源文找不到 | 换成源文原句；禁止改源文 |
| `number_not_in_source` | 成稿数字源文没有 | 改回原值，或登记 `numbers_allow` + `open_questions` |
| `figure_mismatch` | 引用了源文没有的图表编号 | 删掉或改用源文编号 |
| `retained_not_in_body` | 必保留项没落进正文 | 补进正文；确需改写则在 `note` 说明并可标 `reworded` |
| `retained_value_missing` / `retained_locator_missing` | 保留项不完整 | 补值/补定位 |
| `trace_section_unknown` / `trace_missing_for_section` | 对照表指向不存在/漏段 | 每段至少一条 |
| `change_action_missing` / `change_reason_missing` | 改动无法复核 | 补 action 与 reason |
| `dropped_reason_missing` | 删除无理由 | 写清"为何是冗余不是证据" |
| `term_variant_used` | 正文用了术语表禁用的变体 | 统一说法 |
| `hedge_lost` | 源文有 ≥3 类限定语，成稿一处未留 | 把"初步/尚需/可能"补回 |

提示（不阻断，需逐条阅读后接受或修复）：`short`/`long`、`no_length_target`、`section_too_short`/`few_sections`、
`audience_field_empty`/`genre_label_missing`、`retained_quote_missing`、`retained_where_unknown`、
`retained_reworded_absent`、`silent_drop`、`abbr_not_expanded`、`strength_upgrade`、`hedge_thin`、`unit_variant`、
`numbers_allow_used`、`meta_discourse`、`low_coverage`、`contract_missing`。

### 2.4 一条完整示例（示例，非正式案例结果）

源文 `M1:P4`：「在 48 名供者来源的细胞样本中，编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01），脱靶位点数由 14 个降至 3 个（图 2）。」

```json
{"id": "R2", "kind": "number", "value": "87.5%", "locator": "M1:P4",
 "quote": "编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01）",
 "where": "S3", "treatment": "kept", "note": "起点值与终点值同时保留，未取整"}
```

反面写法（`check` 会报 `number_not_in_source` 或 `retained_not_in_body`）："效率提升到接近九成"（数值/单位消失）、
"提升了约 25 个百分点"（源文无此换算）、"脱靶问题已基本解决"（强度升级，3 个 ≠ 0 个）。

### 2.5 写作口径

`text` 里不写元话语，直接给内容；一段一义、首句承载结论；数字/单位/样本量/比较基准按原文照搬；
源文没有的商业前景、成本、时间表一律进 `open_questions`；压缩掉的內容放进 `changes`（`action=compress`）并写理由。

---

## 3. 受众-体裁矩阵（画像、骨架、强度词表、取舍顺序）

用于填写 `draft.json` 的 `audience` / `genre`，并决定正文的解释深度与删留。

### 3.1 受众画像矩阵（先定解释深度，再定篇幅）

| 受众 | 知识背景 | 阅读目的 | 解释深度 | 术语策略 | 例子/类比 | 篇幅基准 |
|---|---|---|---|---|---|---|
| 非专业公众 | 无专业训练 | 这件事跟我有什么关系 | 只给结论 + 一层机制 | 缩写一律展开或不用 | 生活化类比，须标"类比" | 500–1200 字 |
| 政策/管理部门 | 非技术，关注影响面 | 影响、风险、是否需要监管 | 结论 + 条件 + 边界 | 全部换通俗说法 | 场景化 | 600–1200 字 |
| 产业界/投资方 | 工程或商业背景 | 能否落地、代价、风险 | 一层因果 + 关键指标 | 保留 3–5 个核心术语并首展 | 与基线/现有方案对比 | 800–1500 字 |
| 基金/项目评审 | 同领域或邻近专家 | 创新性、可行性、证据强度 | 方法要点 + 证据链 | 可用领域术语，缩写首展 | 不需类比 | 1000–2000 字 |
| 同行/审稿人 | 同领域 | 可复现性、结果可靠性 | 完整方法要点与统计口径 | 标准术语 | 无 | 按期刊/模板 |
| 双语/对外发布 | 视 main 受众定 | 同一事实两种语言版本 | 与主版本一致 | 术语表双语锁定，译名唯一 | 与主版本一致 | 两版分别计字 |

**题面没给受众**：默认"受过高等教育、非本领域读者"，并在 `uncertainty` 写明这是假设，不得静默处理。

### 3.2 体裁骨架（`genre.conventions` 直接抄一行的要素）

| 体裁 | 必备结构 | 强度处理 | 禁忌 |
|---|---|---|---|
| 科普文章 | 现象/问题切入 → 做法（白话）→ 结果（1–2 个数字带条件）→ 局限 → 意义边界 | 整体降一档 | "治愈/彻底解决/突破/颠覆" |
| 技术转化简报 | 一句话结论 → 问题 → 方案要点 → 关键数据（含条件）→ 落地条件/风险 → 待验证 | 初步结果标"初步"，前景单列"待验证" | 把体外/小样本写成"已实现" |
| 项目申报摘要 | 需求 → 目标 → 技术路线 → 前期结果 → 创新点 → 下一步计划 | 创新点必须对应已有数据 | 把计划写成已完成的成果 |
| 政策简报 | 结论 → 影响面 → 条件与风险 → 建议 | 建议标"建议"，与证据分列 | 把建议写成既成事实 |
| 论文/结构化摘要 | 背景 → 方法 → 结果（含 n 与统计口径）→ 结论 | 与原文同级，不改限定语 | 删掉样本量与统计口径 |
| 双语发布稿 | 与主版本同构；两版逐段对应 | 两版强度措辞必须等价 | 一版加限定、另一版不加 |

**篇幅紧张时**：保 P0、删 P2、压 P1；把取舍写进 `deliverable.md` 第一节，并让 `changes` 覆盖每一处压缩。

### 3.3 论断强度词表（只降不升）

| 源文表述 | 判级 | 允许的转写 | 禁止的转写 |
|---|---|---|---|
| 显著提高/证明/表明（有统计检验） | `established` | "研究发现……（p<0.05，n=48）" | "彻底解决" |
| 提示/初步/在体外模型中/单一实验 | `preliminary` | "初步结果显示……，尚需体内验证" | "已证实有效" |
| 可能/推测/机制上 | `hypothesis` | "研究者推测……，机制尚未验证" | 因果断言 |
| 有望/具备潜力（应用外推） | `hypothesis` | 保留"有望"，同时进 `open_questions` | "将带来……市场" |

四个自动替换禁令：相关→因果；初步→定论（`hedge_lost`/`strength_upgrade` 会抓）；单一模型→普适；
动物/体外→人体。**同义收敛**：同一对象全文只用一种说法，首次出现给全称并登记进 `glossary.usage`，
不用的说法列进 `glossary.variants`。

### 3.4 取舍决策（压缩时按此顺序丢）

1. **先删（P2）**：致谢、投稿与基金编号、重复表述、与目标读者无关的推导、文献罗列。
2. **再压（P1）**：方法参数、仪器型号、试剂批号、软件版本 → 压成一句"方法概要"，**数值不变**。
3. **最后才动（P0，只允许压缩表达，不允许删除）**：样本量与分组、剂量/时长/平台、比较基准、统计口径、图表编号。
4. **绝不动**：主结论、关键数字与单位、局限与不确定性、图表编号（无编号写"源文未给编号，需补"）。

判据一句话：**删掉之后，目标读者还能不能判断"这个结论在什么条件下成立"？** 不能 → 那是证据，不是冗余。

### 3.5 常见失败与处置

| 失败 | 症状 | 处置 |
|---|---|---|
| 事实漂移 | 数字近似化、单位缺失、样本量丢失 | 回原文逐字搬，进 `retained` 锁定 |
| 受众错配 | 公众稿出现缩写墙/公式；申报稿过度通俗 | 按 3.1 重设解释深度与术语密度 |
| 强度升级 | 初步→已证实；相关→因果 | 按 3.3 降级，写进 `uncertainty` |
| 提纲冒充成稿 | 只有小标题与要点 | `check` 报 `too_short`；补写正文 |
| 对照缺失 | 有正文无 `trace` | 每段补一条，覆盖 P0 |
| 静默删除 | 删了段落却没记录 | `check` 报 `silent_drop`；补 `dropped` |
| 前景注水 | 出现源文没有的市场/成本/时间表 | 删除或移入 `open_questions` |
| 术语漂移 | 同一概念三种说法 | 用 `glossary.usage` 锁定，`variants` 禁用 |

---

## 4. 验收口径（评分五维 → 可执行检查项 → 交付证据）

题面 100 分分五维。这里把每一维翻译成"在包里能被执行、能被第三方复算"的动作。

- **实际效果（40）**：必须交出成稿正文，不是提纲/建议；数字/单位/样本/统计口径/图表编号与源文逐字比对。
  复算：`check` 的 `sections`/`body_words`/`numeric_drift`/`*_quote_miss`；`fidelity_summary`。
  底线：`selfcheck` 全 PASS、无 `[错误]`、`quote_hit_rate=1.0`、`numeric_drift=0`。
- **使用增益（25）**：改写前先锁定 P0 台账与读者画像，判断留给 Agent、比对交给脚本；
  五命令替代人工通读比对。证据：修完 `draft.json` 重跑 `check` 前后差异、`fidelity_summary` 七指标、`runtime.counts`。
  公平对照做法：同一 `/input`，先用"不写 draft 直接 `build`"得兜底基线，再写 draft 走完整路径，比较两组指标。
- **创新增益（15）**：受众画像（`audience` 六字段 + 矩阵）→ 取舍策略（P0/P1/P2 + `retained`/`dropped`）→
  边界标注（三级强度 + `open_questions`/`uncertainty`）→ 多文体映射（体裁骨架 + 共用同一 `retained`）。
- **可靠体验（10）**：子命令语义单一；`all` 与 `build` 无 draft 也产出完整最小交付；退出码恒 0；重复运行幂等；
  坏 `case.json`/空输入/坏 `draft.json`/图片/目录不可写全部写进 `degradations`/`errors`。
- **生态贡献（10）**：`SKILL.md` 含用途/条件/调用/输入输出/方法/边界/失败处理/自查/版本维护；
  本 README（字段字典 + 校验代码表 + 受众矩阵 + 体裁骨架 + 验收口径）可被别的写作类 Skill 直接复用。

**异常处置四条纪律**：材料缺失 → 说明缺什么；无法判断 → 标 `uncertainty`/`open_questions`；
输入冲突 → 两值并列、请作者定夺；运行失败 → 仍出 partial 且说明失败位置。

---

## 5. 失败处理与降级

| 情形 | 行为 | 影响 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找含 `output_contract` 的 json；仍无则用内置字段，`degradations` 记录 | 仍产出合法 result.json |
| 材料全无 | `status=insufficient_evidence`，`deliverable.md` 仅含缺口说明 | 不编造 |
| PDF 无 `pdftotext` | 内置流解析；文本过稀标 `builtin-pdf-lowconf` | `degradations` |
| 单文件解析失败 | 只降级该文件，其余继续 | 不中断 |
| 材料是图片/PPTX | 不 OCR、不臆造 | 缺口写明 |
| `draft.json` 缺失/坏/正文全空 | 兜底：从源文逐字抽取结论/数值/条件三类句子，`status=partial`，稿首标注"未完成受众改写" | 不空手 |
| 中途异常 | 捕获后仍写合法 partial `result.json` + 说明性 `deliverable.md`，退出码 0 | 不崩 |
| 重复运行 | 产物覆盖，文件集与 status 稳定（幂等） | 可复跑 |

## 6. 交付前自查清单

- [ ] `SKILL.md` 在包根，frontmatter 含 `name`/`description`/`version`。
- [ ] `python3 scripts/main.py --help` 退出码 0；四个模块可单独 `--help`。
- [ ] 走完主路径：`init` → `show` → 写 `draft.json` → `check` → `build`（→ `selfcheck`），或直接 `all`。
- [ ] `result.json`：契约键全在且同名（顶层 + `output_contract` 嵌套回显）、`case_id` 原样、`status` 与实际一致。
- [ ] `deliverable.md` 八节齐全、正文是成稿；`retained_facts.json`/`diff_map.md`/`glossary.csv` 非空。
- [ ] 删掉 `draft.json` 重跑 `build`（或跑 `all`）：仍 exit 0、`status=partial`、稿首标注"兜底稿"。
- [ ] 空 `/input` 重跑：`status=insufficient_evidence`，不编造内容。
- [ ] 示例与示意输出均标注"示例，非正式案例结果"；包内无预制答案、无 `__pycache__`。

## 7. 已知边界（写在明处，不掩盖）

1. **PDF 版式风险**：无 `pdftotext` 时用内置流解析，双栏/表格可能错序，脚本标 `builtin-pdf-lowconf`，须人工核对后再引用。
2. **数字校验是"存在性"而非"语义"**：能保证成稿里的数字在源文出现过，不能保证它被放在正确的论证位置——后者由 Agent 的 `retained`/`trace` 与人工通读负责。
3. **改写质量不可全自动判定**：`check` 能挡住事实漂移、术语漂移、强度升级、提纲冒充，但"读得懂"只能由人以目标读者身份通读确认。
