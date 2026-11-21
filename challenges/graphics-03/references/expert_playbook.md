## 1. 任务理解与判分要点

本任务真正要交付的不是“一张图”，而是从机制材料到**可编辑源文件 + 导出件 + 可追溯证据链**的完整闭环。评委重点看五件事：

1. **实体与关系是否正确**：基因/蛋白/复合物/细胞类型/区室不混用；激活、抑制、磷酸化、泛素化、结合、转运可区分。
2. **通路方向与区室布局是否准确**：上下游方向、跨膜受体位置、胞质/核内定位、反馈环走向。
3. **图例与数据编码是否自洽**：颜色、线宽、节点大小、形状与实际图面一致，且能回溯到输入数据。
4. **可编辑源文件是否真实可用**：SVG/draw.io 分层、文本可编辑、字体可替换，不是位图截图。
5. **可核验性**：每个关键图面元素有 locator（页码/段落/逐字引用），导出参数可复算，异常有说明。

常见失败模式逐条对照：

| 错误做法 | 正确做法 |
|---|---|
| 把输入名词平铺成节点，随意连线 | 先抽取实体和关系，每条边有语义类型、方向和证据 |
| 不区分激活与抑制，箭头样式混用 | 定义箭头端点：激活 `→`，抑制 `⊣`，磷酸化 `→P`，泛素化 `→Ub`，结合 `—`，转运 `→跨膜/入核` |
| 跨膜受体画在膜内，核蛋白画在胞质 | 建立区室约束：受体胞外域在膜外、激酶域在胞内；转录因子在核内 |
| 图例缺失或与图面不一致 | 图例由数据映射生成，校验图面颜色/线宽/形状与图例逐项匹配 |
| 只输出 PNG 位图 | 必须输出 SVG/draw.io 源文件 + PNG/PDF 导出件 |
| 图中数值找不到来源 | 每个数据映射标注 locator，如 `{"page":3,"quote":"TGFBR2 phosphorylates TGFBR1"}` |
| 不处理实体歧义 | 基因/蛋白/同义名归一，歧义实体列出候选并说明选择依据 |
| 不记录版本、不确定性、异常 | result.json 包含 status、sources、uncertainty、change_records |

## 2. 求解框架：从输入材料到交付物的分步流程

每步冻结产物，通过门控才进入下一步。

**步骤 0：输入读取与任务解析**  
读取 `/input/case.json`、`task.md` 及实际材料文件（PDF 等）。  
冻结：`input_manifest.json`（文件路径、哈希、页数）。  
门控：确认 `case_id` 存在，材料可读；缺失/损坏则记录 `status: "partial"` 或 `"failed"`，不得伪造。

**步骤 1：证据抽取与实体识别**  
从材料中抽取实体提及，记录 locator。  
冻结：`entities_raw.json`。  
门控：每个实体至少一个 locator；无 locator 的实体标记为 `"待确认"`，不得进入图面。

**步骤 2：实体规范化与消歧**  
分类为 gene/protein/complex/cell_type/compartment；同义名归一；映射权威 ID（HGNC、UniProt）。  
冻结：`entities_norm.json`。  
门控：每个实体有唯一 ID、类别、名称、来源；歧义实体列出候选并给出选择依据。

**步骤 3：关系语义判定**  
从文本抽取相互作用，映射到关系类型：activation、inhibition、phosphorylation、ubiquitination、binding、recruitment、transport、transcriptional_regulation。  
冻结：`edges.json`。  
门控：每条边有 source/target/type/evidence；方向可判定；无方向信息时标记 `undirected` 或 `uncertain`，不得随意画箭头。

**步骤 4：布局与区室约束**  
确定通路方向，划分区室（细胞外、膜、胞质、核等），定位跨膜实体，处理分支/反馈环。  
冻结：`layout_spec.json`（区室边界、节点位置或自动布局规则、箭头路径）。  
门控：受体跨膜域在膜上，胞外域在膜外，核蛋白在核内；反馈环方向明确。

**步骤 5：图例与数据编码**  
定义颜色、线宽、节点大小、形状到数据（表达量、显著性、置信度、时间点）的映射。  
冻结：`legend_spec.json`。  
门控：图例项与图面元素一一对应；数值有来源；使用色盲安全配色。

**步骤 6：源文件生成**  
生成 SVG/draw.io 分层源文件，图层命名清晰（background、compartments、nodes、edges、labels、legend）。  
冻结：`source.svg` 或 `source.drawio`。  
门控：文本为 `<text>` 元素而非路径；图层可锁定/隐藏；字体可替换。

**步骤 7：导出与校验**  
导出 PNG（目标 dpi）、PDF（字体嵌入）、SVG（独立）。  
冻结：`exports/` 和 `checks.json`。  
门控：PNG 尺寸≥目标；PDF 字体全部嵌入；SVG 通过 XML 解析。

