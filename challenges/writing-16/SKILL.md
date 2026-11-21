---
name: source-faithful-retargeting
description: Retarget a scientific source (paper, technical report, abstract, data table, figure caption) into a finished piece for a named audience and genre — popular-science article, industry transfer brief, grant/application summary, journal abstract, bilingual release — inside a hard length budget, while every number, unit, sample size, condition, figure/table reference and claim strength stays traceable to a verbatim source locator. Use when a task asks to "rewrite this result for <readers>", "turn this paper into a briefing / application / popular piece", "convert the same result into several genres", or "compress without losing the evidence". The script indexes and checks; the Agent reads, judges and writes the actual draft; build never fails and always emits a valid result.json.
version: 10.0.0
---

# source-faithful-retargeting — 受众/体裁改写，且每句话都留得住来源

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册给出任务本质与
判分要点、错误做法→正确做法、8 步求解框架、量化口径与公式（证据保留率 / 数值一致率与复算容差 /
论断越级率 / 缩写首现展开率·术语锁定率·段落可追溯率 / 效率增益）、领域知识与单位陷阱、交付物
清单与 22 项专家检查表、完整虚构案例、交付前门控。执行顺序固定为：先读手册 → 再按求解框架逐
阶段落盘冻结产物 → 交付前逐项勾选手册 §5.2 专家检查表。手册与本文冲突时，契约键名与入口命令以
本文为准，方法与判分口径以手册为准。

## 0. 输出契约样例（result.json 骨架，逐键回填）

下面是骨架示例：真实运行时每个键都用本次运行的实测值回填，顶层与嵌套 `output_contract` 同时出现，
不留空壳；示例值仅说明类型。

```json
{
  "case_id": "demo-001",
  "status": "ok",
  "output_contract": {
    "dropped": [],
    "retained": [],
    "errors": {"count": 0, "items": [], "note": "本次运行无阻塞错误"},
    "deliverable": "deliverable.md",
    "preserved_facts": [],
    "evidence_map": [],
    "change_log": [],
    "glossary": [],
    "uncertainty": []
  }
}
```

## 0.1 单命令入口（等价入口，一次性跑完整流程）

评测只跑这一条也能过：**无工作稿时自动走逐字兜底稿**，仍然产出 `deliverable.md`、`retained_facts.json`、
`diff_map.md`、`glossary.csv` 与逐键回填的 `result.json`，退出码恒 0：

```bash
python3 scripts/main.py all --input /input --work /app/work --output /app/output
```

`all` = `init → build → selfcheck` 的封装：`build` 无条件 finalize（契约顶层+嵌套回填、`errors` 用
`{count, items, note}` 形状给出真实计数），工作稿缺失时用逐字抽取兜底并在稿首与 `degradations` 标注
“未完成受众改写”。这是保底路径；语义改写质量仍取决于 Agent 写的工作稿。

## 0.2 30 秒上手：五命令主路径（Agent 增强路径，**先读这一节**）

```bash
python3 scripts/main.py init       # 解析 /input，建材料+段落+候选保留项索引，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的原文（--ids / --grep / --mat），供逐字引用
#   ↓ 你（Agent）亲自读材料，写工作稿 /app/work/draft.json（正文真写，不是提纲）
python3 scripts/main.py check      # 机械校验：契约/引文命中/数字漂移/保留覆盖/术语/强度/篇幅
python3 scripts/main.py build      # 由工作稿生成 deliverable.md + 附表 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 复检产物：契约字段、可复算指标、文件清单（交付前跑一次）
```

> **脚本不代替阅读理解：必须先读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> 没有工作稿时 `build` 只产出“逐字摘录兜底稿”（`status=partial`，稿首标注“未完成受众改写”），
> 保证不空手而归，但对不上一次真正的改写。`init`/`build` 是唯一写 `result.json` 的步骤；
> `show`/`check`/`selfcheck` 只读。

---

## 1. 用途与适用条件

**做一件事**：把一份科研事实底稿，改写成"目标读者读得懂、原作者接得住、每条事实找得到来源"的成稿，并交付可逐段复核的记录。

