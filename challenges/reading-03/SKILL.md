---
name: sci-lit-bilingual-audit
description: >-
  科研文献「双语对照 + 译后核验审计」工作流。当任务要求把一篇科研论文（PDF / TXT / DOCX /
  HTML / case.json 内嵌正文）翻译成双语段落对照，并且要求术语全篇统一、段落与原一一对应、
  数字单位/公式编号/图表编号/文献引用标记逐字保留、每段译文可指回原文证据时使用。
  提供五项确定性能力：段落对齐索引（含跨页续段与双栏处理）、术语锁定与全篇回扫漂移检测、
  保护性 span 双向差集、逐字引文指纹校验、按契约回填并可降级的结构化结果。
  触发语：翻译这篇文献 / 生成双语对照 / 译文核验 / 术语一致性检查 / bilingual translation
  with verifiable evidence。
version: 1.0.0
---

# sci-lit-bilingual-audit — 文献翻译：回答问题，也给出依据

**本文件是操作指令，不是介绍文案。** 你是评审 Harness 里的执行 Agent。你负责读懂原文并把
每一段真正翻译出来；脚本只负责切段、定位、回扫、校验、渲染。两者职责不得互相替代。

---

## 0. 主路径（第一步，五条命令）

```bash
python3 scripts/main.py init       # 建索引：解析 /input/case.json + 契约 + 材料，切段建对象表，先写合法 partial result.json
python3 scripts/main.py show       # 打印带 locator 的段号与原文片段、保护性 span、术语候选，供你逐字引用
#   ↓↓↓ 在这里你必须亲自阅读材料、逐段翻译，并把结果写成工作稿 /app/work/draft.json ↓↓↓
python3 scripts/main.py check      # 机械校验：契约字段、quote 命中、覆盖率、数字/引用/术语一致、否定与限定
python3 scripts/main.py build      # 由工作稿生成 paragraph_pairs.jsonl / audit_report.json / glossary.json + 最终 result.json
python3 scripts/main.py selfcheck  # 复检产物自身（可选，但建议跑）
```

> **脚本不会代替你阅读理解与翻译；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> 只跑 `init → build` 的结果必然是 `status=partial`、全部段落为 `〔待补:…〕` 占位，只能拿到
> 「完整但降级」的基础分。真正的分数来自 draft.json 里逐段由你写下的译文与术语决定。

命令统一可加 `--input/--work/--output` 覆盖路径（默认 `/input`、`/app/work`、`/app/output`，
不可写时自动回退到 `./input`、`./work`、`./output`）。脚本只用 Python 标准库，不联网，
不依赖当前目录（按脚本自身位置定位包根）。全部命令**退出码恒为 0**；判断结果看 stdout 的
`STATUS:` / `CHECK:` / `BUILD:` 行与产物文件，不看退出码。

---

## 1. 何时使用 / 何时不使用

**适用**：任务给出一篇或一段明确的科研材料，要求（a）译成目标语言或做成双语对照，
（b）术语前后一致，（c）保留数字/单位/公式/图表编号/引用标记，（d）结论可回到原文定位。

**不适用**：只需摘要或大意概述（本 Skill 的价值在逐段可核验，不在泛读）；纯图片扫描件
且环境无 OCR（只能降级为 `insufficient_evidence` 并说明）；非文献类文本（合同、代码）除非
用户明确要求同样口径。

---

## 2. 输入发现顺序（不要假设，要探查）

1. `/input/case.json` — 读 `case_id`、`task_instruction`、`output_contract`、可选内嵌正文
   （`text` / `content` / `body` / `paper_text` / `materials[].text`）、可选 `target_language`。
2. `/input/task.md` — 题面补充要求。**与 case.json 冲突时以 task.md 的显式指令为准**，
   并把冲突写入 `uncertainties`（脚本已记录在 `index.json.conflicts`）。
3. 材料文件：递归扫描 `/input` 下 `.pdf .txt .md .markdown .html .htm .docx .json`，
   跳过 `case.json`、`task.md` 自身。PDF 用 `pdftotext -layout`（若系统有），否则用内置
   PDF 文本层解析器；两条路都记入 `index.json.sources[].extractor`。
