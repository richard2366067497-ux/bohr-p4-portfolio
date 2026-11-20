# 统计审查规则与字段字典（合并参考：draft schema / 台账与严重度 / 审查清单）



---

## 来源：draft_schema.md

# draft.json 字段字典（工作稿）

工作稿路径：`/app/work/draft.json`。骨架由 `python3 scripts/main.py init` 生成在
`/app/work/draft_skeleton.json`，复制后逐行填判定即可。**脚本只读 draft.json，不读 skeleton。**

```json
{
  "case_id": "与 /input/case.json 一致，或省略（脚本取 init 派生的 id）",
  "manuscript_meta": {
    "title": "稿件标题（原文照抄，未知 null）",
    "design_type": "如 三臂随机对照试验 / 回顾性队列 / 横断面调查（未报告盲法可写在括号里）",
    "field": "学科领域",
    "target_guideline": "CONSORT / STROBE / PRISMA / STARD / TREND / ARRIVE（按设计类型选，不适用写 null）",
    "n_reported": "随机数 / 分析集，如 \"90 randomized / 78 analyzed\""
  },
  "statistics_ledger": [ /* 见下，一行 = 一个被报告的结果或检验 */ ],
  "extra_findings": [ /* 台账覆盖不到的发现：设计、变量、规范、引用类 */ ],
  "unchecked_items": [{"item": "Figure 2", "reason": "图片无数据，无法核对"}],
  "uncertainties": ["未提供原始数据，无法重算检验"],
  "summary": "3~5 句：覆盖范围 + 最严重问题 + 未核实部分"
}
```

## 1. statistics_ledger 行

| 字段 | 类型 | 要求 |
|---|---|---|
| `ledger_id` | str | `L-01` 起顺延；`init` 给的候选行沿用其 id，补行继续编号 |
| `result_question` | str | 这一行结果回答什么（如「12 周 TUG 变化的组间差异（主要终点）」） |
| `comparison` | str | 谁和谁比（「三臂两两比较」「训练组 vs 对照」） |
| `n` | str | 报告的分析样本量；分析集与随机数不同时都写 |
| `test_declared` | str | 稿件**声明**的检验（「independent-samples t test」「mixed model」） |
| `test_appropriate` | `"true"`/`"false"`/`"unknown"` | 检验与数据结构、分布、独立性是否匹配；判不了写 `unknown` |
| `assumptions` | obj | `normality`/`variance`/`independence`，取值 `checked`/`violated`/`not_reported`/`n/a` |
| `statistic` `df` `p` | str | 原文报告值，**照抄**；没写填 `"not_reported"`，不重算 |
| `effect_size` `ci` | str | 同上；只报 p 值时填 `"not_reported"` |
| `multiple_comparison` | str | `corrected`/`uncorrected`/`not_reported`/`n/a` |
| `sample_size_basis` | str | 事前估算依据（效应量来源、α、把握度）；缺失填 `"not_reported"` |
| `attrition` | str | 失访/退出/剔除的人数与处理方式；缺失填 `"not_reported"` |
| `source_locator` | str | 定位串，必须能在材料中找到（`manuscript:§Results/L21`、`paper:p3`） |
| `quote` | str | **逐字**原文，≥8 字符；脚本按 NFKC + 空白折叠做包含匹配，找不到即 `evidence_rejected` |
| `cell_status` | obj | 五个检查面（`design_fit`/`variable_definition`/`statistics`/`sample_size`/`reporting`），取值 `ok`/`gap`/`na`；`na` 用于该行确实不涉及的检查面 |
| `defect_nature` | 枚举 | `method_flaw`/`underreporting`/`acceptable_but_should_clarify`/`none`，定义见 `ledger_and_severity.md` |
| `severity` | 枚举 | `critical`/`major`/`minor`/`suggestion`/`none`；受性质封顶 |
| `severity_reason` | str | 为什么是这个级别：缺陷如何影响结论、为什么不是更高/更低一级 |
| `issue_type` | 枚举 | 见 `ledger_and_severity.md` 的 28 项表 |
| `recommendation` | str | 作者可执行的修改动作（补什么、改成什么、怎么报告） |

