# 专家参考手册 —— 论文结构化字段抽取

面向单篇（或少量）论文的结构化字段抽取：把「论文里印了什么」逐字段还原成一张可核对、可回源、
可复跑的字段表。以下内容按方法论组织：先讲清交付物与判分关注点，再给出带冻结产物的求解框架、
字段口径与公式、领域陷阱、证据定位规则、交付形态，最后用一个数字自洽的虚构案例贯穿演示，
并以交付前自查表收束。

---

## 1. 任务本质与高分要素

要交付的不是论文摘要，也不是压缩总结，而是一张**逐字段、带证据定位的结构化字段表**。
任何一个字段都要回答五件事：原文写了什么（`scalar`）、以什么单位写（`unit`）、
是什么统计量（`statistic`，如 point、mean ± SD、p 值）、在什么条件下成立
（`condition`）、谁与它比较（`comparator`）；同时必须能指回原文位置（`locator`）
并附逐字引用（`quote`），最后给出状态（`reported` / `not_reported` /
`source_conflict` / `extraction_failed`）。

评委实际看五件事，任何一件缺失都会扣分：

1. **实际效果**：字段覆盖完整；数值、单位、误差、统计量、条件限定与原文字面一致；
   作者明确结论、限制条件、推测性表述被分层；每个字段能指回原文位置。
2. **使用增益**：加载 Skill 后抽取质量是否稳定高于无锚点基线；耗时、人工核对条目、
   重试成本是否下降；改善是否来自可复核的对照而非自述。
3. **创新增益**：是否具备基础 Agent 不具备的能力，例如条件与数值同源绑定、
   跨页表格还原、字段级证据定位、结论与推测分层。
4. **可靠体验**：不同论文类型、版式、重复运行下是否稳定；对扫描件无文本层、
   表格跨页、单位缺失、字段未报告、多来源冲突等异常是否识别并处置。
5. **生态贡献**：字段词典、抽取口径、定位规则、依赖、示例、适用范围、限制是否齐全，
   他人能否直接复跑与迁移。

---

## 2. 求解框架：每步冻结产物与门控

框架的核心是「先冻结、再前进」：上一步的产物未冻结，不进入下一步；任何一步失败都留下
可人工接管的明确位置，而不是把不确定项静默提升为成功。

| 步骤 | 操作 | 冻结产物 | 门控 |
|---|---|---|---|
| 0 输入盘点 | 读取 `case.json`、`task.md`、字段字典与材料清单，并实际打开材料 | `case_id`、`field_id` 清单、材料清单 | 所有 `field_id` 已解析；材料可读；材料缺失即记 `extraction_failed` |
| 1 语料索引 | 抽取每页文本、表格、图注，分配合法 locator | `corpus_index.json`（段落 / 表格 / 单元格 / 行） | 每个来源有文本或表格；空文件与坏解析记入 `degradations` |
| 2 字段映射 | 对每个字段在全文、表格、图注中检索候选位置 | 候选位置表（字段 → locator + 引文片段） | 每个字段至少一个候选，或标记 `not_reported` |
| 3 值-条件绑定 | 抽取 `scalar`、`unit`、`statistic`、`condition`、`comparator` | `candidate_values` | 数值字段有单位，或显式记录「原文无单位」；条件覆盖最小成立条件集 |
| 4 多来源对齐 | 比较同一字段的多个候选读数 | `aligned_fields` | 冲突不得强行合并，标 `source_conflict` 并保留各方原文 |
| 5 结论分层与语义核验 | 判定明确结论 / 限制条件 / 推测性表述；核验引文与数值指向同一对象 | `final_fields` | 无「可能 / 提示 / 建议」被改写为事实；语义核验通过 |
| 6 出件 | 回填契约、写字段表与运行日志 | `result.json`、`fields.csv`、`run.log` | 契约键齐全；`status` 由产物推导；缺口可人工接管 |

预算分配建议：前 70% 用于索引与落位，20% 用于对齐与口径核验，至少 10% 用于复核与出件。
首批字段落位后先保存诚实的部分结果，再增量修正，避免一次大改之后无法回退。

