---
name: longdoc-source-ledger
description: Source-faithful revision of long documents (degree-thesis chapters, reports) against an organizer edit workorder. Indexes every supplied chapter into locator-addressable blocks, lets the agent author one source-grounded editorial annotation per target paragraph and its own cross-chapter findings, then re-verifies every quote against its locator, keeps all author text byte-identical, and returns an editable manuscript with per-target revision records, an evidence map bound to locators, preserved-fact inventory, change log, six-category consistency ledger, impact back-links, rubric coverage matrix and rendered preview. Trigger on degree-thesis or long-document chapter revision, paragraph target ids such as C01-P002, terminology/symbol/definition/numbering/citation consistency, "which paragraphs are affected if I change this one", or any request for a reviewable record of what a machine changed in a manuscript.
version: 1.0.0
---

# longdoc-source-ledger — 长文档章节修订与跨章节一致性台账

## 1. 用途与适用条件

本 Skill 处理**一类**任务：作者交来一份被切分成可编辑章节的长文档（学位论文章节、
报告、被拆成段落的源论文），同时给出一份编辑工单（`organizer_edit_workorder`），
工单用段落级 id（如 `C01-P002`）指定必须处理的位置。本 Skill 负责：

- 把材料建成**可定位的块索引**（每块有 locator、行号、id、哈希）；
- 让**评审 Agent 亲自读材料**，为每个 target 写 1 条有源依据的编辑注记，并写出
  自己判读出的跨章节问题（术语、符号、定义、编号、图表引用、前后结论）；
- 机械复验每条引文的**逐字命中**与**定位一致**，保留全部作者原文，产出可编辑稿件；
- 交付修订记录、证据映射、保留清单、改动日志、六类一致性台账、**受影响段落回链**、
  版本回退证明、评分维度覆盖矩阵与可查看预览；
- 材料不足、来源冲突、需要人工确认的地方**逐条标注**，不补造、不静默纠正。

**用**：任务里出现段落/块 id（`C01-P002`、`T01-P057`）；出现“修订/批注/改稿/章节”
且材料跨多章；存在 `target_ids`、`output_contract`；“改动一处后哪些段落受影响”；
需要变更记录与一致性报告；正文长到通读一遍记不住术语与编号（约 >8k 词或多文件）。

**不用**：从零自由创作、纯翻译、没有事实底稿的润色、没有任何材料文件、只需一句话
建议的任务。这些场景本 Skill 会给出降级说明而不是硬凑产物。

**前置条件**：一个可读的 case JSON、至少一份含文本的材料。没有工单时流程仍会执行，
但只按 `task_instruction` 做通用编辑，并把“工单缺失”写进 `uncertainty`。

## 2. 主路径：五条命令（先读这一节）