4. `init` 会把以上全部结果落到 `work/index.json`，并对无文本层、页数不符、双栏错乱、
   编码异常分别写 `warnings`。**先看 `show` 的 WARN 行再决定翻译策略。**

---

## 3. 输入 / 输出契约

| 方向 | 路径 | 内容 |
|---|---|---|
| 入 | `/input/case.json` | `case_id`、`task_instruction`、`output_contract`（必回填）、内嵌正文可选 |
| 入 | `/input/task.md` | 题面（冲突时优先） |
| 入 | `/input/*` 其余 | 论文 PDF / TXT / DOCX / HTML |
| 中 | `work/index.json` | 材料清单、页表、段落对象表（sid / locator / type / spans / bridged）、术语候选 |
| 中 | `work/draft.json` | **你写的工作稿**（schema 见 `references/checks_spec.md` §5） |
| 中 | `work/check_report.json` | `check` 的机械校验明细 |
| 出 | `output/result.json` | 主产物：原样回填 `output_contract` 全部字段 + 信封字段 |
| 出 | `output/paragraph_pairs.jsonl` | 主产物：每行一段 `{sid, locator, page, type, source, target, terms, spans_ok, notes, uncertain}` |
| 出 | `output/audit_report.json` | 主产物：每条核验项 `pass/fail/warn/skip` + 段号 + 原文/译文片段 + 指标率 |
| 出 | `output/glossary.json` | 术语表：`term / target / status(locked|proposed|conflict) / evidence / quote_verified / occurrences[]` |
| 出 | `output/bilingual_review.md` | 人读视图（派生自段落对，供评审快速核对，不替代 jsonl） |

`result.json` 信封固定字段：`case_id`、`status`、`skill{name,version}`、`task_understanding`、
`sources`、`summary`、`glossary`、`audit_summary`、`evidence`、`uncertainties`、`pending_human`、
`degradations`、`errors`、`change_log`、`outputs`、`runtime`，加上 `output_contract` 的每个键
（名字不改、不漏；无值用 `null`，列表型契约给 `[]`）。

`status` 取值与含义：

- `answered` — 全部段落译完、覆盖率 1.0、核验 fail 数 0。
- `partial` — 有缺失段落 / 有 fail 项 / 有未解决存疑；**必须**在 `degradations` 写明缺口段号。
- `insufficient_evidence` — 材料存在但无可翻译文本（无文本层、文本量过小、语言不支持）。
- `input_error` — `/input` 缺失、`case.json` 坏 JSON、材料全不可读。

---

## 4. 五条命令详解

### 4.1 `init`
建 `work/index.json`，切段，抽取保护性 span 与术语候选，并**立即写出**一份合法
`output/result.json`（契约字段全在、`status=partial`、`degradations` 说明尚未翻译）。
该文件在任何后续步骤失败时都保证存在且可解析——这是兜底底线，不要删除它。

### 4.2 `show`
```bash
python3 scripts/main.py show                  # 全部段落
python3 scripts/main.py show --from 1 --to 8  # 分批（推荐：每批 6–10 段）
python3 scripts/main.py show --terms          # 只打术语候选（含出现段号与上下文）
```
输出形如：
```
S007 @p3 [body] bridged=p2-p3 words=64
  SRC  : ...原文...
  SPANS: pct=87.3% | cite=[12] | fig_ref=Fig. 2
```
`SRC` 是**唯一合法引文来源**：你写进 draft 的 `source` 与术语 `quote` 必须从 `SRC` 逐字复制
（允许行内多个空格压成一个，脚本按空白归一化比对，但标点、大小写、连字符必须一致）。

### 4.3 写工作稿（你的主要工作，也是预算主要消耗处）
把译文写成 `work/draft.json`。**分批写**：每翻完 6–10 段就落盘一次，不要攒到最后一次性写；
脚本会合并 `work/draft.json` 与 `work/draft_part_*.json`（后者覆盖前者同 sid）。
schema 与字段字典见 `references/checks_spec.md` §5，最小可用样例：

