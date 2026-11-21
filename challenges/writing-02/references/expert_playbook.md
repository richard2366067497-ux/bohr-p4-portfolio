# 专家参考手册：学术语言润色（主张守恒型最小编辑）

执行任何命令、产出任何交付物之前，先读本手册；按 §2 流程推进，交付前逐项过 §7 检查表。

## 1. 判分要点

### 1.1 真正要交付什么

不是"写作建议"，也不是"整段重写"，而是**可编辑的润色全文 + 逐句修改说明 + 事实/来源映射 + 版本边界**：

- 润色后的完整文本，**保留原格式**（Markdown / LaTeX / 纯文本 / 章节稿）。
- 逐句修改说明：每条含 `原文 / 改文 / 修改类型 / 修改理由 / 来源定位`。
- 事实与来源映射：数字、单位、术语、引用编号、图表指向、关键论断的来源与修改记录，可逐条回溯。
- 版本与边界：修改差异、人工确认项、材料缺口、异常说明。

### 1.2 评委维度

| 维度 | 关键考察点 |
|-|-|
| 实际效果(40) | 是否交付"润色全文＋逐句说明"；限定强度/数据/单位/引用编号/图表指向是否保持；术语是否统一；说明是否足以让第三方判断"该不该改" |
| 使用增益(25) | 相比无 Skill 基线，语法修正、术语一致、语义保持、语气贴合是否稳定更好、返修更少 |
| 创新增益(15) | 是否具备基线没有的能力：术语表驱动回扫、限定强度守恒、双语术语对齐 |
| 可靠体验(10) | 触发准确；长文/分章/重复运行稳定；异常可识别可处置 |
| 生态贡献(10) | SKILL、术语表、风格指南、示例、限制齐全可复用 |

## 2. 流程与门控（前一步未冻结不进入下一步）

| 步 | 动作 | 冻结产物 | 门控 |
|-|-|-|-|
| 0 读输入 | 读 `/input/case.json` 与 `task.md`，解析受众、文体、格式约束、评分证据范围 | `case_meta`（任务类型/材料清单/约束/输出字段） | 材料存在、缺失已记录；不假设材料内容 |
| 1 事实与术语 | 抽取数字、单位、术语、引用编号、图表指向、关键论断；建术语表 | 事实表（带 locator＋逐字摘录）、术语表 | 每个数字与引用有来源定位；术语冲突在案 |
| 2 逐句处理 | 按句/段切分，保留结构；每句做语法、术语、语气修正并做语义保持检查 | 逐句计划（原文/改文/类型/理由/定位） | 每处修改有类型与理由；限定词/数据/单位/引用编号不变 |
| 3 全篇回扫 | 用术语表回扫：缩写首现、大小写、连字符、同义混用；核对引用与图表指向 | 一致性报告（冲突项与处理） | 术语一致率 100% 或冲突已标注 |
| 4 生成交付物 | 输出可编辑全文、逐句说明表、来源映射表、版本边界；渲染预览 | `/app/output/*` + `result.json` | 契约键与 case_id 齐全；可编辑产物与预览存在 |
| 5 自检与改进 | 检查编辑距离、术语一致率、限定词保持率、来源映射覆盖率 | 自检报告 | 指标达标或记录未达标原因 |

## 3. 错误做法 → 正确做法

1. 整段重写 → 最小编辑，逐句对照，保留限定词、数据、引用编号。
2. 只给建议不给可编辑文本 → 交付完整润色文本 + 修改清单。
3. 术语前后漂移 → 建术语表，全篇回扫统一，缩写首现定义。
4. 来源不明 → 每条修改带原文定位、改文、类型、理由；数字保留来源。
5. 材料不足/冲突却不标注、擅自补造 → 明确标注人工确认项、材料缺口、异常。
6. 输出格式不可用（丢 LaTeX 公式、图表编号）→ 保留原格式，输出可编辑文件 + PDF/PNG 预览。
7. 重复运行结论漂移 → 固定规则与术语表，确定性输出，记录版本。
8. 超预算/不存中间产物 → 分步保存，增量改进，部分结果诚实。

## 4. 量化口径与公式

