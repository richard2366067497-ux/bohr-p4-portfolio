## 任务理解与判分要点

### 真正要交付什么

对每篇输入论文产出一份**可复核的结构化审查报告**，核心交付物是问题清单，每条问题必须包含：

- **位置**：精确到句子或字符偏移，评审能直接回到原文核对；
- **类型**：事实错误 / 证据不足 / 规范问题 / 建议性意见；
- **严重度**：可解释的分级（Critical / Major / Minor / Suggestion）；
- **证据**：原文摘录、数据/引用/方法依据；
- **修改建议**：能落到具体句子或具体补充动作。

同时必须覆盖六类检查项：事实核验、引用支持、方法设计、统计报告、论证链、学术规范，并检查跨章节的主张—证据对应关系。

### 评委看哪几件事

1. **问题是否真实成立**：能否回到原文某一句话；是否把作者有意设置的对照、明确标注的假设、转述他人观点误判为缺陷。
2. **定位粒度**：是否精确到句子/字符偏移，而不是只给章节名。
3. **严重度是否可解释**：是否说明影响主结论、可修正性、可复现性。
4. **建议是否可执行**：是否说清补什么证据、改哪一句表述、把哪个结论强度降下来。
5. **覆盖完整性**：是否覆盖六类检查项和跨章节一致性。
6. **可核验性**：是否保留原文摘录、判断依据、运行状态和不确定性。

### 常见失败模式：错误做法 → 正确做法

| 错误做法 | 正确做法 |
|---|---|
| 输出“本文结构完整、论证较为充分”等无法核对的判断 | 输出逐条问题，每条带原文位置和证据 |
| 定位只到“结果部分”“讨论部分” | 定位到句子，给出字符偏移和原文摘录 |
| 把对照组、假设情形、他人观点当成作者自相矛盾报出 | 先区分作者主张 / 引用他人 / 假设情形，再判断 |
| 所有问题一律标“中” | 按影响主结论、可修正性、可复现性分级 |
| 建议写“建议补充论证”“建议加强逻辑” | 建议写“在结果部分补充独立样本t检验，报告p值；或将摘要表述改为‘数值上提高45%，但未达统计显著’” |
| 长文被截断后仍宣称完成全文审查 | 明确标记未检查部分，输出部分结果并说明限制 |
| 只有最终报告，没有可复核记录 | 保留每条问题的 locator、quote、判断依据、复算命令 |

## 求解框架

从输入材料到交付物的分步流程，每步有冻结产物和门控。

### 第1步：输入解析与预处理

**输入**：`/input/case.json`、`/input/task.md`、实际论文 PDF（或文本）。

**动作**：
- 读取 case.json 获取 case_id、材料路径、任务说明；
- 解析 PDF 提取文本，保留页码、段落、句子、字符偏移；
- 若为扫描版无文本层，标记 `parse_status=failed`，不强行 OCR；
- 若文本超长（>16384 tokens），分块处理，记录每块范围，禁止宣称完成全文审查。

**冻结产物**：`parsed_text.json`，包含 `case_id`、`pages`、`paragraphs`、`sentences`、`char_offsets`、`parse_status`。

**门控**：解析成功才进入下一步；失败则输出 `status=parse_failed` 并说明原因。

### 第2步：主张抽取

**动作**：
- 从摘要、引言、结果、讨论中抽取作者核心主张；
- 每条主张标注：`claim_id`、`claim_text`、`source_section`、`claim_type`（author_claim / cited_claim / hypothesis）、`qualifiers`（限定条件如“可能”“显著”“在…条件下”）；
- 区分作者主张、引用他人观点、假设情形。

**冻结产物**：`claims.json`，主张清单。

**门控**：主张清单非空；每条主张有原文定位。

### 第3步：证据支撑核查

**动作**：
- 对每条作者主张，定位其支撑证据；
- 判断证据是否存在、来自本文实验还是所引文献、是否足以支撑该强度表述；
- 识别“结论超出数据”与“引用不支持观点”。

