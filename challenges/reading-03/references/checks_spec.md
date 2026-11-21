# 核验口径规格（checks_spec）

本文件是 `scripts/audit.py` 的行为规格，也是可复用资源：判据、术语表模板、题集与评分表模板都在这里，换学科只需替换材料与术语表。

## 1 状态与分档

- `status`：`answered`（全覆盖且无 fail）｜`partial`（覆盖不足或有 fail）｜`insufficient_evidence`｜`input_error`
- 每条 check 的 `status ∈ {pass, warn, fail, skip}`：`fail`=确定性缺陷（丢信息，必须修）；`warn`=需人工判断；`skip`=原文未检出该类成分
- `fail>0` 时 `status` 最高只到 `partial`；工作稿自报更高状态会被降级并写入 `degradations`
- 有 `fail` 时 `result.json.human_review` 逐条给出 `sid` 与"怎么修"

## 2 核验项（17 项）

| check | 判据 | fail / warn | 怎么修 |
|-|-|-|-|
| `sid_integrity` | 段号与 `work/index.json` 一致 | fail：重复/不存在；warn：漏段 | 用 `show` 核对，不自造段号 |
| `source_verbatim` | 工作稿粘的原文与索引逐字一致 | fail：被改写/截断 | 复制索引 `text` |
| `coverage` | 要素型段落与正文的译出比例 | fail：低于阈值 | 补齐缺失段后 `build` |
| `element_coverage` | 题注/表头表行/公式/文献都要成段 | fail：整类缺失 | 不要只译正文 |
| `glossary_quote` | 术语 `quote` 在原文逐字命中 | fail：未命中（含回译） | 换成原文片段 |
| `glossary_drift` | 同术语译名一致 | warn：多译名 | 统一译名或拆义项 |
| `glossary_lock` | locked 术语在每个出现段同名 | fail：漏用 | 按术语表回填全篇 |
| `protected_numbers` | 数字/单位多重集一致 | fail：少/多数字；warn：格式差异 | 按原文回填 |
| `citations` | `[1]` 与 `(Author, 2019)` 数量编号一致 | fail：减少/错号 | 引用标记原样保留 |
| `figure_table_refs` | `Fig. 1`/`Table 1` 引用一致 | fail：缺失 | 保留编号与类型词 |
| `equation_tags` | 公式编号 `(1)` 一致 | fail：缺失 | 公式与编号单独成段 |
| `negation` | 否定关系逐句核对 | fail：否定↔肯定 | 允许换措辞，不丢否定 |
| `hedge` | 限定/可能性表达 | warn：语气丢失 | 别把"可能"写成"必然" |
| `target_language` | 译文语言符合目标语言 | fail：有段落不符 | 数值表行/文献条目豁免 |
| `placeholder_policy` | 译文无占位符 | warn：`TBD`/`待写`/`...` | 未译就留空 + `uncertain` |
| `repeated_target` | 不同段落译文不应完全相同 | warn：疑似复制 | 逐段检查 |
| `contract_fields` | 契约键都能给值 | fail：未给值也无法派生 | 在 `draft.json.result_fields` 给值 |

指标率：`coverage_rate`、`glossary_consistency`、`span_retention`、`element_coverage`、`negation_rate`、`hedge_rate`、
`quote_verbatim`（进 `result.json.audit_summary.rates` 与 `bilingual_review.md`）。

## 3 切段规则（R1–R7）与要素判定

R1 空行断段｜R2 句末兜底｜R3 行尾连字符拼接（记 `hyphen_joined`）｜R4 跨页续段（上页段末无终句标点且下页段首小写→合并，
`bridged=true`、`pages=[p1,p2]`）｜R5 页眉页脚丢弃｜R6 双栏投影切分（中部空白槽在 ≥60% 行成立才切）｜R7 标题自成块。

要素判定：`Fig./Figure/图`、`Table/表` 开头的短行→题注；含制表符或 ` | ` 的行→表头/表行；形如 `E = mc^2  (1)`→`formula`；
`[1] …` 或 `Author A. Title. Journal, Year.`→`reference`。

## 4 术语表模板（复制到新题）

```json
{
  "case_id": "<case_id>", "source_language": "en", "target_language": "zh",
  "policy": {"locked": "quote 逐字命中且全篇一致", "proposed": "工作稿译名，quote 未通过校验", "candidate": "索引候选，未定名"},
  "terms": [
    {"term": "germination rate", "target": "萌发率", "status": "locked",
     "quote": "the germination rate decreased from 92.4 %", "sid": "S003", "locator": "p1:S003",
     "occurrences": ["S003", "S005"], "occurrence_count": 2}
  ]
}
```

规则：`term` 用原形（缩写保留大写）；`target` 是唯一译名；`quote` 必须可逐字定位；`occurrences` 由脚本回扫；一义多条。

## 5 题集模板

```json
{
  "case_id": "<case_id>", "language": "en", "target_language": "zh", "materials_root": "materials",
  "notes": "材料来源、篇幅、难度与要素构成",
  "output_contract": {"case_id": null, "status": null, "result": null, "claims": [], "uncertainties": []}
}
```

评分维度：实际效果 40（段落级对照、要素覆盖、数字与引用合计数）；使用增益 25（`audit_summary.rates` + `runtime.efficiency`）；
创新增益 15（术语回填、跨页续段、保护性 span、否定/限定核验）；可靠体验 10（退出码恒 0、`selfcheck`、降级矩阵）；
生态贡献 10（文档 + 术语表/题集模板 + `examples/` 最小用例）。

## 6 未译标注与对齐约定

- 未译段：`target` 留空 + `uncertain=true` + `notes` 写原因，`target_status=untranslated`，计入 `coverage_rate` 分母不计分子
- 保留原样（不译）：纯数值表行、文献条目、公式本体；按 `type` 标记，语言检查自动豁免
- 对齐：一行一段（一个 `sid`），`source` 为索引用文，`target` 为译文；不要一行多段或一段多行
- 保护性 span 中的数字/单位/引用/图表编号/公式号必须在译文里全部出现（多重集相等）