---

## 3. 字段契约与状态语义

每个字段记录至少包含：`field_id`、`value`（原文字面值）、`units`、`statistic`、
`condition`、`comparator`、`source`、`quote`、`locator`、`status`、`claim_type`、
`condition_complete`、`notes`。字段的 `value` 与 `units` 必须来自同一处原文，
不得一半取自正文、一半取自表格。

状态语义一经确定就不再用自然语言「说圆」：

- `reported`：原文印出了该值，且引文在索引中逐字命中、locator 可独立定位。
- `not_reported`：材料明确未测（如单元格为 `n.r.`、正文写 not determined），或全文无该字段；
  这是「看过了但没有」，不是「没看」。
- `source_conflict`：同一字段在正文、表格、图注、补充材料中给出不同读数；
  两条读数都保留，并说明冲突来源。
- `extraction_failed`：材料存在但该字段无法判读（如扫描件无文本层、字段定义缺失）；
  需附失败原因与可人工接管位置。

`claim_type` 用于区分 `measured`（测量值）、`reported`（原文陈述值）、
`qualitative`（定性描述）、`unsupported`（未得到证据支持）。覆盖率
`coverage = reported / total`，四类状态分别计数；四类计数之和必须等于字段总数。

---

## 4. 关键口径、公式与单位

### 4.1 效率与质量指标

| 指标 | 定义 | 公式 |
|---|---|---|
| 字段级准确率 | 完全正确的字段占应抽取字段的比例 | `正确字段数 / 应抽取字段数 × 100%` |
| 证据可核验率 | 含有效 locator 且逐字引文可回原文的字段占比 | `可核验字段数 / 总字段数 × 100%` |
| 单位保留率 | 数值字段中保留原文字面单位的比例 | `保留单位字段数 / 数值字段总数 × 100%` |
| 条件绑定率 | 数值字段中同时给出成立条件的比例 | `绑定条件字段数 / 数值字段总数 × 100%` |
| 重试成本 | 平均每字段人工核对条目数 | `总核对条目数 / 总字段数` |

重复运行三次时，字段值一致率宜不低于 95%，证据定位一致率不低于 90%；字段级准确率低于
85% 应触发重跑或人工接管。

### 4.2 反应的三个量：转化率、选择性、产率

- 转化率：`conversion = (初始底物 − 剩余底物) / 初始底物 × 100%`。
- 选择性：`selectivity = 目标产物 / 全部产物 × 100%`。
- 产率：`yield = conversion × selectivity` 只在同一基准（同一底物、同一分析口径）下成立，
  得到的是粗样或 NMR 基准的产率。
- **分离产率**（isolated yield）指纯化后实际所得产品的质量基准产率，与 NMR 产率、粗产率
  不是同一个量。三者必须按原文标注分别记录，不可互相替代。

### 4.3 误差与统计量

- 标准差：`SD = sqrt( Σ(xi − x̄)² / (n − 1) )`。
- 标准误：`SEM = SD / sqrt(n)`。
- 95% 置信区间：`x̄ ± t(0.975, n−1) · SEM`。
- `±` 单独出现时不得自行认定为 SD；原文写 SD 就记 SD，写 SEM 就记 SEM，没写就记
  「误差类型未注明」。`p < 0.05` 与 `p < 0.01` 不可混同；原文只写「显著」而无具体 p 值时，
  记为「未报告具体 p 值」。

### 4.4 用量与单位

- `mol%` 是相对底物的摩尔百分比，`equiv` 是当量数，两者是不同计量口径。
  以底物为共同基准时，10 mol% 对应 0.10 equiv，但原文写 `mol%` 就必须保留 `mol%`，
  不能改写成 `equiv` 或 `M` 后冒充原文值；若基准对象不同，数值换算根本不成立。
- 浓度（M、mM、μM、nM）、质量（g、mg、μg、ng）、体积（L、mL、μL）、压力
  （MPa、bar、psi、atm）、温度（°C、K）、时间（h、min、s）一律保留原文字面值与单位；
  需要换算时另存为 `converted_value`，并注明换算依据（如 `T(K) = t(°C) + 273.15`、
  `1 MPa = 10 bar ≈ 145.04 psi`），不得替换 `scalar` 与 `unit`。