| 指标 | 定义 | 公式 | 可接受 |
|-|-|-|-|
| 编辑操作数 E | 语法/术语/语气/格式等操作总数 | 人工计数 | — |
| 最小编辑距离 D | 原文与改文的词级 Levenshtein 距离 | `difflib.SequenceMatcher` | D/E ≤ 2.5 |
| 术语一致率 C_term | 同一概念用同一术语 | `1 − 不一致出现次数 / 术语总出现次数` | ≥ 98% |
| 限定词保持率 C_hedge | 原文限定词在改文保留或等价保留 | `保留数 / 原文限定词数` | 100% |
| 数据/单位保持率 C_data | 数字、单位、引用编号、图表指向不变 | `保留数 / 总数` | 100% |
| 来源映射覆盖率 C_src | 带来源定位的修改条目占比 | `带定位条目 / 总条目` | 100% |
| 修改说明完整率 C_doc | 每条含原文/改文/类型/理由 | `完整条目 / 总条目` | 100% |

**算例（数字自洽）**：原文 98 词，含 3 处语法错、2 处术语不一致、1 处 `may` 被误删、1 处因果被加强、2 处格式错；润色后 102 词。E = 9；词级 D = 12；D/E = 12/9 = 1.33 ≤ 2.5；术语总出现 15 次，修正后 C_term = 100%；限定词原 4 保留 4，C_hedge = 100%；数据/单位 5 处全保留，C_data = 100%；9 条说明全带定位，C_src = C_doc = 100%。

**可复算**：词级 diff `python -c "import difflib,sys; print(difflib.SequenceMatcher(None,open('original.md').read().split(),open('edited.md').read().split()).ratio())"`；术语核对 `grep -o 'SEM\|TEM\|nanoparticle' edited.md | sort | uniq -c`。

## 5. 领域陷阱

1. **术语漂移**：同一概念中英混用（扫描电子显微镜 / SEM / 扫描电镜 / 电镜）。正解：首现全称（缩写），后文统一用缩写。
2. **缩写大小写与连字符**：`mRNA` vs `MRNA`、`T-cell` vs `T cell`，依领域惯例。
3. **单位量纲**：`10 μm` 不可改成 `10 µm`（除非原文如此）；单位符号大小写敏感（mL vs ml、kg vs Kg）。只修格式（空格），不改数字与单位。
4. **限定词强度**：`may indicate` 不可改成 `indicates`；`suggests` 不可改成 `proves`；`possibly` 不可删。保留或等价替换。
5. **因果与相关**：`associated with` 不可改成 `caused by`；`correlated with` 不可改成 `led to`。
6. **引用编号与图表指向**：润色不得改引用顺序或图表编号；句子重排导致顺序变化须同步调整并记录。
7. **数据精度**：`p = 0.032` 不可改成 `p = 0.03`；保留原值。
8. **中译英直译腔**：`according to our results, we can see that...` 冗余，可调整主语与信息结构，但保留信息重心。

修改理由须基于语法规则、领域术语惯例或风格指南；不确定则标注人工确认，不擅改。

## 6. 交付物与 locator

| 文件 | 内容 | 自证 |
|-|-|-|
| `result.json` | case_id、status、output_contract 全部字段、sources、uncertainty、change_records | 可解析，字段齐全 |
| `polished.md`(或 .tex) | 润色后完整文本 | 与原文 diff 可复现，格式保留 |
| `changes.csv` | 逐句说明：定位、原文、改文、类型、理由、来源定位 | 每条可回溯到原文行号 |
| `evidence.json` | 事实/来源映射：locator、原文摘录、改文摘录、是否保留 | locator 可定位到输入文件 |
| `glossary.csv` | 术语表：术语、缩写、首现位置、统一写法 | 全篇回扫一致 |
| `verification.json` | 量化指标（原子守恒、限定强度、否定、覆盖率） | 附计算命令与输出 |
| `human_review.md` | 需人工确认项、建议复核项、材料缺口（每条给选项） | 每条可直接决策 |

每个数字/引用/图表指向的 locator 形如 `{文件} → {段号/行号} → {字段}`；每条改动给逐字 quote。

## 7. 防扣分检查表（交付前逐项通过）

