# 专家参考手册：引言与相关工作写作（intro-relatedwork-writer）

执行任何命令、产出任何交付物之前，先读本手册；按 §2 八步推进，交付前逐项过 §6 检查表。

## 1. 判分要点

本任务要求交付一个可被 Agent 调用的 Skill，用于在 3 个未知固定科研案例上完成"引言与相关工作写作"并保留来源。评委核心看五件事：**立得住、分得清、说得实、对得上、可核验**。实际效果 40 分，使用增益 25 分，创新增益 15 分，可靠体验 10 分，生态贡献 10 分。

### 1.1 常见失败模式（错误做法 → 正确做法）

| 错误做法 | 正确做法 |
|-|-|
| 背景写"近年来受到广泛关注"式空话 | 从具体技术约束和未解决问题入手，如"医学影像分类在标注数据低于 2k 时，监督方法准确率下降至 85% 以下（L1）" |
| 相关工作逐篇摘要拼接 | 按问题/方法/技术路线分组，在同一维度（问题设定、方法路线、数据与评价方式）上比较各工作取舍 |
| 研究空白声称"尚无研究" | 从已引文献的共同限制、未覆盖场景或冲突结论推导，如"现有自监督方法需要 50k 无标注数据（L3），在仅有 5k 无标注的低资源场景下未覆盖" |
| 贡献写"首次提出""显著优于" | 限定适用范围，如"在 2k 标注 + 5k 无标注设定下，本文方法达到 92% 准确率，计算成本降低 30%" |
| 引用元数据错误（作者、年份、期刊、卷期页码） | 逐条核对原文，生成元数据准确率报告 |
| 转述失真，把"在 X 条件下有效"写成"普遍有效" | 保留条件限定词，如"在 10k 标注图像上准确率 92%" |
| 不标注材料不足、冲突、需人工确认项 | 明确标注"材料未提供目标期刊格式，按 APA 默认处理" |
| 只生成文本，没有来源映射 | 附 fact_source_map，每条事实/数字/引用定位到来源文件页码/段落/图表编号 |
| 忽略格式约束（引用格式、字数、语言） | 从任务说明中提取约束，生成 task_contract.md |
| 贡献与图表不对应 | 每条贡献定位到图/表编号，如"贡献 2 对应表 2 第 3 行" |

## 2. 求解框架（每步冻结产物并设门控，未通过门控不得进入下一步）

| 步 | 动作 | 冻结产物 | 门控标准 |
|-|-|-|-|
| 0 输入解析 | 读 `/input/case.json`、`task.md`、`resources.yaml`，解析 PDF 原文，提取事实底稿、受众、文体、格式约束 | `evidence_inventory.json` | 至少识别任务类型、目标期刊/格式、语言、引用风格；材料缺失项已标记 |
| 1 任务契约提取 | 明确输出类型、受众、文体、格式、引用风格、字数限制、必需章节 | `task_contract.md` | 输出字段与评分证据范围对齐，无歧义 |
| 2 文献与事实抽取 | 从材料中抽取文献元数据、关键论断、方法路线、数据、图表、局限 | `literature_corpus.jsonl` | 每篇至少提取元数据 + 1 条可引用论断；无法提取的标记 `extraction_failed` |
| 3 分组与比较维度设计 | 按问题/方法/技术路线分组，确定比较维度 | `grouping_plan.md` | 每组至少 2 篇或说明单篇原因；维度覆盖问题设定、方法路线、数据与评价方式 |
| 4 空白推导与贡献映射 | 从已引文献共同限制、未覆盖场景、冲突结论推导空白；将贡献条目与正文方法/图表/实验结果对应 | `gap_contribution_map.md` | 每条空白至少引用 1 条文献缺口；每条贡献至少 1 个正文证据定位 |
| 5 草稿生成与引用绑定 | 生成引言与相关工作，引用落在具体论断上 | `draft.md` + `citation_binding.jsonl` | 每个引用至少绑定一个论断；无来源事实不新增 |
| 6 核验与修改 | 逐条核对引用元数据、转述一致性、格式、贡献对齐 | `verification_report.md` + `revised_draft.md` | 元数据准确率、绑定率、对齐率达阈值（见 §3） |
| 7 交付物打包 | 生成 `result.json`、可编辑稿件、事实来源映射、版本边界、预览 PDF/PNG | `/app/output/` 下所有文件 | `result.json` 含所有必需字段；可编辑文件存在；预览渲染成功 |