- 「过夜」「室温」等模糊表述按原文记录，并标注「未报告具体数值」，不擅自折算成 12 h 或 25 °C。
- 单位缺失时 `units` 留空并在 `notes` 说明；不凭常识补单位，也不把单位写进 `value`。

---

## 5. 领域陷阱清单（错误做法 → 正确做法）

1. 把分离产率与 NMR 产率合并成一项 → 分别记录，并在 `statistic` 或 `notes` 标注产率类型。
2. 用 `conversion × selectivity` 的结果替代分离产率 → 两者分列，注明基准不同。
3. 把所有误差统一写成 `±` → 保留 SD / SEM / 95% CI 的原标注。
4. 把 SEM 当作 SD 直接比较离散度 → 先按 `SEM = SD / sqrt(n)` 还原，再在 `notes` 说明。
5. 把 `10 mol%` 改写成 `0.1 equiv` 或 `0.1 M` → 保留 `mol%`；换算另存 `converted_value`。
6. 把 `2.0 equiv` 与 `2.0 mmol` 混用 → 当量数与绝对摩尔量分开记录，基准写清。
7. 缺失字段填 0、填「无」或从其他文献补值 → 记 `not_reported`，`notes` 写明搜索范围。
8. 多来源冲突时只取一方或取平均 → 记 `source_conflict`，保留各方读数与定位。
9. 把「可能」「提示」「建议」改写成确定结论 → 分层标注，必要时写「作者推测，未直接证实」。
10. 只引段落号、不引表格行列或图注编号 → locator 精确到 `Table 1, Entry 3` 或
    `Figure 1 caption, line 2` 这一级。
11. 跨页表格把续表当成新表，或合并单元格被拆散、重复 → 识别 `Table 1 (continued)` 等标记，
    还原合并单元格并按行号对齐。
12. 单元格 `n.r.` 被当作 0 或空 → 判 `not_reported`，并把该行作为「确实看过、只是未测」的证据。
13. 把 100 °C 换算成 373 K 后替换原文 → 原文写 °C 就记 °C，换算值另存。
14. 数值与条件分离，例如只写「产率 92%」→ 每个数值绑定最小条件集
    （催化剂用量、碱、溶剂、温度、时间、规模）。
15. 只做字面匹配、不做语义核验（如把反应温度当成室温）→ 引文必须与数值指向同一对象。
16. 把「补充材料未找到」当成「未报告」→ 区分「材料缺失」（`extraction_failed` 或 `input_error`）
    与「材料在、但没印该字段」（`not_reported`）。

---

## 6. 证据定位、多来源对齐与语义核验

定位符采用稳定、可复算的方案：段落为 `{source_id}#{paragraph_id}`，
表格行为 `{source_id}#{table_id}:r{row}`，单元格为 `{source_id}#{table_id}:r{row}c{col}`，
字段定义本身为 `{source_id}#field:{field_id}`。定义段落只用于确认字段含义，
**永不作为字段值来源**。`quote` 必须是索引中某段落或某表格行渲染串的逐字切片
（仅允许空白规范化）；引文不在索引中即撤回该值并记 `extraction_failed`。

多来源对齐的默认顺序为「与实验条件同表的读数优先，其次是正文明确实验句、图注、
补充材料」，这一顺序只用于**同一字段、同一读数**的取值；一旦数值不一致，顺序不构成
自动择优的理由，必须记 `source_conflict` 并保留全部读数。图注与补充材料与正文同等对待，
因为同一字段常常只在其中一处被完整报告。

语义核验关注三件事：引文与 `scalar` 指向同一对象；单位与数值同源；条件限定没有在转写中丢失。
逐字命中只是必要步骤，不是充分条件——原文「100 °C」被截成「100」而丢单位，
虽仍逐字命中片段，但已改变语义，属于必须拦截的错误。

---

## 7. 交付物与可核验方式