`defect_nature = "none"` 的行不派生 finding，但仍参与覆盖统计——**判 ok 也要写 cell_status**。

## 2. extra_findings 条目

台账只能覆盖"被报告的结果"。以下问题没有对应结果行，写 `extra_findings`：

| 字段 | 要求 |
|---|---|
| `facet` | 五面之一（与 `issue_type` 默认面不一致时以此为准） |
| `dimension` | `fact`/`citation`/`method`/`stat_report`/`argument`/`norm` |
| `issue_type` / `defect_nature` / `severity` / `severity_reason` | 同台账行规则 |
| `title` | ≤40 字的问题名（报告里作小标题） |
| `source_locator` + `quote` | 必备；`severity ≥ minor` 时缺 quote 直接判 `missing_quote` |
| `recommendation` | 可执行修改动作 |

典型用途：无对照/无盲法的设计缺陷（`design_mismatch`）、切点无来源（`variable_definition`）、
未注册/无伦理号/无数据可得性声明（`registration_missing`/`ethics_missing`/`data_availability_missing`）、
讨论里的比较性结论无引用（`citation_support_missing`）。

## 3. 填写纪律

1. **照抄 vs 判断分开**：`statistic`/`p`/`ci`/`n` 只抄原文；`test_appropriate`/`defect_nature`/`severity` 才是你的判断。
2. **未报告不写 0**：没报告就写 `not_reported`，不要写 `0` 或空串以外的猜测值。
3. **一问题一条目**：同一句里既有"检验不匹配"又有"缺 CI"，倾向拆成两行/两条（不同性质、不同严重度）。
4. **quote 不许改写**：无法逐字引用 → 该条降级为 `unchecked_items`，不要凑。
5. **不编造案例事实**：不确定是否报告了某事，就写 `unknown`/`not_reported` 并进 `uncertainties`。

## 4. 最小示例（示例，非正式案例）

```json
{"case_id": "demo-001",
 "manuscript_meta": {"title": "…", "design_type": "三臂 RCT", "field": "康复", "target_guideline": "CONSORT", "n_reported": "90/78"},
 "statistics_ledger": [
   {"ledger_id": "L-01", "result_question": "主要终点组间差异", "comparison": "三臂两两", "n": "78",
    "test_declared": "independent-samples t test", "test_appropriate": "false",
    "assumptions": {"normality": "not_reported", "variance": "not_reported", "independence": "checked"},
    "statistic": "t = 2.31", "df": "58", "p": "0.03", "effect_size": "not_reported", "ci": "not_reported",
    "multiple_comparison": "not_reported", "sample_size_basis": "not_reported", "attrition": "12 例随机后剔除",
    "source_locator": "manuscript:§3.1/L19",
    "quote": "The primary outcome differed significantly (t(58) = 2.31, p = 0.03).",
    "cell_status": {"design_fit": "ok", "variable_definition": "na", "statistics": "gap", "sample_size": "gap", "reporting": "gap"},
    "defect_nature": "method_flaw", "severity": "major", "issue_type": "multiple_comparison_uncorrected",
    "severity_reason": "三臂做三次未校正 t 检验抬高 I 类错误；终点与分组明确、数据独立，故 major。",
    "recommendation": "改用单因素方差分析 + Tukey/Holm 校正的两两比较，报告校正后 p 与效应量。"}
 ],
 "extra_findings": [], "unchecked_items": [], "uncertainties": [], "summary": "…"}
```


---

## 来源：ledger_and_severity.md

# 判定规则：缺陷性质、issue_type、严重度锚点、覆盖口径

本文件是脚本内规则的说明版。脚本中的枚举与兼容表与本文一致；改规则须同时改
`scripts/ledger.py` 的 `ISSUE_META` / `NATURE_CAP` 与本文件。

## 1. 缺陷性质三态（本题最关键的区分）

