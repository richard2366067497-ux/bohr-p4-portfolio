---
name: statistical-audit-ledger
description: Audit a manuscript's research design, variable definitions, statistical methods, sample size and result reporting by building a per-result statistical audit ledger first, then deriving typed findings from the ledger's non-OK cells. Every finding carries a verbatim quote plus a resolvable locator, separates "not reported" from "done wrong", and caps severity accordingly; outputs result.json (full output_contract backfill), audit_report.md, statistics_ledger.json, findings.json and coverage.json. Use for 论文质量审查 / 统计审查 / 方法学审查 / 结果报告核对 / 审稿意见单 / statistical review tasks.
version: 1.0.0
---

# 统计审计台账：研究方法与统计审查（台账优先 / Agent 主答 + 脚本辅助）

## 0. 单命令入口（评测环境先看这里）

```bash
SK=/skills/weekly-skill; [ -f "$SK/SKILL.md" ] || SK="$(dirname "$(find / -maxdepth 5 -name SKILL.md 2>/dev/null | head -1)")"
cd /app/work

# ★ 单命令完成全流程：init → 确定性自动推导（无 draft 时的回退）→ build → 契约回填
python3 -B "$SK/scripts/main.py" all
```

`all` 是**自包含单入口**：一条命令即可产出 `result.json`（output_contract 全回填）+ `audit_report.md` +
`statistics_ledger.json` + `findings.json` + `coverage.json`。若评测 Agent 只有一次命令机会，**请运行 `all`**。
无工作稿时，脚本按**原文可逐字核验的报告完整性规则**派生 findings（`auto_derived=true`、`confidence=low`），
每条都带引文 + locator，绝不编造数据；写了 `draft.json` 再跑则进入高质量人工判定路径（推荐）。

## 0.1 完整 agent-first 路径（有工作稿时质量更高，按顺序执行）

```bash
python3 -B "$SK/scripts/main.py" init        # ① 建索引 + 抽取候选台账行 + 先写合法 partial result.json
python3 -B "$SK/scripts/main.py" show        # ② 打印带 locator 的原文与候选台账行，供逐字引用
#   ③ 你（Agent）亲自阅读材料，判断每一行，写 /app/work/draft.json（台账 + 台账外发现）
python3 -B "$SK/scripts/main.py" check       # ④ 机械校验：契约字段、quote 逐字命中、枚举、严重度上限、覆盖计数
python3 -B "$SK/scripts/main.py" build       # ⑤ 台账 → 报告/台账/findings/coverage/result.json（`all` 已内置 init+build）
python3 -B "$SK/scripts/main.py" selfcheck   # ⑥ 复检（可选）
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
>
> 脚本只做确定性的活（解析、定位、逐字比对、枚举校验、覆盖统计、渲染、契约回填）。
> 判断类的工作必须在 `draft.json` 里由你写：哪一行结果用了什么检验、这个检验配不配这个数据结构、
> 缺的是"没报告"还是"做错了"、严重度定几级、怎么改。
> 只跑 `build` 而不写 `draft.json`，脚本只能给你"降级版最小交付"（status=partial），拿不到审查质量分。

## 1. 用途与适用条件

**用途**：把一份科研稿件（论文、预印本、学位论文方法/结果章、审稿回复稿）变成一份**可逐条回复的统计审查单**。
过程是「先建台账，再派问题」：

1. **台账**（`statistics_ledger.json`）：稿件里**每一个被报告的结果/检验占一行**，逐列记录它该有的要素——
   比较对象、样本量 n、声明的检验、检验与数据结构是否匹配、前提假设、统计量与自由度、p 值、效应量、置信区间、
   多重比较处理、失访/剔除、原文位置、逐字引文、五个检查面的格子状态、缺陷性质、严重度。
2. **问题**（`findings.json`）：**只由台账里非 `ok` 的格子派生**，每条带 `ledger_id` 可反查；台账覆盖不到的
   设计/规范/引用类问题走 `extra_findings`。

**适用**：随机对照试验、观察性队列/病例对照、横断面调查、诊断准确性、Meta 分析、机器学习/组学模型的
方法与结果报告审查；稿件有可读文本层（PDF/TXT/MD/DOCX/XLSX/CSV/JSON）。

**不适用**（明确不做）：文献检索与综述、全文翻译、语言润色、代写审稿结论（accept/reject）、投稿决策、
对未提供的原始数据重新做统计分析、图像造假的像素级取证。遇到这类请求，在 `summary` 与
`unchecked_items` 写明“超出本 Skill 范围”，不要把超出范围的部分硬做成结论。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`（`case_id`、`output_contract`、`task_instruction` 等）+ `/input/task.md` + `/input/**` 材料 |
| 工作区 | `/app/work`（`index.json`、`ledger_seed.json`、`draft.json`、`check_report.json`） |
| 产物 | `/app/output/result.json`、`audit_report.md`、`statistics_ledger.json`、`findings.json`、`coverage.json` |
| 依赖 | 仅 Python 3 标准库；`pdftotext` 存在时优先用，缺失自动回退；不联网、不装包 |
| 路径 | 不依赖 CWD；`SCIM_INPUT` / `SCIM_OUTPUT` / `SCIM_WORK` 可覆盖；无 `/input` 时回退 `./input`、`/bohr-workspace/input` |
| 退出码 | 恒 0（异常写进 `errors` / `degradations`，不中断） |

