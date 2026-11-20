# 原子化拆分规则（附可判定的检查 id）

目标：把论文里的结论拆成**单条可在证据上判 真 / 假 / 证据不足**的断言。每条断言只承载**一个关系实例**。

## 一、拆分

| 规则 | 做法 | 检查 id |
|-|-|-|
| 并列句 | 以 `and` / `but` / `whereas` / `while` / `;` 连接、且两侧各有独立动词与宾语 → 拆成两条 | `ATO-02` |
| 因果句 | 观察到的现象是一条；作者的因果主张是另一条，用 `relation_type=causes` 且保留原文措辞 | `ATO-02` |
| 比较句 | **不拆**：基线放 `object`（或 `conditions`），差值放 `quantity` | `ATO-05` |
| 多个指标 | 一个指标一条；不要把 accuracy 与 latency 并进一条 | `ATO-05` |
| 代词回指 | 把 `it` / `this` / `they` / `our model` 换成具名实体；以回指开头的断言判失败 | `ATO-01` |
| 整段/整句过长 | 超过一句话（>320 字符）判失败，须收窄到单句 | `ATO-03` |
| 空槽 | `subject` / `predicate` / `object` 任一为空判失败 | `ATO-04` |

## 二、条件与限定词是内容，不是装饰

`in mice`、`at 24 h`、`at pH 7.4`、`n = 12`、`95% CI`、`versus placebo` 进 `conditions`，
并**必须同现于引文**里；hedge（`may` / `suggests` / `is consistent with`）进 `qualifiers`，
且**降低置信级别**而不是被抹掉。

## 三、极性与方向

- `did not reduce` → `polarity: negated`，不得翻转；
- 断言为肯定句而引文含否定（或反之）→ `EV-05` 告警，重写**断言**而非改引文；
- 关系方向与引文相反 → `EV-06`，同样改断言。

## 四、证据绑定

- 引文必须是**逐字连续片段**：一整句或一个完整小句，绝不用 `...` 拼接两句，绝不翻译、绝不复述、绝不凭记忆。
- 一句话可服务多条断言；共享引文优于改写出的第二条引文。
- 引文若含 `It` / `This` / `Our model`，再补一条 `evidence_role: supporting` 的引文点明实体——两条合起来才同时满足原子化与证据绑定。
- 表格行：连同行表头一起引用，并把 `section` 设为该表标题。
- 无法绑定的内容进 `excluded[]` 并写明原因（`no_verbatim_evidence` / `not_atomic` / `prediction_not_result` / `other_evidence_conflicts` / `out_of_scope` / `extraction_failure`）。**如实记录拒绝，比伪造引文得分更高。**

## 五、定位与置信（由脚本判定，不得手写）

- 定位顺序：精确子串 → 归一化（空白/连字符/连字）→ `>= 0.90` 句子窗口（`fuzzy`）。
- 只有前两者可称 `verbatim`；`fuzzy` 一律 `ambiguous`，`unverified` 一律 `unsupported`。
- 置信度为**有序、由证据推导**：`direct_verbatim` > `direct_reported` > `inferred` > `aggregated` > `ambiguous` > `unsupported`。

## 六、词汇表

`relation_type` / `entity_type` / `assertion_type` 取 `assets/controlled-vocab.json` 的值；
没有合适关系时用 `associated_with`，并在 `uncertainty` 说明理由。不要新造关系名。
