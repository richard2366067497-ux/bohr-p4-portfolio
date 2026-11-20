# 缺陷类型库与严重度锚点（可复用；与 `scripts/auditlib.py` 的 `BUILTIN_ISSUES`/`BUILTIN_CAPS` 同源）

把本文件放进 `materials/` 后，`scripts/auditlib.py` 的 `parse_library` 会逐行解析下面的两张表；
解析失败才退到内置库。行格式必须保持：`| \`issue_type\` | 含义 | facet / dimension / 允许性质 |`。

## 1. 缺陷性质与严重度上限

| `defect_nature` | 判据 | 严重度上限 |
|---|---|---|
| `method_flaw` | 写了做法但做法本身错 | `critical` |
| `underreporting` | 没有报告该报告的要素 | `major` |
| `acceptable_but_should_clarify` | 做法可接受但表述需澄清 | `minor` |
| `no_defect` | 该面无缺陷 | `no_defect` |

**硬规则**：`underreporting` 的 severity 超过 `major` 会被脚本自动降级并在 `change_log.json` 记录；
`acceptable_but_should_clarify` 超过 `minor` 同理。这不是惩罚，而是让「缺报告」与「方法错」各自归位。

## 2. issue_type 表（28 项）

| issue_type | 含义 | 默认面 / 维度 / 允许性质 |
|---|---|---|
| `test_misuse` | 检验方法与数据结构不匹配（三组用两两 t、等级资料用 t、配对数据用独立样本、比例用卡方但期望频数过小） | statistics / method / method_flaw |
| `assumption_unchecked` | 前提假设未检验或违反后未处理（正态性、方差齐性、比例风险、线性） | statistics / method / method_flaw, underreporting |
| `independence_violation` | 重复测量、聚类、配对、同一受试多次观测被当作独立样本 | statistics / method / method_flaw |
| `multiple_comparison_uncorrected` | 多组/多终点/多亚组比较未校正或校正方法未说明 | statistics / method / method_flaw, underreporting |
| `sensitivity_analysis_missing` | 缺失值处理、离群值、模型设定无敏感性分析 | statistics / method / underreporting, acceptable_but_should_clarify |
| `model_variable_mismatch` | 变量类型与模型不符（连续变量当分类、分类当连续、时依协变量入 Cox） | variable_definition / method / method_flaw |
| `variable_definition` | 暴露/结局/协变量定义、测量方式、切点、编码、缺失值规则缺失或不一致 | variable_definition / method / underreporting, acceptable_but_should_clarify |
| `outcome_measure_unclear` | 结局测量工具、时点、评分者与一致性未交代 | variable_definition / method / underreporting, acceptable_but_should_clarify |
| `unit_conversion_error` | 单位、量纲、换算错误或前后不一致 | variable_definition / fact / method_flaw |
| `terminology_ambiguity` | 术语/缩写前后不一致或未定义，导致无法判断所指变量 | variable_definition / argument / acceptable_but_should_clarify |
| `design_mismatch` | 设计类型回答不了研究问题（无对照、无时间先后、组间不可比、盲法缺失影响主观终点） | design_fit / method / method_flaw |
| `confounding` | 关键混杂未测量或未调整，却按因果解释 | design_fit / method / method_flaw |
| `outcome_switching` | 主要终点不明确、多个主要终点、注册与报告不一致 | design_fit / method / method_flaw |
| `argument_gap` | 结论强度超过数据支持（相关说因果、亚组当结论） | design_fit / argument / method_flaw, acceptable_but_should_clarify |
| `registration_missing` | 试验/系统评价未报告前瞻性注册 | design_fit / norm / underreporting |
| `sample_size_unjustified` | 无事前样本量估算，或无效应量来源/α/把握度 | sample_size / method / underreporting, acceptable_but_should_clarify |
| `power_claim` | 声称有足够把握度/效能但无计算依据，或事后效能计算 | sample_size / method / method_flaw, underreporting |
| `attrition_missing` | 失访、退出、剔除的人数与原因、分析集（ITT/PP）未交代 | sample_size / stat_report / underreporting |
| `effect_size_missing` | 只报 p，不报效应量 | reporting / stat_report / underreporting |
| `ci_missing` | 不报置信区间（尤其主要终点） | reporting / stat_report / underreporting |
| `p_reporting` | 只写 p<0.05 / p=NS，无精确 p、无统计量与自由度 | reporting / stat_report / underreporting, acceptable_but_should_clarify |
| `internal_inconsistency` | 摘要、正文、表格、图之间的数值/样本量/方向不一致 | reporting / fact / method_flaw |
| `factual_error` | 与稿件自身数据或公认事实冲突的陈述 | reporting / fact / method_flaw |
| `reporting_gap` | 报告规范要求的条目缺失（如 CONSORT 流程图、STROBE 亚组说明） | reporting / stat_report / underreporting, acceptable_but_should_clarify |
| `citation_support_missing` | 关键论断无引用，或引用不支持该句 | reporting / citation / underreporting, method_flaw, acceptable_but_should_clarify |
| `norm_deviation` | 学术规范条目缺失或不一致（伦理批号、知情同意、利益冲突、作者贡献、数据可得性表述含糊） | reporting / norm / underreporting, acceptable_but_should_clarify |
| `data_availability_missing` | 无数据可得性声明或声明无法执行 | reporting / norm / underreporting |
| `ethics_missing` | 无伦理审批/知情同意说明（涉及人体或动物时） | design_fit / norm / underreporting |

## 3. 严重度锚点

判定顺序：**先看它是否改变结论或使结论不可复核，再看它是否属于「未报告」**。

| 级别 | 锚点（满足其一） | 例 |
|---|---|---|
| `critical` | 主要终点结论不成立；假设被严重违反且未处理；数值自相矛盾达主要结论；设计无法支持因果结论 | 未校正多重比较后唯一的 p=0.049 支撑结论；配对数据按独立样本检验 |
| `major` | 结论方向可能不变，但精度/可信度无法评估；关键方法信息缺失使复核不可能 | 主要终点无 CI 与效应量；三臂用两两 t；样本量依据缺失 |
| `minor` | 影响局部解释或二次结果，不影响主要结论；规范条目缺失但不改变可信度 | 次要终点无效应量；自定义切点无来源 |
| `suggestion` | 报告更清晰的建议，可采纳也可说明 | 建议补流程图、统一小数位、报告软件版本 |
| `no_defect` | 无缺陷 | — |

`severity_reason` 必须写出**为什么不是上一级/下一级**，否则复核人无法判断你是否只是随手定级。
