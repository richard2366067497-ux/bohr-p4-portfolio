# 学术规范与合规检查 Skill 专家参考手册

## 1. 任务理解与判分要点

### 1.1 真正要交付什么

本任务要求产出一份**可复核的结构化审查报告**，而不是一段泛泛的规范提醒。每个案例的交付物必须包含：

- 逐条问题（finding）：每条有原文定位、判定依据、严重度、可执行修改建议。
- 覆盖题目要求的全部检查项（facets），不遗漏真实风险面。
- 区分四类判定：事实错误、证据不足、规范问题、建议性意见。
- 对无法确认的条目标记“待复核”，不凭空补结论。
- 结果状态：通过 / 问题 / 待复核 / 未检查项。

### 1.2 评委看哪几件事

| 评分维度 | 关键考察点 |
|-|-|
| 实际效果（40分） | 是否产出可交付报告；报出的问题是否成立；是否覆盖全部风险面；每条能否回查原文 |
| 使用增益（25分） | 相比基础 Agent 是否提升质量、效率；是否通过公平对照证明 |
| 创新增益（15分） | 是否形成稳定可复用的审查能力；方法是否带来实质改进 |
| 可靠体验（10分） | 能否正确触发调用；不同材料下是否稳定；异常是否识别与处置 |
| 生态贡献（10分） | 文档、检查项清单、条款库、示例是否齐全可复用 |

### 1.3 常见失败模式：错误做法 → 正确做法

1. **泛泛提醒** → 错误：“建议检查参考文献格式是否规范”。正确：“参考文献 [12] 作者列表与 Crossref 不一致，locator `[manuscript.pdf:7:ref12]`，quote `Smith J, et al. 2020. J Example Sci. 12(3):45-50.`，依据 Crossref 实际作者为 `Smith J, Brown K, et al.`，严重度 High，建议核对并更正。”
2. **把风格差异误判为违规** → 错误：把“本文采用被动语态”判为规范问题。正确：仅当有明确规范条款或期刊指南禁止时才判定，否则归为建议性意见或不报。
3. **编造条款或文献元数据** → 错误：写“根据 ICMJE 第 5 条要求……”但实际无此条款。正确：只引用可获取的规范原文，无法获取时标记“待复核：依据条款未能获取”。
4. **只挑最容易的一项出报告** → 错误：只检查参考文献格式，忽略隐私、伦理、版权等。正确：按任务说明的 facets 逐项映射检查，每项有检查结果。
5. **输出不可复核** → 错误：只写“第 3 页有问题”。正确：locator 精确到句/行/段落，quote 逐字匹配原文，basis 给出规范条款编号和版本。
6. **把建议当错误** → 错误：把“建议增加样本量”列为 High 问题。正确：区分“证据不足”（如样本量未报告）和“建议性意见”（如可考虑增加样本量），严重度分开。
7. **忽略材料缺失或解析失败** → 错误：PDF 缺页仍假装检查完成。正确：在 result.json 的 status 和 uncertainty 中说明“第 5 页缺失，相关检查项未检查”。
8. **预制答案** → 错误：根据案例标签直接写结论。正确：实际读取 /input/case.json 和材料文件，所有 finding 来自实际内容。
9. **不保留中间产物** → 错误：只交最终 JSON。正确：保留 /app/work 下的解析文本、证据索引、判定草稿，便于复算。
10. **result.json 字段不全** → 错误：只输出 findings 数组。正确：包含 case_id、status、findings、sources、uncertainty、change_records 全部字段。

## 2. 求解框架：从输入材料到交付物的分步流程

### Step 0：输入解析与案例识别
- 读取 `/input/case.json`、`/input/task.md`，解析材料清单。
- 冻结产物：`case_id`、材料文件列表、解析状态（成功/部分失败/失败）。
- 门控：能定位所有材料文件；若有缺失，记录到 `uncertainty` 并继续。

### Step 1：审查计划与检查项映射
- 根据 task.md 中的 facets 拆成具体检查项。例如 facets 为 `["citation","privacy","ethics","submission"]`，拆成 12 个检查项：参考文献真实性、元数据一致性、引证对应性、格式统一性、可识别信息、数据授权、伦理批件、知情同意、风险获益、字数限制、图表限制、格式冲突。
- 冻结产物：`checklist.json`，每项有 `id`、`name`、`applicable`、`basis_source`。
- 门控：检查项覆盖任务要求的所有 facets。

### Step 2：证据抽取与定位
- 对材料全文建立可定位索引。PDF 转文本后按页/段落/句子编号；Office 文件按段落/表格编号。
- 抽取关键证据：参考文献列表、正文引用位置、数据描述、方法描述、统计结果、伦理声明、基金信息、图片/表格来源、代码许可。
- 冻结产物：`evidence_index.json`，每条有 `locator`、`quote`、`type`。
- 门控：关键证据可回查原文；quote 与原文逐字一致。

