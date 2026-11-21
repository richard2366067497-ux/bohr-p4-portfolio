---
name: writing-09-results-discussion
description: Results and Discussion section writer. Reads data tables, figures-as-data and statistics output, extracts numeric readouts with their units, writes a Results section that reports only observations, a Discussion that checks each interpretation against the data or a located source, and a Limitations block with causal boundaries. Use when a manuscript needs a submittable Results/Discussion chapter built from materials already in hand.
version: 10.0.0
---

# 结果与讨论章节写作 / Results and Discussion writing

数据与图表已经在手时，本 Skill 负责把它们变成可投稿的结果段与讨论段：读数读得准、结果只陈述观察、讨论承担解释与文献对照、局限写到方法层面。运行完全离线，只用 Python 标准库。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按它组织全部产出：

- **流程**：按其 **§2 七步法（S1–S7）** 推进——解析契约 → 建证据账本（`D/L` 编号）→ 定比较与论断
  → 复算与单位审计 → 起草章节 → 反向核验 → 打包交付；前一步未冻结不进入下一步。
- **统计口径**：按其 **§3.1–§3.3** 计算均值、`s`（`n−1`）、`SEM`、绝对差/相对差与逐批次产率
  `Y=X·S/100`，区分百分点与百分比、SD 与 SEM。
- **读数优先级**：按其 **§3.4** “原始数据/统计输出 > 表格与图注 > 矢量图标签 > 位图数字化”，
  冲突来源并列不平均；语气分级与证据强度一致。
- **领域红线**：按其 **§4** 检查口径、归一化、表征边界、稳定性与文献条件可比性。
- **门控**：交付前逐项通过其 **§5 专家检查表**，并按其 **§7** 做交付前门控。

## 单命令入口 / 评测入口（single command，一次跑完；无 draft 时执行）

这一条命令就是完整流程：读取材料 → 抽取带单位的读数 → 写结果段 → 写讨论段（含证据对照与因果边界）→ 写局限 → 输出结构化结果。**不依赖任何草稿或前置步骤**；缺材料时仍退出码 0 并写出带局限说明的合法结果。**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

可选参数：`--case /input/case.json`、`--lang zh|en`（默认按材料自动判断）、`--version`。

### 最小调用示例（示意，非正式案例结果）

输入目录示意：

```text
/input/case.json              # { "case_id": "...", "language": "en", "output_contract": {...} }
/input/materials/paper.md     # 方法与结果原文（含数值、单位）
/input/materials/refs.md      # 用于讨论对照的文献片段
```

调用：`python3 scripts/main.py --input /input --output /app/output --work /app/work`

示意输出：`manuscript.md`、`results_map.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`result.json`。以上为接口示意，正式结果由平台用固定案例生成。

## 产物清单

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 主产物：Results、Discussion、Limitations、Sources 四节 |
| `results_map.json` | 每个读数 token 到来源与上下文的映射 |
| `evidence_map.json` | 讨论中的论断到数据或文献定位的映射 |
| `preserved_facts.json` | 保留的数值、单位与来源 |
| `change_log.json` | 本次写作动作与边界处理记录 |
| `preview.svg` | 成稿离线预览（文本渲染，CJK 可用浏览器直接打开） |
| `metrics.json` | 与包内声明阈值的基线对照（单位保留率、证据定位率、因果措辞、契约字段） |
| `result.json` | 结构化结果，含 output_contract 回填、`figure_inventory` 与预览路径 |

## result.json 字段

顶层固定字段：`case_id`、`status`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`outputs`、`metrics`、`sources`、`uncertainties`、`change_records`、`limits`、`human_review`、`degradations`、`errors`、`runtime`，以及**逐键回填**的 `output_contract` 对象。

- `status` ∈ `success` / `partial` / `failed`。
- 输入契约的每个键都会出现在 `output_contract` 中：给路径的键指向真实文件；描述性键回填为真实值或列表；`case_id` 透传输入值。
- `preserved_facts`、`evidence_map`、`change_log`、`uncertainties`、`limits` 恒为非空，保证降级也可复核。

## 撰写规则

1. **结果段只写观察**：逐条列出带单位的读数与其来源；不在此节解释原因。
2. **讨论段承担解释**：每条解释要么指向本研究数据，要么指向可定位文献；一致/不一致都要说明。
3. **因果边界**：只用"相关/提示/一致"等措辞；机制推测明确标注为待检验假设。
4. **局限到方法层面**：抽样与样本量、测量与单位、统计处理、可推广性四项分列。
5. **单位保持**：读数按材料原样记录，不做换算；误差棒含义不明时如实说明。

## 异常处理

- 无材料或无读数：退出码 0，`status=failed` 或 `partial`，仍写出带 `limits` 的 `manuscript.md` 与 `result.json`。
- 坏文件（坏 JSON / 空文件 / 二进制）：记入 `degradations`，不阻断。
- 输出目录不可写：回退到当前目录下的 `output/`。

## 材料解析（v9）

| 类型 | 处理 |
|---|---|
| `.md .txt .tex .bib .html .csv .tsv .json` | 直接读取；JSON 扁平化为可检索文本 |
| `.docx .xlsx .pptx` | 从 OOXML 解出正文 / 共享字符串 / 幻灯片文本 |
| **PDF** | 标准库解出**文本层**（FlateDecode 流 + 字面串）；无文本层的扫描件记 `no_text_layer` |
| **PNG / JPEG** | 读文件头记录尺寸（PNG IHDR / JPEG SOFn），内容进 `figure_inventory` 并转 `human_review` 人工读数 |
| 位图或扫描件存在时 | 记 `png_skipped`：离线无字体渲染器，预览改为 `preview.svg`，不伪造 PNG |

## 自检与增益（v10）

- 离线自测：`python3 scripts/main.py --selftest` → 19 项（PDF 文本层、位图清点、坏件降级、8 件产物、
  SVG 预览、契约回填、基线指标、因果措辞、占位符扫描），退出码 0。
- 评分口径到检查项的映射见 `references/rubric.md`；基线对照怎么读见 `references/benchmark.md`；
  骨架模板见 `references/templates/results_discussion_template.md`；专家方法见 `references/expert_playbook.md`。
- 自检清单：单命令退出码 0 且 `result.json` 合法；契约逐键回填、`case_id` 透传；
  每个读数可回溯到 `D-ID`；**`references/expert_playbook.md` §5 专家检查表逐项通过**；
  异常已分类、阴性结果未消失。

## 适用条件与限制

- 适用：已有数据表/图表/统计输出，需要写成结果段与讨论段的章节写作。
- 限制：离线，不联网查询文献；位图与扫描 PDF 无 OCR（只能清点并转人工）；显著性仅在材料给出时报告；
  数值分级为启发式，最终以人工复核为准。

结构约定见 `references/schema.md`，撰写口径见 `references/writing-rules.md`，专家方法见 `references/expert_playbook.md`，增益证据见 `GAIN_EVIDENCE.md`。