**步骤 8：结果打包与可追溯记录**  
生成 `result.json`，包含 `case_id`、`status`、`entities`、`edges`、`legend`、`sources`、`uncertainty`、`change_records` 及原始 `output_contract` 字段。  
冻结：`/app/output/result.json`。  
门控：所有关键图面元素可回溯到 locator；异常有说明；部分结果诚实标识限制。

## 3. 专家方法与量化口径

关键指标定义、公式、单位、可接受波动：

| 指标 | 公式 | 目标 | 可接受波动 |
|---|---|---|---|
| 实体覆盖率 EC | `N_drawn / N_expected × 100%` | 100% | ≥95%，低于需补充或说明 |
| 关系语义准确率 RSA | `N_correct_edges / N_total_edges × 100%` | 100% | ≥90%，不确定边不计入正确但需标记 |
| 方向正确率 DA | `N_correct_directed / N_total_directed × 100%` | 100% | 100%，方向错误为硬伤 |
| 图例一致性 LC | `N_matched_legend_items / N_total_legend_items × 100%` | 100% | 100% |
| 可追溯率 TR | `N_elements_with_locator / N_total_elements × 100%` | 100% | 100% |
| 可编辑性检查 | `N_editable_text / N_total_text × 100%` | 100% | 100% |

计算示例：某案例材料明确提到 8 个实体、6 条边、4 个图例项。图面画出 8 个实体、6 条边、4 个图例项，且全部有 locator。  
EC = 8/8 = 100%；RSA = 6/6 = 100%；DA = 6/6 = 100%；LC = 4/4 = 100%；TR = (8+6)/(8+6) = 14/14 = 100%。  
导出：PNG 300 dpi，尺寸 2400×1800 px（8×6 英寸）；PDF 字体嵌入 12/12 文本元素；SVG 通过 XML 解析。  
若 EC = 7/8 = 87.5%，低于 95%，必须停止，补充缺失实体或说明忽略理由。

## 4. 领域知识清单

本领域容易犯的事实性错误：

1. **基因与蛋白混淆**：人类基因符号大写斜体（如 *TGFBR2*），蛋白正体大写（TGFBR2）；小鼠基因首字母大写其余小写斜体（*Tgfbr2*），蛋白正体（TGFBR2）。图中通常用蛋白名，若用基因名需标注。
2. **复合物与家族成员**：SMAD2/3 表示 SMAD2 和 SMAD3 两个蛋白，不是复合物；SMAD2/3-SMAD4 复合物需明确标注。
3. **亚细胞区室**：跨膜受体如 TGFBR2 的配体结合域在细胞外，激酶域在胞内；SMAD 蛋白在胞质，激活后入核；转录因子在核内。
4. **箭头语义**：激活 `→`，抑制 `⊣`，磷酸化 `→P`，泛素化 `→Ub`，结合 `—`，转运 `→跨膜/入核`，转录调控 `→基因`。
5. **通路方向**：配体→受体→胞内信号→转录因子→靶基因。反馈环需明确正/负。
6. **数据编码**：颜色映射表达量（如红高蓝低），线宽映射置信度，节点大小映射显著性，形状映射实体类型。
7. **单位/量纲陷阱**：表达量 log2FC 无单位，显著性 -log10(p) 无单位，置信度 0-1；颜色标尺需标注范围。
8. **文献依据**：每个实体和边需有来源定位（如 PMID 或材料页码/段落）。不能凭记忆补造。

## 5. 高质量交付物清单

应交付文件及自证可核验方式：

| 文件 | 内容 | 自证可核验 |
|---|---|---|
| `/app/output/result.json` | case_id、status、entities、edges、legend、sources、uncertainty、change_records、output_contract 字段 | 每个实体/边有 `source_locator` 字段，如 `{"page":3,"quote":"TGFBR2 phosphorylates TGFBR1"}` |
| `/app/output/source.svg` 或 `source.drawio` | 分层可编辑源文件 | 用文本编辑器打开，确认 `<text>` 元素存在，非路径；图层可锁定/隐藏 |
| `/app/output/exports/figure.png` | 300 dpi PNG | 复算命令：`python check_export.py --png figure.png --dpi 300` |
| `/app/output/exports/figure.pdf` | 字体嵌入 PDF | 复算命令：`python check_export.py --pdf figure.pdf --check-fonts` |
| `/app/output/exports/figure.svg` | 独立 SVG | 复算命令：`python check_export.py --svg figure.svg --validate-xml` |
| `/app/output/entities.json` | 实体清单，含 locator | 逐条核对 locator 指向原文 |
| `/app/output/edges.json` | 边清单，含 locator | 逐条核对语义类型和方向 |
| `/app/output/legend.json` | 图例映射 | 逐项核对图面元素 |
| `/app/output/evidence.md` | 逐元素来源定位（逐字引用） | 每个引用可定位到原文页码/段落 |
| `/app/output/checks.md` | 导出检查结果 | 包含复算命令及输出 |
| `/app/output/README.md` | 使用说明、限制、失败处理 | 他人可按说明独立复现 |