### Step 3：逐项判定
- 对每个检查项，比对证据与规范/期刊指南/伦理要求。
- 判定类型：`factual_error`（事实错误）、`insufficient_evidence`（证据不足）、`normative_issue`（规范问题）、`suggestion`（建议性意见）、`pending_review`（待复核）。
- 严重度分级：`Critical` / `High` / `Medium` / `Low` / `Suggestion`。
- 冻结产物：`findings_draft.json`。
- 门控：每条 finding 有 locator、quote、basis、severity、suggestion。

### Step 4：误报抑制与复核
- 对每条 finding 反向检查：是否可能是风格差异？依据是否确实适用？是否过度推断？
- 无法确认的条目标记 `pending_review`，不强行判定。
- 冻结产物：`findings_reviewed.json`。
- 门控：无编造依据；无无定位问题；误报率目标 0%。

### Step 5：生成交付物
- 生成 `/app/output/result.json`、`report.md`、`checklist.csv`、`evidence_index.json`、`run_log.txt`。
- result.json 字段：`case_id`、`status`、`findings`、`sources`、`uncertainty`、`change_records`。
- 冻结产物：最终交付物。
- 门控：JSON 有效；字段完整；locator 可回查。

### Step 6：自检与增量保存
- 运行校验脚本 `validate.py`，检查 locator 命中率、quote 匹配率、JSON 有效性。
- 保存中间产物到 `/app/work`。
- 门控：通过防扣分自查表（见第 6 节）。

## 3. 专家方法与量化口径

### 3.1 关键指标定义与公式

| 指标 | 定义 | 公式 | 目标 | 可接受波动 |
|-|-|-|-|-|
| 定位精度 | 可回查 finding 占比 | `可回查 finding 数 / 总 finding 数` | 100% | ≥95% |
| 误报率 | 误报问题占比 | `误报数 / 总报出问题数` | 0% | ≤5% |
| 漏报率 | 漏报真实风险占比 | `漏报数 / (报出真实风险数 + 漏报数)` | 0% | ≤10% |
| 覆盖率 | 已检查项占比 | `已检查项数 / 任务要求检查项数` | 100% | ≥90% |
| 依据可核验率 | 有可核验依据的 finding 占比 | `有依据 finding 数 / 总 finding 数` | 100% | ≥95% |
| 严重度分布 | Critical+High 占比 | `(Critical+High) / 总 finding 数` | ≤30% | ≤40% |
| 效率增益 | Skill 耗时相对基础 Agent | `Skill 耗时 / 基础 Agent 耗时` | <1 | ≤0.8 |
| 复算一致性 | 重复运行 finding 集合相似度 | Jaccard = `|A∩B| / |A∪B|` | ≥0.9 | ≥0.8 |

### 3.2 计算示例

某案例任务要求 5 个检查项，Skill 报出 12 条 finding，其中 10 条可回查，1 条误报，1 条待复核。

- 定位精度 = 10/12 = 83.3% → **不合格**（目标 100%，可接受 ≥95%）
- 误报率 = 1/12 = 8.3% → **不合格**（目标 0%，可接受 ≤5%）
- 覆盖率 = 5/5 = 100% → 合格
- 依据可核验率 = 11/12 = 91.7% → **不合格**（目标 100%，可接受 ≥95%）
- 严重度分布：假设 12 条中 4 条 Critical，占比 33.3% → 可接受但需关注

改进方向：提高 locator 精度，减少误报，为待复核项补充依据或明确标记。

### 3.3 复算命令示例

```bash
python validate.py --case /input/case.json --output /app/output/result.json
# 输出：locator_hit_rate=1.0, quote_match_rate=1.0, json_valid=true
```

## 4. 领域知识清单

### 4.1 引用规范
- 常见事实性错误：把预印本当正式发表；把 arXiv 当 peer-reviewed；卷号/页码错位；作者列表不完整；DOI 格式错误。
- 依据要求：目标期刊指南、Crossref/PubMed 元数据。每条引用问题必须给出 Crossref 实际元数据与稿件不一致的具体字段。

### 4.2 统计与方法
- 常见错误：p 值报告不完整（只写 p<0.05 不写具体值）；未报告效应量；样本量不足；把相关性当因果；统计方法描述与结果不一致。
- 依据要求：CONSORT、STROBE、PRISMA 等报告规范的具体条目。

### 4.3 隐私与数据合规
- 常见错误：可识别个人信息未脱敏（姓名、身份证号、病历号、人脸、地址、出生日期）；未公开数据未说明授权；数据授权范围不明确。
- 依据要求：GDPR Art. 4(1)、HIPAA、机构数据使用协议。必须指出具体字段和位置。

