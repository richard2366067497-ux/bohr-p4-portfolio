# 要求目录：33 条可核对要求 × 需求来源 × 检索词

本文件是 `scripts/rules.py` 中 `CAT` 与 `DECL` 的**人类可读镜像**（`rule_version = acm-1.0.0`）。矩阵的 33 行种子从这里生成；改目录必须同时改 `rules.py` 并升版本号。

**目录只写"要求内容 + 检索词 + 依据类型"，不收录条款号、期刊字数上限、DOI 等具体元数据**。这些必须来自用户材料或用户提供的官方原文，否则该行只能判 `unverifiable`。

## 1. 依据类型（`rule_source`）与其判定权限

| 类型 | 判 violation 的前提 | 典型来源 |
|---|---|---|
| `ethical_norm` | 要求是通行学术伦理的一部分（署名、诚信、隐私、知情同意、动物福利） | ICMJE / COPE / 赫尔辛基宣言所体现的通则，**写要求内容，不写条款号** |
| `venue_guideline` | **材料内**有该作者指南文本 | 目标期刊 Guide for Authors、会议 CFP 附件 |
| `provided_policy` | **材料内**有该政策文本 | 数据使用协议、单位科研规范、基金结题要求 |
| `general_practice` | 只能判 minor/suggestion | 领域惯例（编号连续、元数据齐全、格式统一） |
| `internal_consistency` | 材料两处互相矛盾，两侧都有 locator | 摘要 n 与表格 n 不一致、基金号前后不同 |

## 2. 六个方向的 24 条要求

### 2.1 学术诚信 `integrity`

| row_id | 要求 | 检索词（`init` 已内置） | 依据 |
|---|---|---|---|
| INT-01 | 复用/改编他人数据或图像时在正文或图注声明来源 | adapted from, reproduced from/with, previously published, 改编, 转载, 引自…文献 | ethical_norm |
| INT-02 | 若已有会议版/预印本，应交叉引用并说明增量 | preprint, conference version, extended version, 预印本, 会议版, arXiv | general_practice |
| INT-03 | 作者列表与作者贡献/致谢的角色分配一致 | author contributions, CRediT, contributed equally, 作者贡献, 共同一作 | general_practice |
| INT-04 | 基金编号与项目名在正文、致谢、声明区块一致 | grant/fund/project/NSF/NIH + 编号, 基金, 项目编号, 资助 | internal_consistency |

图像复用的可判定写法：`observed` 里写清"图 3 与图 1 像素级相似/同一实验条件重复出现"这类**可核对观察**，而不是"疑似重复"。判不出就 `unverifiable` + "需比对原始高分辨率图与作者提供的原始数据"。

### 2.2 引用规范 `citation_norm`

| row_id | 要求 | 检索词 | 依据 |
|---|---|---|---|
| CITE-01 | 正文每个引用标记都能在文献表找到条目（无悬空） | `[n]`、`（Author, 2020）` | general_practice |
| CITE-02 | 文献表条目均被正文引用（无凑数条目） | — | general_practice |
| CITE-03 | 编号连续、无重复、与首次出现顺序一致 | `[n]` | internal_consistency |
| CITE-04 | 正文论断与所引文献内容对应（无引而不证/张冠李戴） | `[n]`, et al., 等. | general_practice |
| CITE-05 | 条目元数据完整（作者/年/题名/出处/卷期页或 DOI）且格式统一 | doi, vol., pp., 年;卷 | general_practice |
| CITE-06 | 被引文献真实存在且元数据与原文一致 | — | general_practice |

- `init` 直接给出 `dangling` / `orphan` / `duplicate` / `gaps`，CITE-01/02/03 通常可以确定性判定。
- **CITE-06 在离线环境永远 `unverifiable`**：写清"需核对的 DOI/PMID 与要核对的字段"，不要声称"文献真实"或"文献不存在"。
- CITE-04 判 `violation` 需要同时给正文论断和条目内容两侧证据；只凭标题不符就下结论容易误报，拿不准就 `unverifiable`。

### 2.3 隐私与数据合规 `privacy`

| row_id | 要求 | 检索词 | 依据 |
|---|---|---|---|
| PRIV-01 | 可识别个人信息最小化并脱敏（示例值用占位符） | 邮箱、手机号、18 位证件号、患者/受试者编号 | ethical_norm |
| PRIV-02 | 受限/未公开数据说明授权范围与使用条件 | data use agreement, restricted, under license, 授权, 受限数据 | ethical_norm |
| PRIV-03 | 涉及人的数据同时具备伦理审批与知情同意依据（与 ETH 行交叉核对） | ethics, IRB, consent, 伦理, 知情同意 | ethical_norm |

判断口径：**公开材料里出现真实邮箱/身份证号/患者编号 = PRIV-01 violation（major）**；出现在"示例数据"且明显为占位（`[GOVERNED_CONTENT:gcr_CdnmADZoP90Ig6WSkZyBJEmDztCfFqxL]`、`XXXX`）= `compliant` 或 `not_applicable`，并说明理由。台账只记位置与类型，报告渲染时自动遮罩。

### 2.4 版权与许可 `copyright`

| row_id | 要求 | 检索词 | 依据 |
|---|---|---|---|
| COPY-01 | 第三方图片/表格标注来源与许可（adapted/reproduced + permission 或 CC） | CC-BY, creative commons, copyright, permission, 版权, 许可协议 | general_practice |
| COPY-02 | 代码/数据集许可声明与实际可用性一致 | github.com, zenodo, figshare, MIT/Apache/GPL, 代码可用, 数据可用 | general_practice |
| COPY-03 | 超出合理使用范围时补授权或替换（材料内无法确认则待复核） | adapted from, reprinted, with permission, 转载, 改编 | general_practice |