适用（命中任一条即可触发）：论文/预印本 → 科普文章、产业转化简报、项目申报摘要、政策简报、
新闻稿；技术报告 → 立项/投资/合作说明；同一成果 → 多体裁、多受众、双语版本（换读者不换数字）；
硬篇幅压缩（“不超过 800 字”）仍保住结论、样本、条件与图表引用；摘要/图注/结果段 → 结构化产物。

不适用或必须明确拒绝：没有任何源材料只给题目（不给结论、不造数据，列所需材料清单）；要求补写
源文没有的市场规模/成本/时间表/机制（拒绝写入正文，进 `open_questions`）；统计推断、显著性重算、
meta 分析（交回作者/统计人员）；代替同行评审、伦理审查、涉密解密判断（只做“标注 + 待授权”）。

三条硬线（违反任一条即失败）：**不改源文的数字与单位**、**不写源文不支持的新结论**、
**删冗余不删证据**。

---

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`output_contract`、`task_instruction`）、`/input/task.md`、`/input/` 下任意材料（PDF/DOCX/XLSX/CSV/MD/TXT/JSON/TEX/图片） |
| 工作目录 | `/app/work`：`index.json`（索引，locator 的唯一权威）、`draft.json`（你写的工作稿）、`check.json`（最近一次校验报告） |
| 产物 | `/app/output/`：`deliverable.md`（主产物）、`retained_facts.json`、`diff_map.md`、`glossary.csv`、`result.json` |
| 依赖 | 仅 Python 3 标准库；离线；**不依赖 CWD**（脚本以 `Path(__file__)` 定位自身，默认目录可被 `--input/--work/--output` 或 `SKILL_INPUT/SKILL_WORK/SKILL_OUTPUT` 覆盖） |
| 退出码 | **恒为 0**；异常写入 `result.json.errors`，已产出的文件保留 |
| 预算 | 64 次模型请求 / 900 秒 / 单次回复 16384 tokens。约 700 秒时立即 `build` 收口，不要再打磨文笔 |
| 语言 | 成稿语言跟随案例材料与 `task_instruction`（通常中文）；脚本本身与语言无关 |

输出目录不可写时，自动退到包旁边的 `work/`、`output/`，并把该降级写进 `degradations`。

---

## 3. 主流程（按序执行，不要跳步）

### 3.1 `init`：先把事实底稿变成可引用的对象表

```bash
python3 scripts/main.py init
```

它做五件事，并在**任何解析之前**先写一份合法的 partial `result.json`（契约字段已按原名占位）：

1. 递归扫描 `/input`，按扩展名 + 魔数识别材料；PDF 优先 `pdftotext`，无则内置流解析并标 `builtin-pdf-lowconf`；DOCX/XLSX 走 zip+XML；图片不 OCR（记 `image-no-ocr`，不臆造图注）。
2. 每份材料切段编号 `M1:P1`、`M1:P2`……这是全文唯一允许的定位语法。
3. 抽数字+单位对、缩写、图表引用（`图 3`/`Table 2`）、引文标记（`[12]`/`(Smith 2020)`）、hedge（初步/提示/可能/尚待）。
4. 生成**候选必保留项**清单（结论句/带单位数值/样本量/图表引用/引文/限定条件），作为 `check` 算“保留覆盖率”与“静默删除”的分母。
5. 解析工作单：受众、体裁、篇幅上限、双语要求，并打印命中依据（`<- '原文'`）；未命中就写“未识别，按默认”。

`init` 还会生成 `draft.json` 模板（字段齐全、留空待填）。**不要删字段**，只填值。

### 3.2 `show`：读原文，不要读文件名

```bash
python3 scripts/main.py show --ids M1:P1-M1:P12
python3 scripts/main.py show --grep "sample|dose|局限|significant" --limit 20
python3 scripts/main.py show --mat M2            # 只看某份材料
```

至少读完：摘要/首段、所有含数字的段落、方法与条件段、局限段、图表标题与引文。**按读到的文本判断，不按文件名、领域标签或题面假设补内容。**

