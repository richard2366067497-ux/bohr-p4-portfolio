# appraisal_rules — 量表与关键词族（v2.0.0）

`scripts/engine.py` 在 import 时解析下面的规则块；改量表只改这里，重跑 `python3 scripts/main.py` 生效。
块缺失/不可解析时退到内置最小量表（5 维 × 2 检查点）并记 `degradations: rules_fallback`。

行格式：`kw 名|正则`、`cp 检查点|维度|问题|关键词族|反向词族(-)|优先章节|风险下限|类型(-=通用)`、
`type 类型|正则`、`gen 名称|正则`。首个 `|` 后才是正则，正则内部的 `|` 属于正则。

```rules
kw design|randomi[sz]|study design|prospective|retrospective|cross-sectional|设计
kw elig|eligib|inclusion criteria|exclusion criteria|participants were|纳入标准|排除标准
kw control|control (group|arm)|comparator|compared (with|to)|placebo|对照
kw sample|\bn\s*=\s*\d|sample size|participants|patients|样本量|\d+\s*例
kw sampling|consecutive|convenience|random(ly)? (select|sampl)|recruit|enrol|single[- ]cent|多中心|抽样
kw power|power (analysis|calculation)|powered to detect|sample[- ]size calculation|把握度
kw outcome|primary (outcome|endpoint)|secondary (outcome|endpoint)|outcomes? were|主要结局|结局指标
kw measure|measured|assessed (using|with)|assay|questionnaire|scale|ELISA|PCR|测定|测量
kw valid|validat|reliability|kappa|inter-?rater|calibrat|blinded (assessment|reading)|信度|校准
kw stats|statistical analysis|analys[ei]s (was|were)|t-test|ANOVA|regression|统计
kw effect|95%\s*(CI|confidence interval)|p\s*[<=]\s*0?\.\d+|odds ratio|hazard ratio|置信区间
kw missing|missing data|loss(es)? to follow-up|withdrawn|缺失|失访|脱落
kw limit|limitation|局限|caution|should be interpreted|generalisab|generalizab
kw fund|funding|funded by|conflict of interest|competing interests|资助|利益冲突
kw data|data availability|repository|ethic(al)? (approval|committee)|伦理|知情同意
kw selection|selection bias|consecutive|allocation conceal|sampling frame|选择偏倚
kw blind|blind|masked|盲
kw register|regist(ered|ration)|trial registration|NCT\d|ISRCTN|CRD\d|预注册|注册号
kw seq|sequence generation|random[- ]number (table|generator)|computer[- ]generated|随机数字
kw alloc|allocation conceal|sequentially numbered|opaque (sealed )?envelope|分配隐藏
kw exposure|exposure was (defined|ascertained)|exposed (group|cohort)|暴露
kw confound|adjust(ed)? for|confound|covariate|multivariable|propensity score|校正|混杂
kw followup|followed (up )?for|follow-up (period|duration)|person-years|随访
kw casedef|cases? (were )?(defined|identified)|controls? (were )?selected|matched (on|for|by)|病例组
kw dxref|index test|reference standard|gold standard|sensitivity|specificity|灵敏度|特异度|金标准
kw twobytwo|true positive|false positive|2\s*[×x]\s*2|AUC|阳性|阴性
kw search|search(ed)? (PubMed|Embase|Cochrane)|search strategy|检索(式|策略)
kw rob|risk of bias|RoB\s*2?|quality assessment|GRADE|偏倚风险
kw het|heterogeneity|I\s*2\s*=|funnel plot|publication bias|异质性|发表偏倚
kw animal|mice|murine|rats?|zebrafish|cell lines?|in vivo|动物|小鼠|大鼠
kw model|model (structure|assumption)|governing equation|finite element|Monte Carlo|模型|边界条件
kw validate|validat(ed|ion)|calibrat(ed|ion)|external validation|校准|验证
kw sens|sensitivity analysis|uncertainty analysis|scenario analysis|robustness|敏感性分析|不确定性
kw synth|synthesi[sz]|prepared (by|using)|anneal|sinter|fabricat|合成|制备|退火
kw instr|XRD|X-ray diffrac|SEM|TEM|Raman|FTIR|spectromet|仪器|光谱|衍射
kw uncert|error bar|standard deviation|standard error|±|误差|标准差
kw coding|cod(ed|ing)|thematic analysis|framework analysis|编码|主题分析
kw reflex|reflexiv|positionality|negative case|member check|反身性|立场
kw timeline|presented (to|with)|on admission|hospital course|主诉|病史
kw overreach|we (conclude|suggest|believe)|causal(ity)?|attribut|说明.{0,6}(因果)
kw designneg|not randomi[sz]ed|non[- ]randomi[sz]ed|quasi[- ]experimental|uncontrolled|非随机|无对照
kw blindneg|not blind|no blinding|unblind|open[- ]label|未设盲|非盲
kw sampleneg|convenience sample|no sample size (calculation|justification)|sample size was not|未做样本量
kw powerneg|no power (calculation|analysis)|was not powered|未做把握度
kw missneg|no missing data|complete case|未报告缺失
cp D1|DESIGN|设计类型是否支撑结论|design|designneg|Methods,Abstract|low|-
cp D2|DESIGN|有无明确对照|control|-|Methods,Abstract|low|-
cp D3|DESIGN|纳入排除条件|elig|-|Methods,Abstract|low|-
cp S1|SAMPLE|样本量是否报告|sample|sampleneg|Methods,Results,Abstract|low|-
cp S2|SAMPLE|抽样招募与场景|sampling|-|Methods|low|-
cp S3|SAMPLE|样本量估算/把握度|power|powerneg|Methods|low|-
cp M1|MEASURE|主要结局是否预定义|outcome|-|Methods,Abstract|low|-
cp M2|MEASURE|测量方法与工具|measure|-|Methods|low|-
cp M3|MEASURE|测量有效性与可靠性|valid|-|Methods,Results|low|-
cp T1|STATSREP|统计分析方法|stats|-|Methods,Results|low|-
cp T2|STATSREP|效应量与不确定性|effect|-|Results,Abstract|low|-
cp T3|STATSREP|缺失数据与失访|missing|missneg|Results,Methods|low|-
cp T4|STATSREP|局限性与缺项|limit|-|Discussion,Body|some|-
cp T5|STATSREP|资助与利益冲突|fund|-|Body,Discussion|low|-
cp T6|STATSREP|伦理与数据可得性|data|-|Body,Methods|low|-
cp B1|BIAS|选择偏倚是否被处理|selection|-|Methods|low|-
cp B2|BIAS|盲法覆盖范围|blind|blindneg|Methods|low|-
cp B3|BIAS|注册与预设结局|register|-|Methods,Body|low|-
cp R1|DESIGN|随机序列生成|seq|-|Methods|low|rct
cp R2|DESIGN|分配隐藏|alloc|-|Methods|low|rct
cp H1|DESIGN|暴露与随访起点|exposure|-|Methods|low|cohort
cp H2|STATSREP|关键混杂校正|confound|-|Methods,Results|low|cohort
cp C1|DESIGN|病例对照来源|casedef|-|Methods|low|case_control
cp C2|BIAS|暴露测量是否设盲|blind|blindneg|Methods|low|case_control
cp X1|SAMPLE|抽样框与应答率|sampling|-|Methods|low|cross_sectional
cp X2|DESIGN|是否说明不能定因果|limit|-|Discussion,Body|some|cross_sectional
cp G1|DESIGN|待评价试验与参考标准|dxref|-|Methods|low|diagnostic
cp G2|MEASURE|2×2 计数或灵敏度区间|twobytwo|-|Results|low|diagnostic
cp G3|BIAS|是否独立设盲判读|blind|blindneg|Methods|low|diagnostic
cp Y1|DESIGN|检索式与日期|search|-|Methods|low|sysrev
cp Y2|STATSREP|逐研究偏倚风险|rob|-|Methods,Results|low|sysrev
cp Y3|STATSREP|异质性与发表偏倚|het|-|Results|low|sysrev
cp P1|DESIGN|模型与随机盲法|animal|-|Methods|low|preclinical
cp P2|SAMPLE|独立重复与样本量|sample|-|Methods,Results|low|preclinical
cp O1|DESIGN|模型结构与假设|model|-|Methods|low|modelling
cp O2|MEASURE|校准与验证|validate|-|Results,Methods|low|modelling
cp O3|STATSREP|敏感性分析|sens|-|Results,Discussion|some|modelling
cp A1|DESIGN|制备参数可复现|synth|-|Methods|low|materials
cp A2|MEASURE|仪器与标定|instr|-|Methods|low|materials
cp A3|STATSREP|重复次数与误差|uncert|-|Results|low|materials
cp Q1|SAMPLE|抽样策略与饱和度|sampling|-|Methods|low|qualitative
cp Q2|MEASURE|编码与审计链|coding|-|Methods|low|qualitative
cp Q3|BIAS|反身性与反面案例|reflex|-|Discussion,Methods|some|qualitative
cp Z1|DESIGN|时间线与诊疗节点|timeline|-|Body,Methods|low|case_report
cp Z2|MEASURE|客观检查与随访|followup|-|Results,Body|low|case_report
cp Z3|BIAS|因果归因是否越界|overreach|-|Discussion|major|case_report
type sysrev|systematic review|meta-?analys[ie]s|PRISMA|系统评价|荟萃分析
type rct|randomi[sz]ed (controlled )?trial|randomi[sz]ed|randomly assigned|随机对照|随机分组
type diagnostic|diagnostic accuracy|sensitivity and specificity|index test|reference standard|诊断准确性
type case_control|case-?control|病例对照
type cross_sectional|cross-?sectional|prevalence survey|横断面
type cohort|cohort|follow-?up study|longitudinal|prospective study|队列
type preclinical|mice|murine|rats?|zebrafish|cell lines?|in vivo|动物实验
type materials|alloy|composite|synthesis|microstructure|anneal|XRD|specimen|合金
type modelling|finite element|Monte Carlo|numerical simulation|machine learning model|数值模拟
type qualitative|semi-?structured interview|thematic analysis|质性研究
type case_report|case report|we present a case|single patient|病例报告
gen preprint|preprint|medRxiv|bioRxiv|arXiv|预印本
gen fixture|fixture|synthetic|dummy|duplicate|conflict|占位
```

