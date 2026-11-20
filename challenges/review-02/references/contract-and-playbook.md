# 契约、工作稿与审查手册（contract-and-playbook）

本文件给出 `draft.json` 的完整 schema、`result.json` 的字段字典、`output_contract` 同义映射表，以及八步审查手册与异常处置。

## 1. `draft.json` 完整 schema

路径：`/app/work/draft.json`（也可用 `--draft` 指定）。`init` 会生成 `/app/work/draft.template.json`，其中已按 `claim_candidates` 预填 `claim_locator` 与 `claim_quote`，审查者只需改写 quote（如需）并填判定。

```jsonc
{
  "case_id": "与 case.json 一致",
  "summary": "3–6 句：审了什么、报了几类问题、最严重的是什么、哪些没能核实",

  "citation_checks": [{
    "claim_id": "CC-01",                       // 必填；缺省时保留候选编号
    "claim_text": "被核验论断（可截断）",
    "claim_quote": "本文侧逐字原文，≤420 字，须落在单个段落单元内",
    "claim_locator": "manuscript.pdf §Results P4 ¶2",
    "claim_strength": "strong|moderate|hedged",
    "cited_source": {"label": "[12] / Smith et al., 2021",
                     "source_locator_if_available": "参考文献[12] / 附件摘要 P2 §3"},
    "source_claim_if_available": "来源侧逐字原文或 null",
    "source_quote": "来源侧逐字原文或 null（有就填，能显著提高可核验性）",
    "verdict": "full_support|partial_support|no_support|undetermined",
    "semantics": {"direction_match": true, "numeric_match": null, "scope_match": false,
                  "comparator": "versus", "negation": null, "significance": "p=0.03"},
    "rationale": "三要素哪个不满足、原文怎么写的（可复核的推理链）",
    "unresolved_reason": "verdict=undetermined 必填：缺什么材料",
    "human_check_needed": "verdict=undetermined 必填：人工下一步核对什么"
  }],

  "findings": [{
    "finding_id": "F-01",                      // 可省略，build 自动编号
    "facet": "citation|fact|statistics|logic|method|compliance",
    "location": {"section": "Discussion", "locator": "manuscript.pdf §Discussion P7 ¶3",
                 "page": 7, "table_or_figure": null},
    "quote": "本文侧逐字原文，≤420 字，必须命中，不得跨段",
    "issue_type": "九种之一，见 verdict-rubric §6",
    "severity": "critical|major|minor|suggestion",
    "severity_reason": "指向 verdict-rubric §4 的锚点",
    "verdict_type": "fact_error|insufficient_evidence|compliance_issue|suggestion",
    "evidence": "判定依据：来源侧引文 / 另一处原文 / 机械核对结果（另一处的 locator 要写出来）",
    "rationale": "推理链",
    "revision": "可执行改法：改成什么句子 / 补什么对照 / 删哪句（≥6 字）",
    "claim_ref": "关联的 CC-xx（可选）"
  }],

  "coverage": {
    "citation": {"checked": true, "items": 12, "findings": 3, "note": "..."},
    "fact": {...}, "statistics": {...}, "logic": {...}, "method": {...}, "compliance": {...},
    "support_verdict": {...}, "source_reliability": {...}, "evidence_locator": {...},
    "numeric_consistency": {...}, "argument_chain": {...}
  },
  "unchecked_items": [{"item": "source_reliability", "reason": "离线无数据库权限"}],
  "uncertainties": [{"topic": "...", "detail": "...", "human_check_needed": "..."}]
}
```

字段别名容错：`claim_quote` 可写成 `quote` 或 `claim_text`；`facet` 接受 `reference/citations/统计/逻辑/规范` 等中英别名；`location` 可直接写 locator 字符串。但**枚举值不做容错**——非法 verdict/severity/facet 会被 `check` 报错并按保守值处理。

## 2. `result.json` 字段字典