**冻结产物**：`claim_evidence_alignment.json`，每条主张对应证据状态：`supported` / `partially_supported` / `unsupported` / `needs_review`。

**门控**：所有作者主张都有证据状态标记；无法确认的标记 `needs_review`。

### 第4步：推理链与章节一致性检查

**动作**：
- 检查从前提到结论的推理是否存在跳跃、隐含假设未说明、替代解释未排除、相关性与因果性混用；
- 检查引言承诺的问题是否在方法与结果中交付；
- 检查方法与结果的口径是否一致；
- 检查摘要与正文结论是否一致；
- 检查图表与正文描述是否对应。

**冻结产物**：`cross_section_issues.json`，跨章节问题清单。

**门控**：至少检查摘要—引言—方法—结果—讨论的对应关系。

### 第5步：严重度分级与建议生成

**动作**：
- 按严重度标准分级（见下节）；
- 为每条问题生成可执行建议，落到具体句子或补充动作。

**冻结产物**：`findings.json`，最终问题清单。

**门控**：每条问题有严重度、建议、证据。

### 第6步：输出与自检

**动作**：
- 生成 `/app/output/result.json`，包含 `case_id`、`status`、`findings`、`sources`、`uncertainty`、`change_records`；
- 自检每条问题的 locator 能否回到原文；
- 保存部分结果，避免超时丢失。

**冻结产物**：`result.json`。

**门控**：所有问题有 locator 和 quote；输出包含运行状态和不确定性。

## 专家方法与量化口径

### 关键指标定义

| 指标 | 定义 | 公式 | 可接受范围 |
|---|---|---|---|
| 主张抽取覆盖率 | 抽取的主张数 / 人工标注主张数 | `coverage = extracted_claims / total_claims` | ≥ 90%（内部评估） |
| 证据支撑率 | 有直接证据的主张数 / 总作者主张数 | `support_rate = supported / author_claims` | 报告实际值，不设阈值 |
| 问题定位精度 | 字符偏移误差 | `error = |reported_start - true_start|` | ≤ 50 字符为合格 |
| 误报率 | 误判对照/假设/他人观点为缺陷的条目数 / 总问题数 | `false_positive_rate = fp / total_findings` | 目标 0 |
| 待复核率 | 无法确认条目数 / 总条目数 | `needs_review_rate = needs_review / total_items` | ≤ 20%，且必须标记 |
| 建议可执行率 | 包含具体动作的建议数 / 总建议数 | `actionable_rate = actionable / total_suggestions` | 100% |
| 严重度分布 | 各级问题数量 | `critical + major + minor + suggestion = total_findings` | 报告实际值 |

### 严重度分级公式

严重度分数 = 影响主结论(0/1) × 2 + 不可修正(0/1) × 1 + 影响可复现性(0/1) × 1

- 分数 ≥ 3 → **Critical**：影响主结论且不可修正或需撤回；
- 分数 = 2 → **Major**：影响主结论但可修正；
- 分数 = 1 → **Minor**：不影响主结论，规范或局部问题；
- 分数 = 0 → **Suggestion**：改进建议。

**计算示例**：某问题“方法部分声称用XRD表征分散性，但XRD无法直接表征分散性”，影响主结论（1×2=2），不可修正需补充实验（1×1=1），影响可复现性（1×1=1），总分=4 → Critical。

### 证据强度等级

1. **直接实验数据**：本文结果部分的数据、图表；
2. **引用文献**：所引文献直接支持该句；
3. **作者推断**：作者基于数据的推理；
4. **无证据**：无任何支撑。

### 复算命令示例

```bash
python scripts/check_locator.py --case_id demo-001 --finding F1
# 输出：quote 与原文匹配，char_start=120, char_end=180，误差=0
```

## 领域知识清单

### 材料/化学工艺方向容易犯的事实性错误

