# 阅读批注与知识沉淀 · 专家方法论手册

本手册描述「阅读批注与知识沉淀」任务的判分口径、求解框架、量化公式、错误模式、自查表与案例。命令接口见 SKILL.md，方法论以下文为准。核心原则：**不追求抽取数量，追求逐条可回溯、可复跑、可核验**。

## 1. 交付本质与判分要点

任务不是「把 PDF 里的文字抽出来」，而是完成闭环：**批注提取 → 笔记结构化 → 知识关联 → 检索入库 → 可核验交付**。交付物须让复核者：对任意批注回到原文件具体页与位置；对任意笔记论断找到支撑原文；对任意关联看到关联依据；按记录复跑得到一致结果。

| 维度 | 关键考察 |
|---|---|
| 实际效果（40） | 是否跑完闭环；批注锚点/类型/颜色是否保留；笔记是否有原文支撑；关联是否有依据；是否覆盖重复文件、版本差异、权限与来源 |
| 使用增益（25） | 抽取准确率、笔记可用性、关联有效性是否稳定提升；人工修改量是否下降；是否有同输入对照 |
| 创新增益（15） | 扫描件锚点校正、跨版本批注归并、批注→笔记→检索贯通 |
| 可靠体验（10） | 正确触发；不同文件类型/页数/版式稳定；对加密、损坏、无文本层、OCR 低置信度、旧版本批注、重复文件、权限不足的识别处置 |
| 生态贡献（10） | 文档、脚本、schema、规则、题集可复用；沉淀可分享案例 |

## 2. 错误做法 → 正确做法

| 错误做法 | 正确做法 |
|---|---|
| 只抽文字，不记页码/坐标/类型/颜色 | 每条批注带 `file_hash + page + rect/quad + type + color + raw_text` |
| 把高亮、下划线、页边、手写混为一类 | 显式区分 `highlight / underline / margin_note / handwritten / sticky_note` |
| 笔记写成摘抄，无结构无来源 | 每条笔记含 `note_id + type + claim + source_annotation_ids + locator` |
| 仅凭关键词重合建关联 | 关联须写明依据：`same_doi + text_similarity + version_chain` 或 `same_entity + context_overlap` |
| 多版本/重复下载未归并 | `sha256` 识别重复；元数据（DOI/标题/版本号/日期）建版本链 |
| 过程不可复现，缺哈希与脚本版本 | 记录每文件 `sha256`、抽取脚本版本、OCR 引擎版本、参数、运行时间 |
| 把未完成写成完成 | 区分 `completed / partial / skipped / failed` 并给原因与恢复方式 |
| 只输出最终结果，无中间证据 | 除 result.json 外附批注表、笔记表、关联表、运行日志 |

## 3. 求解框架（每步冻结产物 + 门控）

| 步 | 操作 | 冻结产物 | 门控 |
|---|---|---|---|
| 0 输入解析 | 读 case.json / task.md，取 case_id、材料目录、规则、证据范围 | case_meta.json | case_id 非空、材料路径存在可读 |
| 1 盘点与哈希 | 遍历目录，记路径、大小、权限、mtime、sha256；识别重复/版本 | file_inventory.csv/json | 所有文件有哈希；权限不足标 permission_denied |
| 2 批注提取与锚点校正 | PDF 优先原生批注层，无则文本层定位；扫描件 OCR 后校正坐标；双栏按栏 | annotations.jsonl | 每条有 file_hash+page+rect；OCR<0.6 标 low_confidence |
| 3 笔记结构化 | 批注整理为结构化笔记（question/method/conclusion/reusable_point/doubt/gap） | notes.jsonl | 每条 source_annotation_ids 非空且可回溯 |
| 4 知识关联与版本归并 | 在批注/笔记/文献/作者/方法间建关联；重复与版本归并 | relations.jsonl | 每条关联有 basis；无依据不建立 |
| 5 检索索引入库 | 设计可检索入口（主题/标签/实体/来源/时间），生成索引 | search_index.json | 索引字段覆盖所有笔记/批注关键属性 |
| 6 证据打包与自检 | 汇总产物、写 result.json、运行自检 | result.json、run_log.txt、self_check_report.json | 含全部 output_contract 字段；自检通过才标 completed |

## 4. 量化口径

| 指标 | 公式 | 合格线 |
|---|---|---|
| 锚点准确率 | `正确锚定批注数 / 总批注数 × 100%` | ≥95% |
| 类型召回率 | `正确识别类型数 / 标注类型总数 × 100%` | ≥90% |
| 笔记支撑率 | `有来源定位的笔记数 / 总笔记数 × 100%` | 100% |
| 关联精确率 | `有效关联数 / 总关联数 × 100%` | ≥90% |
| 检索命中率 | `相关命中数 / 检索返回总数 × 100%` | ≥80% |
| 可复跑率 | `可复现步骤数 / 总操作步骤数 × 100%` | 100% |

**自洽示例**：案例 A 抽 12 条批注、8 条笔记、6 条关联、3 次检索。锚点 `11/12=91.7%`（<95%，查第 12 条）；类型 `10/12=83.3%`（<90%，查 2 条）；笔记支撑 `8/8=100%`；关联 `5/6=83.3%`（<90%，剔除 1 条无效）；检索 `2/3=66.7%`（<80%，优化索引）；可复跑 100%。结论：锚点/类型/关联/检索未达标，回对应步骤修正，不得标 completed。