顶层 = `output_contract` 的全部键（原名保留）+ 下列信封字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str/null | 与 `case.json` 一致；坏 JSON 时用正则抢救，仍取不到为 null 并记 `errors` |
| `status` | str | `completed`（有实质判定）/ `partial`（降级或有阻塞缺口）/ `input_error`（无可读材料） |
| `findings[]` | list | 问题清单，见 §2.2 |
| `citation_checks[]` | list | 核验矩阵，见 §2.1 |
| `coverage` | obj | 六类 facet + 五个专项，每项 `checked/items/findings/note` |
| `unchecked_items[]` | list | `{item, reason}` 未检查项 |
| `uncertainties[]` | list | `{topic, detail, human_check_needed}` |
| `sources[]` | list | 实际读到的文件：`source_id/rel/kind/format/parser/bytes/units/text_chars/quality/sha256_12` |
| `errors[]` | list | 硬错误（坏 JSON、解析异常、draft 不可用） |
| `degradations[]` | list | 降级缺口：`code/scope/detail`，code 见 §4 |
| `changes[]` | list | `build` 对判定的自动修正：`scope/field/from/to/rule/basis` |
| `runtime` | obj | 版本与计数；**默认不含墙钟时间**（保证两次运行字节一致），`--stamp` 才写 |
| `run_summary` | obj | `draft_used/validation_errors/validation_warnings/blocking_gaps` |
| `metrics` | obj | 计数：`citation_checks/findings/confirmed_findings/pending_findings/verdicts/severities/facets/quote_unverified/...` |
| `result` | obj | 嵌套摘要：`summary/status/metrics/top_findings/verdicts`（供契约要求 `result` 键的场合） |
| `claims` | list | 论断-判定扁平表 |
| `severity_summary` | obj | 严重度分布 |
| `revisions` | list | `{finding_id, revision}` |
| `method_notes` | obj | 规则版本、四级取值、三要素、fallback 与 quote 校验口径 |

### 2.1 `citation_checks[]`

`check_id`(=`claim_id`)、`claim_text`、`claim_quote`、`claim_strength`、`cited_source{label, source_locator_if_available}`、`source_claim_if_available`、`verdict`、`semantics{direction_match,numeric_match,scope_match,comparator,negation,significance}`、`locators{claim_loc,source_loc}`、`rationale`、`checked_evidence[]`、`quote_verified`、`unresolved_reason`、`human_check_needed`、`status`(`confirmed|pending_review`)。

### 2.2 `findings[]`

`finding_id`、`facet`、`location{section,locator,page,table_or_figure}`、`quote`、`quote_verified`、`issue_type`、`severity`、`severity_reason`、`verdict_type`、`evidence`、`rationale`、`revision`、`claim_ref`、`status`。

`quote_verified=false` 的条目 `status` 恒为 `pending_review`，且计入 `metrics.quote_unverified`。

## 3. `output_contract` 同义映射

`build` 先做字段名归一（小写、去标点），再按同义表取内容；取不到就按契约声明的类型填空值（`[]`/`{}`/`null`）并在 `degradations` 记 `contract_field_filled_empty`。**不改名、不删键。**

| 契约里可能出现的键 | 映射到 |
|---|---|
| findings / issues / problems / 问题清单 | `findings` |
| citation_checks / citation_matrix / citations / claims / 核验矩阵 | `citation_checks` |
| coverage / checklist / checks / 检查项 | `coverage` |
| summary / overview / conclusion / 结论 | `summary` |
| uncertainties / pending / limitations / 待复核 | `uncertainties` |
| unchecked_items / skipped / 未检查 | `unchecked_items` |
| sources / evidence / materials | `sources` |
| numeric_checks / numbers / statistics_checks | 统计类 findings |
| compliance_checks / compliance / norms | 规范类 findings |
| severity_summary / severity_counts | `severity_summary` |
| revisions / suggestions / recommendations | `revisions` |
| result / results / outcome | 嵌套 `result` |
| report / review_report / markdown | 主产物文件名 |
| metrics / counts | `metrics` |
| method_notes / methodology | `method_notes` |
| case_id / id / task_id | `case_id` |
| status | `status` |

