# 判定规范（verdict-rubric，规则版本 rules/1）

本文件是 `citation_checks[].verdict`、`semantics`、`severity`、`verdict_type` 的唯一口径。脚本不判定，只校验；判定由审查者按本文件写入 `draft.json`。

## 1. 核心区别：引用存在 ≠ 引用支持结论

| 情形 | 不等于 | 正确判定 |
|---|---|---|
| 正文 `[12]` 能在文献表找到条目 | ≠ 支持该结论 | 只是配对成功，还要比对三要素 |
| 引文是同一主题的研究 | ≠ 支持该结论 | 至多 `partial_support`，常为 `undetermined` |
| 引文作者就是本文作者 | ≠ 支持该结论 | 仍须比对方向/数值/范围 |
| 引文标题里出现相同关键词 | ≠ 支持 | 关键词共现不构成支持 |
| 引文是综述 | ≠ 支持原始结论 | 综述可作背景，不能替代原始证据 |

仅在这个前提下才可能给出 `full_support`。

## 2. 四级支持度

| verdict | 定义 | 判定条件（必须同时满足） | 典型例子 |
|---|---|---|---|
| `full_support` | 来源明确支持该论断的全部要素 | ① `direction_match=true` ② `numeric_match=true`（论断无数字时要求来源未给出相反数值）③ `scope_match=true` ④ 来源句与论断的主语/对象/条件一致 ⑤ 能找到这对齐的来源原文或可核实的来源标识 | 正文："Compound X reduced 12-week mortality (82% vs 61%, p=0.03) [2]"，来源摘要同报告 82%/61%/p=0.03、同人群同终点 |
| `partial_support` | 只支持一部分 | 三要素中恰好一项为 `false`，其余为 `true`；或来源只支持子集人群/条件/强度 | 来源是单中心亚组，正文写"所有患者"（`scope_match=false`） |
| `no_support` | 不支持或方向相反 | `direction_match=false`，或存在矛盾数值（`numeric_match=false` 且来源给出相反数值），或否定极性相反（来源"无差异"→正文"显著改善"） | 来源报告"无显著差异"，正文写"显著降低死亡" |
| `undetermined` | 材料不足以判定 | 缺文献表、缺来源原文/摘要、编号错位无法映射、仅有标题、quote 无法定位、来源语言不可读 | 正文 `[5]` 但文献表只有 `[1][2][3]`；或只有题名无法判断结论方向 |

### 2.1 决策顺序（固定，不可跳步）

1. **可判定性**：来源原文/摘要/结论是否存在？不存在 → `undetermined`，写 `unresolved_reason` + `human_check_needed`。**到此结束，不得继续推测。**
2. **对象对齐**：来源研究对象/干预/终点与论断是否同一？不同 → `no_support`（当作支持是最大误报）。
3. **方向对齐**：升高/降低、有效/无效、正相关/负相关是否一致？相反 → `no_support`。
4. **数值对齐**：论断中的数值、样本量、效应量、p 值在来源中是否出现同值？矛盾 → `no_support`；来源未报告但无矛盾 → `numeric_match=null` 并说明（此时最高 `partial_support`）。
5. **范围对齐**：论断强度/范围是否超出来源？超出 → `scope_match=false`。
6. 汇总：三项全 true → `full_support`；一项 false → `partial_support`；方向/对象/数值矛盾 → `no_support`。

### 2.2 硬规则（`build` 会强制执行并记入 `changes`）

- `full_support` 且 `direction_match`/`numeric_match`/`scope_match` 任一为 `false` → 自动重算为 `no_support`（方向 false 时）或 `partial_support`，`changes[]` 记录 `from`/`to`/`rule`/`basis`。
- `quote` 未在原文逐字命中 → 该行/该条降级 `pending_review`，不得 `confirmed`。
- `undetermined` 缺 `unresolved_reason` 或 `human_check_needed` → `check` 报错。
- 无 `rationale` 的判定 → 降级 `pending_review`（不可复核的判定不算结论）。

## 3. 三要素 `semantics`

| 字段 | 取值 | 含义 | 记录要求 |
|---|---|---|---|
| `direction_match` | true / false / null | 来源结论方向与论断方向是否一致 | false 时必须写来源原句 |
| `numeric_match` | true / false / null | 论断数值/样本量/效应量/显著性表述是否与来源同值 | 单位换算差异要写换算；来源未报告用 null |
| `scope_match` | true / false / null | 论断强度与范围是否未超出来源 | false 时写清超出哪一维（人群/条件/因果强度） |
| `comparator` | 字符串 / null | 原文比较词（高于/低于/higher than/versus…），逐字取自原句 | 有比较就必须填 |
| `negation` | 字符串 / null | 原文否定词（无/未/not…），逐字 | 有否定就必须填 |
| `significance` | 字符串 / null | 显著性表述（p=0.03 / 95% CI…），逐字 | 论断含显著性必须填 |

**结论强度阶梯**（用于 `scope_match` 判断）：

```
相关 < 预测/关联强度 < 因果（导致/因为…所以） < 普适（所有/总是/任何）
单一材料/单细胞系 < 单一队列/单中心 < 多中心 < 全人群
体外 < 动物 < 人体观察 < 随机对照
```

论断所在层级高于来源层级 → `scope_match=false`。例：来源"单中心 CKD 3-4 期队列"（人体观察/单中心）→ 正文"all patient populations"（全人群）→ false。

