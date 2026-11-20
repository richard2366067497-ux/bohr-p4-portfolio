# 工作稿 schema 与判定口径（`draft.json`）

`draft.json` 是本 Skill 的**唯一事实源**：脚本只负责把它的内容变成矩阵、findings、报告与 `result.json`，并按下面的规则逐条做机械校验。字段名不要改；`row_id` 不要改（改了会与目录种子脱钩，被当作新增行）。

## 1. 顶层结构

```json
{
  "case_id": "由 init 从 case.json 读出，可原样保留",
  "doc_meta": {"title": "", "doc_type": "manuscript|report|thesis_chapter",
                "venue_name": "", "guideline_present": false, "guideline_note": ""},
  "compliance_matrix": [ /* 行，见 §2 */ ],
  "citation_reconciliation": [ /* 引用-文献表对账，见 §4 */ ],
  "pii_ledger": [ /* 可识别信息台账，见 §5 */ ],
  "uncovered_requirements": [ {"requirement": "", "reason": ""} ],
  "summary": "3 行以内结论（会插到报告第 1 节前）",
  "uncertainties": ["..."]
}
```

`init` 生成的 `draft.template.json` 已经把 33 个种子行、悬空/孤立引用、PII 候选都填好，**复制成 `draft.json` 再改成判断**，比从零写快得多，也不会漏行。

## 2. 矩阵行字段字典

| 字段 | 必填 | 取值 / 写法 | 校验点 |
|---|---|---|---|
| `row_id` | 是 | 目录种子 id（`INT-01`…`DEC-09`），不要改名 | 重复 → `row_id_duplicate` |
| `domain` | 是 | `integrity` `citation_norm` `privacy` `copyright` `ethics` `venue` `declaration` | 越界 → `domain_invalid`；某 domain 无行 → `domain_uncovered` |
| `rule_source` | 是 | `ethical_norm` `venue_guideline` `provided_policy` `general_practice` `internal_consistency` | 越界 → `rule_source_invalid` |
| `requirement` | 是 | 一句可核对的要求（"稿件应……"），**不写条款号** | 编造编号 → `invented_identifier` |
| `expected` | 建议 | 满足时应当长什么样（可核对） | — |
| `observed` | 建议 | 实际观察到的内容或"检索未找到" | 影响报告可读性 |
| `verdict` | 是 | `compliant` `violation` `not_applicable` `unverifiable` | 空/越界 → `verdict_invalid` |
| `doc_id` | 条件 | `D1`…`Dn`（`show` 打印的 id） | 缺失但引文命中 → `doc_id_missing` 警告 |
| `evidence_locator` | violation 必填 | `p3#para7` 形式，取自 `show` | violation 缺 → `evidence_missing` |
| `quote` | violation 必填 | **逐字**原文片段（不改写、不翻译、不拼接） | 找不到 → `quote_not_found`；与该 locator 段落不符 → `locator_quote_mismatch` |
| `searched_scope` | `not_applicable` 必填 | "检索了 §1–§6 与文献表，关键词：IACUC/animal/mice" | 缺 → `not_applicable_no_scope` |
| `severity` | violation / unverifiable 必填 | `critical` `major` `minor` `suggestion` | 缺 → `severity_missing`；越界 → `severity_invalid` |
| `severity_reason` | severity ≥ minor 必填 | `<事实> → <后果> → 因此为 <档位>` | 缺 → `severity_reason_missing` |
| `remediation` | violation 必填 | 可执行动作（改哪里、加什么、向谁确认） | 缺 → `evidence_missing` |
| `what_human_must_check` | `unverifiable` 必填 | "查 DOI 10.xxxx/yyy 的原文作者列表与结论" | 缺/过短 → `unverifiable_no_human` |

`rule_source=general_practice` 的行如果给了 `critical`/`major`，会被判 `severity_overstated`：通行实践不是硬性规范，最高只能是 `minor`。

## 3. 判定的三种失败模式（对照写）

