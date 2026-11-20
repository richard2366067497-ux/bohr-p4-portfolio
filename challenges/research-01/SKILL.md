---
name: research-investigation-notebook
description: 深度研究调查笔记本。把一段研究任务拆成可独立检索的子问题并标注依赖，安排检索与工具调用顺序，读材料后写成自带逐字证据、反证、适用范围与置信度的发现卡，再合成只引用发现编号的综述备忘录，显式登记冲突、检索缺口与研究空白。适用于文献综述、系统筛选、趋势分析、选题评估一类需要证据回链的深度研究案例；产出 notebook/ 五章与 result.json（原样回填 output_contract 全部字段）。
version: 1.0.0
license: MIT
---

# 深度研究调查笔记本（research-01）

## 0. 单命令等价入口（single command — 评测方只需这一条）

```bash
python3 scripts/main.py build --input /input --work /app/work --output /app/output
```

`build` 本身就无条件完成整条链：**输入发现 → 无工作稿时用确定性兜底推导（任务句拆子问题、材料句机械抽取
发现卡，全部标注 `provisional/low`，不编造、不补数值）→ 渲染 notebook 五章 → 写最终 `result.json`
（`output_contract` 逐键回填 + `case_id`）→ status 推导**，恒 `exit 0`。它等价于把 §2 的
`init → show →（draft）→ check → build` 串跑，但无需先读材料；空/坏输入也保证写出合法 `result.json`。

### result.json 契约（`case.json` 未声明 `output_contract` 时的默认回填键，键名不改）

| result.json 键 | 类型 | 含义 |
|---|---|---|
| `case_id` | string | 案例标识，原样透传 |
| `research_question` | string | 研究问题原文 |
| `sub_questions` | array | 子问题拆解（含 depends_on 与四层 layer） |
| `search_plan` | array | 检索/读材料步骤日志（可重放） |
| `evidence_matrix` | array | 证据登记（逐字引文 + locator） |
| `findings` | array | 发现卡（statement/support/counter/scope/confidence/status） |
| `synthesis` | string | 综合备忘录（只引用 finding 编号） |
| `conflicts` | array | 未决冲突登记 |
| `open_questions` | array | 检索缺口与研究空白 |
| `sources` | array | 材料清单 |
| `status` | string | ok/partial/insufficient_evidence/input_error |

> 每个键必须在 `result.json` 出现（顶层与 `output_contract` 各一份，键名不改）；无产出时按契约填
> `""`/`[]`，绝不删键、绝不编造。

## 1. 用途与适用条件

**做什么**：输入一份研究任务（`/input/case.json` 的 `task_instruction` / `research_question`、`/input/task.md`、以及 `/input` 下的科研材料），输出一本可复跑的**调查笔记本**：把问题拆成可独立检索的子问题 → 记录检索与读材料的动作 → 把读到的句子写成**发现卡**（statement + 逐字 support + 反证 + scope + confidence + status）→ 合成只引用 finding 编号的**综述备忘录** → 登记未决冲突、检索缺口与研究空白。最终 `result.json` 原样回填 `output_contract` 的所有字段。

**四个必须成立的性质**（本题评分内核）：

| 要求 | 本 Skill 的落实 |
|---|---|
| 拆得开 | 子问题带 `object / mechanism / method / time_scope / comparison / evidence_requirement / depends_on / layer`，`layer` 覆盖「是什么—做到哪—为什么—还缺什么」四层，`depends_on` 让检索有先后而不是平铺关键词 |
| 查得到 | `02-search-log.jsonl` 逐步记录 `action/target/params/hits/status/retry_count`，检索路径能被人按记录重放 |
| 回得去 | 每条 support 是 `source_id + locator + 原文逐字 quote`；脚本做 `quote ∈ material` 命中校验，命中但定位写错时**自动回改 locator 并记录修复** |
| 说得住 | 综合备忘录只准引用已登记 `finding_id`；表述强度与卡 `status/confidence` 一致（越级判 FIX）；有反证而标 `established` 判冲突隐藏（FIX） |

