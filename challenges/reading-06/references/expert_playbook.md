# 专家参考手册 —— 论文结构化字段抽取

面向单篇（或少量）论文的字段抽取：把「论文里印了什么」逐字段还原成一张可核对、可回源、
可复跑的字段表。以下按方法论组织：交付物与判分关注点、带冻结产物的求解框架、字段口径与公式、
领域陷阱、证据定位规则、交付形态，再用一个数字自洽的虚构案例演示复算，以交付前自查表收束。

---

## 1. 任务本质与高分要素

要交付的不是摘要，而是一张**逐字段、带证据定位的结构化字段表**：每个字段都要给出原文字面值
（`scalar`）、单位（`unit`）、统计量（`statistic`，如 point、mean ± SD、p 值）、成立条件
（`condition`）、比较对象（`comparator`），并能指回原文位置（`locator`）、附逐字引用（`quote`）、
给出状态（`reported` / `not_reported` / `source_conflict` / `extraction_failed`）。高分要素：

1. **对得准**：数值、单位、误差、统计量、条件限定与原文字面一致；明确结论、限制条件、推测表述
   分层；每个字段能指回原文位置。
2. **增益实**：质量稳定高于无锚点基线，耗时、人工核对条目、重试成本下降，且改善来自可复核对照。
3. **有创新**：条件与数值同源绑定、跨页表格还原、字段级证据定位、结论与推测分层。
4. **体验稳**：不同版式与重复运行下稳定；对无文本层、跨页表格、单位缺失、字段未报告、
   多来源冲突等异常能识别并处置。
5. **可迁移**：字段词典、口径、定位规则、依赖、示例、限制齐全，他人可直接复跑。

---

## 2. 求解框架：每步冻结产物与门控

核心是「先冻结、再前进」：上一步产物未冻结不进入下一步；失败时留下可人工接管的明确位置，
不把不确定项静默提升为成功。

| 步骤 | 操作 | 冻结产物 | 门控 |
|---|---|---|---|
| 0 输入盘点 | 读 `case.json`/`task.md`/字段字典/材料并实开材料 | `case_id`、字段 ID 清单、材料清单 | 字段 ID 已解析、材料可读；缺失记 `extraction_failed` |
| 1 语料索引 | 抽文本/表格/图注并分配合法 locator | `corpus_index.json` | 每来源有文本或表格；空/坏解析记 `degradations` |
| 2 字段映射 | 对每字段在全文/表格/图注检索候选 | 候选位置表 | 每字段有候选或标 `not_reported` |
| 3 值-条件绑定 | 抽 `scalar`/`unit`/`statistic`/`condition`/`comparator` | `candidate_values` | 数值有单位或显式「原文无单位」；条件为最小成立集 |
| 4 多来源对齐 | 比较同字段多候选读数 | `aligned_fields` | 冲突不合并，标 `source_conflict` 并留各方原文 |
| 5 分层与语义核验 | 判结论/限制/推测；核验引文与数值同指 | `final_fields` | 无「可能」改写成事实；语义核验通过 |
| 6 出件 | 回填契约、写字段表与日志 | `result.json`、`fields.csv`、`run.log` | 契约键齐全；`status` 由产物推导 |

前 70% 预算用于索引与落位，20% 用于对齐与口径核验，至少 10% 用于复核出件；首批字段落位后先存诚实的部分结果再增量修正。

---

## 3. 字段契约与状态语义

字段至少含 `field_id`、`value`（原文字面值）、`units`、`statistic`、`condition`、`comparator`、
`source`、`quote`、`locator`、`status`、`claim_type`、`condition_complete`、`notes`；`value` 与
`units` 必须同源，不得一半取自正文、一半取自表格。状态语义一经确定不再「说圆」：

- `reported`：原文印出该值，引文在索引中逐字命中且 locator 可独立定位。
- `not_reported`：材料明确未测（单元格 `n.r.`、正文 not determined）或全文无此字段——「看过但没有」。
- `source_conflict`：正文、表格、图注、补充材料给出不同读数；两条都保留并说明来源。
- `extraction_failed`：材料在但无法判读（无文本层、字段定义缺失），须附原因与接管位置。