- XRD 峰位归属错误：将非晶峰误标为石墨烯特征峰；
- TGA 失重台阶归属错误：将吸附水失重误标为聚合物分解；
- FTIR 峰位对应官能团错误：将 C=O 伸缩振动误标为 C=C；
- SEM 标尺与放大倍数不一致；
- EDS 元素定量未归一化，或轻元素（C、O）定量不可靠；
- BET 线性区间选择错误，导致比表面积偏差；
- 催化剂 TOF 计算未说明活性位点数；
- 电化学阻抗拟合电路不合理，未说明物理意义。

### 单位/量纲陷阱

- wt% vs vol% vs mol% 混用；
- ppm/ppb 未说明是质量比还是体积比；
- MPa vs GPa 换算错误（1 GPa = 1000 MPa）；
- ℃ vs K 混用（热力学计算必须用 K）；
- mL/min vs sccm 未说明标准状态；
- mg/g vs mg/m² 混用（吸附量单位）；
- 电流密度 mA/cm² 未说明几何面积还是电化学活性面积；
- 电位 V vs RHE 未说明参比电极。

### 文献依据要求

- 引用必须支持原句，不能只支持相关领域；
- 引用他人观点需标注“作者认为”“研究表明”等；
- 假设情形需明确“假设”“如果”等词；
- 引用文献的物种、基体、条件必须与原文一致。

### 统计报告要求

- n ≥ 3 且报告均值 ± 标准差，需说明误差棒含义（SD 或 SEM）；
- 显著性检验需报告 p 值或置信区间；
- 相关性不能表述为因果；
- 效应量需报告（如 Cohen's d、η²）。

## 高质量交付物清单

### 应交付文件

| 文件 | 内容 | 自证可核验方式 |
|---|---|---|
| `SKILL.md` | 用途、适用条件、调用方式、输入输出、异常处理 | 说明如何触发、如何读取输入、如何输出 |
| `references/expert_playbook.md` | 本手册 | 包含量化口径、领域知识、自查表 |
| `scripts/extract_claims.py` | 主张抽取脚本 | 输入 parsed_text.json，输出 claims.json |
| `scripts/check_evidence.py` | 证据核查脚本 | 输入 claims.json + 原文，输出对齐表 |
| `scripts/severity.py` | 严重度分级脚本 | 输入问题特征，输出严重度分数 |
| `scripts/check_locator.py` | 定位核验脚本 | 输入 finding，输出 quote 匹配结果 |
| `templates/report_template.json` | 报告模板 | 定义字段结构 |
| `examples/demo_case.md` | 最小调用示例 | 标明为示例，不冒充正式结果 |

### 每条问题如何自证可核验

每条 finding 必须包含：

```json
{
  "finding_id": "F1",
  "type": "evidence_insufficient",
  "severity": "Major",
  "locator": {
    "file": "paper.pdf",
    "page": 1,
    "paragraph": 2,
    "sentence": 2,
    "char_start": 120,
    "char_end": 180
  },
  "quote": "添加0.5 wt%石墨烯使拉伸强度提高45%",
  "evidence": "表1显示对照组32.1±4.2 MPa，实验组46.5±5.1 MPa，n=3，未报告统计检验",
  "suggestion": "在结果部分补充独立样本t检验，报告p值和效应量；或将摘要表述改为‘数值上提高45%，但未达统计显著’",
  "confidence": "high",
  "needs_review": false
}
```

复算命令：`python scripts/check_locator.py --case_id demo-001 --finding F1` 应返回 `quote 匹配，误差=0`。

## 防扣分自查表

