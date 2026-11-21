---
name: academic-compliance-matrix
description: 把一篇论文/科研材料过一遍学术规范与合规审查：以「可核对要求 × 状态」的合规矩阵为唯一事实源（需求来源分级、四态判定、逐字证据 + locator），派生违规清单、待人工核实项、PII 台账与整改优先级，产出 compliance_report.md / compliance_matrix.csv / pii_ledger.json / result.json。脚本只做抽取、定位、校验与渲染，判断由 Agent 写工作稿完成；缺稿也会输出完整降级交付。
version: 1.0.0
---

# 学术规范与合规审查：合规矩阵优先（Agent 主答 + 脚本辅助 + 兜底必成）

## 1. 这是什么

输入一份论文、报告或学位论文章节（可能附带文献表、目标期刊作者指南、数据/材料清单），输出一份**逐条可核对**的合规审查：

- **主产物是合规矩阵**（`compliance_matrix`）：每一行 = 一条可核对的要求（requirement）+ 它的来源等级（`rule_source`）+ 期望（`expected`）+ 实际观察（`observed`）+ 判定（`verdict`）+ 原文位置（`evidence_locator`）+ 逐字证据（`quote`）+ 严重度与整改建议。
- **违规清单 `findings[]` 是矩阵的派生视图**：只由 `verdict=violation` 与需要人工确认的行生成，每条带 `matrix_row_id` 可以反查回矩阵行。矩阵是唯一事实源，报告不是。
- 另外三个产物：`pii_ledger.json`（可识别个人信息台账，只记类型+位置+脱敏形式）、`compliance_report.md`（矩阵→违规→待核实→整改）、`result.json`（原契约字段全回填 + 信封字段）。

这样设计的理由：审查结论最大的失败模式不是"少列几条"，而是"结论无法回查"。矩阵把结论强制绑定到 (要求, 位置, 逐字证据) 三元组上，报告、findings、整改建议都从同一张表生成，因此同一份材料可以复跑出基本一致的结论。

**做什么**：合规矩阵构建、逐条判定、证据定位、严重度分级、误报抑制、PII 台账、引用-文献表对账、整改优先级、可复跑脚本与结果信封。

**不做什么**：不润色、不代写、不代投稿、不重新分析数据、不设计实验、不出具法务或伦理委员会的正式意见；不核实文献是否真实存在（离线无法联网，只能核对形式与内部一致性，存在性一律 `unverifiable` + 人工核对项）。

## 2. 何时用 / 何时不用

- **用**：手上有稿件/报告/章节文本 + 需要"按学术规范逐条过一遍"；投稿前自查、结题材料自查、答辩前检查、编辑部初审预检；材料含文献表、声明区块、图注、伦理/数据可用性说明的任意组合。
- **不用**：任务要求的是写作、翻译、润色、数据分析复现、查重率计算（需要外部库/服务）、或要求给出正式伦理/法务结论。
- **不适用**：无法解析的材料（纯扫描件且无 OCR）、只有标题没有正文、任务要求对不存在的外文指南逐条比对而材料里没有该指南（此时矩阵相关行必须 `unverifiable`）。

## 3. 五命令主路径（先看这里）

在 Skill 根目录（评测环境为 `/skills/weekly-skill`）依次执行：

```bash
python3 scripts/main.py init       # 1) 建索引：解析 case.json/output_contract/task.md，切段落带 locator，扫声明区块/引用/文献表/PII 候选，生成矩阵种子行；先写一份合法 partial result.json
python3 scripts/main.py show       # 2) 打印带 locator 的候选清单（种子行 + 命中片段 + 引用缺口 + PII 候选），供逐字引用
#    3) 评审 Agent 亲自读材料，把判断写进工作稿 /app/work/draft.json（从 /app/work/draft.template.json 复制后逐行填）
python3 scripts/main.py check      # 4) 机械校验：契约/枚举/逐字证据命中/locator 与引文一致/覆盖/台账/编造检测
python3 scripts/main.py build      # 5) 由工作稿生成 compliance_matrix.csv + compliance_report.md + pii_ledger.json + run_manifest.json + result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # 6) 复检产物（可重复执行，只读）
```

**脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 `build`；禁止只跑 `build` 就结束。**

只跑 `build` 的后果是可预期的：矩阵行全部停在 `unverifiable`，`status=partial`，报告里写满"未读材料"的缺口——这是"完整但降级"的地板，不是交付。真正的分数来自 `draft.json` 里你亲自写下的判断。

预算意识：确定性重活（解析、切段、定位、去重、校验、渲染）都在脚本里；模型只做"读 + 判 + 写"三件事，单案例 5 次命令左右，不要为了重跑而重读全文。

## 4. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`output_contract`、`task_instruction` 等）、`/input/task.md`、`/input/**` 下的案例材料（pdf/docx/txt/md/csv/json/html…） |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`draft.template.json`） |
| 产物目录 | `/app/output`（`result.json` 等 5 个文件） |
| 路径覆盖 | `--input/--output/--work`，或环境变量 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK`；默认路径不存在时自动回退到 CWD 下的 `input/output/work`，并记入 `degradations` |
| 退出码 | **恒为 0**。失败信息写进 `result.json.errors/degradations`，不靠退出码表达 |
| 首写 | `init`/`build` 的第一件事都是先落盘一份**契约字段齐全**的 partial `result.json`，后续任何异常都不至于留下空目录 |
| result.json | `output_contract` 的**全部键原样回填**（不改名、不漏键、缺值 null/[]，嵌套 dict 契约逐层回填）；再叠加信封字段 `case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime/method/coverage/artifacts` |
| status | `ok` \| `partial` \| `insufficient_evidence` \| `input_error`，语义见 §10 |
| 依赖 | 纯 Python 标准库；不联网；不依赖 CWD；无第三方包；`pdftotext` 可选（缺失走内置解析器） |

## 5. 矩阵模型（核心方法，先读懂再写 draft）

### 5.1 需求来源五级 `rule_source`

矩阵的每一行必须声明这条要求"凭什么"。等级决定它能不能被判定为 `violation`：

| rule_source | 含义 | 可否判 violation | 写法要求 |
|---|---|---|---|
| `ethical_norm` | 通用学术伦理/科研诚信规范（如 ICMJE、COPE、赫尔辛基宣言所体现的通行要求） | 可以 | 只写"要求内容"，**不写条款号**（无原文时写条款号就是编造） |
| `venue_guideline` | 材料中实际给出的目标期刊/会议作者指南 | 可以 | 必须给指南出处（材料内 locator 或文件名）|
| `provided_policy` | 材料中实际给出的机构/项目/数据方政策（数据使用协议、单位规范） | 可以 | 同上 |
| `general_practice` | 领域通行实践（不是硬性规范） | 判 `minor`/`suggestion` 不受限；判 `major` 须在 `severity_reason` 说明为何属必改项；**`critical` 不允许** | 通行实践判 `critical` → `severity_overstated`；判 `major` 但理由过短 → `severity_practice_high` 警告 |
| `internal_consistency` | 材料内部一致性（A 处与 B 处互相矛盾） | 可以 | 必须同时给两侧 locator |

**硬规则**：材料里没有目标期刊指南时，`venue_guideline` 类的行只能判 `unverifiable` 并写清"需要用户提供哪份指南的哪一节"。脚本会把"声称依据指南、但输入里找不到指南文本"的行判为 `guideline_basis_unavailable` 错误——这是反编造闸门，不是笔误提示。

### 5.2 四态判定 `verdict`

| verdict | 什么时候用 | 必填 | 禁止 |
|---|---|---|---|
| `compliant` | 要求被满足，能指出满足的原文位置 | 建议 `evidence_locator`+`quote` | 无证据的"看起来没问题" |
| `violation` | 要求未被满足/被违反，且能定位、能引原文 | **必填 `quote` + `evidence_locator`**，`remediation` | 凭印象判定；把风格差异当违规 |
| `not_applicable` | 该要求对本材料不适用（如纯计算研究无动物实验） | **必填 `searched_scope`**（在哪些范围、用什么关键词确认不适用） | 用 `not_applicable` 掩盖"没查" |
| `unverifiable` | 材料内不足以判定（指南缺失、文献存在性、第三方授权范围、被删页） | **必填 `what_human_must_check`** | 猜一个结论；把 `unverifiable` 写成 `compliant` |

### 5.3 严重度锚点 `severity`

| severity | 含义 | 典型 |
|---|---|---|
| `critical` | 可致拒稿/撤稿/伦理事故：编造数据、未声明的人体数据、无伦理批件、图像复用未声明 | 每条必须给 `severity_reason`（为什么是这一档，而不是相邻档） |
| `major` | 发表/提交前必改：引用悬空、COI 缺失、基金号不一致、声称有批件但无编号 | 同上 |
| `minor` | 规范瑕疵：格式不统一、文献元数据缺 DOI、声明区块用词不规范 | 同上 |
| `suggestion` | 改进建议，非缺陷（可提高可核查性/可复现性） | 同上 |

锚定方式写在 `severity_reason` 里，格式建议：`"<事实> → <后果> → 因此为 <档位>"`。相邻档之间要能说清差别，否则降一档。

### 5.4 三态声明区块（9 项固定）

`DEC-01..DEC-09` 覆盖：基金、致谢、作者贡献、利益冲突（COI）、数据可用性、伦理批件、知情同意、代码可用性、版权许可。每项必须有行，状态为：

- `found`：找到声明，给 locator + 逐字片段；
- `missing`：确认没有，给 `searched_scope`（检索了哪些段落/哪些关键词、是否包含补充材料）；
- `inconsistent`：找到了但与正文/其他区块矛盾（如致谢里的基金号与首页不同），给两侧 locator。

### 5.5 引用-文献表对账

`citation_reconciliation` 每行 = 一个正文引用标记：`{marker, claim_locator, claim_quote, ref_entry, match, note}`，`match ∈ consistent|dangling|duplicate|mismatch|unverifiable`。`dangling`＝正文有标记但文献表无条目；`duplicate`＝同一编号出现两个条目或同一文献两条编号；`mismatch`＝标记对应的条目与正文论断的作者/年份/主题不符；`unverifiable`＝文献表条目本身残缺、无法形式核对。

## 6. `init`：建索引

```bash
python3 scripts/main.py init
```

输出与落盘：

1. 材料清单：`D1..Dn`、文件名、类型（按扩展名 + 魔数判断，不按文件名猜内容）、抽取器、段数、文本质量分；
2. `work/index.json`：每篇的段落数组（每段带 `locator`，形如 `p3#para7`）、全文、种子行、信号；
3. `work/draft.template.json`：**已预填 33 个种子行骨架**（`requirement/expected/verdict` 留空或置 null），复制成 `draft.json` 后逐行填判定；
4. `output/result.json`：合法 partial（契约全键 + `status=partial`）。