```json
{
  "case_id": "CASE-01",
  "task_understanding": "任务要求：把论文正文译为中文双语对照，锁定术语，保留数字与引用。",
  "glossary": [
    {"term": "few-shot", "target": "少样本", "basis": "P003 首次定义", "sid": "S003", "quote": "few-shot fault diagnosis"}
  ],
  "segments": [
    {"sid": "S003", "source": "我们提出…（逐字原文）", "target": "……译文……",
     "term_hits": ["few-shot"], "notes": "被动改主动，未改限定词", "uncertain": false}
  ],
  "result_fields": {}
}
```
翻译口径（硬性，脚本会机械检查）：
- **不合并不拆分**原段；段号与原一一对应，`sid` 只能取 `show` 给出的值。
- **数字/单位/百分号/p 值/统计量/公式编号/图表编号/文献引用标记逐字保留**；可把 `Fig. 2`
  译为 `图2`，但编号必须一致；`[12]`、`(Smith et al., 2020)` 原样留在译文中。
- **否定与限定不得弱化**：`not / only / rarely / may / suggest / associated with` 必须在译文中
  有对应成分（不/仅/罕/可能/提示/相关）；不得把"可能"译成"会"，不得把"相关"译成"导致"。
- **不润色、不改写、不省略从句**；译者补的说明只能写进 `notes`，不能混入 `target`。
- 拿不准的句子：给最佳译文 + `uncertain: true` + `notes` 写疑点；这是诚实降级，不是扣分点，
  但**不许**把不确定内容写成确定事实。
- 参考文献条目、纯符号公式：`target` 保留原文（可只译引导语），`notes` 说明"reference kept verbatim"。

### 4.4 `check`
```bash
python3 scripts/main.py check          # 打印 CHECK: 汇总 + 每条 fail 的段号与片段
python3 scripts/main.py check --strict # 有 fail 时退出码 1（仅用于本地，Harness 里不要用）
```
检查项（规则表见 `references/checks_spec.md`）：`contract_fields`、`sid_integrity`、
`source_verbatim`、`coverage`、`glossary_lock`、`glossary_quote`、`glossary_drift`、
`protected_numbers`、`citations`、`figure_table_refs`、`equation_tags`、`negation`、`hedge`、
`placeholder_policy`、`target_language`。
`fail` 必须回去改 draft 并重跑 `check`；`warn` 表示需要人工确认，写进 `pending_human` 即可。
改不动又必须交付时：把该段标 `uncertain: true` 并在 `notes` 引用具体检查项（如
`number_missing: 4.2%`），这样失败会如实进入审计报告而不是被掩盖。

### 4.5 `build`
```bash
python3 scripts/main.py build                    # 状态由覆盖率与 fail 数推导
python3 scripts/main.py build --status partial   # 只允许更保守的方向（answered→partial 可以，反向被拒）
python3 scripts/main.py build --note "第二轮修正 S012 数字"   # 追加 change_log
```
`build` **无条件 finalize**：即使 `draft.json` 不存在、坏 JSON、只覆盖了一半段，也会产出
契约字段齐全的 `result.json` + 三个机器可读产物 + 人读视图，`status=partial`，
`degradations` 逐条写明缺口（缺哪几段、缺哪个契约字段、哪个检查 fail）。

### 4.6 `selfcheck`
不复用 build 的内存结果，而是**重新读盘**：验证 `result.json` 可解析、契约键一个不少、
`paragraph_pairs.jsonl` 行数与 `index.json` 段数一致、`answered` 状态下滑稽项为 0
（无占位符、无 fail、locked 术语 quote 全部命中）。输出 `SELFCHECK: PASS|WARN|FAIL n`。

---

## 5. 术语表怎么定（locked 的门槛）

1. `init` 给出候选（缩写、连字符词、双词短语、`full name (ACRONYM)` 定义对）。
2. 你从原文确认 10–40 条领域术语，写进 `draft.glossary`，每条给 `sid` + `quote`。
3. 脚本判定：`quote` 在该 `sid` 原文中逐字命中 → `locked`；未命中 → 降为 `proposed`
   并记 fail（**没有逐字证据的术语不允许锁定**）；同一 `term` 出现两个不同 `target` → `conflict`。
4. 全篇回扫：每个 `locked` 术语在其出现的所有段落里，译文必须包含锁定译名，否则
   `glossary_lock` fail 并列出漂移段号；漂移率写进 `audit_report.rates.glossary_consistency`。