`claim_type` 区分 `measured` / `reported` / `qualitative` / `unsupported`；覆盖率
`coverage = reported / total`，四类状态计数之和等于字段总数。

---

## 4. 关键口径、公式与单位

### 4.1 效率与质量指标

字段级准确率 = `正确字段数 / 应抽取字段数 × 100%`；证据可核验率 = `可核验字段数 / 总字段数 × 100%`
（含有效 locator 且引文可回原文）；单位保留率 = `保留单位字段数 / 数值字段总数 × 100%`；
条件绑定率 = `绑定条件字段数 / 数值字段总数 × 100%`；重试成本 = `总核对条目数 / 总字段数`。
重复运行三次时值一致率宜 ≥ 95%、定位一致率 ≥ 90%；准确率 < 85% 应触发重跑或人工接管。

### 4.2 转化率、选择性、产率

`conversion = (初始底物 − 剩余底物) / 初始底物 × 100%`；
`selectivity = 目标产物 / 全部产物 × 100%`；`yield = conversion × selectivity` 仅在
同一基准下成立，得到的是粗样或 NMR 基准产率。**分离产率**（isolated yield）是纯化后实际所得
产品的质量基准产率，与 NMR 产率、粗产率不是同一个量，须按原文标注分别记录，不可互相替代。

### 4.3 误差与统计量

`SD = sqrt(Σ(xi − x̄)² / (n − 1))`；`SEM = SD / sqrt(n)`；95% CI `= x̄ ± t(0.975, n−1)·SEM`。
`±` 单独出现时不得自行认定为 SD；写 SD 记 SD、写 SEM 记 SEM、没写就记「误差类型未注明」。
`p < 0.05` 与 `p < 0.01` 不可混同；原文只写「显著」而无具体 p 值时记为「未报告具体 p 值」。

### 4.4 用量与单位

`mol%` 是相对底物的摩尔百分比，`equiv` 是当量数，两者是不同计量口径；以底物为共同基准时
10 mol% 对应 0.10 equiv，但原文写 `mol%` 就必须保留 `mol%`，不可改写成 `equiv` 或 `M` 冒充原文值，
基准对象不同时换算不成立。浓度（M/mM/μM/nM）、质量（g/mg/μg/ng）、体积（L/mL/μL）、
压力（MPa/bar/psi/atm）、温度（°C/K）、时间（h/min/s）一律保留原文字面值与单位；换算另存
`converted_value` 并注明依据（`T(K) = t(°C) + 273.15`、`1 MPa = 10 bar ≈ 145.04 psi`），
不替换 `scalar` 与 `unit`。「过夜」「室温」按原文记录并标注「未报告具体数值」；单位缺失时
`units` 留空并在 `notes` 说明，不凭常识补、不把单位写进 `value`。

---

## 5. 领域陷阱清单（错误做法 → 正确做法）

1. 分离产率与 NMR 产率合并 → 分别记录并标注产率类型。
2. 用 `conversion × selectivity` 替代分离产率 → 两者分列并注明基准不同。
3. 误差统一写成 `±`，或把 SEM 当 SD → 保留 SD / SEM / 95% CI 原标注，必要时按 `SEM = SD / sqrt(n)` 还原。
4. `10 mol%` 改写成 `0.1 equiv` / `0.1 M`，或把 `2.0 equiv` 与 `2.0 mmol` 混用 → 保留原文口径，写清基准，换算另存。
5. 缺失字段填 0、填「无」或从别的文献补值 → 记 `not_reported` 并写搜索范围。
6. 冲突只取一方或取平均 → 记 `source_conflict`，保留各方读数与定位。
7. 「可能」「提示」「建议」改写成确定结论 → 分层标注，写「作者推测，未直接证实」。
8. 只引段落号不引表格行列 / 图注编号 → locator 精确到 `Table 1, Entry 3` 一级。
9. 跨页续表当新表、合并单元格被拆散 → 识别 `Table 1 (continued)`，还原合并单元格并对齐行号。
10. 单元格 `n.r.` 当 0 或空 → 判 `not_reported`，并把该行作为「看过但未测」的证据。
11. 数值与条件分离，或只做字面匹配不做语义核验 → 每个数值绑定最小条件集，且引文须与数值指向同一对象。
12. 「补充材料没找到」当成「未报告」→ 区分「材料缺失」（`extraction_failed` / `input_error`）与「材料在但没印」（`not_reported`）。