`init` 打印的四块信号，就是你 `show` 之后要逐条确认的对象：

| 信号 | 用途 |
|---|---|
| `== seeds ==` 33 行（24 条要求 + 9 项声明） | 矩阵行骨架，覆盖 7 个 domain |
| `== citations ==` 正文标记数 / 文献表条目数 / 悬空·孤立·重号·跳号 | 直接喂 `citation_reconciliation` 的待判清单 |
| `== declarations ==` 9 项命中/未命中 + 命中片段 | `found`/`missing` 的初判，`missing` 要写检索范围 |
| `== pii ==` 邮箱/电话/证件/患者号候选 | `pii_ledger` 的行 |

## 7. `show`：读材料的入口

```bash
python3 scripts/main.py show                          # 总览：材料 + 种子行 + 全部命中片段
python3 scripts/main.py show --domain privacy         # 只看某个 domain 的种子行与候选
python3 scripts/main.py show --doc D1 --paras 1:40    # 读某篇正文（带 locator）
python3 scripts/main.py show --grep "ethic|同意"       # 按正则检索，打印命中段落 locator
```

规则：

- **引用必须逐字复制 `show` 打印的文本**，包括全角/半角、连字符、`et al.`；不要翻译、不要拼接两段、不要改写标点。
- `locator` 用 `show` 给出的形式；跨段引文取起始段，并在 `observed` 里说明"跨段"。
- 图表内容只能标"约/目测"，无文本可依则不写数值。