## 3. 输入发现（按语义识别，不按标签猜内容）

1. `case.json` 依次尝试 `utf-8-sig` / `utf-8` / `gb18030` / `latin-1`；损坏也继续，原因写 `errors`。
2. 递归 `/input/**`，跳过 `case.json`；类型按**扩展名 + 魔数**判定（`%PDF`、`PK` + `word/`、`xl/`、PNG/JPEG 魔数等），
   不依据文件名里的领域词推断内容。`task.md`/`README.md` 标为 `instruction`，只作任务说明，不进台账候选行。
3. 语义字段识别：`task_instruction` / `task` / `instruction` / `prompt`、`output_contract` / `output_spec` / `contract` /
   `deliverables`、`case_id`（缺失时用目录名 + 哈希派生，并记为降级）。
4. 每个材料分配稳定 `id`，正文切成带 `locator` 的单元：`mat:p3`（PDF 页）、`mat:p3.2`（超长页再切块）、
   `mat:§Results/L21`（按标题切段 + 起始行）、`mat:L12`（无标题纯文本）。`locator` 前缀即材料 id，
   引文校验命中后脚本会把 locator 回写成真实位置。

## 4. 输出契约（result.json）

- **原样回填 `output_contract` 的全部字段**：不改名、不漏键；识别不到对应内容的填 `null` / `[]`，
  并在 `degradations` 写 `contract_field_unmapped:<字段>`。同时在 `output_contract` 子对象里回显同样内容（兼容两种读法）。
- 必备信封字段：`case_id`、`status`（`ok` 全部到位 / `partial` 有降级或待复核 / `input_error` 无可用材料）、
  `sources`、`uncertainty`、`pending_review`、`errors`、`degradations`、`changes`、`runtime`；另附
  `unchecked_items`（未检查项）与 `artifacts`（产物路径），便于第三方定位。
- 契约字段按语义映射（键名不必一致）：`report/audit/review*` → 审查报告；`finding/issue/defect/问题*` → 问题列表；
  `ledger/stat*` → 台账；`coverage/checklist/facet*` → 覆盖表；`evidence/source/quote*` → 证据索引；
  `status/state*` → 运行状态；`pending/uncertain/unknown*` → 待复核与不确定。
- `init` 与 `build` 开头都先写一份**合法的 partial** `result.json`，之后只做覆盖式升级，绝不留在半写状态。

## 5. 台账模型（本题核心）

一行 = 一个被报告的结果/检验。列分三组：

| 组 | 字段 | 说明 |
|---|---|---|
| 事实 | `ledger_id` `result_question` `comparison` `n` `test_declared` `statistic` `df` `p` `effect_size` `ci` `multiple_comparison` `sample_size_basis` `attrition` `source_locator` `quote` | 只抄稿件里**写了的**；没写就填 `not_reported`，不许推算 |
| 判定 | `test_appropriate`(`true|false|unknown`)、`assumptions{normality,variance,independence}`(`checked|violated|not_reported|n/a`) | 方法与数据结构是否匹配 |
| 定性 | `cell_status{design_fit,variable_definition,statistics,sample_size,reporting}`(`ok|gap|na`)、`defect_nature`、`severity`、`severity_reason`、`issue_type`、`recommendation` | 五个检查面 × 缺陷性质 × 严重度 |

**缺陷性质三态**（`references/audit-rules-and-schema.md` 有完整锚点表）：

| `defect_nature` | 含义 | 严重度上限 |
|---|---|---|
| `method_flaw` | 方法/判定本身错了（检验不匹配、独立性违反、多重比较未校正、变量编码与模型冲突、数值自相矛盾） | `critical` |
| `underreporting` | 作者**没报告**该报告的要素（无 CI、无效应量、样本量依据缺失、失访未交代）——不等于做错 | `major`（`check` 自动降级并记 `changes`） |
| `acceptable_but_should_clarify` | 做法可接受但表述/边界需澄清（自定义切点无来源、术语歧义、规范条目缺失） | `minor` |
| `none` | 该格没问题 | `none` |