---

## 6. 证据定位、多来源对齐与语义核验

定位符稳定可复算：段落 `{source_id}#{paragraph_id}`、表格行 `{source_id}#{table_id}:r{row}`、
单元格 `{source_id}#{table_id}:r{row}c{col}`、字段定义 `{source_id}#field:{field_id}`。
定义段落只用于确认字段含义，**永不作为值来源**。`quote` 必须是索引中某段落或某表格行渲染串的
逐字切片（仅允许空白规范化）；引文不在索引中即撤回该值并记 `extraction_failed`。

多来源默认顺序为「与实验条件同表的读数优先，其次正文明确实验句、图注、补充材料」，该顺序只用于
**同一字段、同一读数**的取值；数值一旦不一致，顺序不构成自动择优的理由，必须记 `source_conflict`
并保留全部读数。图注与补充材料与正文同等对待，因为同一字段常只在其中一处被完整报告。

语义核验关注引文与 `scalar` 是否指向同一对象、单位与数值是否同源、条件限定是否在转写中丢失。
逐字命中是必要条件而非充分条件——原文「100 °C」被截成「100」丢掉单位，虽仍逐字命中片段，却已改变语义。

---

## 7. 交付物与可核验方式

| 交付物 | 必需内容 | 可核验方式 |
|---|---|---|
| `result.json` | 契约键逐键回填真实值、`case_id`、字段表、覆盖率、状态、来源、不确定性、变更记录 | 程序化校验键与状态；`status` 由产物推导 |
| `fields.csv` | 逐字段一行（含 `value,units,statistic,condition,comparator,source,quote,locator,status,claim_type`） | 与 `result.fields[]` 逐行对照，列数与行数一致 |
| `work/corpus_index.json` | 段落、表格、单元格、行、字段字典 | 随机抽行回原文逐字核对 |
| `run.log` | 版本、`case_id`、来源数、字段数、覆盖率、耗时 | 复跑同一命令对比摘要 |

推荐复跑命令（单命令产出全部交付物）：

```bash
python3 -B /skills/weekly-skill/scripts/extract.py --stage run \
  --input /input --output /app/output --work /app/work
```

核验顺序：确认退出码 0、`result.json` 可解析 → 逐键检查 `output_contract` 非空且无类型占位符 →
抽 3 行回原文核对 `quote` 与 `locator` → 核对 `coverage` 四类计数之和等于字段总数。

---

## 8. 完整虚构案例：镍催化 Suzuki–Miyaura 条件优化

> 以下论文、数值与 ID 均为合成示例，仅用于演示流程与复算，不是正式测试结果。

**输入**：`case_id = DEMO-SYN-R06`，字典要求 10 个字段；材料为正文 `paper.md`、`Table 1`、补充材料 `si.md`。

**Table 1**（催化剂均为 NiCl2(dppp)，分离产率 %）：Entry 1 = 5 mol% / K3PO4 (2.0 equiv) / dioxane / 100 °C / 24 h → 72；
Entry 2 = 10 mol% / K3PO4 (2.0 equiv) / dioxane / 100 °C / 24 h → 92（最优）；
Entry 3 = 10 mol% / K3PO4 (2.0 equiv) / dioxane / 80 °C / 24 h → 61；
Entry 4 = 10 mol% / K2CO3 (2.0 equiv) / dioxane / 100 °C / 24 h → 48；
Entry 5 = 10 mol% / K3PO4 (2.0 equiv) / THF / 100 °C / 24 h → 83。