## 3. 专家方法与量化口径（单位均为百分比，保留 1 位小数）

| 指标 | 公式 | 可接受波动 | 计算示例 |
|-|-|-|-|
| 引用覆盖率 CC | 关键工作覆盖数 / 应覆盖关键工作数 × 100% | ≥ 90% | 应覆盖 10 篇实覆盖 9 篇 → 90.0% |
| 引用-论断绑定率 CBR | 绑定到具体论断的引用条数 / 总引用条数 × 100% | ≥ 95% | 15 条中 14 条绑定 → 93.3% |
| 分组纯度 GP | 同组文献共享同一分组依据的文献数 / 总文献数 × 100% | ≥ 90% | 12 篇中 11 篇依据明确 → 91.7% |
| 空白推导支持率 GSR | 有文献缺口直接支持的空白条数 / 空白总条数 × 100% | ≥ 80%，未支持项须标注为作者判断 | 3 条中 2 条有据 → 66.7%（第 3 条已标注，合格） |
| 贡献-证据对齐率 CEA | 有正文证据定位的贡献条数 / 贡献总条数 × 100% | 100% | 4 条全部有据 → 100.0% |
| 元数据准确率 MA | 元数据正确条数 / 总引用条数 × 100% | ≥ 95%，错误项须修正或标注 | 15 条中 14 条正确，1 条年份错误已修正 → 修正后 100.0% |
| 事实可回溯率 FT | 可回溯到来源的事实/数字条数 / 总事实/数字条数 × 100% | 100% | 20 条全部可回溯 → 100.0% |
| 材料缺口标注率 GAR | 已标注缺口/不确定项数 / 总缺口/不确定项数 × 100% | 100% | 2 项全部标注 → 100.0% |
| 转述一致性 PC | 转述与原文一致的引用条数 / 总引用条数 × 100% | ≥ 95%，不一致项须修正 | 15 条中 14 条一致，1 条修正 → 修正后 100.0% |
| 格式一致性 FC | 符合目标引用格式的引用条数 / 总引用条数 × 100% | 100% | 15 条全部符合 APA → 100.0% |

**综合计算示例**：总引用 15 条，应覆盖关键工作 10 篇实覆盖 9 篇；绑定 14 条；分组 12 篇中 11 篇明确；空白 3 条中 2 条有据；贡献 4 条全部对齐；元数据 14 条正确；事实 20 条全部可回溯；缺口 2 项全部标注；转述 14 条一致；格式 15 条全部符合。则 CC=90.0%，CBR=93.3%，GP=91.7%，GSR=66.7%（但第 3 条已标注），CEA=100.0%，MA=93.3%（修正后 100%），FT=100.0%，GAR=100.0%，PC=93.3%（修正后 100%），FC=100.0%。整体合格，但 CBR 和 MA 需在核验报告中说明修正动作。

## 4. 领域知识清单（事实性错误、单位/量纲陷阱、文献依据要求）

### 4.1 事实性错误

- 将"近年来受到广泛关注"作为背景，没有具体时间、领域、问题。应改为具体技术约束和未解决问题。
- 逐篇摘要而非分组比较。应按问题/方法/技术路线分组，在同一维度比较。
- 引用元数据错误：作者拼写、年份、期刊/会议名、卷期页码、DOI。需逐条核对原文。
- 转述失真：把"在 X 条件下有效"写成"普遍有效"；把"优于 A"写成"优于所有"。需保留条件限定词。
- 研究空白无据：声称"尚无研究"但已有文献覆盖。应改为"在 Y 场景下未覆盖"并引用具体文献。
- 贡献夸大：声称"首次提出"但已有类似工作。应限定范围或改为"在 Z 设定下"。

### 4.2 单位/量纲陷阱

- 百分比与百分点混淆：准确率从 90% 提升到 92% 是提升 2 个百分点，不是提升 2%。
- 跨数据集比较绝对数值：不同数据集上的准确率不可直接比较，需注明数据集和评价协议。
- 性能指标单位：F1、BLEU、准确率、召回率等需保留原始单位和评价协议，不擅自换算。
- 计算成本：如"降低 30%"需注明基准和单位（如 FLOPs、训练时间、显存占用）。