## 8. 工作稿 `draft.json`（唯一事实源，Agent 亲手写）

完整 schema、字段字典与正反例见 `references/matrix-schema.md`；最小骨架：

```json
{
  "case_id": "示例-cid",
  "doc_meta": {"title": "…", "doc_type": "manuscript|report|thesis_chapter", "venue_name": "", "guideline_present": false},
  "compliance_matrix": [
    {"row_id": "DEC-04", "domain": "declaration", "rule_source": "ethical_norm",
     "requirement": "稿件应明确声明利益冲突（含无冲突声明）",
     "expected": "独立 COI 声明段落，覆盖全体作者",
     "observed": "全文检索 conflict of interest / competing interests / 利益冲突，未找到声明段落",
     "verdict": "violation",
     "doc_id": "D1", "evidence_locator": "p1#para4", "quote": "All authors declare that they have no competing interests.",
     "searched_scope": "", "severity": "major",
     "severity_reason": "COI 声明是多数期刊强制项，缺失需在投稿前补 → 发表前必改 → major",
     "remediation": "在参考文献前新增『利益冲突声明』小节，逐作者说明；若存在财务关系须列明。",
     "what_human_must_check": ""}
  ],
  "citation_reconciliation": [{"marker": "[12]", "claim_locator": "p4#para2", "claim_quote": "…",
     "ref_entry": "[12] Author A, Author B. Title. Journal. 2019;12(3):45-56.", "match": "mismatch",
     "note": "正文称该文献支持随机对照试验结论，但条目为综述且年份差 5 年"}],
  "pii_ledger": [{"ledger_id": "PII-01", "pii_type": "email", "location": "p2#para6",
     "redaction": "[REDACTED-EMAIL]", "rationale": "通讯作者邮箱属可识别信息，公开发布前应保留但避免在示例中复现"}],
  "uncovered_requirements": [{"requirement": "目标期刊字数上限", "reason": "材料未提供作者指南，无法核对"}],
  "summary": "一句话结论（3 行以内）",
  "uncertainties": ["…"]
}
```

字段级要求：`row_id` 唯一；`domain ∈ integrity|citation_norm|privacy|copyright|ethics|venue|declaration`；`verdict/severity/rule_source` 用 §5 的枚举；`violation` 行必须有 `quote`+`evidence_locator`+`remediation`+`severity_reason`；`unverifiable` 行必须有 `what_human_must_check`；`not_applicable` 行必须有 `searched_scope`。

## 9. `check`：机械校验（跑完再改稿）

```bash
python3 scripts/main.py check
```

输出 `ok/errors/warnings/counts` 与 `FIX [code] where :: detail` 列表。主要错误码与修法：

| code | 含义 | 修法 |
|---|---|---|
| `verdict_invalid` / `severity_invalid` / `domain_invalid` / `rule_source_invalid` | 枚举越界 | 改成 §5 枚举值 |
| `quote_not_found` | 引文在该篇文本中逐字找不到 | 回 `show` 重新复制；或改判 `unverifiable` |
| `locator_quote_mismatch` | locator 指向的段落里没有这段引文 | 用 `show --grep` 找到真正段落 |
| `evidence_missing` | `violation` 行缺 quote/locator/remediation | 补齐或降级为 `unverifiable` |
| `unverifiable_no_human` | 待复核行没写人工核对项 | 写"需要核对什么、在哪核对" |
| `not_applicable_no_scope` | 判"不适用"但没写检索范围 | 写检索的段落区间与关键词 |
| `guideline_basis_unavailable` | 声称依据期刊指南，但输入里没有指南 | 改 `unverifiable` + 人工核对项，或在 `doc_meta` 说明指南未提供 |
| `invented_identifier` | 写出的批件号/基金号在原文中不存在 | 删掉编号，只写"未提供编号" |
| `pii_not_redacted` / `pii_location_missing` | 台账含真实 PII 或缺位置 | 换成 `[REDACTED-*]`，补 locator |
| `declaration_row_missing` / `domain_uncovered` | 9 项声明或某 domain 没行 | 补行（`not_applicable` 也要显式行） |
| `citation_reconciliation_missing` | 没有对账表 | 按 `show` 的引用信号补 |
| `severity_overstated` | 用 `critical` 评价一条只属通行实践的要求 | 降档为 `major`，或把 `rule_source` 换成有原文依据的等级 |
| `severity_practice_high`（警告） | 通行实践判 `major`，但 `severity_reason` 没说清为什么是必改项 | 补 `severity_reason`：`<事实> → <后果> → 因此为 major` |
| `no_material` | `/input` 下没有可解析材料 | 修输入后重跑；此时 `status=input_error`，矩阵仍完整输出 |