**正文关键句**：「…92% isolated yield (mean ± SD of three runs, ±2.4%)」；
「…95% NMR yield and 97% conversion with 95% selectivity」；
「The authors suggest that dioxane stabilizes the nickel(0) intermediate」；
「We conclude that the protocol tolerates electron-poor aryl chlorides」；
「0.5 mmol scale in 2.0 mL dioxane」。
**补充材料**：「The base loading was 1.5 equiv in all runs」（与 Table 1 的 2.0 equiv 冲突）。

**抽取结果（10 字段）**：catalyst_identity、catalyst_loading_opt、base_opt、solvent_opt、temp_opt、time_opt
六个字段均从 Entry 2 取 `reported`（原值分别为 NiCl2(dppp)、10 mol%、K3PO4、dioxane、100 °C、24 h，
条件与数值同源绑定）；`base_equiv` 因 Table 1（2.0 equiv）与 SI（1.5 equiv）不一致标 `source_conflict`
并保留两条读数；`yield_isolated = 92 %`（mean ± SD, n=3）与 `yield_sd = 2.4 %`（SD, n=3）均 `reported`；
`ee_opt` 原文未测，标 `not_reported`。

**复算**：粗样基准产率 `0.97 × 0.95 = 0.9215`（92.15%），与 92% 分离产率基准不同、不可互替，NMR 产率 95% 另记；
`SEM = 2.4 / sqrt(3) = 1.39%`，95% CI 半宽 `4.303 × 1.386 ≈ 5.96`，约 `92.0 ± 6.0%`；
`0.5 mmol / 2.0 mL = 0.25 mmol/mL`（换算 250 mM，原文不变）。指标（首轮）：字段级准确率 `9/10 = 90.0%`
（首轮把 95% NMR 产率误记为分离产率，复核改回后转 10/10）；证据可核验率 `10/10 = 100%`；
单位保留率与条件绑定率均 `6/6 = 100%`；无锚点基线 `6/10 = 60.0%`（仅结构对照，非官方分数）。
**分层**：dioxane 稳定 Ni(0) 属推测；容忍缺电子芳基氯属结论；碱当量冲突如实保留；ee 记 `not_reported`。

---

## 9. 防扣分自查表（交付前逐项通过）

- [ ] 已实际读取材料文件，未按文件名、领域标签或示例内容推测。
- [ ] 字段字典中每个 `field_id` 都出现在结果里，无遗漏也无擅自新增。
- [ ] 每个字段都有 `value` 或明确状态，不存在静默留空。
- [ ] 每个数值字段保留原文字面值与原单位，换算值只出现在 `converted_value`。
- [ ] 每个数值字段绑定最小实验条件集（用量、碱、溶剂、温度、时间、规模等）。
- [ ] 每个字段的引文在索引中逐字命中，locator 可独立定位。
- [ ] 分离产率、NMR 产率、粗产率未混为一项，统计量与基准已标注。
- [ ] `±` 后误差类型已按原文区分 SD / SEM / 置信区间，未自行认定。
- [ ] `mol%` 与 `equiv` 未互相替换书写，基准对象已说明。
- [ ] `n.r.` 等未测标记判为 `not_reported`，未当作 0 或空值。
- [ ] 多来源冲突已标 `source_conflict`，各方读数与定位均保留，未强行合并或取平均。
- [ ] 作者明确结论、限制条件、推测表述已分层，未把「可能」「提示」写成事实。
- [ ] 跨页表格与合并单元格已还原，表行号与图注编号可回查。
- [ ] 单位缺失时留空并说明，未凭常识补单位。
- [ ] `status` 由产物推导且与覆盖率一致，所有非成功项都有 `uncertainties` 记录。
- [ ] `result.json` 含全部契约键与 `case_id`，无类型占位符、无空值。
- [ ] 未伪造数值、软件状态或分数；示例数据已明确标注为合成。

**门控**：上述任一项未通过，`status` 记为 `partial`，未决项写入 `uncertainties`，绝不静默提升为成功。