**不做什么**（硬边界）：不联网、不检索外部数据库、不从记忆补文献或 DOI、不补造数值、不把「材料没写」写成「不存在」、不把相关性写成因果、不替作者判断单篇论文的方法学质量。材料范围之外的问题一律落到 `05-open-questions.md`（`scope_limit`），不硬答。

**何时该用**：需要围绕固定研究问题做文献综述/系统筛选/趋势分析/选题评估；输入里已有 `case.json` 与若干材料文件；要求结论可回链到原文。

**何时不该用**：单篇精读、全文翻译、写作润色、纯元数据核对（这些是相邻课题）。若 `/input` 只有一个空目录，请直接照第 10 节失败处理走，不要编材料。

## 2. 五命令主路径（先看这里）

```bash
python3 scripts/main.py init       # 建索引：解析 case.json / output_contract / task.md，登记材料清单与对象表，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的原文与对象清单（逐字可抄），供你逐条引用
#   ← 你自己读材料，把判断写进工作稿 /app/work/draft.json（schema 见第 6 节）
python3 scripts/main.py check      # 机械校验：契约字段、quote 逐字命中、locator、子问题覆盖、memo 引用、冲突与越级表述
python3 scripts/main.py build      # 由工作稿生成 notebook 五章 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 复检：产物齐全性、计数一致、二次渲染确定性
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**

脚本只做确定性重活（解析、定位、去重、校验、渲染、回填契约）。**判断权在你手里**：哪些材料与子问题相关、结论怎么提炼、冲突怎么处置、方案怎么取舍、哪种表述才算不过度——这些都写进 `draft.json`，`check` 只负责把不一致挑出来。

`build` 有兜底：工作稿缺失/不完整/超时时，仍会产出**完整但降级**的交付——契约字段全回填的 `result.json`、五章齐全的 `notebook/`、`status=partial`、`degradations` 写清缺口，退出码 0。兜底只是保底，不是合格线：`degradations` 里出现 `draft_missing` 就说明这次没有真正走读完材料这一步。

## 3. 调用方式

```bash
python3 scripts/main.py <command> [--input DIR] [--work DIR] [--output DIR] [选项]
python3 scripts/main.py --help            # 退出码 0
```

| 参数 | 默认解析顺序 |
|---|---|
| `--input` | 显式值 → `$RESEARCH_INPUT` → `/input` → `<skill>/input` → `./input` |
| `--work` | 显式值 → `/app/work` → `<output>/work` → `<skill>/work` |
| `--output` | 显式值 → `/app/output` → `./output` → `<skill>/output` |

Skill 装在 `/skills/weekly-skill` 时无需任何参数，脚本按 `Path(__file__).parent.parent` 定位自身，**不依赖 CWD**。若 CWD 不是 Skill 根目录，用绝对路径调用：`python3 /skills/weekly-skill/scripts/main.py init`。`show` 的选项：`--source ID`（只看一份材料）、`--grep 词`（只看含该词的句子）、`--max-blocks N`（默认 12，`0` 表示全部）、`--max-chars N`（单句截断，默认 240）、`--max-sents N`（每份材料句数上限，默认 60，`0` 为全部）、`--records`、`--brief`。

## 4. 输入发现

`init` 按以下顺序找输入，每一步的降级都写进 `degradations`：

1. `case.json`：根目录 → 一级子目录。坏 JSON 记 `case_json_invalid`，继续用 `task.md` 兜底。
2. 研究问题：`research_question` / `question` / `task_instruction` / `instruction` / `brief` / `title`，取第一个非空；都没有则用 `task.md` 的首个标题。
3. 检索约束：`search_protocol` / `protocol` / `constraints` / `inclusion` / `exclusion` / `stop_rules` / `time_range`，字符串或列表都接受。
4. 契约：`output_contract` / `outputContract` / `contract` / `deliverable_contract`。支持五种形态：`{键: 说明}`、`{fields: {...}}`、JSON-Schema `{properties: {...}}`、`[{name, ...}]` 或字符串列表、以及 Markdown 表格/`键: 说明` 文本（保守取键，记 `contract_parsed_from_text`）。**键名不改、不漏、不合并**。
5. 材料：`/input` 全树递归（跳过隐藏文件与 `case.json`/`task.md`）。支持 `.pdf`（先试 `pdftotext`，失败用内置 Flate 流解析，再失败标 `read_method=none` 并提示 OCR）、`.docx`、`.md/.txt/.rst/.tex`、`.html`、`.json/.jsonl/.ndjson`、`.csv/.tsv`、`.yaml/.yml`。单文件读取上限 2 MB 文本。
6. 内联材料：`case.json` 的 `sources[] / records[] / documents[] / papers[] / articles[] / corpus[]`，若元素含 `text/abstract/content/full_text/body` 则登记为材料（locator 前缀 `case.json:source[i]`），否则登记为记录行。
7. 记录表：`records.jsonl`、`records.json`、`*.csv` 与内联列表统一成对象表（`rec_id / source_id / locator / title / year / doi / 首字段摘要`），供 `show --records` 与证据矩阵使用。

## 5. 输出契约

`/app/output/` 下产物：

| 文件 | 内容 |
|---|---|
| `result.json` | **主产物**：`output_contract` 全字段回填 + 信封字段（见下） |
| `notebook/00-README.md` | 章节导航与读数（材料数、子问题数、发现卡数、证据条数、命中率） |
| `notebook/01-brief.md` | 研究简报：原问题、范围与纳排、停止条件、拆解表（含依赖与四层）、检索顺序 |
| `notebook/02-search-log.jsonl` | 检索/读材料日志，一行一步；同时导出 `02-search-log.md` 便于阅读 |
| `notebook/03-findings/finding-cards.jsonl` | 发现卡（机器可读，一张卡一行） |
| `notebook/03-findings/findings-index.md` | 发现卡（人可读，逐卡渲染 + 状态统计） |
| `notebook/04-synthesis.md` | 综合备忘录：每段只引 `[F001]` 式 finding 编号 + 段末强度标注 + 回链表 |
| `notebook/05-open-questions.md` | 未决问题：`retrieval_gap / unresolved_conflict / method_limitation / scope_limit` 四型 + 依据 |
| `appendix/evidence-register.jsonl` | 证据登记：`evidence_id / source_id / locator / quote（逐字）/ verified / used_by_findings` |
| `selfcheck.json` | `selfcheck` 的复检报告（9 项检查：契约键、章节、计数、引文复算、确定性等） |

`result.json` 信封字段：`case_id, status, task_type, research_question, sub_questions[], search_steps[], findings[], conflicts[], synthesis_claims[], synthesis_markdown, evidence_summary{}, coverage{}, open_questions[], uncertainties[], sources[], degradations[], errors[], changes[], quality{}, contract_audit[], artifacts[], runtime{}`。

- 回填规则：先按 `output_contract` 的键顺序逐键写入（不改名、不漏键），无对应内容写 `null`（列表型写 `[]`），随后写信封字段；同名键取同一语义值。`contract_audit` 逐键记录 `filled / empty / inferred_from`。
- `status`：`ok`（无 FIX、工作稿来自 Agent）｜`partial`（有 FIX、走了兜底推导或工作稿损坏）｜`insufficient_evidence`（材料为空或全部无文本层）｜`input_error`（`case.json` 坏且没有可读材料）。与缺口一一对应，不美化。

## 6. 工作稿 schema（`/app/work/draft.json`）

```json
{
  "case_id": "原样",
  "brief": {
    "question": "复述研究问题（可加限定，不改指向）",
    "scope": "纳入范围一句话",
    "inclusion": ["纳入判据"], "exclusion": ["排除判据"], "stop_rules": ["停止条件"],
    "sub_questions": [{
      "sq_id": "SQ1", "text": "可独立检索的子问题",
      "object": "研究对象", "mechanism": "机制/通路", "method": "方法学限定",
      "time_scope": "时间范围", "comparison": "比较关系或 无",
      "evidence_requirement": "什么样的材料段落才算答上",
      "depends_on": [], "layer": "what|how_far|why|what_missing"
    }]
  },
  "search_log": [{"step_id": "S1", "action": "search|read|extract|calc",
                  "target": "src-1 或 rel 路径", "params": "检索式/参数",
                  "result_summary": "命中了什么", "hits": ["src-1"],
                  "status": "ok|failed|retried", "retry_count": 0}],
  "findings": [{"finding_id": "F001", "statement": "一句话结论",
                "type": "material_fact|inference|undetermined",
                "confidence": "high|medium|low",
                "support": [{"source_id": "src-1", "locator": "sources/a.md#B3.S2 chars:812-940", "quote": "逐字原文"}],
                "counter": [{"source_id": "src-2", "locator": "...", "quote": "相反结论的逐字原文"}],
                "scope": "这条结论适用的对象/条件/时间边界",
                "sub_question_id": "SQ1",
                "status": "established|provisional|contested|undetermined"}],
  "synthesis": [{"paragraph": "备忘录段落，引用处写 [F001]", "finding_ids": ["F001"],
                 "strength_note": "established|provisional|contested|undetermined"}],
  "open_questions": [{"oq_id": "OQ1", "description": "缺口描述",
                      "type": "retrieval_gap|unresolved_conflict|method_limitation|scope_limit",
                      "basis": "依据：哪条检索/哪份材料的哪处缺失"}]
}
```

字段字典、词表与错误码见 `references/draft_schema.md`（第 8 节给了一份最小示例，可直接改，非正式案例结果）；方法与评分维度映射见 `references/method_and_rubric.md`。

工作稿可以只写一部分：`check` 会逐项报缺口，`build` 会把缺失补成占位并在 `degradations` 注明。但 `findings[].support[].quote` 必须从 `show` 的输出里逐字复制——不要手打、不要翻译、不要合并两句。

## 7. 方法说明：五章怎么生成

### 第 1 章 研究简报与拆解（`01-brief.md`）

规则：`sub_questions` ≥ 4 且 `layer` 覆盖四层；每个子问题必须写 `evidence_requirement`（否则无法判断「答上了没有」）。`depends_on` 形成先后关系，渲染时按依赖排序并标 `前置/并行`。`check` 报：`C201` 子问题缺字段、`C202` 子问题少于 4 条、`C203` 层次缺失。

### 第 2 章 检索日志（`02-search-log.jsonl`）

规则：一步一个动作，`target` 用材料 id 或相对路径，`hits` 列出实际命中；失败动作保留并写 `retry_count`，不删除——**删掉失败步就等于伪造可复跑路径**。`check` 报：`C250` 日志为空、`C251` 证据所在材料没在任何步骤里被读到。

### 第 3 章 发现卡（`03-findings/`）

规则（自足性）：每张卡必须有 ≥1 条 `support`（`source_id + locator + 逐字 quote`）、`scope`、`confidence`、`status`。`counter` 有则填，出现反证却标 `established` 视为**隐藏冲突**。`statement` 不得超出 `scope`；`type=undetermined` 的卡不要求 support，但要写清「为什么无法确定」。`check` 报：`C210` 无支持、`C211` quote 不逐字命中、`C212` 缺 scope/confidence/status、`C213` 冲突隐藏、`C214` 支持项字段不全、`C215` finding_id 重复、`C216` 指向未登记子问题、`C217` 词表外取值。

### 第 4 章 综合备忘录（`04-synthesis.md`）

规则：段落**只**用 `[F001]` 引用发现卡，不直接引原文（原文只能通过卡进入正文，这样每条结论都有卡作为中间层）；段末标本条强度（`已被证明 / 有提示性证据 / 仍有争议 / 无法确定`），且不得强于所引卡的最高 `status`。`check` 报：`C220` 引用未登记卡、`C224` 段落无引用、`C221` 越级表述、`C222` 出现「证明/证实/proves/confirms」等绝对措辞而卡片只是 provisional/contested、`C223` 卡片未被任何段落引用（提示）。

### 第 5 章 未决问题（`05-open-questions.md`）

规则：四型分类，每条给 `basis`（哪条检索、哪份材料的哪处缺失）。有子问题没有任何卡覆盖时，必须有对应 `retrieval_gap` 条目。`check` 报：`C240` 类型不在词表、`C241` 未覆盖子问题没有对应条目、`C230` 子问题未覆盖、`C231` 子问题只有单一来源支撑。

## 8. 证据与定位规范

- `locator` 形如 `<相对路径>#B<块>.S<句> chars:<start>-<end>`，块/句基于 `init` 的分段（空行分块、句末标点断句），可独立回查。
- `quote` 必须与材料**逐字**一致（含标点、单位、数字、上下标写法）。脚本先做精确匹配，再做「仅忽略空白与引号差异」的匹配，均失败则判 FIX 并给出**最长前缀的可疑定位**供你回原文核对。
- 精确命中但 `locator` 写错：脚本按命中位置**回改 locator**，记入 `changes[]`（`locator_repaired`）与 `quality.locators_repaired`，不算 FIX——这是为了提高回链正确率，不是放水。
- 只转录材料里已有的书目信息；缺 DOI/年份/期刊就写缺，不补造。
- 证据不足的卡写 `type=undetermined` + `status=undetermined`，并进第 5 章，不用常识填空。

