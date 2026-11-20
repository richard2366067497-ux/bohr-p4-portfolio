# SELFTEST — sci-lit-bilingual-audit（reading-03 v9）

**2026-11-20** 实测记录（Windows + Python 3.12.14；评测器：仓库根 `scripts/eval_sim.py`，本地仿真沙箱，纯标准库）。

## 1 评测结论：4/4 PASS（0 FAIL、0 WARN）

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | **PASS** | case.json:output_contract | 5 键 | 6 | insufficient_evidence |
| rich | agent | **PASS** | case.json:output_contract | 5 键 | 6 | insufficient_evidence |
| boundary | single | **PASS** | SKILL.md (json sample) | 5 键 | 6 | insufficient_evidence |
| boundary | agent | **PASS** | SKILL.md (json sample) | 5 键 | 6 | insufficient_evidence |

契约键均为 `case_id, status, result, claims, uncertainties`。逐项 PASS：`exit_code`、`result_json`、`contract_echo`、
`contract_values`、`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

复现：

```bash
python scripts/eval_sim.py --pkg  work/p4/v9/reading-03 --case work/p4/synth_cases/reading-03/rich     --mode single
python scripts/eval_sim.py --pkg  work/p4/v9/reading-03 --case work/p4/synth_cases/reading-03/rich     --mode agent
python scripts/eval_sim.py --pkg  work/p4/v9/reading-03 --case work/p4/synth_cases/reading-03/boundary --mode single
python scripts/eval_sim.py --pkg  work/p4/v9/reading-03 --case work/p4/synth_cases/reading-03/boundary --mode agent
```

agent 模式实际执行 7 步（退出码全 0）：`init` → 写入包内示例工作稿 → `check` → `build` → `selfcheck` → `compare`
→ `all`（单命令入口在文档中排最后，因此最后一步重新装配出完整产物集）。

## 2 包内功能用例（`examples/`）实测

`python scripts/main.py all --input examples --output <out> --work <work>`：
`status=answered`、`segments=17`、`translated=17`、`audit_fail=0`；核验 16 项全 `pass`（fail/warn/skip 均为 0）；
指标率全 1.0（`coverage_rate`、`glossary_consistency`、`span_retention`、`negation_rate`、`hedge_rate`、
`element_coverage`、`quote_verbatim`）；要素覆盖 13/13（`caption_figure=1 caption_table=1 formula=1 heading=5
reference=2 table_row=3`）；术语 4 条 locked、38 条 candidate。

`selfcheck` 逐项（`work/selfcheck_report.json`，`ok=true`）：`exit_code` / `result_json` / `contract_echo`（5/5 已回显）/
`contract_values`（空值键: 无）/ `deliverables`（缺失产物: 无）/ `substantive`（无小于 40 字节的产物）/
`placeholder_sweep`（占位符命中: 无）/ `status_field` / `case_id` / `field:sources` / `field:uncertainties` /
`field:change_records` / `field:limits` / `pairs_rows`（段落对 17 行）/ `degrade_graceful`（降级路径
status=insufficient_evidence；缺失键=无 空值=无 产物问题=无）—— 全 PASS。

## 3 降级路径实测

| 场景（真实构造） | 结果 |
|-|-|
| rich/boundary 用例：空材料目录、0 字节文件、坏 JSON、只有占位符的 txt | 退出码 0；`status=insufficient_evidence`；仍产出 **6 个非空、无占位符**的产物，契约键全回显 |
| `selfcheck` 的 `degrade_graceful`：自动构造空文件 + 非法 JSON + `[占位符]` 文本 + `output_contract: null` | PASS（缺失键=无、空值=无、产物问题=无） |
| 只有占位符的页/空白页 | 整页判不可用并跳过（`placeholder_or_empty_pages_dropped`、`skipped`） |
| `case.json` 损坏 | 字面抢救 `case_id` 与契约键名（`case_json_salvaged`），不编造取值 |
| 工作稿段号与索引对不上 | 按无工作稿处理（`draft_sids_match_zero_segments`），不臆造译文 |

## 4 缺陷注入复现（核验器确实在拦人）

临时改 `work/draft.json`（不动包内示例）：① 删掉 `S003` 译文里的 `[1]`；② 把 `S013` 的否定关系改成肯定句。

```
exit=0  status=partial  segments=17  translated=17  audit_fail=3
fail_by_check = {citations: 1, negation: 1, protected_numbers: 1}
FAIL protected_numbers S003 数字/单位缺失: 1
FAIL citations         S003 文献引用编号缺失: 1
FAIL negation          S013 原文该句含否定/限制成分，对应译文未出现否定标记（第 2 句）
human_review = [S003 protected_numbers, S003 citations, S013 negation]（每条带"怎么修"）
```

即：删一个引用编号会被抓（`citations` + `protected_numbers` 命中同段），改否定关系会被抓且**定位到句**，
`status` 自动从 `answered` 降到 `partial`（工作稿自报状态不覆盖核验结论）。

## 5 确定性复现

同输入连跑两次：`paragraph_pairs.jsonl`、`audit_report.json`、`glossary.json`、`bilingual_review.md` **逐字节一致**；
`result.json` 除 `runtime` 与 `change_records[].seconds` 计时字段外**逐值一致**；`run_log.txt` 只差秒数。

## 6 示意输出（节选，来自实测运行）

```json
{"sid": "S003", "locator": "p1:S003", "page": 1, "pages": [1], "type": "body", "section": "abstract",
 "source": "Seed germination of table salt (NaCl) treated samples was measured at 20 °C, ... [2].",
 "target": "在 20 °C 下测定了经食盐（NaCl）处理样品的种子萌发情况，...（表 1），拟合系数为 r = -0.93（p < 0.01）[1]。",
 "target_status": "translated", "protected_spans": ["20", "92.4", "150", "1", "74.6", "0.93", "0.01"],
 "terms": ["NaCl", "germination rate"], "uncertain": false, "basis": "逐段对照翻译；数字/单位/引用编号/公式号按原文保留"}
```

`work/compare_report.json`（基线搬运 vs 本 Skill）：`paragraphs_aligned 0→17`、`locators 0→17`、`span_checks 0→4`、
`glossary_locked 0→4`、`audit_checks 0→16`、`deliverables 1→6`。

## 7 自检覆盖不到的（诚实声明）

- **语义质量**：通顺度、措辞、译名是否最优——机械核验不判断，只列 `human_review`
- **扫描件 OCR**：无文本层 PDF 一律降级（不内置 OCR，也不假装识别）
- **极端排版**：表格套表格、脚注混排、图文混排的切段需人工确认（记 `warnings`）
- **术语该不该进表**：候选按频次与形态排序给出，是否锁定由人/Agent 决定