`check` 不阻塞 `build`，但 `check` 的错误会进 `result.json.errors`，直接影响"正确性/可核验性"两项评分，请在 `build` 前清零。

## 10. `build`：产物生成与兜底

```bash
python3 scripts/main.py build
```

生成（`/app/output`）：

| 文件 | 内容 |
|---|---|
| `result.json` | 契约字段全回填 + findings + 矩阵 + 台账 + 覆盖 + 信封 |
| `compliance_matrix.csv` | 矩阵长表（row_id, domain, rule_source, requirement, expected, observed, verdict, evidence_locator, quote, severity, remediation, …） |
| `compliance_report.md` | 矩阵 → 违规清单（派生）→ 待人工核实 → 整改优先级 → 覆盖与缺口 → 复跑说明 |
| `pii_ledger.json` | PII 台账（只含类型/位置/脱敏形式），报告正文中的原始 PII 会被自动遮罩 |
| `run_manifest.json` | 输入文件 sha256、规则版本、行数统计、两次运行可比对的确定性字段 |

派生规则：

1. `findings[]` 由矩阵派生：`verdict=violation` → `issue_type=violation`；`verdict=unverifiable` 且 `severity ∈ {critical, major}` → `issue_type=pending_review`。每条带 `matrix_row_id` 可反查。
2. `coverage` 由矩阵统计：`rows / judged / violation / unverifiable / compliant / not_applicable`、按 domain 计数、`quote_pass_rate`、`evidence_coverage`。
3. 排序：矩阵按 `(domain, row_id)` 稳定排序，`findings` 按 `(severity 权重, row_id)`；同一输入两次运行除时间戳外 diff 为空。

**兜底（必须知道）**：`draft.json` 缺失、坏 JSON、或只填了一半时，`build` 仍然产出完整最小交付——矩阵种子行以 `unverifiable` 落表（`what_human_must_check` 写明"未读材料，需人工核对"）、契约字段全回填、`status=partial`、`degradations` 列出缺口、退出码 0。所以**先跑通再打磨**永远安全。

## 11. `selfcheck`：交付前复检

```bash
python3 scripts/main.py selfcheck
```

只读检查：`result.json` 可解析且契约键与 `/input/case.json` 完全一致、矩阵非空且排序稳定、`violation` 行证据门控通过、`findings` 全部能反查到 `matrix_row_id`、台账无真实 PII、报告非空且四个必需小节都在。任何 FAIL 都给出对应修法（改 draft 重跑 build）。

## 12. 误报抑制与"不编造"（判分最敏感的部分）

宁少报一条，不报一条假的。以下都不算违规，除非材料内有明确规范依据：

1. **风格与学科惯例差异**：单栏/双栏、英式/美式拼写、`et al.` 数量、被动语态、图注长度、"我们"vs"本文"。
2. **作者的有意取舍**：合作作者未列贡献细则（若指南未要求）、未公开数据仅写"因隐私不公开"（若伦理要求如此）。
3. **无法确认的事实**：文献是否存在、第三方图片的许可范围、伦理批件是否覆盖本文数据、期刊 2024 年后的新要求。
4. **看似矛盾其实自洽**：正文 n 与表格 n 不同但已说明"缺失值剔除"。

对应的写法：`unverifiable` + `what_human_must_check`（"查 DOI 10.xxxx/yyy 的原文与作者列表"），而不是猜 `violation`。**禁止**编造条款号（"违反 GB/T 7714 第 5.2.3 条"而无原文）、期刊要求（"该刊要求 ≤3500 词"而无指南）、文献元数据（作者/年份/DOI）、伦理批件号与基金号。

## 13. 异常与降级