**"未报告 ≠ 做错"是硬规则**：把"没写样本量估算"判成 `method_flaw` + `critical` 的，`check` 会报
`defect_nature_mismatch` 并按上限回写；`underreporting` 一律 ≤ `major`。

## 6. 工作稿 `/app/work/draft.json`

骨架由 `init` 生成到 `/app/work/draft_skeleton.json`，字段字典见 `references/audit-rules-and-schema.md`。
最小可用内容：

```json
{"case_id": "...",
 "manuscript_meta": {"title": null, "design_type": null, "field": null, "target_guideline": null, "n_reported": null},
 "statistics_ledger": [{"ledger_id": "L-01", "...": "见 §5 与 references/audit-rules-and-schema.md"}],
 "extra_findings": [{"facet": "design_fit", "issue_type": "design_mismatch", "...": "..."}],
 "unchecked_items": [{"item": "...", "reason": "..."}],
 "uncertainties": ["..."],
 "summary": "..."}
```

填写纪律：

- `quote` 必须与材料原文**逐字一致**（含标点）；只允许 NFKC、空白折叠、去零宽这类无害规范化。
  `check` 会逐字查找，找不到记 `evidence_rejected`。
- 抽不到的台账行（例如只有图注、只有一句话的摘要结果）由你手动补行，`ledger_id` 顺延。
- 读不出的（扫描件无文本层、图表无数据、统计输出缺失）写 `unchecked_items`，不要猜。

## 7. 五个检查面与六类审查面

五个检查面（写入 `cell_status`）：`design_fit`（设计与研究问题/对照/盲法/主要终点）、
`variable_definition`（暴露/结局/协变量定义、切点、单位、缺失值、变量类型与模型）、
`statistics`（检验与数据结构、分布假设、独立性、多重比较、重复测量、交互、敏感性分析）、
`sample_size`（估算依据、效应量来源、α/把握度、实际入组、失访剔除）、
`reporting`（效应量与 CI、精确 p、统计量与 df、图表与正文一致、报告规范条目）。

六类审查面（写入每条 finding 的 `dimension`）：`fact`（事实/数值核验）、`citation`（引用是否支持该句）、
`method`（方法设计）、`stat_report`（统计报告）、`argument`（论证链）、`norm`（学术规范：伦理、注册、数据可得、利益冲突）。

`coverage.json` 会同时给出两张表：五面判定分布 + 六维命中计数；`check` 对"零覆盖"的检查面报 `coverage_gap`。

## 8. 证据与定位规范（可核验性）

- 每条 finding 必须有：`source_locator`（可回到材料的定位串）+ `quote`（逐字原文，≥8 字符）+ `severity_reason`（判断依据，写清用了哪条方法学规则、为什么是这个级别）。
- 数值必须溯源：p 值、CI、n、统计量都要落在台账对应列的原文 quote 上；脚本**不重算统计量**，
  只做"文内一致性"比对（摘要 vs 正文 vs 表格），差异写 `internal_inconsistency` 并给两处 locator。
- 严重度必须给 `severity_reason`，且与 `defect_nature`、`issue_type` 的锚点一致（见 §5 与规则文件）。

## 9. 失败处理与降级

| 情况 | 处理 | status |
|---|---|---|
| `/input` 全空 | 写空台账 + 说明性报告，`degradations:[no_input_materials]` | `input_error` |
| `case.json` 缺失/坏 JSON | 继续，`errors:[case_json_missing|bad_case_json]`，`case_id` 用目录名 + 哈希派生；材料可读时仍出审查单 | `partial` |
| `output_contract` 缺失 | 用内置默认字段集（report/findings/status…），`degradations:[no_output_contract]` | `partial` |
| PDF 无文本层/扫描件 | `pdftotext` → 内建回退；仍为空则 `material_unreadable`，进 `unchecked_items`，不猜内容 | `partial` |
| 图表无数据、统计输出缺失 | 进 `unchecked_items`，标 `pending_review` | `partial` |
| `draft.json` 缺失/不完整 | `build` 输出完整最小交付：骨架台账 + 契约全回填 + 说明性 `audit_report.md`，缺口写 `degradations` | `partial` |
| quote 找不到 | 该条降级为 `pending_review` 并记 `evidence_rejected`，不冒充已核实 | `partial` |
| 任一未捕获异常 | 兜底写 partial `result.json`，`errors` 记录 traceback 首行，退出码 0 | `partial` |

## 10. 自查