| 写法 | 结果 | 为什么 |
|---|---|---|
| `{"row_id":"DEC-04","verdict":"violation","requirement":"利益冲突声明缺失","severity":"major"}` | `evidence_missing` ×3 | 没位置、没原文、没整改 → 评审无法核对，也无法执行 |
| `{"row_id":"CITE-06","verdict":"compliant","requirement":"文献真实","observed":"看起来都是正规期刊"}` | `compliant_without_evidence` 警告 | 离线无法核实存在性 → 应写 `unverifiable` + 人工核对 DOI |
| `{"row_id":"VEN-02","rule_source":"venue_guideline","verdict":"violation","severity":"major"}` | `guideline_basis_unavailable` | 输入里没有指南文本，声称违反指南就是编造 |

正确写法（示例，非正式案例结果）：

```json
{
  "row_id": "DEC-04", "domain": "declaration", "rule_source": "ethical_norm",
  "requirement": "稿件应有独立的利益冲突声明，覆盖全体作者",
  "expected": "参考文献之前的独立小节，逐作者说明财务/非财务利益或无冲突",
  "observed": "全文检索 conflict of interest / competing interests / 利益冲突，仅在投稿信模板中出现，正文无声明",
  "verdict": "violation", "doc_id": "D1", "evidence_locator": "p5#para2",
  "quote": "Acknowledgements: We thank the participants of the pilot survey.",
  "searched_scope": "",
  "severity": "major",
  "severity_reason": "多数期刊把 COI 声明列为强制项，缺失会在投稿阶段被退回 → 发表前必改 → major",
  "remediation": "在致谢之后新增『利益冲突声明』小节，逐作者说明；如存在财务关系须列明资助方与角色。",
  "what_human_must_check": ""
}
```

注意上例的 `quote` 引的是"本该出现 COI 的位置上的实际文本"——这是**位置证据**，用来证明"这里没有声明"。反面示例是引一句与结论无关的句子。

## 4. `citation_reconciliation`（引用-文献表对账）

| 字段 | 说明 |
|---|---|
| `marker` | 正文标记：`[12]`、`(Smith et al., 2019)` |
| `claim_locator` / `claim_quote` | 标记所在的正文位置与逐字片段（能引就引） |
| `ref_entry` | 文献表中的对应条目，**逐字**复制（`show` 的 `ref[n]` 行） |
| `match` | `consistent` `dangling` `duplicate` `mismatch` `unverifiable` `no_reference_list` |
| `note` | 非 `consistent` 必填：差在哪里（编号、作者、年份、主题） |

- `dangling`：正文有标记、文献表无该编号（init 的 `dangling` 列表已给出候选）。
- `orphan`（文献表有、正文未引）：写成 `match=unverifiable` 或 `duplicate`，并在 note 说明"正文未见引用"，不要硬塞 `mismatch`。
- `mismatch`：标记指向的条目与正文论断不符（作者/年份/主题/研究类型）。
- 材料无文献表：整表给一行 `match=no_reference_list` + note。

## 5. `pii_ledger`（可识别信息台账）

```json
{"ledger_id": "PII-01", "pii_type": "email", "location": "p2#para6",
 "redaction": "[REDACTED-EMAIL]", "rationale": "通讯作者邮箱属可识别信息，正式发布前应确认是否必须公开"}
```

- `pii_type`：`email` `phone` `id_number` `patient_id` `name_pattern`。
- `location` 必填（`pii_location_missing`）。
- **台账内不得出现真实 PII**（`pii_not_redacted`）：只写类型、位置、`[REDACTED-*]` 占位。报告渲染时会自动遮罩正文引文里的 PII，所以不要把原值抄进台账"留证据"——证据靠 locator。

## 6. `uncovered_requirements`

材料缺失导致的审查空白（"目标期刊没说 → 字数上限无法核对"）。每条给 `requirement` + `reason`。这些会进 `result.json.pending_human` 与报告第 3 节，是"诚实"的加分点，不是减分项。

## 7. 写工作稿的最小顺序

1. `show` 看材料和种子行（先 `--domain declaration`，声明区块最容易出确定结论）；
2. 一个 domain 一个 domain 地写，先写有逐字证据的行（violation），再写 `compliant`，最后处理 `not_applicable`/`unverifiable`；
3. `check` → 按 `FIX` 逐条改；
4. `build` → `selfcheck` → 需要时只补被 FAIL 的那几行。
