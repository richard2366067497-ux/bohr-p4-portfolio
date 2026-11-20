# 审查清单（五面 × 六维，可直接复用为人工 checklist）

用法：逐项问「材料里有没有、对不对、能不能复算」。**只有能落到原文位置的项才写进 findings**；
答不上来（材料没给、图表读不出）写 `unchecked_items`。每项后面标注通常对应的 `issue_type`。
本文件是随包可复用清单，与 `scripts/auditlib.py` 的 `FACETS`/`DIMENSIONS` 同源。

## A. 研究设计（facet `design_fit`）

- [ ] 设计类型与研究问题匹配吗？（疗效问题 → 对照试验；预后问题 → 队列；诊断 → 横断面/STARD）`design_mismatch`
- [ ] 有对照/比较组吗？对照是否同期、同条件、同入排标准？`design_mismatch`
- [ ] 分组方式：随机？怎么随机、分配隐藏做了吗？`design_mismatch`
- [ ] 盲法：谁被盲、盲到什么程度、主观终点是否盲？`design_mismatch`
- [ ] 主要终点是否唯一、事先明确？有无终点切换或事后挑选？`outcome_switching`
- [ ] 混杂是否识别并调整？按因果解释是否成立？`confounding`
- [ ] 注册号、伦理批号、知情同意（人体/动物）是否齐备？`registration_missing` / `ethics_missing`
- [ ] 结论强度是否超过设计支持的范围？`argument_gap`

## B. 变量定义（facet `variable_definition`）

- [ ] 暴露/干预的定义、剂量、时长、依从性判定标准 `variable_definition`
- [ ] 结局的定义、测量工具、时点、评分者与一致性（kappa/ICC）`outcome_measure_unclear`
- [ ] 协变量清单与纳入理由（是否数据驱动筛选）`variable_definition`
- [ ] 分类切点来源、连续变量是否被二分类及理由 `variable_definition` / `terminology_ambiguity`
- [ ] 单位与量纲前后一致、换算正确 `unit_conversion_error`
- [ ] 缺失值：比例、机制假设、处理方法 `variable_definition`
- [ ] 变量类型与模型匹配（连续/有序/分类、时依协变量）`model_variable_mismatch`

## C. 统计方法（facet `statistics`）

- [ ] 检验方法与数据结构匹配（组数、配对/独立、分布、方差齐性）`test_misuse`
- [ ] 前提假设是否检验/说明（正态性、等方差、比例风险、线性）`assumption_unchecked`
- [ ] 独立性：重复测量、聚类、中心效应是否用相应模型 `independence_violation`
- [ ] 多重比较：多组、多终点、多亚组是否校正，方法是否说明 `multiple_comparison_uncorrected`
- [ ] 交互与亚组：是否预设、是否只作探索性解释 `argument_gap`
- [ ] 敏感性分析：缺失值、离群值、模型设定、不同分析集 `sensitivity_analysis_missing`
- [ ] 分析集定义（ITT/mITT/PP）与主分析是否一致 `attrition_missing`

## D. 样本量与效能（facet `sample_size`）

- [ ] 有事前样本量估算吗？α、把握度、效应量来源、最小临床重要差值 `sample_size_unjustified`
- [ ] 实际入组 vs 估算：达标了吗？不足时如何影响结论 `sample_size_unjustified`
- [ ] 是否声称「效能足够」或做事后效能计算 `power_claim`
- [ ] 失访/退出/剔除：人数、原因、时点、是否与结局相关 `attrition_missing`
- [ ] 流程图与正文人数是否一致 `reporting_gap` / `internal_inconsistency`

## E. 结果报告（facet `reporting`）

- [ ] 每个主要/次要结果：效应量 + 95% CI 齐备 `effect_size_missing` / `ci_missing`
- [ ] 精确 p 值（非 p<0.05）、统计量与自由度 `p_reporting`
- [ ] 摘要、正文、表格、图之间的 n、均值、p、方向一致 `internal_inconsistency`
- [ ] 表格有单位、有组别、有缺失说明；图有误差条定义 `reporting_gap`
- [ ] 对应报告规范条目逐项覆盖 `reporting_gap`
- [ ] 讨论中的比较性论断有引用支持 `citation_support_missing`
- [ ] 利益冲突、资金、作者贡献、数据可得性 `norm_deviation` / `data_availability_missing`

## 六类审查面的默认归属（finding.dimension）

| dimension | 覆盖上面哪些项 | 说明 |
|---|---|---|
| `fact` | 数值一致性、单位换算、与自身数据冲突 | 能对账的硬事实 |
| `citation` | 引用是否支持该句、关键论断有无引用 | 只判「引用与论断是否对得上」 |
| `method` | A/B/C/D 的大部分 | 设计与统计推断的成立性 |
| `stat_report` | E 的数值报告、失访流程 | 报告完整性与可复核性 |
| `argument` | 结论强度、因果措辞、亚组解释、术语歧义 | 论证链是否闭合 |
| `norm` | 注册、伦理、数据可得性、利益冲突 | 学术规范条目 |

## 自检（提交前）

- [ ] 五个面都有判定（`ok` 或 `gap`），不是靠「没问题」跳过
- [ ] 每条 finding 的 `quote` 能在材料中逐字找到
- [ ] `underreporting` 没有写成 `critical`（受 `NATURE_CAP` 封顶）
- [ ] `severity_reason` 说了为什么不是相邻级别
- [ ] `unchecked_items` 写清了没检查什么、为什么
- [ ] 报告中问题数 ≠ 审出多少，而是「每条都能落回原文」