- [ ] 1 读取了实际输入文件，非假设内容。
- [ ] 2 解析了 task.md 的受众、文体、格式约束。
- [ ] 3 建立了术语表并全篇回扫。
- [ ] 4 逐句处理，非整段重写。
- [ ] 5 每条修改有原文、改文、类型、理由。
- [ ] 6 保留了所有限定词、数据、单位、引用编号、图表指向。
- [ ] 7 材料不足、冲突、需人工确认内容已明确标注。
- [ ] 8 输出了可编辑产物与 PDF/PNG 预览。
- [ ] 9 `result.json` 含全部 output_contract 字段与 case_id。
- [ ] 10 来源映射覆盖率 100%。
- [ ] 11 修改说明完整率 100%。
- [ ] 12 术语一致率 ≥ 98% 或冲突已标注。
- [ ] 13 限定词保持率 100%。
- [ ] 14 数据/单位保持率 100%。
- [ ] 15 编辑距离与操作数比值合理（D/E ≤ 2.5）。
- [ ] 16 预算内保存了中间产物与部分结果。
- [ ] 17 重复运行结论不漂移（确定性输出）。
- [ ] 18 对超长输入、编码混乱、公式混杂有识别与处置。
- [ ] 19 文档完整：SKILL、术语表、风格指南、示例、限制。
- [ ] 20 不伪造数据、不补造材料外事实。

任一项未过：状态记 `partial`，未决项写入不确定性，不静默提升为 `success`。

## 8. 完整虚构案例（自洽校验）

**输入**（英文摘要）：
`The study investigate the effect of nanoparticle size on cellular uptake. The results shows that smaller nanoparticles (10 nm) was uptake more efficiently than larger ones (100 nm). This may indicates that size play a key role. The uptake rate of 10 nm particles was 2.5 fold higher than 100 nm particles (p = 0.032). SEM and TEM images confirmed the size distribution. The data suggests that cellular uptake is caused by particle size.`

**关键中间量**：原文 98 词；E = 9；词级 D = 12；D/E = 1.33 ≤ 2.5；术语总出现 15、不一致 2、修正后 C_term = 100%；限定词原 1（may）保留 1，C_hedge = 100%；数据/单位 5 处（10、100、2.5、0.032、nm）全保留，C_data = 100%；说明 9 条全带定位，C_src = C_doc = 100%。

**输出（润色后）**：
`The study investigated the effect of nanoparticle size on cellular uptake. The results show that smaller nanoparticles (10 nm) were taken up more efficiently than larger ones (100 nm). This may indicate that size plays a key role. The uptake rate of 10 nm particles was 2.5-fold higher than 100 nm particles (p = 0.032). Scanning electron microscopy (SEM) and transmission electron microscopy (TEM) images confirmed the size distribution. The data suggest that cellular uptake is associated with particle size.`

**逐句说明（节选）**：

| 定位 | 原文 | 改文 | 类型 | 理由 |
|-|-|-|-|-|
| 摘要1 | investigate | investigated | 语法-时态 | 过去时 |
| 摘要2 | shows | show | 语法-主谓一致 | 主语 results 复数 |
| 摘要2 | was uptake | were taken up | 语法-语态/搭配 | 被动语态；take up 搭配 |
| 摘要3 | may indicates | may indicate | 语法-情态动词 | may 后接原形 |
| 摘要3 | play | plays | 语法-主谓一致 | 主语 size 单数 |
| 摘要4 | 2.5 fold | 2.5-fold | 格式-连字符 | 复合形容词需连字符 |
| 摘要5 | SEM and TEM | scanning electron microscopy (SEM) and transmission electron microscopy (TEM) | 术语-缩写首现定义 | 首现需全称 |
| 摘要6 | suggests | suggest | 语法-主谓一致 | data 复数 |
| 摘要6 | is caused by | is associated with | 语义保持-因果改相关 | 原研究仅显示关联 |

**复核**：词级 diff 输出 `ratio: 0.89`，opcodes 显示 9 处替换/插入；`p = 0.032` 逐字保留；因果被弱化为相关。所有数字、单位、引用编号与原文多重集相等。