### 3.3 写工作稿 `/app/work/draft.json`（**这一步是你的主要工作**）

结构见 `references/draft-schema.md`。六个块必须齐全：

1. `audience`：读者标签 + 知识背景 + 阅读目的 + 解释深度 + 术语策略 + 强度策略。
2. `genre`：体裁 + 结构惯例 + 字数上限。
3. `headline` / `deck`：一句话结论（含对象与效果，不夸大）。
4. `sections[]`：**真正的成稿正文**，一段一义、结论先行；每段带 `cites`（源 locator）与 `strength`（established/preliminary/hypothesis）。
5. `retained[]`：必保留项台账，每条 = 值 + locator + **逐字 quote** + `where`（落在哪一段）+ `treatment`（kept/condensed/moved/reworded）。
6. `trace[]` / `changes[]` / `dropped[]` / `glossary[]` / `open_questions[]` / `uncertainty[]`：逐段对照、每处删改的理由、被删项为何不是证据、术语统一、待确认。

写正文而不是写建议：`sections[].text` 是要直接交付的段落。**不要写"本文将讨论……"这类元话语。**

### 3.4 `check`：把机械问题清零

```bash
python3 scripts/main.py check
```

报告分 `[错误]`（阻断 `ok` 状态）与 `[提示]`（需阅读后接受或修掉），并写入 `work/check.json`。修复顺序固定：

1. 引文没命中 → 换成源文里真有的一句（**不许改源文凑通过**）；
2. locator 不存在 → 回 `init` 的段落清单重抄；
3. 数字对不上 → 改回原值；确需换算/取整，写进 `numbers_allow` 并同时进 `open_questions`；
4. 篇幅超限 → 先删 P2（重复表述、无关推导、致谢投稿），再压 P1（方法参数），**不动 P0**；
5. 术语漂移/缩写未展开 → 改正文或在 `glossary` 登记 `variants`。

### 3.5 `build`：排版 + 无条件 finalize

```bash
python3 scripts/main.py build
```

- 生成 `deliverable.md`（八节：转换说明 / 正文 / 逐段对照 / 必保留项台账 / 删改清单 / 术语表 / 待确认 / 自检）。
- 生成 `retained_facts.json`、`diff_map.md`、`glossary.csv`（供原作者继续编辑与逐段复核）。
- **无条件**重写 `result.json`：`output_contract` 的每个原始键按原名回填，缺值按原类型给 `null`/`[]`/`{}`，并写 `contract_fill` 统计；`status` 按实况给 `ok`/`partial`/`insufficient_evidence`/`input_error`。

### 3.6 `selfcheck`：交付前复检

```bash
python3 scripts/main.py selfcheck
```

对**已产出的** `result.json` 做一次独立审计：契约键是否齐全且同名、引文命中率、数字漂移数、保留覆盖率、术语一致、篇幅比值、文件是否非空。打印 PASS/FAIL 表，任何 FAIL 都给出对应修复命令。若断言失败，回到 3.3 修改后重跑 `check` → `build`。

---

## 4. 谁做什么（分工是这套 Skill 的核心）

| | 脚本（确定性） | Agent（判断） |
|---|---|---|
| 材料 | 解析、切段、编号、抽数字/图表/引文/hedge、生成候选保留项 | 判断哪句是主结论、哪段是可删的方法堆叠 |
| 受众 | 从题面抽取受众/体裁/篇幅并打印命中依据 | 补全画像、定解释深度与术语密度 |
| 取舍 | 统计覆盖率与静默删除清单 | 决定 keep / compress / drop，并写理由 |
| 写作 | — | **逐段写正文**（唯一不能外包的部分） |
| 证据 | 逐字比对 quote、校验 locator、数字漂移 | 选哪句原文作为逐字证据 |
| 交付 | 排版、回填契约、写 status、降级记录 | 审读成稿是否真的"读得懂、说得准" |

判定失败的头号原因不是文笔，而是**只给了提纲/建议**。`check` 在正文不足目标 45% 时直接报 `too_short`；`build` 在无工作稿时只产出兜底摘录并降级为 `partial`。

---