## 9. 边界与限制

- 只覆盖「按已有材料做证据综合」；不替代真实数据库检索，不声称检索穷尽（`coverage` 只报「材料内覆盖率」，不报领域覆盖率）。
- PDF 内置解析只处理带文本层的常见编码；复杂版式、双栏、扫描件会丢字或乱序——出现 `read_method=internal-flate` 时请 `show` 回看原文确认，必要时用外部 `pdftotext`/OCR 工具（若环境提供），并在 `degradations` 记明。
- 冲突识别是**机械提示**：`check` 只会指出「同子问题下方向相反的陈述」候选，是否真冲突由你在卡里判定。
- 单案例预算：纯本地计算，秒级；不占用模型请求。

## 10. 失败处理与降级

| 情况 | 处置 |
|---|---|
| `case.json` 缺失 | 用 `task.md` + 材料名兜底，`degradations: case_json_missing`，`case_id` 从文件名/标题推导 |
| `case.json` 坏 JSON | `case_json_invalid` + `errors`，继续走 `task.md`，`status=partial` |
| `output_contract` 缺失 | 用内置默认键集（`case_id, sub_questions, search_plan, evidence_matrix, findings, synthesis, open_questions, sources, status`）并记 `contract_defaulted` |
| 材料为空 | `status=insufficient_evidence`，五章仍生成（第 3 章空卡 + 第 5 章 `retrieval_gap`），不编条目 |
| PDF 无文本层 | `read_method=none` + `pdf_no_text_layer`，提示 OCR，材料保留在清单里 |
| 文件不可读/权限不足 | `errors: unreadable_file`，跳过该文件继续 |
| 工作稿缺失 | `draft_missing`，走推导兜底：子问题由任务句拆出、发现卡由材料句机械抽取，`status=partial`，卡片全部标 `provisional/low` 并注明「未经 Agent 复核」 |
| 工作稿坏 JSON | `draft_invalid` + 同上兜底 |
| quote 找不到 | 判 FIX，`build` 保留该卡但把 `verified=false`、`confidence` 降为 `low`、`status` 降为 `provisional`，并写 `degradations` |
| 证据互相冲突且无法在卡内解决 | 进 `05-open-questions.md`（`unresolved_conflict`），不静默取一方 |
| 输出目录不可写 | 回退到 `<skill>/output` 或 CWD，`errors` 记录 |
| 任意未捕获异常 | 仍写合法 `result.json`（`status=partial`，`degradations: unexpected_error:<type>`），退出码 0 |