## 判定规则（rule_id 可逐条复核）

| rule_id | 触发 | judgment | risk |
|---|---|---|---|
| `R_J1_ABSTAIN` | 关键词族在文献所有块中无命中 | `not_assessable` | `insufficient` |
| `R_J2_NEG` | 锚点句命中该检查点反向词族（未随机/未设盲/未做样本量…） | `not_met` | `major` |
| `R_J3_MET` | 有效锚点 ≥2，或 1 条锚点且含数字 | `met` | 检查点 `floor` |
| `R_J4_WEAK` | 仅 1 条锚点且无量化信息 | `partial` | `some` |

弃权原因：`unreported`（可读但未报告）/ `not_parsable`（无文本层、加密、仅题录）；同时写
`searched_scope`（块数、章节、关键词族），使"没找到≠不存在"可被复核。

## 分级阈值（与 `grading.json.thresholds` 同源，可复算）

1. 维度级：取最严重者 `major > some > low`；维度内无有效判断 → `insufficient`。
2. 设计强度下限：`DESIGN` 不得高于该类型可达上限——`rct/sysrev=low`；多数观察性/实验性类型 `some`；
   `qualitative/case_report=major`。仅在该维度已有有效判断时生效，并写入 `trace`。
3. 总体：弃权 ≥50% → `insufficient_evidence`；`DESIGN/SAMPLE/BIAS` 任一 `major` → `high_risk`；
   `some` 维度 ≥2 → `some_concerns`；否则 `low_risk`。