许可范围（"CC-BY-NC 是否允许本用途"）属于需要原文与用途判断的事项：**默认 `unverifiable`**，写明"需核对许可版本与用途是否构成商业使用"。

### 2.5 伦理审查 `ethics`

| row_id | 要求 | 检索词 | 依据 |
|---|---|---|---|
| ETH-01 | 涉及人的研究给出伦理批件编号、批准机构、覆盖范围 | IRB/Ethics + No./编号/approval, approved by, 伦理委员会 | ethical_norm |
| ETH-02 | 说明知情同意的获取方式（书面/口头/豁免及理由） | informed consent, 知情同意, consent was obtained/waived | ethical_norm |
| ETH-03 | 动物实验说明伦理审批与福利措施（无动物实验须显式说明不适用） | animal, mice/mouse/rat, 动物, 3R, IACUC | ethical_norm |
| ETH-04 | 风险/获益表述与实际设计、样本量相符 | risk, benefit, 风险, 获益, 安全性 | internal_consistency |

- **批件编号只能引用原文出现的字符串**：写"批件号 2021-045"而原文没有 → `invented_identifier` 错误。
- 纯计算/文献研究：ETH-01/02/03 写 `not_applicable` + `searched_scope`（"检索 Methods 与声明区块，无 human subjects/animal/IRB 相关表述"）。

### 2.6 投稿要求 `venue`

| row_id | 要求 | 检索词 | 依据 |
|---|---|---|---|
| VEN-01 | 材料包含目标期刊/会议作者指南 | instructions for authors, guide for authors, 投稿要求, 征稿, CFP | venue_guideline |
| VEN-02 | 篇幅/字数/图表/参考文献数量符合指南上限 | word limit, 字数, maximum of N, no more than N | venue_guideline |
| VEN-03 | 结构要素（摘要/关键词/声明区块/补充材料）符合指南 | structured abstract, keywords, supplementary material, 关键词 | venue_guideline |
| VEN-04 | 所依据指南的版本与生效日期注明 | version, 版本, effective 20XX | venue_guideline |

**没有指南文本时这四行全部 `unverifiable`**，`what_human_must_check` 写"需用户提供目标期刊 Guide for Authors（版本/日期），再逐条映射字数、图表数、声明区块"。这是本 Skill 最容易踩的编造点：不要凭"大多数期刊要求"下结论。

## 3. 九项声明区块 `declaration`（DEC-01…DEC-09）

| row_id | 区块 | 检索词 | 三态判定要点 |
|---|---|---|---|
| DEC-01 | 基金声明 | funding, grant, supported by, 基金, 资助 | 有声明但编号与首页不同 → `inconsistent`（两侧 locator） |
| DEC-02 | 致谢 | acknowledg, 致谢, authors thank | 致谢里的资助与基金声明冲突 → `inconsistent` |
| DEC-03 | 作者贡献 | author contributions, CRediT, 作者贡献 | 贡献角色与作者列表人数不符 → `inconsistent` |
| DEC-04 | 利益冲突（COI） | conflict of interest, competing interests, 利益冲突 | 只在投稿信模板出现、正文无声明 → `violation` |
| DEC-05 | 数据可用性 | data availability, data are available, 数据可用 | "可向作者索取"但无联系人/仓库 → `minor` |
| DEC-06 | 伦理批件 | ethics approval/committee, IRB, 伦理批件 | 无人类受试者 → `not_applicable` + `searched_scope` |
| DEC-07 | 知情同意 | informed consent, 知情同意 | 涉及人的数据但无同意说明 → `violation` |
| DEC-08 | 代码可用性 | code available, github.com, 代码可用 | 声称开源但无仓库/许可 → `minor` |
| DEC-09 | 版权许可 | copyright, license, 版权, 许可协议 | 转载他人图但无许可说明 → 与 COPY-01 交叉引用 |

三态：`found`（给 locator + 逐字片段）/ `missing`（给 `searched_scope`）/ `inconsistent`（给两侧 locator）。**每项都必须有成行**，`not_applicable` 也要显式写出并给检索范围。

## 4. 误报抑制表（判"不算问题"的标准）

| 现象 | 不是违规的理由 | 应写成 |
|---|---|---|
| 单栏排版、英式/美式拼写混用、图注长短不一 | 排版与语言风格，与学术规范无关 | 不建行，或 `compliant` |
| `et al.` 数量与某期刊习惯不同 | 属指南细节，且材料无指南 | `unverifiable`（VEN-03 行内说明） |
| 合作作者贡献只写"共同完成" | 若指南未要求细粒度 CRediT，属作者取舍 | `compliant` 或 `suggestion` |
| 未公开原始数据，但写了"因隐私/伦理限制不公开" | 这正是合规做法 | `compliant`（DEC-05） |
| 正文 n 与表格 n 不同但已说明缺失值剔除 | 内部自洽 | 不建 INT 行 |
| 文献表缺 DOI（年代较早的条目） | 常见且不一定违反指南 | `suggestion` |
| 图片来自作者自己先前论文并已声明 | 已声明即合规 | `compliant`（INT-01） |

## 5. 反编造清单（写进报告前自查）

1. 有没有写出材料里不存在的条款号（GB/T、ICMJE 第几条第几款）？
2. 有没有声称"该刊要求 ≤XXXX 词"，而输入里没有指南？
3. 有没有给出 DOI、作者、年份、卷期页等材料中没有的文献元数据？
4. 有没有引用伦理批件号、基金号，而原文没有？
5. 有没有把"离线无法核实"写成结论（"文献不存在"/"文献真实"）？
6. `quote` 是否真的来自 `show` 的输出（而不是记忆或改写）？

任一条为"是"，就把该行降级为 `unverifiable` 并写清人工核对路径——**这比编造一条更得分**。