### 4.3 文献依据要求

- 关键论断必须有引用；数字必须有来源；图表引用需定位到图/表编号。
- 引用需可回溯到原文，提供文件路径、页码/段落/图表编号。
- 不新增材料外事实；如需补充领域常识，必须标注为作者判断或外部知识。

## 5. 高质量交付物清单（应交付文件/章节及自证方式）

| 文件/章节 | 内容 | 自证可核验方式 |
|-|-|-|
| `result.json` | `case_id`、`status`、`target_artifact`、`fact_source_map`、`version_boundary`、`uncertainty`、`change_record` 等字段 | 字段齐全，status 为 success/partial，fact_source_map 每条有 locator |
| 可编辑稿件 `draft.md`/`draft.docx` | 四部分（研究背景、相关工作、研究空白、贡献）齐全，引用绑定具体论断 | 每个引用可定位到 `citation_binding.jsonl` 中的论断 ID |
| 事实与来源映射 `fact_source_map.json` | 每条事实/数字/引用/图表定位到来源文件路径、页码/段落/图表编号，附逐字引用 | 每条含 locator、quote、status（verified/uncertain） |
| 修改记录 `change_record.md` | 修改差异、人工确认项、材料缺口 | 每条修改有前后对比和原因 |
| 核验报告 `verification_report.md` | 量化指标、逐条核对结果、未通过项 | 含复算命令，如 `python check_citations.py --input draft.md --corpus literature_corpus.jsonl` |
| 分组与比较矩阵 `grouping_plan.md` | 分组依据、每组文献、比较维度矩阵 | 矩阵可复算，每组文献 ID 与 `literature_corpus.jsonl` 一致 |
| 空白与贡献映射 `gap_contribution_map.md` | 空白推导和贡献证据定位 | 每条空白有文献缺口引用，每条贡献有正文证据定位 |
| 预览 `preview.pdf`/`preview.png` | 可编辑稿件的渲染预览 | 文件存在且可打开，内容与稿件一致 |
| 运行日志 `run.log` | 脚本、参数、耗时、异常 | 记录完整，异常有处理说明 |

## 6. 防扣分自查表（交付前逐项通过）

1. ☐ 是否读取实际输入文件 `/input/case.json`、`task.md`、`resources.yaml` 而非假设来源内容？
2. ☐ 是否提取任务说明中的受众、文体、格式约束？
3. ☐ 是否生成四个部分（研究背景、相关工作、研究空白、贡献）且彼此承接？
4. ☐ 是否每条引用绑定具体论断？
5. ☐ 是否逐条核对引用元数据（作者、年份、期刊、卷期页码、DOI）？
6. ☐ 是否按问题/方法/技术路线分组，而非逐篇摘要？
7. ☐ 是否在同一维度（问题设定、方法路线、数据与评价方式）比较各工作？
8. ☐ 是否从已引文献缺口推导空白，而非声称"尚无研究"？
9. ☐ 是否每条贡献有正文证据定位（图/表/实验编号）？
10. ☐ 是否不新增材料外事实？
11. ☐ 是否标注材料不足、冲突、需人工确认项？
12. ☐ 是否保留修改记录和来源定位？
13. ☐ 是否生成可编辑产物和预览 PDF/PNG？
14. ☐ 是否 `result.json` 包含所有必需字段？
15. ☐ 是否处理异常（文献库为空、引用查不到原文、格式未知、语言切换）？
16. ☐ 是否量化指标达到阈值（CC≥90%，CBR≥95%，CEA=100%，FT=100% 等）？
17. ☐ 是否避免空泛背景和逐篇摘要？
18. ☐ 是否统一引用格式（APA/IEEE/其他）？
19. ☐ 是否保留原始单位和评价协议？
20. ☐ 是否在预算内保存部分交付物并诚实标注 limits？

## 7. 完整虚构案例（输入 → 关键中间量 → 输出）