## 6. 防扣分自查表

1. ☐ 是否读取了 `/input/case.json` 和 `task.md` 实际文件？
2. ☐ 是否从材料中抽取实体并记录 locator？
3. ☐ 是否区分基因/蛋白/复合物/细胞类型/区室？
4. ☐ 是否对同义名归一？
5. ☐ 是否每条边有语义类型和方向？
6. ☐ 是否区分激活/抑制/磷酸化/泛素化/结合/转运？
7. ☐ 是否跨膜受体位置正确（胞外域在膜外，激酶域在胞内）？
8. ☐ 是否核蛋白在核内？
9. ☐ 是否通路方向正确（配体→受体→胞内信号→转录因子→靶基因）？
10. ☐ 是否图例与图面一致？
11. ☐ 是否数据映射有来源？
12. ☐ 是否输出可编辑源文件（SVG/draw.io）？
13. ☐ 是否导出 PNG/PDF/SVG？
14. ☐ 是否检查 PNG 分辨率、PDF 字体嵌入、SVG 可打开？
15. ☐ 是否 result.json 包含所有 output_contract 字段和 case_id？
16. ☐ 是否记录不确定性、异常、变更记录？
17. ☐ 是否部分结果诚实标识限制？
18. ☐ 是否不预制答案、不补造数据？
19. ☐ 是否资源文件在限制内（50 文件、500KB/文件、2MB 总量）？
20. ☐ 是否提供最小调用示例？

## 7. 一个完整虚构案例演示（输入 → 关键中间量 → 输出）

> 以下为虚构演示，仅用于说明流程，不冒充正式案例结果。

**输入**  
`case.json` 包含 `case_id: "demo-001"`，材料为一段文字（虚构）：
> “在肝星状细胞中，TGF-β1 与 TGFBR2 结合，TGFBR2 磷酸化 TGFBR1，TGFBR1 磷酸化 SMAD2 和 SMAD3，磷酸化的 SMAD2/3 与 SMAD4 形成复合物并转运入核，激活 SERPINE1 基因转录。SMAD7 蛋白抑制 TGFBR1 的磷酸化，形成负反馈。图中需用颜色表示 SMAD2/3 的磷酸化水平（高=红，低=蓝），线宽表示证据强度（强=2pt，中=1pt）。”

**关键中间量**  
- 实体抽取：TGF-β1（配体，胞外）、TGFBR2（受体，膜）、TGFBR1（受体，膜）、SMAD2（蛋白，胞质）、SMAD3（蛋白，胞质）、SMAD4（蛋白，胞质/核）、SMAD7（蛋白，胞质/核）、SERPINE1（基因，核）。共 **8 个实体**。
- 关系抽取：TGF-β1→TGFBR2 结合；TGFBR2→TGFBR1 磷酸化；TGFBR1→SMAD2 磷酸化；TGFBR1→SMAD3 磷酸化；SMAD2/3-SMAD4 复合物入核→SERPINE1 转录激活；SMAD7⊣TGFBR1 磷酸化（负反馈）。共 **6 条边**。
- 图例：颜色映射磷酸化水平（红高蓝低），线宽映射证据强度（强=2pt，中=1pt），形状映射实体类型（配体=圆，受体=矩形，蛋白=椭圆，基因=菱形）。共 **4 个图例项**。
- 布局：胞外区（TGF-β1），膜区（TGFBR2、TGFBR1），胞质区（SMAD2、SMAD3、SMAD4、SMAD7），核区（SERPINE1）。方向：TGF-β1→TGFBR2→TGFBR1→SMAD2/3→SMAD4→核→SERPINE1；SMAD7 从胞质/核指向 TGFBR1 抑制。

**输出**  
- `source.svg`：分层，8 个实体，6 条边，4 个图例项。
- `exports/figure.png`：300 dpi，尺寸 2400×1800 px（8×6 英寸）。
- `exports/figure.pdf`：字体嵌入 12/12 文本元素。
- `result.json`：`case_id: "demo-001"`，`status: "success"`，`entities: 8`，`edges: 6`，`legend: 4`，`source_locator` 覆盖 14/14（100%），`uncertainty: 0`，`change_records: 1` 条。
- 量化指标：EC = 8/8 = 100%；RSA = 6/6 = 100%；DA = 6/6 = 100%；LC = 4/4 = 100%；TR = 14/14 = 100%。
- 复算命令：`python check_export.py --png figure.png --dpi 300 --pdf figure.pdf --svg figure.svg` 输出全部通过。