- [ ] `init` → `show` → 写 `draft.json` → `check` → `build` 全部执行，`check` 无 ERROR（或 ERROR 已进 `pending_review`）
- [ ] `result.json` 含 `output_contract` 全部字段 + 信封字段（`case_id`/`status`/`sources`/`uncertainty`/`pending_review`/`errors`/`degradations`/`changes`/`runtime`），`case_id` 与输入一致
- [ ] 每条 finding 有 `ledger_id` 或 `extra_findings` 的定位+逐字 quote，且 quote 命中
- [ ] `underreporting` 的严重度 ≤ `major`，`acceptable_but_should_clarify` ≤ `minor`
- [ ] 五个检查面都有判定（不是全 `na`）；六维覆盖表无零行，或缺口写进 `unchecked_items`
- [ ] `audit_report.md` 七节齐全，台账总表行数 = `statistics_ledger.json` 行数
- [ ] 两次运行 `result.json` 内容一致（脚本输出确定性；时间戳只进 `run_manifest.json`）

## 11. 文件清单

```
SKILL.md                              本文件：契约、台账模型、流程、降级、自查
scripts/main.py                       init | show | check | build | selfcheck（CLI 编排）
scripts/extract.py                    路径/JSON IO、材料嗅探与抽取、locator、逐字比对、候选行抽取（--selftest）
scripts/ledger.py                     枚举与兼容表、严重度封顶、行/发现校验、派生、覆盖、契约映射、渲染（--selftest）
references/audit-rules-and-schema.md            draft.json 字段字典与填写示范
references/audit-rules-and-schema.md     缺陷性质三态、issue_type 表、严重度锚点、覆盖口径
references/audit-rules-and-schema.md        五面 × 六维检查项清单（可直接复用为人工 checklist）
```

维护约定：脚本行为改 §0/§9，字段改 §5/§6 与 `draft_schema.md`，判定规则改
`ledger_and_severity.md`；改完跑 `python3 -B scripts/extract.py --selftest`、
`python3 -B scripts/ledger.py --selftest` 与 §0 的五个命令。

## 12. 最小调用示例（示例，非正式案例结果）

输入：`/input/case.json`（`case_id=demo-001`，`output_contract={"case_id","status","review_report","findings","evidence","coverage","uncertainty","pending_review"}`）
+ `/input/task.md` + `/input/manuscript.md`（三臂研究，Methods 写「三臂两两 t 检验」，Results 只给 `t(58)=2.31, p=0.03`）。

```bash
SK=/skills/weekly-skill; cd /app/work
python3 -B "$SK/scripts/main.py" init
# → INIT case_id=demo-001 | materials=2 | chars=1160 | seed_rows=3 | contract_fields=8
python3 -B "$SK/scripts/main.py" show
# → L-01 [manuscript:§3.1_Primary_outcome/L19]  p=['p = 0.03'] stat=['t=2.31']
#      “The primary outcome differed significantly (t(58) = 2.31, p = 0.03).”
# 写 draft.json（两行台账 + 三条 extra_findings）后：
python3 -B "$SK/scripts/main.py" check
# → CHECK rows=2 extra=3 findings(derived)=5 | CAP L-02 critical>major | coverage facets 5/5 | RESULT: PASS
python3 -B "$SK/scripts/main.py" build
# → BUILD status=ok | ledger_rows=2 findings=5 | severity {major:3, minor:1, suggestion:1}
python3 -B "$SK/scripts/main.py" selfcheck
# → SELFCHECK quotes_ok=5 quotes_bad=0 | RESULT: PASS
```

示意输出（**示例，非正式结果**）：`result.json.findings[0]` =
`{"finding_id":"F-01","source":"ledger","ledger_id":"L-01","facet":"statistics","dimension":"method",
"issue_type":"multiple_comparison_uncorrected","defect_nature":"method_flaw","severity":"major",
"source_locator":"manuscript:§3.1_Primary_outcome/L19","quote":"The primary outcome differed significantly (t(58) = 2.31, p = 0.03).",...}`。

## 13. 版本、来源与兼容性

| 项 | 值 |
|---|---|
| 版本 | `1.0.0`（`SKILL.md` frontmatter 与 `scripts/*.py` 的 `VERSION` 一致） |
| 依赖 | Python ≥ 3.8 标准库；可选外部命令 `pdftotext`（poppler-utils），缺失时用内建回退并记 `pdf_engine:raw_fallback` |
| 安装 | 无安装步骤：把本目录放到 `/skills/weekly-skill`（或任意目录，用 §0 的 `find` 回退定位） |
| 数据来源 | 只读 `/input/**`；不联网、不调用外部 API、不读作者个人文件 |
| 不适用 | 文献检索与综述、全文翻译、语言润色、代写审稿结论、投稿决策、对未提供原始数据的重新统计分析 |

已知限制：PDF 只有文本层时可用；扫描件、纯图片表格、图中曲线读数不在能力范围内（会写进
`unchecked_items`，不猜数值）。中文与英文稿件都支持；混排或双栏 PDF 可能出现断行错位，
此时 `quote` 只取单句/单行片段，避免跨栏拼接。