## 4. 严重度 `severity`

| severity | 锚点 | 判据 |
|---|---|---|
| `critical` | 结论不成立 | 核心结论 `no_support`；关键数字矛盾且改变主结论方向；来源已撤稿仍作为主要证据 |
| `major` | 影响可解释性/可复现性 | 过度推断（scope 越界且落在摘要或结论）；样本量/显著性表述冲突；关键方法信息缺失；来源不可靠（预印本当正式文献、版本不一致） |
| `minor` | 局部准确性 | 单处数字/单位/编号错位；引用范围过宽但不改结论；图注与正文措辞不一致 |
| `suggestion` | 不影响正确性 | 补限定语、补数据/代码可用性声明、统一术语、补对照说明 |

`severity_reason` 必须指向上面某一行判据，不能只写"较严重"。

**反模式**：全部条目同为 `major`。若所有条目严重度相同，`check` 不报错但人工评审会判为分级失效——请重读锚点。

## 5. `verdict_type`（题面要求可区分的四类）

| verdict_type | 用于 | 与 issue_type 的典型搭配 |
|---|---|---|
| `fact_error` | 事实错误：数字矛盾、单位错、来源结论被写反 | `numeric_inconsistency`、`fact_mismatch` |
| `insufficient_evidence` | 证据不足：无来源、来源不支持却当支持、过度推断 | `citation_unsupported`、`citation_partially_supported`、`overclaim` |
| `compliance_issue` | 规范问题：编号错位、缺声明、署名/伦理/数据可用性 | `compliance`、`source_unreliable` |
| `suggestion` | 建议性意见：不改正确性的改进 | `improvement` |

## 6. `issue_type` 九种取值

| issue_type | 定义 | 默认 facet |
|---|---|---|
| `citation_unsupported` | 引文完全不支持该论断 | citation |
| `citation_partially_supported` | 只支持一部分（人群/条件/强度） | citation |
| `overclaim` | 结论超出来源范围（相关写成因果、单组写成普遍） | citation |
| `fact_mismatch` | 正文陈述与来源或稿件他处事实冲突 | fact |
| `source_unreliable` | 来源等级/出版状态/版本有问题（预印本、撤稿、会议摘要当正式文献） | citation |
| `numeric_inconsistency` | 摘要/正文/表格/图注数值、样本量、p 值冲突 | statistics |
| `logic_gap` | 论证跳跃、循环论证、以偏概全、缺对照 | logic |
| `compliance` | 署名、重复发表、数据/代码可用性、伦理、利益冲突、编号错位 | compliance |
| `improvement` | 可执行的改进建议，不构成错误 | 任意 |

## 7. 覆盖矩阵（`coverage`）

六类 facet 必检：

| facet | 检查对象 | 最低要求 |
|---|---|---|
| `citation` | 每处引文标记的配对与支持度 | 每个标记有配对状态；每个被引论断有四级判定 |
| `fact` | 正文内部与来源的事实一致性 | 摘要/正文/表格/图注两两比对 |
| `statistics` | 样本量、百分比、p 值、效应量、CI、单位 | 同一数值桶跨章节比对 |
| `logic` | 结论句与证据句之间的推理链 | 标出跳跃/循环/以偏概全 |
| `method` | 设计、对照、随机化、盲法、终点定义、样本量估算 | 至少检查对照与终点 |
| `compliance` | 署名、重复发表、数据与代码可用性、伦理审批、利益冲突、基金 | 缺声明即记 `compliance` |

五个专项子检查（`coverage` 里以同名字段登记）：

| 子检查 | 落点 |
|---|---|
| `support_verdict` | 四级判定是否覆盖全部被引论断 |
| `source_reliability` | 出版状态/版本/撤稿；离线不可核实时 `checked=false` + 理由 |
| `evidence_locator` | 每条结论是否有本文 locator（+来源 locator/标识） |
| `numeric_consistency` | 数值桶是否跨章节比对过 |
| `argument_chain` | 讨论/结论段论证链是否逐句检查 |

`coverage.<项>.checked=false` 必须同时在 `unchecked_items` 写理由。声称 `checked=true` 但 `items=0` 会被人工评审判为空检查。

## 8. 误报抑制（比提高召回更重要）

| 诱惑 | 处置 |
|---|---|
| 把"主题相同"当"支持" | 只有对象+方向+数值+范围对齐才 `full_support` |
| 把作者自己的转述当"矛盾" | 转述、假设情形、讨论中的可能性不是事实陈述 |
| 把分组差异当"数字冲突" | 不同亚组/不同时间点的数值不矛盾；写清分组 |
| 把单位换算当矛盾 | mg/dL 与 μmol/L、% 与比例为同一值，写换算 |
| 把措辞差异当错误 | 同义改写不是错误；只报语义/数值/范围冲突 |
| 编造外部文献结论 | 离线不可核实的引用一律 `undetermined`，写清需要核对什么 |
| 把"未找到证据"当"证据表明无" | 前者是 `undetermined`，后者才可能是 `no_support` |

## 9. 判定自检三问

1. 这条判定能否指到一个具体的 `文件 §章节 P页 ¶段`？
2. 判定能否被另一人用同一份 quote 复述出同样结论？
3. 若把这条判定交给作者，作者能否凭 quote 直接反驳？能反驳说明证据不足 → 降级为 `undetermined` 或补证据。