## 11. 自查清单

```bash
python3 scripts/main.py check     # FIX 必须为 0
python3 scripts/main.py build     # 看 contract_audit 是否 empty=0、quality.quote_failed 是否为 0
python3 scripts/main.py selfcheck # chapters 齐全、计数一致、deterministic=true
```

- [ ] `result.json` 存在，`case_id` 原样，`output_contract` 每个键都在且未改名
- [ ] `contract_audit` 中 `empty` 的键都在 `degradations`/`uncertainties` 有解释
- [ ] 五章文件齐全且非空；`finding-cards.jsonl` 行数 = `result.findings` 条数
- [ ] 每条 support 有 `source_id + locator + quote`，`verified=true` 占比 = `quality.quote_verified/total`
- [ ] 综合备忘录引用的每个 `[Fxxx]` 都能在 `finding-cards.jsonl` 找到
- [ ] 有反证的卡 `status != established`
- [ ] 第 5 章四型分类齐全（至少 `retrieval_gap` 与 `method_limitation` 各一条）
- [ ] `degradations` 里没有 `draft_missing`（有就说明没读材料）

## 12. 预算与断点

- `init` 先写 partial `result.json`，此后任何命令失败，磁盘上都有一份合法结果。

包结构（8 个文本文件、纯标准库、离线）：