| `defect_nature` | 判据（满足即归此类） | 严重度上限 | 常见错判 |
|---|---|---|---|
| `method_flaw` | 稿件**写了**做法，但做法本身错：检验与数据结构不匹配、把重复测量当独立、多重比较未校正、变量编码与模型冲突、单位/换算错误、文内数值自相矛盾、按因果解释非随机比较 | `critical` | 把"未报告"写成这一类（最常被扣分） |
| `underreporting` | 作者**没有报告**该报告的要素，因此无法判断或无法复算：无效应量、无 CI、无精确 p 与 df、无样本量依据、无失访流程、无注册号 | `major` | 因为"很重要"就判 `critical`；把缺失当成"做错" |
| `acceptable_but_should_clarify` | 做法可接受，但表述/边界需澄清：自定义切点未给来源、术语定义含糊、报告规范里属"推荐项"的条目缺失、把连续变量二分类但理由未说明 | `minor` | 把可接受做法判成硬伤 |
| `none` | 该行该面无缺陷（`cell_status` 全 `ok` 时用） | `none` | 为凑条数写无关问题 |

**硬规则**：`underreporting` 的 `severity` 超过 `major` 会被脚本自动降级并在 `result.json.changes`
记录 `severity_capped_by_nature`；`acceptable_but_should_clarify` 超过 `minor` 同理。
这不是惩罚，而是让"缺报告"和"方法错"在评分上各自归位。

## 2. issue_type 表（28 项，括号内为默认检查面 / 审查维度 / 允许的性质）

| issue_type | 含义 | 默认面 / 维度 / 允许性质 |
|---|---|---|
| `test_misuse` | 检验方法与数据结构不匹配（三组用两两 t、等级资料用 t、配对数据用独立样本、比例用卡方但期望频数过小） | statistics / method / method_flaw |
| `assumption_unchecked` | 前提假设未检验或违反后未处理（正态性、方差齐性、比例风险、线性） | statistics / method / method_flaw, underreporting |
| `independence_violation` | 重复测量、聚类、配对、同一受试多次观测被当作独立样本 | statistics / method / method_flaw |
| `multiple_comparison_uncorrected` | 多组/多终点/多亚组比较未校正或校正方法未说明 | statistics / method / method_flaw, underreporting |
| `sensitivity_analysis_missing` | 缺失值处理、离群值、模型设定无敏感性分析 | statistics / method / underreporting, acceptable |
| `model_variable_mismatch` | 变量类型与模型不符（连续变量当分类、分类当连续、时依协变量入 Cox） | variable_definition / method / method_flaw |
| `variable_definition` | 暴露/结局/协变量定义、测量方式、切点、编码、缺失值规则缺失或不一致 | variable_definition / method / underreporting, acceptable |
| `outcome_measure_unclear` | 结局测量工具、时点、评分者与一致性未交代 | variable_definition / method / underreporting, acceptable |
| `unit_conversion_error` | 单位、量纲、换算错误或前后不一致 | variable_definition / fact / method_flaw |
| `terminology_ambiguity` | 术语/缩写前后不一致或未定义，导致无法判断所指变量 | variable_definition / argument / acceptable |
| `design_mismatch` | 设计类型回答不了研究问题（无对照、无时间先后、组间不可比、盲法缺失影响主观终点） | design_fit / method / method_flaw |
| `confounding` | 关键混杂未测量或未调整，却按因果解释 | design_fit / method / method_flaw |
| `outcome_switching` | 主要终点不明确、多个主要终点、注册与报告不一致 | design_fit / method / method_flaw |
| `argument_gap` | 结论强度超过数据支持（相关说因果、亚组当结论） | design_fit / argument / method_flaw, acceptable |
| `registration_missing` | 试验/系统评价未报告前瞻性注册 | design_fit / norm / underreporting |
| `sample_size_unjustified` | 无事前样本量估算，或无效应量来源/α/把握度 | sample_size / method / underreporting, acceptable |
| `power_claim` | 声称有足够把握度/效能但无计算依据，或事后效能计算 | sample_size / method / method_flaw, underreporting |
| `attrition_missing` | 失访、退出、剔除的人数与原因、分析集（ITT/PP）未交代 | sample_size / stat_report / underreporting |
| `effect_size_missing` | 只报 p，不报效应量 | reporting / stat_report / underreporting |
| `ci_missing` | 不报置信区间（尤其主要终点） | reporting / stat_report / underreporting |
| `p_reporting` | 只写 p<0.05 / p=NS，无精确 p、无统计量与自由度 | reporting / stat_report / underreporting, acceptable |
| `internal_inconsistency` | 摘要、正文、表格、图之间的数值/样本量/方向不一致 | reporting / fact / method_flaw |
| `factual_error` | 与稿件自身数据或公认事实冲突的陈述 | reporting / fact / method_flaw |
| `reporting_gap` | 报告规范要求的条目缺失（如 CONSORT 流程图、STROBE 亚组说明） | reporting / stat_report / underreporting, acceptable |
| `citation_support_missing` | 关键论断无引用，或引用不支持该句 | reporting / citation / underreporting, method_flaw, acceptable |
| `norm_deviation` | 学术规范条目缺失或不一致（伦理批号、知情同意、利益冲突、作者贡献、数据可得性表述含糊） | reporting / norm / underreporting, acceptable |
| `data_availability_missing` | 无数据可得性声明或声明无法执行 | reporting / norm / underreporting |
| `ethics_missing` | 无伦理审批/知情同意说明（涉及人体或动物时） | design_fit / norm / underreporting |