### 4.4 版权与许可
- 常见错误：图片/表格/代码未标注来源；许可类型冲突（如 CC BY-NC 用于商业）；代码未附许可证。
- 依据要求：原始来源的许可条款、CC 许可类型、MIT/GPL 等许可证文本。

### 4.5 伦理审查
- 常见错误：涉及人的研究未说明知情同意；伦理批件编号缺失或与机构不符；风险获益表述与实际设计不一致。
- 依据要求：赫尔辛基宣言、CIOMS、机构伦理委员会政策。必须给出具体条款编号。

### 4.6 学术诚信
- 常见错误：数据/图像复用未说明；重复发表；不当署名；利益冲突声明缺失；致谢与基金信息不一致。
- 依据要求：ICMJE Recommendations、COPE 指南、期刊政策。

### 4.7 投稿要求
- 常见错误：摘要超字数；图表数量超限；参考文献格式不符；摘要结构不符。
- 依据要求：目标期刊/会议作者指南的版本和日期，具体到条款编号。

### 4.8 单位/量纲陷阱
- 浓度单位：μM vs mM；温度：°C vs K；时间：h vs min；统计符号：P vs p；基因符号斜体；物种名斜体。
- 常见错误：单位不一致；量纲错误；符号格式错误。判定时需区分“学科惯例”和“明确规范要求”。

### 4.9 文献依据要求
- 每个 finding 必须引用可核验的规范条款或原文位置。不能只写“根据学术规范”。需要具体到条款编号、指南版本、日期、URL（如果可获取）。

## 5. 高质量交付物清单

### 5.1 应交付文件

| 文件 | 内容 | 自证可核验方式 |
|-|-|-|
| `/app/output/result.json` | case_id、status、findings、sources、uncertainty、change_records | JSON schema 校验；locator 可回查；quote 逐字匹配 |
| `/app/output/report.md` | 人类可读报告，摘要、逐条问题、依据与边界、结果状态 | 每条问题有锚点链接到原文位置；依据有出处 |
| `/app/output/checklist.csv` | 检查项清单及状态 | 每项有检查结果和证据 |
| `/app/output/evidence_index.json` | 证据索引 | 每条证据有 locator 和 quote |
| `/app/output/run_log.txt` | 运行日志，记录解析、检查、判定过程 | 可复算 |
| `/app/output/previews/` | Office/slide/diagram 输出的 PDF/PNG 预览 | 文件存在且可打开 |
| `/app/work/` | 中间产物：parsed_text.txt、findings_draft.json、review_notes.md | 可追溯 |

### 5.2 自证可核验的具体方法

- **locator 格式**：`[文件名:页码:段落:句子]` 或 `[文件名:行号]`。示例：`[manuscript.pdf:3:para2:sent1]`。
- **逐字引用**：quote 字段必须与原文完全一致，可用 `grep -F "quote" parsed_text.txt` 验证。
- **依据出处**：basis 字段包含规范名称、条款编号、版本、日期。示例：`ICMJE Recommendations (2024) Section II.A.1`。
- **复算命令**：提供校验脚本 `validate.py`，运行后输出 locator 命中率、quote 匹配率、JSON 有效性。

## 6. 防扣分自查表

1. [ ] 是否读取了 `/input/case.json` 和 `task.md` 中的实际任务说明，而非假设？
2. [ ] 是否解析了所有提供的材料文件（PDF/文本/图片）？
3. [ ] 是否按任务要求的检查项逐项覆盖，无遗漏？
4. [ ] 每条 finding 是否有 locator 精确到句/行/段落？
5. [ ] 每条 finding 是否有逐字引用 quote 与原文一致？
6. [ ] 每条 finding 是否有可核验依据（规范条款/期刊指南/数据授权范围）？
7. [ ] 是否区分了事实错误、证据不足、规范问题、建议性意见？
8. [ ] 是否对无法确认的条目标记待复核，而非凭空补结论？
9. [ ] 是否避免了把风格差异、学科惯例误判为违规？
10. [ ] 是否避免了编造文献元数据、条款、期刊要求？
11. [ ] 是否提供了严重度分级，且 Critical/High 占比合理？
12. [ ] 是否提供了可执行修改建议，而非泛泛提醒？
13. [ ] 是否在 result.json 中包含 case_id、status、findings、sources、uncertainty、change_records？
14. [ ] 是否处理了材料缺失、无法解析、依据条款获取不到等异常？
15. [ ] 是否保留了中间产物和运行日志，便于复算？
16. [ ] 是否运行了校验脚本，确认 locator 可回查、quote 匹配、JSON 有效？
17. [ ] 是否避免了预制答案，所有输出基于实际输入？
18. [ ] 是否在 `/app/output` 下保存了最终结果和可编辑产物？
19. [ ] 是否提供了最小调用示例，且标明为示例？
20. [ ] 是否在提交目录根路径放置了 `GITHUB_URL.txt`？