| 情况 | 处置 |
|---|---|
| `/input` 不存在或为空 | `status=input_error`，契约全键回填，矩阵为空但字段齐全，`errors` 写明路径，退出码 0 |
| `case.json` 坏 JSON | 用默认契约空壳，`errors: case_json_invalid`，仍出完整交付 |
| `output_contract` 缺失 | 用内置 15 键默认契约（matrix/findings/pii_ledger/citation_reconciliation/coverage/summary/…），`degradations` 注明 |
| PDF 无文本层（扫描） | 记 `degradations`，该篇相关行 `unverifiable` + 需 OCR，不猜内容 |
| `pdftotext` 缺失 | 内置 zlib/文本流解析器，locator 退化为 `s1#para3`，页号不权威记降级 |
| DOCX/XLSX/PPTX | DOCX 走 XML 抽文本；XLSX/PPTX 不解析，记降级并提示用户给 PDF/CSV |
| 材料缺页/只有摘要 | `unverifiable` + `what_human_must_check`，不按领域常识补内容 |
| 目标期刊指南缺失 | 全部 `venue_guideline` 行 `unverifiable`；报告单列"需要用户补充的指南条目" |
| 材料涉及受限数据 | 台账记位置与类型，判定"是否具备授权说明"，不复制数据本身 |
| `draft.json` 缺失/坏 | `build` 兜底：种子行 `unverifiable` + `status=partial` + `degradations`，退出码 0 |
| 契约键无对应内容 | 置 null/[] 并写 `pending_human`，不编造填充 |

## 14. 最小调用示例（示例，非正式案例结果）

```bash
cd <skill-root>
python3 scripts/main.py init --input ./demo/input --output ./demo/output --work ./demo/work
python3 scripts/main.py show --domain declaration
cp demo/work/draft.template.json demo/work/draft.json     # 逐行填入判断
python3 scripts/main.py check --input ./demo/input --output ./demo/output --work ./demo/work
python3 scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
python3 scripts/main.py selfcheck --input ./demo/input --output ./demo/output --work ./demo/work
```

示意输出（**示例，非正式案例结果**）：

```
status=partial rows=33 judged=9 violations=3 unverifiable=6 quote_pass=1.0 coverage=0.273
artifacts: result.json, compliance_matrix.csv, compliance_report.md, pii_ledger.json, run_manifest.json | unfilled contract: none
```

含义：33 行矩阵、9 行已给出判断（其中 3 条 violation）、6 条待人工核实、引文命中率 1.0、契约字段全部回填。

## 15. 文件、来源与维护

```
SKILL.md                          本文件（用途/契约/主路径/矩阵模型/异常）
scripts/main.py                   CLI 分发 + 索引与工作稿模板 + 契约回填 + 兜底 finalize（≤25KB）
scripts/core.py                   抽取与段落化、信号检测（声明/引用/PII/指南）、show 渲染、selfcheck（≤30KB）
scripts/rules.py                  33 条要求目录、四态/严重度校验、证据门控、报告与 CSV 渲染（≤30KB）
references/matrix-schema.md       draft.json 字段字典 + 判定口径 + 正反例（工作稿 schema）
references/requirement-catalog.md 33 条要求目录（6 方向 + 9 声明项）、检索词、误报抑制表
references/audit-playbook.md      严重度锚点、整改优先级、报告结构模板、复核清单
```

- **规则版本**：`rule_version = acm-1.0.0`，写入 `run_manifest.json`；改目录即改版本号。
- **依据来源**：`references/requirement-catalog.md` 每条只写"要求内容 + 检索词 + 依据类型"，不收录未经核对的条款号与期刊要求原文；需要引用具体规范时，以用户材料或官方原文为准。
- **维护**：新增检查项 → 在 `core.py` 的 `CAT`/`DECL` 增行 + 同步 `references/requirement-catalog.md`；调整严重度锚点 → 同步 `references/audit-playbook.md` 与本文件 §5.3；改契约回填 → 只动 `core.py` 的 `PATTERNS`。
- **复用**：矩阵 CSV 与台账 JSON 可直接并入实验室/期刊的内部预检流程；`references/requirement-catalog.md` 可单独作为人工逐条核对的检查表。

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