## 5. 工作稿字段（速查，完整字典见 `references/draft-schema.md`）

```json
{
  "audience": {"label": "", "profile": "", "knowledge": "", "goal": "", "depth": "",
               "term_policy": "", "strength_policy": ""},
  "genre": {"label": "", "conventions": [], "length_target": 0, "length_unit": "字"},
  "headline": "", "deck": "",
  "sections": [{"id": "S1", "title": "", "text": "", "cites": ["M1:P2"], "strength": "established"}],
  "retained": [{"id": "R1", "kind": "number", "value": "87.5%", "locator": "M1:P4",
                "quote": "逐字原文", "where": "S2", "treatment": "kept", "note": ""}],
  "trace":    [{"section_id": "S1", "source_locator": "M1:P2", "source_quote": "逐字",
                "decision": "keep", "note": ""}],
  "changes":  [{"action": "compress", "locator": "M1:P6", "original_quote": "逐字",
                "revised_quote": "改后片段", "reason": "方法与目标读者无关"}],
  "dropped":  [{"item": "测序流程", "locator": "M1:P7", "why": "复现信息，非证据"}],
  "glossary": [{"term": "LNP", "expansion": "脂质纳米颗粒", "usage": "LNP",
                "variants": ["脂质体"], "locator": "M1:P3"}],
  "numbers_allow": [{"value": "90%", "reason": "源文 87.5%，按上限取整（待作者确认）"}],
  "open_questions": [{"issue": "", "why": "", "action": "", "owner": "author"}],
  "uncertainty": [""]
}
```

`kind` 取值：`conclusion|number|condition|sample|metric|figure|citation|limitation|term`。
`treatment` 取值：`kept|condensed|moved|reworded`（压缩也算保留，但必须写 `note` 说明怎么压的）。

---

## 6. output_contract 回填规则

- `case.json` 里 `output_contract` 的**每一个键**都在 `result.json` 顶层以**原样键名**出现；
- 能对上产物的填真实值（`deliverable` / `preserved_facts` / `evidence_map` / `change_log` / `glossary` / `uncertainty` / `pending_human` / `status` / `audience` / `genre` / `length` …按别名表匹配）；
- 对不上或确实没有内容：按契约里该字段的**原始类型**给 `null` / `[]` / `{}`，并在 `contract_fill.null_fields` 与 `degradations` 里点名；
- `case_id` 一律取 `case.json` 原值；`init` 阶段先用 `UNKNOWN-CASE` 占位，`build` 才定稿。

---

## 7. 证据与定位规范（"可核验"就靠这一节）

- **一种定位语法**：`M<材料号>:P<段号>`；区间写 `M1:P3-M1:P6`。材料号与段号只能来自 `init` 打印的清单。
- **quote 必须逐字**：允许空白、全半角、NFKC 等价差异；不允许改词、补字、翻译、省略号截断。
- **每个数字都要能在源文找到**（含单位写法）。`87.5%` 不许写成"约九成"；`1.5 倍` 不许写成"翻倍"。
- **样本量、条件、比较基准、图表编号随结论一起搬**：结论换了句子，条件不能留在原位。
- **每个 section 至少 1 条 `trace`**；被删的段落必须有 `dropped` 条目并说明"为何不是证据"。
- 缺编号/缺引用时**不用占位数字**，写"（源文未给编号，需补）"并进 `open_questions`。

---

## 8. 受众、体裁、论断强度

判定顺序：**读者知识背景 → 解释深度与术语密度 → 例子与篇幅分配**。矩阵、五种体裁骨架、强度词表见 `references/audience-genre-matrix.md`。

论断强度只有三级，写进 `sections[].strength`：

| 级别 | 依据 | 转写规则 |
|---|---|---|
| `established` | 源文有统计支持/明确结论 | 可写"研究发现"，仍带 n 与统计口径 |
| `preliminary` | 体外、单一实验、小样本、动物模型 | 必须保留"初步/尚需验证/在该模型中" |
| `hypothesis` | 机制推测、应用外推、商业前景 | 降级表述并进 `open_questions` |