**输入**：
- `case.json`：`case_id = "demo-001"`，撰写引言与相关工作，APA 格式，约 800 字，四部分齐全。
- `task.md`：受众为医学影像分析期刊读者，文体学术论文引言，引用格式 APA，语言英文。
- `materials/` 下 5 篇 PDF：
  - L1: Smith et al. (2020), "Supervised classification for medical imaging", *Journal of Medical AI*, 12(3), 45-60. 方法监督 CNN，数据 10k 标注，准确率 92%，局限需大量标注。
  - L2: Chen et al. (2021), "Efficient supervised transformers for medical imaging", *IEEE TMI*, 40(5), 1200-1215. 方法监督 Transformer，数据 8k 标注，准确率 93%，局限计算成本高。
  - L3: Lopez et al. (2022), "Self-supervised pretraining for medical image analysis", *Nature Methods*, 19(7), 800-812. 方法自监督对比学习，数据 50k 无标注 + 5k 标注微调，准确率 94%，局限需大规模无标注。
  - L4: Wang et al. (2023), "Hybrid self-supervised and supervised learning for low-resource medical imaging", *Medical Image Analysis*, 85, 102700. 方法混合自监督+监督，数据 2k 标注 + 20k 无标注，准确率 91%，局限低资源下仍低于全监督。
  - L5: Zhang et al. (2024), "Benchmarking medical imaging classification under label scarcity", *Scientific Data*, 11, 500. 方法基准评测，结论自监督在标注稀缺时优于监督但需调参。
- `our_method.pdf`：本文轻量混合方法，2k 标注 + 5k 无标注下达 92% 准确率，计算成本降低 30%，方法图 1，表 2 第 3 行，实验 3.2。

**关键中间量**：文献 5 篇，应覆盖 5 实覆盖 5，CC=100.0%；分组 3 组（监督：L1,L2；自监督：L3；混合/基准：L4,L5），GP=5/5=100.0%；比较维度为问题设定（标注需求）、方法路线、数据与评价方式、局限；引用-论断绑定 5/5，CBR=100.0%；空白：低资源且无大规模无标注场景下如何高效利用少量标注和少量无标注，GSR=100.0%；贡献 3 条各有正文证据（图 1、表 2、实验 3.2），CEA=100.0%；元数据 5/5 正确，MA=100.0%；事实/数字 10 条（准确率 92/93/94/91/92、数据规模 10k/8k/50k/2k+20k/2k+5k、成本降低 30%）全可回溯，FT=100.0%；格式 APA 5/5，FC=100.0%；转述 5/5 一致，PC=100.0%。

**输出**：
- `draft.md`（约 800 字，四部分齐全，引用绑定），示例片段：
  > Medical image classification under label scarcity remains challenging. Supervised CNN achieves 92% accuracy on 10k labeled images (Smith et al., 2020), while supervised Transformer reaches 93% on 8k labeled images but incurs high computational cost (Chen et al., 2021). Self-supervised contrastive learning attains 94% accuracy but requires 50k unlabeled images plus 5k labeled fine-tuning (Lopez et al., 2022). Hybrid methods achieve 91% on 2k labeled + 20k unlabeled images, still below full supervision (Wang et al., 2023). Benchmarking shows self-supervision outperforms supervision under label scarcity but needs careful tuning (Zhang et al., 2024). The gap is efficient learning with only 2k labeled and 5k unlabeled images. We propose a lightweight hybrid method achieving 92% accuracy and 30% lower computational cost (Figure 1, Table 2, Section 3.2).
- `fact_source_map.json`：每条事实定位，如 `{"fact": "92% accuracy on 10k labeled images", "source": "L1.pdf", "locator": "page 3, Table 1", "quote": "Our supervised CNN achieves 92% accuracy on 10k labeled images", "status": "verified"}`。
- `change_record.md`：记录修改，如"将'显著优于'改为'在 2k 标注 + 5k 无标注下达到 92% 准确率'，原因：避免夸大"。
- `verification_report.md`：含上述指标与逐条核对结果。
- `result.json`：含 `case_id: "demo-001"`、`status: "success"`、`target_artifact: "draft.md"`、`fact_source_map`、`version_boundary`、`uncertainty: []`、`change_record` 等字段。
- `preview.pdf`：渲染预览。

所有数字均可复算：CC=100%，CBR=100%，GP=100%，GSR=100%，CEA=100%，MA=100%，FT=100%，FC=100%，PC=100%。