`issue_type` 越界或与 `defect_nature` 不兼容 → `check` 报 `unknown_issue_type` / `defect_nature_mismatch`。

## 3. 严重度锚点

判定顺序：**先看它是否改变结论或使结论不可复核，再看它是否属于"未报告"**。

| 级别 | 锚点（满足其一） | 例 |
|---|---|---|
| `critical` | 主要终点的统计结论不成立；假设被严重违反且未处理；文内数值自相矛盾达主要结论；设计无法支持所作因果结论 | 主要终点用未校正的多重比较后唯一的 p=0.049 支撑结论；配对数据按独立样本检验；摘要与表格的 n 或方向相反 |
| `major` | 结论方向可能不变，但主要结果的精度/可信度无法评估；关键方法信息缺失使复核不可能；多组比较仅部分校正 | 主要终点无 CI 与效应量；三臂比较用两两 t 检验；样本量依据缺失；失访流程缺失 |
| `minor` | 影响局部解释或二次结果，不影响主要结论；规范条目缺失但不改变可信度 | 次要终点无效应量；自定义切点无来源；未报精确 p 与 df |
| `suggestion` | 报告更清晰的建议，作者可采纳也可说明；不影响判断 | 建议补流程图、建议统一小数位、建议报告软件版本 |
| `none` | 无缺陷 | — |

`severity_reason` 必须写出**为什么不是上一级/下一级**，否则复核人无法判断你是否只是随手定级。

## 4. 覆盖口径（coverage.json 怎么算）

- **五个检查面**：`cell_status` 有 `ok` 或 `gap` 即算"已判定"；某面无任何已判定行、且无关联 finding
  → 进 `missing_facets`，并在 `unchecked_items` 写明"该面未检查（不等于无缺陷）"。
- **六类审查面**：由 findings 的 `dimension` 计数；零命中的维度进 `dimensions_missing`。
- **不许刷覆盖**：给某面写一个 `ok` 需要有对应台账行；给某面补一条 finding 需要有逐字 quote。
  覆盖率是"审过什么"的记录，不是得分指标。

## 5. 复核与确定性

1. 同一输入 + 同一 `draft.json` 两次 `build`，`result.json` 与 `findings.json` 应完全一致（脚本内无随机、无
   时间戳；时间只写 `run_manifest.json`）。
2. 复核人取任一 finding：按其 `source_locator` 打开材料，`quote` 应逐字出现（允许 NFKC/空白折叠差异）。
3. 复核人按 `ledger_id` 回查 `statistics_ledger.json`，核对 `cell_status` 与 `defect_nature` 是否自洽：
   全 `ok` 的行不应有 `defect_nature != none`；有 `gap` 的行应有对应性质。
4. `changes` 记录所有被脚本改写的判定（严重度封顶），复核人据此区分"Agent 原判"与"规则修正"。


---

## 来源：review_checklist.md

# 审查清单（五面 × 六维，可直接复用为人工 checklist）