**强度可以持平或降级，永远不能升级。** 相关不写成因果；`可能/提示` 不许改成 `证明/导致`。

---

## 9. 取舍优先级（删什么不是删证据）

| 级别 | 内容 | 处理 |
|---|---|---|
| **P0 必保留** | 主结论、带单位的关键数值、样本量与分组、条件（物种/剂量/时长/平台）、比较基准、统计口径、图表编号、局限与不确定性 | 逐字或等价保留，进 `retained` |
| **P1 可压缩** | 方法参数、仪器型号、试剂批号、文献堆叠 | 压成一句概要，**数值不变** |
| **P2 可删** | 重复表述、与目标读者无关的推导、致谢与投稿信息、基金编号 | 进 `dropped` 并写理由 |

唯一的判据：**删掉之后，目标读者还能不能判断"这个结论在什么条件下成立"？** 不能 → 那是证据，不是冗余。

---

## 10. 冲突、缺口与人工确认

| 情形 | 行为 |
|---|---|
| 受众与体裁冲突（"面向公众"却要"完整方法"） | 受众优先：方法压成一句；冲突写入 `open_questions` |
| 篇幅装不下 P0 | 保 P0、删 P2、压 P1；在"转换说明"里写出取舍；把放弃项写进 `open_questions` |
| 同一指标两个值 | 两个都列，标 `uncertainty`，**不替作者选** |
| 缺引用/缺图表编号 | 写"（源文未给编号，需补）"，不进 `retained` 的 `value` |
| 涉密/未发表/含个人信息 | 不公开细节，不外部推断；`open_questions` 记"需授权确认" |
| 无读者画像/无体裁模板/无篇幅 | 用默认（受过高等教育的非本领域读者 + 800–1500 字），把假设写进 `uncertainty` |
| 材料相互矛盾（正文与表/图注不一致） | 列出两处 locator 与各自原文，标 `uncertainty`，请作者定夺 |

---

## 11. 失败处理与降级

| 情形 | 行为 | 影响 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找含 `output_contract` 的 json；仍无则用内置字段，`degradations` 记录 | 仍产出合法 result.json |
| 材料全无 | `status=insufficient_evidence`，`deliverable.md` 仅含缺口说明与所需材料清单 | 不编造 |
| PDF 无 `pdftotext` | 内置流解析；文本过稀标 `builtin-pdf-lowconf`，提示人工核对 | `degradations` |
| 单文件解析失败 | 只降级该文件，其余继续，记录文件名与原因 | 不中断 |
| 材料是图片/PPTX | 不 OCR、不臆造；记 `image-no-ocr`/`unsupported` | 缺口写明 |
| `draft.json` 缺失/坏 JSON/正文全空 | **兜底**：从源文逐字抽取结论/数值/条件三类句子，`status=partial`，稿首标注"兜底稿，未完成受众改写" | 不空手 |
| 中途异常 | 捕获后仍写合法 partial `result.json` + 说明性 `deliverable.md`，退出码 0 | 不崩 |
| 重复运行 | 产物覆盖，文件集与 status 稳定（幂等） | 可复跑 |

---

## 12. 交付前自查（`selfcheck` 覆盖其中机械项）

- [ ] **`references/expert_playbook.md` §5.2 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `deliverable.md` 八节齐全，正文是成稿不是提纲/要点。
- [ ] `check` 无 `[错误]`；引文命中率 100%；数字漂移 0；篇幅 ≤ 上限。
- [ ] 每个 P0 项在 `retained` 有 locator + 逐字 quote + 落点；覆盖率写进 `fidelity_summary`。
- [ ] 无"静默删除"：被删候选都在 `dropped` 有理由。
- [ ] 以目标读者身份通读：无未展开缩写、无裸公式、无自造术语；同一概念全文一个说法。
- [ ] `result.json` 含全部契约键、`case_id` 原样、`status` 与实况一致。
- [ ] 示例与示意输出均标注"示例，非正式案例结果"。

---

## 13. 最小调用示例（**示例，非正式案例结果**）