契约形态支持：`{键: 规格对象}`、`{键: "类型说明"}`、`["键", ...]`、`[{name: ...}, ...]`，以及嵌在 `case.json` 的 `input/outputs/meta` 之下。

## 4. `degradations` code 表

| code | 含义 | 处置 |
|---|---|---|
| `contract_missing` | case.json 无 output_contract | 用标准信封，全部字段照常产出 |
| `no_input_files` | /input 下无可读材料 | status=input_error，不生成审查意见 |
| `unreadable_material` | 解析后文本 < 60 字符 | 相关结论 `undetermined` |
| `pdf_text_quality_low` | PDF 只能由内置流解析器读出 | locator 粒度降为页/块，需人工复核 |
| `no_reference_list` | 无参考文献表/bib | 引文全部 `undetermined` |
| `numbering_gap` | 文献表编号不连续 | 该引文 `numbering_gap`，报 `compliance` finding |
| `unpaired_citations` | 标记找不到条目 | 逐条报 `compliance`，`pending_review` |
| `numeric_conflict_candidates` | 摘要/正文同桶数值不一致 | 交由审查者确认是否分组差异 |
| `no_claim_candidates` | 未筛出候选句 | 需人工通读 units 指定对象 |
| `units_truncated` | 超过 4000 段上限 | 只审前 4000 段并声明 |
| `draft_unavailable` | 无 draft.json / 坏 JSON | 走兜底，全部 `undetermined` |
| `draft_incomplete` | draft 有必填缺失 | 仍尽量产出，缺失项 `pending_review` |
| `quote_unverified` | quote 未逐字命中 | 降级 `pending_review` |
| `contract_field_filled_empty` | 契约键无法映射 | 填空值并列出字段名 |
| `output_dir_fallback` | 输出目录不可写 | 退回 CWD 同名目录并写明 |
| `initial_partial` | init 阶段写出的初级 partial | 正常，build 会被覆盖 |

## 5. 八步审查手册

1. `init` 后看 `gaps`：材料是否读全、文献表是否存在、引文是否配对。这些决定后面能判到什么程度。
2. `show --part claims`：逐条看候选句。候选是机械筛的**全集**，不保证正确——漏掉的（纯方法/规范问题）需自己从 `units` 补。
3. `show --part refs`：把每个引文标记的配对状态记下来。`missing_entry`/`numbering_gap` 直接进 findings（`compliance`），对应论断判 `undetermined`。
4. `show --part units --offset N --limit 25`：读原文。**quote 必须从这里逐字复制**（包括标点与数字写法）。
5. 逐论断判三要素：先对象，再方向，再数值，最后范围。来源不可见就 `undetermined`，别猜。
6. 数值一致性：`show --part numbers` 给候选对；确认是否同一桶（同一指标、同一时间点、同一人群）。分组差异不是冲突。
7. 补六类 facet 中脚本不会自动发现的部分：方法设计（对照/随机化/终点）、学术规范（数据可用性/伦理/利益冲突/署名）、论证链（结论句是否有中间证据）。
8. `check` → 修 FAIL → `build` → `selfcheck`。每完成 3–5 条就 `check` 一次，避免最后一次性返工。

## 6. 六类 facet 检查清单

| facet | 逐项问 |
|---|---|
| citation | 每个标记都配对了吗？配对成功的，方向/数值/范围真的对齐吗？是否存在"引用存在但不支持"？ |
| fact | 摘要的每个数字在正文/表里都能找到同值吗？正文与图注对同一现象的描述一致吗？ |
| statistics | 样本量在摘要/方法/结果/表中一致吗？p 值与显著性表述匹配吗？百分比之和合理吗？单位统一吗？ |
| logic | 结论句有直接证据吗？是否用相关性支持因果？是否以单组结果推广全体？是否循环论证？有对照吗？ |
| method | 随机化/盲法/对照写了吗？主要终点预先定义了吗？样本量估算有依据吗？排除标准与脱落处理写了吗？ |
| compliance | 数据/代码可用性、伦理审批号、利益冲突、基金、作者贡献、重复发表风险，六项是否齐全？ |