```bash
python3 scripts/main.py init       # ① 建索引：解析 case.json / output_contract / task.md，建材料清单与对象表，先写合法 partial result.json
python3 scripts/main.py show       # ② 打印带 locator 的原文与对象清单，供逐字引用
#   ③ 评审 Agent 亲自读材料，写工作稿 /app/work/draft.json（注记 + 自判发现）
python3 scripts/main.py check      # ④ 机械校验：契约字段齐全、quote 命中且定位一致、覆盖数、数值/引文一致性
python3 scripts/main.py build      # ⑤ 由工作稿生成主产物 + 最终 result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # ⑥ 复检（可选，但推荐在回复前跑一次）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `build` 在没有工作稿时只会产出**降级版**（注记由确定性兜底生成、`status=partial`、
> 每条缺口写进 `degradations`）。降级版拿的是基础分，拿不到“任务完成度/正确性/
> 科学核验”的分。真正得分来自你读过材料后写下的注记与发现。

命令都可以带显式路径（默认 `/input`、`/app/work`、`/app/output`）：

```bash
python3 scripts/main.py init  --input /input --work /app/work --out /app/output
python3 scripts/main.py show  --list                 # 全部块 + locator（分页）
python3 scripts/main.py show  --target C01-P002 --context 2
python3 scripts/main.py show  --find "tensile strength was measured"
python3 scripts/main.py check --draft /app/work/draft.json
python3 scripts/main.py build
python3 scripts/main.py selfcheck
```

退出码恒为 `0`；失败通过 `result.json` 的 `status` / `errors` / `degradations` 表达，
不靠退出码传信号。

## 3. 输入与输出契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（或任意含 `case_id`/`output_contract` 的 JSON）、`/input/task.md`、`/input/**` 下的材料（md/txt/json/docx/pdf/csv/tex） |
| 工作目录 | `/app/work`：`source_index.json`、`draft.json`、`draft_template.json`、`check_report.json`、`paths.json` |
| 输出目录 | `/app/output`：`result.json` + 第 9 节列出的产物 |
| 依赖 | Python 3.9+ 标准库；`pdftotext` 仅在系统已安装时用于 PDF |
| 网络 | 从不使用 |
| 工作目录无关性 | 所有路径来自命令行参数、环境变量（`INPUT_DIR`/`WORK_DIR`/`OUT_DIR`）或 `__file__`；`/app` 不存在时自动回退到 `./output`、`./work` |
| 预算 | 每案例 64 次模型请求 / 900 秒 / 单次响应 16384 token；脚本承担确定性重活 |

### 3.1 `result.json` 信封

`output_contract` 的**全部字段原样回填**：键名不改、不漏键，缺值写 `null`（列表语义
写 `[]`）。`output_contract` 可以是字典、字段名列表或带 `field`/`name` 的列表，三种
形态都会被识别。信封字段：

```json
{
  "case_id": "…", "status": "ok|partial|insufficient_evidence|input_error",
  "deliverable": {...}, "preserved_facts": [...], "evidence_map": [...], "change_log": [...],
  "workorder_execution": {...}, "consistency": {...}, "coverage": {...},
  "sources": [...], "uncertainty": [...], "pending_human": [...],
  "errors": [...], "degradations": [...], "changes": [...],
  "contract_fields": ["…"], "runtime": {...}
}
```

`status` 的口径：`ok` 仅当每个 target 都有被接受的注记、无 high 级校验问题、无错误、
无降级、且确有 Agent 判读发现；否则 `partial`（缺稿/兜底/发现为空）或
`insufficient_evidence`（材料读不出、target 找不到）；输入层失败 `input_error`。
`ok` 不是默认值，是挣来的。

## 4. 工作稿（Agent 必须亲手写的那一份）

写到 `/app/work/draft.json`（也接受 `plan.json`）。`init` 会生成
`draft_template.json`，其中每个 target 已带真实 `locator` 与真实 `anchor_quote`，
你只需要补 `annotation`、`evidence`、`rationale`、`uncertainty`，并补 `findings`。

```jsonc
{"case_id": "C01", "reading_notes": "读了哪几节、统领性问题",
 "annotations": [{"target_id": "C01-P002", "locator": "<show 打印的 locator>",
   "anchor_quote": "该段中逐字复制的一句", "annotation": "2-4 句：确立什么/依赖什么条件或局限/读者能得出什么",
   "evidence": [{"locator": "…", "quote": "材料中的逐字原文"}],
   "rationale": "为什么必要", "uncertainty": "无法从材料确认的点"}],
 "findings": [{"category": "term|symbol|definition|numbering|citation|claim|unit",
   "severity": "high|medium|low", "locator_a": "…", "quote_a": "逐字原文",
   "locator_b": "…", "quote_b": "逐字原文", "statement": "冲突是什么（两边都写，不裁决）",
   "decision_owner": "author|editor|human", "note": "建议如何确认"}],
 "plan": {"chapters": [{"locator": "…", "role": "方法", "argument_task": "…"}]},
 "pending_human": [{"item": "…", "reason": "…", "action": "…"}]}
```

字段字典与全部校验规则见 `references/workflow.md`。

## 5. 方法说明

### 5.1 索引与 locator 语法

locator 由脚本生成、打印、再由你复制，不要手打：

- 散文/表格/公式：`<相对路径> §<节号> <节标题> ¶<段号>`；
- 标题块本身：`… (heading)`；
- 有段落 id 时追加 `· <id>`；
- 文件内行号与文本哈希存在 `work/source_index.json`，供复核。

比较前统一做排版归一（全角/半角、弯引号、长短破折、软连字符、NBSP），归一之后
仍要求逐字命中；命中失败**直接退回**并给原因，脚本从不把失败引文“调整”成成功。

### 5.2 注记协议（每个 target 恰一条）

一条注记必须同时满足：target 在工单内；`anchor_quote` 在被定位块内逐字出现；
`locator` 解析到的块与 target 解析到的块一致（**定位一致**，不只是“全文某处命中”）；
注记长度 ≥60 字；不引入材料中不存在的数字；与材料语汇有足够重叠（防通用套话）；
同一 target 不重复。

好注记做三件事：说明该段确立了什么、说明该论断依赖什么条件或局限（引原文）、
说明读者因此能得出什么结论。**不新增**引用、百分比、样本量、章节号或来源没有的
解读。

### 5.3 一致性六类台账

`consistency_tables.json` / `consistency_report.md` 覆盖六类，全部带 locator 与逐字
引文，可分两类归因：

| 台账 | 记录 |
|---|---|
| `terms` | 缩写↔展开式、首次定义位置、同缩写多展开、同展开多缩写、先用后定义 |
| `symbols` | `where X is …` / `式中 X 为 …` 定义的符号及其多义、重定义 |
| `definitions` | 同一术语被定义多次且措辞不同、重复定义段落 |
| `numbering` | 图/表/式编号的引用集合 vs 题注集合、重号、断号、引用了不存在的编号 |
| `citations` | 正文引用编号/作者年 vs 文献表条目、引而未列、列而未引、占位符、缺文献表 |
| `claims` | 结论性句的极性、是否带量值、跨章同主题异极性、同量纲多写法、同量纲异数值 |

**`basis: computed` 的行只是候选线索，不是结论**：正则找不到不等于不存在，找到也不
等于语义冲突。真正的科学核验由你在 `draft.json` 的 `findings` 里做（`basis: agent_review`），
两者在报告里**分区呈现**，并写明“机械清单不构成科学核验”。

### 5.4 受影响段落回链、保真与版本证明

- **回链**：每条注记/发现按"共享稀有词、符号、编号、量值"算出最多 5 个受影响块，写进
  `revision_records.json[].affects` 与 `consistency_tables.impact`，回答"改这里还要看哪里"。
- **保真**：主产物按原始行重组，除插入的注记块外作者原文逐行不变；`preserved_facts` 逐块
  复算（归一子串比对），不是声明。
- **版本**：`versions/{v1_original.md,v2_revised.md,diff_v1_v2.patch,rollback_check.json}`，
  其中 `rollback_equals_v1`（去掉注记块 → 与 v1 同哈希）与 `reapply_equals_v2` 都是复算值。
- **失效探针**：伪造锚点、未知 target、编造数字、缺字段四种无效操作走同一校验器，回执记录
  拒绝原因与"探针未写任何产物"。

## 6. 边界与限制

- 材料是**源论文分章工作稿**，不是一篇已完成的学位论文：不宣称“论文已完成”，
  缺失的论文框架写进 `pending_human`。
- 不重写、不改写、不删除作者句子；不评价文笔；不改动工单未指定的块。
- 不发明引文、DOI、图表、章节、实验或数值；含糊单位与矛盾陈述**记录不纠正**。
- 不调用远程客户端、合作账号、Word 修订 XML、任何网络 API；只做本地离线处理。
- 已知限制：PDF 无文本层时降级（不臆造文字）；`.xlsx`/`.doc` 旧格式不解析；
  docx 只取段落文本，标题样式不保留，故节划分可能是启发式；PDF 预览不能内嵌 CJK
  字形（以 `?` 呈现，正文以 md/html 为准）；正则台账对自由式定义有漏检；
  超过约 200k 字符仍可运行，但 `init` 只打印前若干块，请用 `show --target` 定点阅读。

## 7. 失败处理与降级

| 情形 | 行为 |
|---|---|
| 无 `/input`、无 case JSON、case JSON 损坏 | 合法 result.json + `errors` 说明（`input_error`/`partial`），退出 0 |
| 材料读不出 / PDF 无文本层 / xlsx·doc / 超长截断 | 该材料 `degraded|skipped|unreadable` 并记入 `degradations`，其余继续，不臆造文字 |
| target 找不到 / 有 id 无锚点 | `pending_human` + 动作；或启发式定位并标 `resolution: heuristic` |
| 无 `draft.json` | 全量确定性兜底注记，`status=partial`，每个兜底 target 都列出 |
| 引文不命中 / 定位不一致 / 引入材料外数字 | 该条 reject 并给原因，原文状态不变；该 target 若无其它注记则转兜底 |
| 脚本中途异常 | 已有 partial result.json 在盘上，异常入 `errors`，退出 0，重跑 `build` |

## 8. 自查（回复用户前跑一次）

`python3 scripts/main.py selfcheck` 复算并打印：契约字段是否齐全、主产物是否存在且非空、
原文是否逐行保真、注记是否全部落位、六类台账是否覆盖、回退证明是否为真、
`status` 与实际是否相符。人工再确认：

1. `result.json` 可解析，`output_contract` 每个键都在且键名未改；
2. 每条注记都有 `locator` + 逐字 `anchor_quote`，且定位一致；
3. `preserved_facts` 里 `preserved` 全为 `true`（否则查 `errors`）；
4. `pending_human` 写清了缺材料、兜底注记、无法确认项；
5. 没有新增数字/引用/章节号；
6. 报告里 `computed` 与 `agent_review` 分区清楚，未把机械清单当科学结论。

## 9. 产物清单

主产物：`revised_manuscript.md`、`revised_chapters/<材料名>.md`（保留段落 id 与层级）。
辅助：`revision_records.json`、`operation_receipts.json`、`evidence_map.json`、
`change_log.json`、`preserved_facts.json`、`pending_human.json`、
`consistency_report.md`、`consistency_tables.json`、`coverage_matrix.json`、
`versions/{v1_original.md,v2_revised.md,diff_v1_v2.patch,rollback_check.json}`、
`preview.html`、`export_preview.pdf`、`run_manifest.json`、`self_check.json`、`result.json`。

## 10. 评分维度映射

| 维度 | 落点（计数见 `coverage_matrix.json`，口径见 `references/checks.md` §2） |
|---|---|
| 实际效果 40 | target 全覆盖、逐字引文 + 定位一致、原文逐行保真、每条结论带 locator |
| 使用增益 25 | 一次索引全篇、六类差异自动汇总、产物哈希可重放（`run_manifest.json`） |
| 创新 15 | locator 绑定式证据校验、受影响段落回链、机械/判读分区报告 |
| 可靠 10 | 空输入/坏 JSON/缺 target/未知格式/超长的降级，状态不被污染，退出码恒 0 |
| 生态 10 | 本文件 + `references/` 两份规则表 + 五命令接口 |

## 11. 最小调用示例（示例，非正式案例结果）

材料 `chapters/ch05.md` 含 `<!-- T07-P003 -->` 标记，工单 `target_ids=["T07-P003"]`，
`output_contract={"case_id":…,"deliverable":…,"preserved_facts":…,"evidence_map":…,"change_log":…}`。

```bash
python3 scripts/main.py init --input /tmp/case7 --out /tmp/out7 --work /tmp/wk7
#   -> 1 材料 / 9 块 / 1 target / 契约键 5 个
python3 scripts/main.py show --target T07-P003
# agent 写 /tmp/wk7/draft.json：anchor_quote + annotation + evidence + 1 条 findings
python3 scripts/main.py check
#   -> high=0 warn=1 targets 1/1 categories 2
python3 scripts/main.py build
#   -> status=ok annotations_applied=1 preserved 9/9
```

示意输出片段（**示例，非正式案例结果**）：

```json
{"case_id": "T07", "status": "ok",
 "workorder_execution": {"targets": [{"target_id": "T07-P003", "status": "done",
   "locator": "chapters/ch05.md §4 Results ¶2 · T07-P003", "annotations": ["EA-01"]}]},
 "change_log": [{"change_id": "CH-01", "action": "insert_annotation",
   "locator": "chapters/ch05.md §4 Results ¶2", "original_quote": "…", "reversible": true}]}
```

## 12. 文件、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本契约与主路径 |
| `scripts/main.py` | 五个子命令、路径与案例发现、result.json 信封、编排 |
| `scripts/ledger.py` | 材料解析、块索引、locator 解析、引文绑定、稿件重组、保真清单 |
| `scripts/audit.py` | 六类台账、影响回链、工作稿校验（与失效探针共用）、契约回填 |
| `scripts/emit.py` | 由索引 + 工作稿生成交付物、回执、兜底注记、版本证明、覆盖矩阵 |
| `scripts/render.py` | 一致性报告 Markdown、HTML 预览、真实 PDF 预览、diff |
| `references/workflow.md` | 主路径细节、材料索引、locator 语法、工作稿 schema、验收规则、build 不变量、降级表 |
| `references/checks.md` | 六类台账的正则口径与误报边界、评分维度→产物→计数映射、`result.json` 字段字典与契约回填规则、人工自查表 |

版本 1.0.0；纯标准库；Python 3.9+（3.12 实测）；无配置文件、无服务、`/app/work`
之外不落缓存状态。维护约定：解析只改 `scripts/ledger.py`，校验口径只改
`scripts/audit.py`（并同步 `references/checks.md`），渲染只改 `scripts/render.py`，
`scripts/main.py` 只做编排；同一输入与同一工作稿必须得到字节一致的 `revised_manuscript.md`。