| 文件 | 职责 |
|---|---|
| `SKILL.md` | 契约、主路径、方法、边界、失败处理、自查 |
| `scripts/main.py` | 五命令 CLI（init/show/check/build/selfcheck）、参数与路径解析、异常兜底 |
| `scripts/parse.py` | 输入发现、PDF/DOCX/HTML/表格解析、分块断句、locator、逐字定位 |
| `scripts/check.py` | 工作稿归一化与全部判据（C2xx / R211） |
| `scripts/render.py` | 五章 + 证据登记 + 导航的确定性渲染、覆盖估计、冲突提示 |
| `scripts/contract.py` | `output_contract` 键映射与回填、`result.json` 信封、兜底推导 |
| `references/draft_schema.md` | 工作稿 schema、字段字典、错误码表、最小示例 |
| `references/method_and_rubric.md` | 方法总览、评分维度映射、边界、复跑对账、维护 |
- 每个命令独立重建索引（不共享进程状态），单次 < 3 s；`build` 幂等，重复运行产物字节一致（`selfcheck` 会验证 `deterministic`）。
- 模型侧建议：`show` 采样 8–12 句/材料，把预算花在写卡和洞察，而不是把全文塞进上下文。

## 13. 最小调用示例（示例数据，非正式案例结果）

```bash
$ python3 scripts/main.py init --input ./demo --work ./demo/work --output ./demo/out
[init] materials=3 records=3 contract_keys=7 -> partial result.json written
[init] next: python3 scripts/main.py show   → read sentences → write work/draft.json
$ python3 scripts/main.py show --source src-1 --max-blocks 3
[src-1] sources/lead.md chars=512 blocks=4 read=utf-8
[src-1] sources/lead.md#B2.S1 chars:118-210
> 在 12 周随访中，干预组收缩压平均下降 7.4 mmHg（n=148）。
$ python3 scripts/main.py check
[check] fix=0 warn=2 quotes=5/5 repaired=0
$ python3 scripts/main.py build
[build] status=ok chapters=6 findings=3 evidence=5 contract=7/7
```

## 14. 版本与维护

| 项 | 值 |
|---|---|
| 版本 | 1.0.0（2026-11） |
| 依赖 | Python ≥ 3.8 标准库；可选外部 `pdftotext`（缺失则用内置解析） |
| 安装 | 整目录放到 `/skills/weekly-skill`（或任意目录，脚本自定位） |
| 维护 | 改规则先改 `references/draft_schema.md` 的错误码表，再同步 `scripts/check.py` 的 `check_draft`，最后跑 `references/method_and_rubric.md` 第 6 节的复跑与对账 |
| 许可 | MIT |