| 交付物 | 必需内容 | 可核验方式 |
|---|---|---|
| `result.json` | 契约键逐键回填真实值、`case_id`、字段表、覆盖率、状态、来源、不确定性、变更记录 | 程序化校验键与状态；`status` 必须由产物推导 |
| `fields.csv` | 逐字段一行：`field_id,field_name,value,units,statistic,condition,comparator,source,quote,locator,status,claim_type,condition_complete,notes` | 与 `result.fields[]` 逐行对照，列数与行数一致 |
| `work/corpus_index.json` | 段落、表格、单元格、行、字段字典 | 随机抽行回原文逐字核对 |
| `run.log` | 版本、`case_id`、来源数、字段数、覆盖率、耗时 | 复跑同一命令，对比摘要 |
| `references/expert_playbook.md` | 口径、公式、陷阱、案例、自查表 | 按本文档复算案例数字 |

推荐复跑命令（单命令产出全部交付物）：

```bash
python3 -B /skills/weekly-skill/scripts/extract.py --stage run \
  --input /input --output /app/output --work /app/work
```

核验顺序：先确认退出码为 0、`result.json` 可解析；再逐键检查 `output_contract` 非空且无类型
占位符；然后按 `fields.csv` 抽 3 行回原文核对引文与 locator；最后核对
`coverage` 四类计数之和等于字段总数，`not_reported` 每条都有搜索范围证据。

---

## 8. 完整虚构案例：镍催化 Suzuki–Miyaura 条件优化

> 以下论文、数值与 ID 均为合成示例，仅用于演示流程与复算，不是正式测试结果。

**输入**：`case_id = DEMO-SYN-R06`，字段字典要求 10 个字段；材料为正文 `paper.md`、
`Table 1` 数据行与补充材料 `si.md`。

**Table 1（优化条件）**：

| Entry | 催化剂 (mol%) | 碱 (equiv) | 溶剂 | T (°C) | t (h) | 分离产率 (%) |
|---|---|---|---|---|---|---|
| 1 | NiCl2(dppp) (5) | K3PO4 (2.0) | dioxane | 100 | 24 | 72 |
| 2 | NiCl2(dppp) (10) | K3PO4 (2.0) | dioxane | 100 | 24 | 92 |
| 3 | NiCl2(dppp) (10) | K3PO4 (2.0) | dioxane | 80 | 24 | 61 |
| 4 | NiCl2(dppp) (10) | K2CO3 (2.0) | dioxane | 100 | 24 | 48 |
| 5 | NiCl2(dppp) (10) | K3PO4 (2.0) | THF | 100 | 24 | 83 |

**正文关键句**：

- 「Reaction of 4-chlorotoluene with phenylboronic acid under the optimized conditions
  gave the biaryl in 92% isolated yield (mean ± SD of three runs, ±2.4%).」
- 「For the same run, 1H NMR analysis indicated 95% NMR yield and 97% conversion with
  95% selectivity.」
- 「The authors suggest that dioxane stabilizes the nickel(0) intermediate.」
- 「We conclude that the protocol tolerates electron-poor aryl chlorides.」
- 「All reactions were run at 0.5 mmol scale in 2.0 mL dioxane.」

**补充材料关键句**：「The base loading was 1.5 equiv in all runs.」
（与 Table 1 的 2.0 equiv 冲突。）

**抽取结果**（10 个字段）：

| field_id | 原值 | 单位 | statistic | 条件 | 状态 |
|---|---|---|---|---|---|
| catalyst_identity | NiCl2(dppp) | — | 文本 | Entry 2 | reported |
| catalyst_loading_opt | 10 | mol% | point | Entry 2 | reported |
| base_opt | K3PO4 | — | 文本 | Entry 2 | reported |
| base_equiv | 2.0 与 1.5 | equiv | point | Table 1 与 SI | source_conflict |
| solvent_opt | dioxane | — | 文本 | Entry 2 | reported |
| temp_opt | 100 | °C | point | Entry 2 | reported |
| time_opt | 24 | h | point | Entry 2 | reported |
| yield_isolated | 92 | % | mean ± SD, n=3 | 10 mol%, 100 °C, 24 h | reported |
| yield_sd | 2.4 | % | SD, n=3 | Entry 2 | reported |
| ee_opt | 未测定 | — | — | — | not_reported |