## 7. 一个完整虚构案例演示

### 7.1 输入

- `/input/case.json`:
```json
{
  "case_id": "case_demo_001",
  "task": "学术规范与合规检查",
  "facets": ["citation", "privacy", "ethics", "submission"],
  "materials": ["manuscript.pdf", "journal_guide.pdf"]
}
```
- `task.md`: 要求逐条审查，输出结构化结果。
- `manuscript.pdf`: 8 页，含 25 条参考文献，涉及人的问卷调查，目标期刊《Journal of Example Science》。
- `journal_guide.pdf`: 作者指南 2024-03 版。

### 7.2 关键中间量

- 解析：PDF 转文本，得到 8 页，共 320 个句子，25 条参考文献。
- 证据索引：抽取 25 条参考文献，每条有 locator；抽取 3 处涉及人的数据描述；抽取 1 处伦理声明；抽取 1 处基金信息。
- 检查项映射：4 个 facets 拆成 12 个检查项。
- 判定：发现 5 条问题，1 条待复核。

### 7.3 输出

**result.json 摘要**：
```json
{
  "case_id": "case_demo_001",
  "status": "issues_found",
  "findings": [
    {
      "id": "F1",
      "check_item": "citation_metadata_consistency",
      "severity": "High",
      "type": "factual_error",
      "locator": "[manuscript.pdf:7:ref12]",
      "quote": "Smith J, et al. 2020. J Example Sci. 12(3):45-50.",
      "basis": "Crossref 实际作者为 Smith J, Brown K, et al.",
      "suggestion": "核对并更正参考文献 [12] 的作者列表。",
      "status": "confirmed"
    },
    {
      "id": "F2",
      "check_item": "citation_claim_correspondence",
      "severity": "Critical",
      "type": "factual_error",
      "locator": "[manuscript.pdf:3:para2:sent3]",
      "quote": "该方法可提高 30% 效率",
      "basis": "参考文献 [12] 原文摘要报告 15% 效率提升。",
      "suggestion": "更正正文论断为 15%，或引用其他支持 30% 的文献。",
      "status": "confirmed"
    },
    {
      "id": "F3",
      "check_item": "privacy_personal_data",
      "severity": "High",
      "type": "normative_issue",
      "locator": "[manuscript.pdf:4:table2]",
      "quote": "Participant A (DOB: 1990-03-12)",
      "basis": "GDPR Art. 4(1) 定义可识别个人信息。",
      "suggestion": "删除或脱敏参与者姓名缩写和出生日期。",
      "status": "confirmed"
    },
    {
      "id": "F4",
      "check_item": "ethics_approval_number",
      "severity": "High",
      "type": "insufficient_evidence",
      "locator": "[manuscript.pdf:5:ethics]",
      "quote": "Ethical approval was obtained.",
      "basis": "目标期刊指南 Section 3.2 要求提供伦理批件编号。",
      "suggestion": "补充伦理批件编号和批准机构。",
      "status": "confirmed"
    },
    {
      "id": "F5",
      "check_item": "submission_abstract_length",
      "severity": "Medium",
      "type": "normative_issue",
      "locator": "[manuscript.pdf:1:abstract]",
      "quote": "摘要全文（280 字）",
      "basis": "期刊指南 Section 2.1 限制摘要 250 字。",
      "suggestion": "压缩摘要至 250 字以内。",
      "status": "confirmed"
    }
  ],
  "sources": ["manuscript.pdf", "journal_guide.pdf"],
  "uncertainty": [
    {
      "id": "U1",
      "item": "citation_metadata_consistency",
      "locator": "[manuscript.pdf:7:ref18]",
      "reason": "参考文献 [18] 元数据无法通过 Crossref 确认，待复核。"
    }
  ],
  "change_records": [
    {"version": "1.0", "time": "2025-01-01T00:00:00Z", "note": "初始审查完成"}
  ]
}
```

**report.md 摘要**：共检查 12 项，发现 5 条问题（1 Critical, 3 High, 1 Medium），1 条待复核。每条问题有锚点链接到原文位置。

**checklist.csv**：12 项检查项，每项状态（通过/问题/待复核/未检查）。

**evidence_index.json**：25 条参考文献和 3 处隐私数据、1 处伦理声明、1 处基金信息的 locator 和 quote。

**run_log.txt**：记录解析和判定过程。

**validate.py 运行结果**：
```
locator_hit_rate=1.0, quote_match_rate=1.0