- [ ] 1. 每条问题是否有 locator 且能回到原文句子？
- [ ] 2. 是否区分作者主张 / 引用他人 / 假设情形？
- [ ] 3. 是否误判对照组、假设情形、他人观点为缺陷？
- [ ] 4. 严重度是否按标准分级且可解释？
- [ ] 5. 建议是否具体到补什么证据、改哪句、降强度？
- [ ] 6. 是否覆盖六类检查项：事实核验、引用支持、方法设计、统计报告、论证链、学术规范？
- [ ] 7. 是否检查跨章节一致性：引言承诺 vs 结果交付、摘要 vs 正文、图表 vs 正文？
- [ ] 8. 是否标记待复核项，不凭空补结论？
- [ ] 9. 是否处理解析失败、扫描版无文本、超长截断？
- [ ] 10. 是否保留运行状态和不确定性？
- [ ] 11. 是否不依赖预制答案，实际读取输入文件？
- [ ] 12. 是否在 `/app/output` 生成 `result.json` 且包含 `case_id`？
- [ ] 13. 是否所有原文摘录与论文一致，无篡改？
- [ ] 14. 是否避免“建议补充论证”“建议加强逻辑”等空话？
- [ ] 15. 是否记录 change records，说明修改过程？
- [ ] 16. 是否在预算内保存部分结果，避免超时丢失？
- [ ] 17. 是否使用实际文件内容而非假设来源？
- [ ] 18. 是否区分事实错误、证据不足、规范问题、建议性意见？
- [ ] 19. 是否对无法确认的条目标记 `needs_review` 并说明原因？
- [ ] 20. 是否输出包含 `status`、`sources`、`uncertainty` 字段？

## 一个完整虚构案例演示

### 输入

`case.json`：

```json
{
  "case_id": "demo-001",
  "material": "paper.pdf",
  "task": "论文逻辑与论证审查"
}
```

论文标题：《石墨烯增强环氧树脂复合材料的力学性能与热稳定性研究》

### 关键中间量

**主张清单**（部分）：

| claim_id | claim_text | claim_type | source_section |
|---|---|---|---|
| C1 | 添加0.5 wt%石墨烯使拉伸强度提高45% | author_claim | 摘要 |
| C2 | 石墨烯可显著提高环氧树脂拉伸强度 | cited_claim | 引言 |
| C3 | 采用XRD表征石墨烯分散性 | author_claim | 方法 |
| C4 | 石墨烯的加入导致热稳定性提高 | author_claim | 讨论 |
| C5 | 研究石墨烯含量对力学和热性能的影响 | author_claim | 引言 |

**证据支撑率**：作者主张 8 条，有直接证据 5 条，支撑率 = 5/8 = 62.5%。

**问题清单**（5条）：

| finding_id | type | severity | locator | quote |
|---|---|---|---|---|
| F1 | evidence_insufficient | Major | 摘要第2句，char 120-180 | 添加0.5 wt%石墨烯使拉伸强度提高45% |
| F2 | citation_unsupported | Major | 引言第3段第2句，char 450-510 | 石墨烯可显著提高环氧树脂拉伸强度[12] |
| F3 | method_error | Critical | 方法2.3节，char 1200-1260 | 采用XRD表征石墨烯分散性 |
| F4 | causal_overreach | Major | 讨论第2段，char 2000-2060 | 石墨烯的加入导致热稳定性提高 |
| F5 | unit_inconsistency | Minor | 图表1，char 1500-1520 | 拉伸强度单位标注为 MPa 和 GPa 混用 |

**严重度分布**：Critical 1，Major 3，Minor 1，Suggestion 0。

**待复核**：F2 引用[12]无法获取全文，标记 `needs_review=true`。

### 输出

`result.json` 片段：