**复算**：

- 粗样基准产率：`0.97 × 0.95 = 0.9215`，即 92.15%，与 92% 分离产率接近但基准不同，
  不能互相替代；NMR 产率 95% 另记。
- 标准误：`SEM = 2.4 / sqrt(3) = 1.386 ≈ 1.39%`；若报 95% CI，`t(0.975, 2) = 4.303`，
  半宽 `4.303 × 1.386 ≈ 5.96`，即约 `92.0 ± 6.0%`。
- 浓度：`0.5 mmol / 2.0 mL = 0.25 mmol/mL`；如换算为 `converted_value = 250 mM`，
  原文 `0.5 mmol`、`2.0 mL` 保持不变。
- 指标（首轮）：字段级准确率 `9/10 = 90.0%`（首轮把 95% NMR 产率误记为分离产率，
  复核后改回 92%，转 `10/10`）；证据可核验率 `10/10 = 100%`；
  单位保留率 `6/6 = 100%`；条件绑定率 `6/6 = 100%`。
- 人工核对条目 4 条（产率口径、碱当量冲突、SD/SEM 区分、ee 缺失），
  重试成本 `4/10 = 0.4 条/字段`。
- 恰当时，基线（无锚点、无逐字引文）在同一材料上为 `6/10 = 60.0%`；
  按本框架复核后为 `10/10 = 100%`。这只是结构可判定项的对照，不代表官方分数。

**分层结论**：dioxane 稳定镍(0)中间体属于作者推测；对缺电子芳基氯的容忍性属于作者明确结论；
碱当量 2.0 与 1.5 equiv 冲突如实保留；ee 未测定记 `not_reported`，不填 0、不推断。

---

## 9. 防扣分自查表（交付前逐项通过）

- [ ] 已实际读取材料文件，而不是按文件名、领域标签或示例内容推测。
- [ ] 字段字典中的每个 `field_id` 都出现在结果里，既无遗漏也无擅自新增。
- [ ] 每个字段都有 `value` 或明确的状态，不存在静默留空。
- [ ] 每个数值字段保留原文字面值与原单位，换算值只出现在 `converted_value`。
- [ ] 每个数值字段绑定最小实验条件集（用量、碱、溶剂、温度、时间、规模等）。
- [ ] 每个字段的引文在索引中逐字命中，locator 可独立定位。
- [ ] 分离产率、NMR 产率、粗产率没有被混为一项，统计量与基准已标注。
- [ ] `±` 后的误差类型已按原文区分 SD / SEM / 置信区间，未自行认定。
- [ ] `mol%` 与 `equiv` 未被互相替换书写，基准对象已说明。
- [ ] 转化率、选择性、产率的关系与各自基准未被混用。
- [ ] `n.r.` 等未测标记判为 `not_reported`，未当作 0 或空值。
- [ ] 多来源冲突已标 `source_conflict`，各方读数与定位均保留，未强行合并或取平均。
- [ ] 作者明确结论、限制条件、推测性表述已分层，未把「可能」「提示」写成事实。
- [ ] 跨页表格与合并单元格已还原，表行号与图注编号可回查。
- [ ] 图注与补充材料已作为来源检查，而不只看正文。
- [ ] 单位缺失时留空并说明，未凭常识补单位。
- [ ] `status` 由产物推导且与覆盖率一致，所有非成功项都有 `uncertainties` 记录。
- [ ] `result.json` 含全部契约键与 `case_id`，无类型占位符、无空值。
- [ ] `fields.csv` 与 `result.fields[]` 逐行一致，列数与行数可对照。
- [ ] 已保存中间产物（语料索引）与运行日志，交付件可由单命令复跑。
- [ ] 未伪造数值、软件状态或分数；示例数据已明确标注为合成。

**门控**：上述任一项未通过，`status` 记为 `partial`，未决项写入 `uncertainties`，
绝不静默提升为成功。