## 7. 异常处置速查

| 现象 | 动作 |
|---|---|
| PDF 无文本层 | `init` 会记 `unreadable_material`/`pdf_text_quality_low`；该材料相关条目全部 `undetermined`，并在 `uncertainties` 写"需 OCR 或人工读页" |
| 只有摘要 | 只能审摘要内部一致性；引用支持度全部 `undetermined` |
| 文献表缺失 | 全部引文 `undetermined`，`compliance` 记一条"缺参考文献表" |
| 同一文献多版本 | 记录版本差异到 `uncertainties`，不擅自选一个判支持 |
| 引文编号与文献表错位 | `numbering_gap`；不要按"最接近的编号"猜，判 `undetermined` |
| 稿件超长 | 分页读 `units`；`units_truncated` 时在 `unchecked_items` 写明未读区间 |
| 中英混排 | 词典覆盖有限，漏检写进 `unchecked_items`，不假装查过 |
| draft 写到一半超时 | 直接 `build`：已写的条目照常产出，其余走兜底，`status=partial` |

## 8. 最小调用示例（**示例数据，仅示意接口，非正式案例结果**）

`case.json`：

```json
{"case_id": "demo-01",
 "output_contract": {"findings": {"type": "list"}, "citation_checks": {"type": "list"},
                     "coverage": {"type": "object"}, "summary": {"type": "string"}}}
```

`manuscript.md`（节选）：

```
## Abstract
We enrolled 48 patients. Survival was 82% versus 61% (p=0.03) [2].
The treatment is therefore effective in all patient populations.

## Methods
We enrolled 32 patients in a single centre.

## References
[2] Smith JA, et al. Compound X in a single-centre CKD cohort. J Renal Med. 2021;8:112-120.
```

`draft.json`（节选）：

```json
{"case_id": "demo-01",
 "citation_checks": [{"claim_id": "CC-02",
   "claim_quote": "The treatment is therefore effective in all patient populations.",
   "claim_locator": "manuscript.md §Abstract ¶1",
   "cited_source": {"label": "[2]", "source_locator_if_available": "manuscript.md §References ¶5"},
   "verdict": "partial_support",
   "semantics": {"direction_match": true, "numeric_match": null, "scope_match": false},
   "rationale": "文献表显示 [2] 为单中心 CKD 队列，正文写 all patient populations，范围超出"}],
 "findings": [{"facet": "statistics", "location": {"locator": "manuscript.md §Abstract ¶1"},
   "quote": "We enrolled 48 patients.", "issue_type": "numeric_inconsistency",
   "severity": "major", "severity_reason": "摘要与方法样本量不一致，影响分母",
   "verdict_type": "fact_error", "evidence": "§Methods ¶2 写 32 patients",
   "rationale": "同一研究两个样本量", "revision": "统一样本量或说明脱落"}],
 "coverage": {"citation": {"checked": true, "items": 1, "findings": 0}},
 "summary": "示例：样本量冲突 + 范围过度推断。"}
```

运行与示意输出：

```bash
python3 scripts/main.py check   # 61 pass / 0 fail
python3 scripts/main.py build   # status=completed; citation_checks=1 findings=1
```

生成 `/app/output/result.json`（契约四键齐全 + 信封）、`citation_report.md`、`evidence.jsonl`、`run_manifest.json`。

## 9. 维护说明

- 改判定口径 → 改 `verdict-rubric.md` 并递增 `audit_build.RULES_VERSION`。
- 新增材料格式 → 只改 `audit_core.read_any`，`result.json` schema 不变。
- 新增契约别名 → 只改 `audit_build.ALIASES`。
- 复跑一致性：无随机、无网络、`result.json` 不含墙钟时间；`selfcheck` 的 14 项可作回归测试。
- 依赖：Python ≥ 3.9 标准库；可选 `pdftotext`（poppler-utils）提升 PDF 抽取质量，缺失时自动回退内置流解析并在 `sources[].parser` 如实记录。