```
$ python3 scripts/main.py init
== 材料索引 ==  M1 demo_paper.md 9段 [material] | M2 reviewer_notes.csv 3段 [material] | M3 task.md [instruction]
== 工作单 ==
case_id: EXAMPLE-NOT-A-TEST-CASE   受众: 非专业公众 <- `面向科学有兴趣的普通读者`
体裁: 科普文章   篇幅: 1200 字 <- `不超过1200字`
契约: case_id, deliverable, preserved_facts, evidence_map, change_log（5 字段）
候选必保留项: 23（结论 4 / 数值 11 / 样本 2 / 图表 3 / 引文 2 / 限定 1）
下一步：读原文 → 写 /app/work/draft.json → check → build

$ python3 scripts/main.py check
状态 ok | 段落 5 | 正文 1043 字（目标 1200，比值 0.869）| 引文 12/12 | 数字 14（漂移 0）
保留覆盖 9/9 | 未解释缺口 0/21 | 术语漂移 0 | 未展开缩写 1 | hedge 源 8/成稿 5
  [提示] 缩写首次出现未展开：IL-6（首现处给全称，或登记进 glossary）

$ python3 scripts/main.py build
status=ok fallback=False 字数=1043 目标=1200
契约 5/5 回填（null 0）| 引文 12/12 | 数字漂移 0 | 保留覆盖 9/9 | errors 0 | pending 2

$ python3 scripts/main.py selfcheck
| PASS | contract 键齐全且同名 | 5 键；缺 无 |    | PASS | quote 全部逐字命中 | 12/12 |
| PASS | 数值漂移为 0 | 0 |                   | PASS | 篇幅在上限内且非提纲 | 比值 0.869 |
PASS 14 / FAIL 0
```

上例材料、数字与输出均为构造示例，仅说明接口；正式案例一律以平台 `/input` 为准。

---

## 14. 文件清单、版本与维护

| 文件 | 作用 | 量级 |
|---|---|---|
| `SKILL.md` | 本说明：流程、契约、规则、降级、自查 | ~17 KB |
| `scripts/main.py` | CLI 五子命令 + 阶段编排 + 异常兜底 | ~22 KB |
| `scripts/kit.py` | 材料解析、切段编号、数字/图表/引文/hedge 抽取、索引、候选保留项 | ~21 KB |
| `scripts/audit.py` | 确定性校验（引文/数字/覆盖/术语/强度/篇幅）与契约回填 | ~23 KB |
| `scripts/render.py` | 排版八节、附表生成、兜底稿、`result.json` finalize | ~20 KB |
| `references/expert_playbook.md` | 专家方法论：判分要点、8 步框架、公式、检查表、虚构案例 | ~13 KB |
| `references/draft-schema.md` | 工作稿字段字典 + 校验代码表 + 正反例 | ~9 KB |
| `references/audience-genre-matrix.md` | 受众矩阵、六种体裁骨架、强度词表、取舍顺序、反模式 | ~7 KB |
| `environment/resources.yaml` | 运行环境、入口命令、预算与依赖声明（离线、纯标准库） | <1 KB |
| `README.md` / `SELFTEST.md` | 安装、调用、环境、自检与复跑记录 | ~4 KB |
| `GAIN_EVIDENCE.md` | 使用增益对照协议 + 本包 eval_sim 运行记录（可复算） | ~4 KB |
| `examples/walkthrough.md` | 最小调用示例：输入契约 + 源材料 + 调用 + 期望产物 | ~3 KB |
| `GITHUB_URL.txt` | 公开作品链接（仓库地址 + 作品相对路径两行） | <1 KB |

版本 `10.0.0`；纯标准库；无网络；无外部服务；无硬编码路径。

维护约定：新材料格式无需改代码（`kit.extract` 按扩展名 + 魔数分派，不支持的类型只降级不报错）；
新增体裁在 `audience-genre-matrix.md` 加一行矩阵 + 一段骨架，并在 `init` 的体裁词表加同义词；
新增校验口径只改 `audit.check_draft`，`main.py` 复用其结论；改脚本后必须跑 `--help`（退出码 0）、
空输入、坏 JSON 各一次，确认仍写出合法 partial `result.json`。