```json
{
  "case_id": "demo-001",
  "status": "completed",
  "summary": {
    "total_findings": 5,
    "critical": 1,
    "major": 3,
    "minor": 1,
    "suggestion": 0,
    "needs_review": 1,
    "coverage": {
      "fact_check": true,
      "citation_support": true,
      "method_design": true,
      "statistical_report": true,
      "argument_chain": true,
      "academic_norm": true
    }
  },
  "findings": [
    {
      "finding_id": "F1",
      "type": "evidence_insufficient",
      "severity": "Major",
      "locator": {
        "file": "paper.pdf",
        "page": 1,
        "paragraph": 2,
        "sentence": 2,
        "char_start": 120,
        "char_end": 180
      },
      "quote": "添加0.5 wt%石墨烯使拉伸强度提高45%",
      "evidence": "表1显示对照组32.1±4.2 MPa，实验组46.5±5.1 MPa，n=3，未报告统计检验",
      "suggestion": "在结果部分补充独立样本t检验，报告p值和效应量；或将摘要表述改为‘数值上提高45%，但未达统计显著’",
      "confidence": "high",
      "needs_review": false
    },
    {
      "finding_id": "F2",
      "type": "citation_unsupported",
      "severity": "Major",
      "locator": {
        "file": "paper.pdf",
        "page": 2,
        "paragraph": 3,
        "sentence": 2,
        "char_start": 450,
        "char_end": 510
      },
      "quote": "石墨烯可显著提高环氧树脂拉伸强度[12]",
      "evidence": "[12]实际研究的是石墨烯/聚丙烯复合材料，未涉及环氧树脂基体",
      "suggestion": "替换为环氧树脂基体的文献，或改为‘在聚丙烯基体中观察到石墨烯显著提高拉伸强度’",
      "confidence": "medium",
      "needs_review": true
    },
    {
      "finding_id": "F3",
      "type": "method_error",
      "severity": "Critical",
      "locator": {
        "file": "paper.pdf",
        "page": 4,
        "paragraph": 1,
        "sentence": 3,
        "char_start": 1200,
        "char_end": 1260
      },
      "quote": "采用XRD表征石墨烯分散性",
      "evidence": "XRD无法直接表征分散性，应使用SEM/TEM或Raman mapping",
      "suggestion": "补充SEM/TEM图像或Raman mapping，并说明分散性判据",
      "confidence": "high",
      "needs_review": false
    },
    {
      "finding_id": "F4",
      "type": "causal_overreach",
      "severity": "Major",
      "locator": {
        "file": "paper.pdf",
        "page": 6,
        "paragraph": 2,
        "sentence": 1,
        "char_start": 2000,
        "char_end": 2060
      },
      "quote": "石墨烯的加入导致热稳定性提高",
      "evidence": "TGA数据仅显示初始分解温度提高，未排除石墨烯本身热导率影响，属于相关性描述",
      "suggestion": "改为‘与热稳定性提高相关’，并补充DSC或动力学分析",
      "confidence": "high",
      "needs_review": false
    },
    {
      "finding_id": "F5",
      "type": "unit_inconsistency",
      "severity": "Minor",
      "locator": {
        "file": "paper.pdf",
        "page": 5,
        "paragraph": 1,
        "sentence": 1,
        "char_start": 1500,
        "char_end": 1520
      },
      "quote": "拉伸强度单位标注为 MPa 和 GPa 混用",
      "evidence": "图表1中纵轴标注为GPa，正文描述为MPa",
      "suggestion": "统一单位，建议全部使用MPa，并检查换算是否正确",
      "confidence": "high",
      "needs_review": false
    }
  ],
  "sources": {
    "paper": "paper.pdf",
    "parsed_text": "/app/work/parsed_text.json",
    "claims": "/app/work/claims.json",
    "evidence_alignment": "/app/work/claim_evidence_alignment.json"
  },
  "uncertainty": {
    "F2": "引用[12]无法获取全文，待复核",
    "parse_status": "success"
  },
  "change_records": [
    {
      "time": "2025-01-01T10:00:00Z",
      "action": "initial_findings",
      "detail": "生成5条问题"
    },
    {
      "time": "2025-01-01T10:05:00Z",
      "action": "severity_adjust",
      "detail": "F3从Major调整为Critical，因影响主结论且不可修正"
    }
  ]
}
```

### 复算验证

```bash
python scripts/check_locator.py --case_id demo-001 --finding F1
# 输出：quote 匹配，char_start=120, char_end=180，误差=0

python scripts/severity.py --finding F3
# 输出：影响主结论=1，不可修正=1，影响可复现=1，总分=4 → Critical
```

以上演示中所有数字自洽：主张清单 8 条作者主张，证据支撑率 62.5%，问题 5 条，严重度分布 1/3/1/0，待复核 1 条，定位字符偏移与原文一致。