用法：逐项问"稿件里有没有、对不对、能不能复算"。**只有能落到原文位置的项才写进 findings**；
答不上来（材料没给、图表读不出）写 `unchecked_items`。每项后面标注通常对应的 `issue_type`。

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
- [ ] 分类切点来源（先验/文献/数据驱动）、连续变量是否被二分类及理由 `variable_definition` / `terminology_ambiguity`
- [ ] 单位与量纲前后一致、换算正确 `unit_conversion_error`
- [ ] 缺失值：比例、机制假设、处理方法（完整案例分析/多重插补）`variable_definition`
- [ ] 变量类型与模型匹配（连续/有序/分类、时依协变量）`model_variable_mismatch`

## C. 统计方法（facet `statistics`）

- [ ] 检验方法与数据结构匹配（组数、配对/独立、分布、方差齐性）`test_misuse`
- [ ] 前提假设是否检验/说明（正态性、等方差、比例风险、线性）`assumption_unchecked`
- [ ] 独立性：重复测量、聚类、中心效应是否用相应模型（混合模型/GEE/稳健方差）`independence_violation`
- [ ] 多重比较：多组、多终点、多亚组、中期分析是否校正，方法是否说明 `multiple_comparison_uncorrected`
- [ ] 交互与亚组：是否预设、是否只作探索性解释 `argument_gap`
- [ ] 敏感性分析：缺失值、离群值、模型设定、不同分析集 `sensitivity_analysis_missing`
- [ ] 分析集定义（ITT/mITT/PP）与主分析是否一致 `attrition_missing`

## D. 样本量与效能（facet `sample_size`）

- [ ] 有事前样本量估算吗？α、把握度、效应量来源、最小临床重要差值 `sample_size_unjustified`
- [ ] 实际入组 vs 估算：达标了吗？不足时如何影响结论 `sample_size_unjustified`
- [ ] 是否声称"效能足够"或做事后效能计算 `power_claim`
- [ ] 失访/退出/剔除：人数、原因、时点、是否与结局相关 `attrition_missing`
- [ ] 流程图（CONSORT/STROBE）与正文人数是否一致 `reporting_gap` / `internal_inconsistency`

## E. 结果报告（facet `reporting`）

- [ ] 每个主要/次要结果：效应量 + 95% CI 齐备 `effect_size_missing` / `ci_missing`
- [ ] 精确 p 值（非 p<0.05）、统计量与自由度 `p_reporting`
- [ ] 摘要、正文、表格、图之间的 n、均值、p、方向一致 `internal_inconsistency`
- [ ] 表格有单位、有组别、有缺失说明；图有误差条定义 `reporting_gap`
- [ ] 对应报告规范条目（CONSORT/STROBE/PRISMA/STARD）逐项覆盖 `reporting_gap`
- [ ] 讨论中的比较性论断有引用支持 `citation_support_missing`
- [ ] 利益冲突、资金、作者贡献、数据可得性 `norm_deviation` / `data_availability_missing`

## 六类审查面的默认归属（finding.dimension）

| dimension | 覆盖上面哪些项 | 说明 |
|---|---|---|
| `fact` | 数值一致性、单位换算、与自身数据冲突的陈述 | 能对账的硬事实 |
| `citation` | 引用是否支持该句、关键论断有无引用 | 不做文献检索，只判"引用与论断是否对得上" |
| `method` | A/B/C/D 的大部分 | 设计与统计推断的成立性 |
| `stat_report` | E 的数值报告、失访流程 | 报告完整性与可复核性 |
| `argument` | 结论强度、因果措辞、亚组解释、术语歧义 | 论证链是否闭合 |
| `norm` | 注册、伦理、数据可得性、利益冲突 | 学术规范条目 |

## 自检（提交前）

- [ ] 五个面都有判定（`ok` 或 `gap`），不是靠"没问题"跳过
- [ ] 每条 finding 的 `quote` 能在材料中逐字找到
- [ ] `underreporting` 没有写成 `critical`
- [ ] `severity_reason` 说了为什么不是相邻级别
- [ ] `unchecked_items` 写清了没检查什么、为什么
- [ ] 报告中问题数 ≠ 审出多少，而是"每条都能落回原文"