缩写首现规则：`full name (ACRONYM)` 首次出现处译为「全名（缩写）」，其后只保留缩写。

---

## 6. 保护性 span 与占位符

**保护性 span**：`pct`、`num_unit`、`pvalue`、`stat`、`pm`（±）、`range`、`cite_bracket`、
`cite_author`、`eq_tag`、`fig_ref`、`greek`、`chem`。脚本对原文与译文做双向差集：
原文有、译文缺 → `fail`；译文多出原文没有的数字 → `warn`（可能是你补的编号/节号）。

**三类占位符语义互不通用**（脚本按字面识别并单独计数）：

| 占位符 | 含义 | 覆盖账本记入 |
|---|---|---|
| `〔待补:S012〕` | 尚未翻译（缺工、超预算） | `missing` |
| `〔未译:S013:reference〕` | 按策略不译（参考文献/纯符号） | `skipped`（不算缺失） |
| `〔存疑:S014:术语待定〕` | 已译但不确信 | `translated` + `uncertain` |

---

## 7. 降级与失败处理（如实上报，不编造）

| 情形 | 脚本行为 | 你必须做的 |
|---|---|---|
| `/input` 不存在 / 空目录 | `status=input_error`，契约字段全 null/[]，退出码 0 | 在 `uncertainties` 写明缺什么，不要编造论文 |
| `case.json` 坏 JSON | 记录 `errors`，仍尝试读 `task.md` 与材料 | 同上；不要因为 JSON 报错就停止落盘 |
| PDF 无文本层 / 扫描件 | `init` 报 `needs_ocr`，`status=insufficient_evidence` | 说明需 OCR 或文本版；不要凭图猜正文 |
| PDF 用内置解析器（无 pdftotext） | `warnings` 记 `builtin_pdf_extractor`，页码可能按流序号估计 | 跨页断言改成"页序估计"，在 notes 标注 |
| 双栏错乱 | `warnings` 记 `column_layout_suspect` + 受影响段号 | 译文顺读为准，notes 标注该段可能串栏 |
| 文本过长 / 预算将尽 | 未译段自动 `〔待补:…〕`，`status=partial` | 优先摘要+正文主体；图注与参考文献可 `〔未译:…〕` |
| 术语无法确定 | 该条 `proposed`，不参与回扫 | 写入 `uncertainties`，给候选译名 |
| 原文语言混杂 | 目标语言检查跳过非目标语种段 | 非英文片段照抄原文并在 notes 说明 |

预算：64 次模型请求 / 900 秒 / 单次响应 ≤16384 token。经验配比：`show` 分批读 3–5 次，
翻译 10–20 次，`check`/返修 3–5 次，`build`/`selfcheck` 各 1 次，留 5 次余量。

---

## 8. 自查清单（交付前）

- [ ] `output/result.json` 可 `json.load`，`case_id` 与 `/input/case.json` 一致。
- [ ] `output_contract` 的键在 `result.json` 中**一个不少**（`selfcheck` 会逐键比对）。
- [ ] `paragraph_pairs.jsonl` 行数 = `index.json` 段数；`sid` 不重不漏、顺序单调。
- [ ] 每个 locked 术语有 `quote_verified: true`；`rates.glossary_consistency` 已给出。
- [ ] `audit_report.json` 的 fail 项为 0，或每个 fail 都能在 `pending_human` 找到对应条目。
- [ ] `status` 与覆盖账本自洽（覆盖率 1.0 且 fail=0 才可能是 `answered`）。
- [ ] `degradations` 和 `uncertainties` 非空时，写的是**具体缺口**（段号/字段/检查项），不是套话。

---

## 9. 复用与维护

- `output/glossary.json` 可跨篇复用：新论文 `init` 后把它拷成 `work/glossary_seed.json`，
  `check` 会自动并入（seed 条目只作 `proposed`，仍需新篇 quote 才能 `locked`）。
- 切段规则、span 规则、核验口径全部写在脚本 docstring 与 `references/checks_spec.md`，
  改规则只改脚本常量，不要改 SKILL.md 里的承诺。
- 同一输入重跑结果稳定（所有列表按 sid / 术语名排序，无时间戳参与排序）。