## 5. 领域知识清单

**事实性错误**
1. PDF 标签页码≠物理页码：区分并记录两者映射。
2. 双栏按单栏顺序读：按栏读取，记录栏位（左/右）。
3. 扫描件 OCR 坐标漂移未校正：记录 OCR 引擎、置信度、校正偏移量（如 dx=+2, dy=-2）。
4. 颜色含义被抹平：保留颜色字段，并在元数据说明颜色约定（如黄=重要、蓝=疑问）。
5. 文件名相同即视为同一版本：用 sha256 判重复；用 DOI/标题/版本号/日期判版本。
6. 仅凭关键词重合建关联：关联须多重依据，如 `same_doi + text_similarity≥0.9`。
7. 忽略权限不足文件：标 permission_denied，不强读、不伪造。
8. 把 OCR 低置信度文本当准确原文：<0.6 标 low_confidence 并在笔记注明。

**单位/量纲**：PDF 坐标为点（pt）、图像为像素，转换须注明 DPI（72 dpi 下 1 pt=1 px）；页码统一 1-based 并声明；OCR 置信度用 0–1 保留 2 位；时间戳 UTC ISO 8601；文件大小统一字节。

**依据要求**：每条批注可回溯到 `file_hash + page + rect/quad + raw_text`；每条笔记论断有 source_annotation_ids 且原文能支撑；每条关联有 basis（same_doi / text_similarity / version_chain）；不据错误标签补造数据，缺失/无法判断/失败分别说明。

## 6. 防扣分自查表

- [ ] 实际读取文件，而非仅依据文件名或标签
- [ ] 记录每个文件 sha256
- [ ] 区分批注类型（高亮/下划线/页边/手写）
- [ ] 保留颜色及其含义
- [ ] 处理双栏排版与扫描件 OCR 坐标漂移
- [ ] 每条笔记有 source_annotation_ids 与原文定位
- [ ] 每条关联有 basis 依据
- [ ] 处理重复文件（相同哈希）与版本差异（同 DOI 不同哈希）
- [ ] 记录跳过、失败、冲突、权限不足及恢复方式
- [ ] result.json 含全部 output_contract 字段与 case_id
- [ ] 所有步骤可复跑（哈希、脚本版本、命令日志）
- [ ] 在 64 次请求、900 秒、16384 tokens/response 预算内完成
- [ ] 未伪造软件状态或科学数据
- [ ] 提供最小调用示例并标明为示例
- [ ] 文档完整（使用说明、依赖、输入输出 schema、边界、维护）
- [ ] GitHub 链接有效且免登录
- [ ] 对低置信度 OCR 结果标记
- [ ] 对材料缺失/无法判断/运行失败分别说明
- [ ] 未完成部分标 partial 而非 completed
- [ ] 输出路径有效、无 symlinks、符合资源限制（≤50 文件，≤500KB/文件，≤2MB 总文本）

## 7. 完整虚构案例（输入 → 中间量 → 输出）

> 虚构示例，说明流程与数字自洽，非正式案例结果。

**输入**：case.json 要求提取所有批注、结构化笔记、关联版本、输出可检索清单。材料：`paper_v1.pdf`（3 页，高亮+页边批注）、`paper_v2.pdf`（4 页，同 DOI 新版本）、`scan_page.png`（扫描件，无文本层，有手写标记）、`notes.txt`（临时笔记，2 条批注）。

**关键中间量**
- 哈希：paper_v1=`3f9a1b2c…`、paper_v2=`c3d4e5f6…`、scan_page=`7a8b9c0d…`、notes.txt=`1e2f3a4b…`。
- 批注 12 条（节选）：A1 paper_v1 第2页 高亮 黄 rect(72,540,200,552) “This method achieves 95% accuracy.” conf0.98；A2 paper_v1 第2页 页边批注 蓝 rect(210,540,300,560) “Check if this holds on dataset X.” conf0.95；A3 scan_page 手写 OCR conf0.87 原始(100,200) 校正(102,198) 偏移(+2,-2) “Important: compare with baseline.”；其余 9 条略。
- 笔记 8 条（节选）：N1 类型 method 论断「该方法在数据集 X 上达到 95% 准确率」来源[A1] 定位 `paper_v1.pdf#page=2&rect=72,540,200,552`；N2 类型 doubt 论断「需验证泛化性」来源[A2] 定位 `paper_v1.pdf#page=2&rect=210,540,300,560`；其余 6 条略。
- 关联 6 条（节选）：R1 A1↔A5（v2 对应段）依据 `same_doi + text_similarity=0.93 + version_chain` 强度0.9；R2 N1↔N3 依据 `same_entity=dataset_X + context_overlap=0.85` 强度0.8；其余 4 条略。
- 检索索引：字段 topic/tag/entity/source_file/time；示例查询 `accuracy` → 返回 N1。

**输出**：result.json 含 case_id、status、资料结果（file_inventory/annotations/notes/relations/search_index 指针）、操作证据（hashes/commands/script_version）、失败与恢复（scan_page OCR 0.87 标 low_confidence）、不确定性、metrics（锚点 11/12=91.7%、类型 10/12=83.3%、支撑 8/8=100%、关联 5/6=83.3%、检索 2/3=66.7%、可复跑 100%）。自检结论：锚点/类型/关联/检索未达标，需修正后重跑——用数字暴露问题，而非掩盖。
