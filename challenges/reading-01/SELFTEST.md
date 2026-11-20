# SELFTEST — evidence-first-pdf-reader（reading-01 v6）

本文件记录 **2026-11-19** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果。所有 4 组均为 **PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-01 \
  --case work/p4/synth_cases/reading-01/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-01 \
  --case work/p4/synth_cases/reading-01/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-01 \
  --case work/p4/synth_cases/reading-01/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/reading-01 \
  --case work/p4/synth_cases/reading-01/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 10 | 11 |
| rich | agent | PASS | case.json:output_contract | 10 | 11 |
| boundary | single | PASS | SKILL.md (json sample) | 10 | 11 |
| boundary | agent | PASS | SKILL.md (json sample) | 10 | 11 |

契约 10 键：`document, blocks, sections, tables, formulas, reading_order_notes, unreadable,
sources, uncertainty, change_records`。入口为单命令 `pdf_layout_extract.py all`（kind=`single-command`）。

逐项检查（每组均 PASS）：

- `exit_code`：exit 0（含无 PDF / 空文件 / 坏 JSON 分支）。
- `result_json`：合法 JSON；`output_contract` 与顶层同名键同时存在。
- `contract_echo`：`output_contract` 覆盖全部 10 个契约键。
- `contract_values`：10/10 非空——`document` 为文档级对象，`blocks/sections/tables/formulas` 为真实抽取行，
  `sources` 为逐字引文 + locator + sha256，`unreadable/uncertainty/change_records` 为实际记录；
  无类型串 `"value"`、无 env 回显、无 missing-file。
- `deliverables`：11 个结构化产物均存在且非空。
- `placeholder_sweep`：11 个产物无 `[待写]`/`null`/`pending`/`TODO` 等占位符。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为核对（无 PDF）

- rich（仅 `task.md`，无 `materials/`、无 PDF）：`status=failed` + `limits` 明确说明
  "No PDF: page geometry … unavailable" 与 "No OCR …"；仍从 `task.md` 逐行锚定
  74 个 blocks、6 个 sections、3 个 tables、5 个 formula 候选，`sources` 6 条逐字引文。
- boundary（空 md + 坏 JSON + 10 字节 txt）：`status=failed`，坏 JSON 记入 `unreadable`，
  不中断，仍写全部 11 个产物，exit 0。
- 无 PDF 时**不臆造版面、页序、图注**；文本表逐字复制，公式只标 candidate。

## 产物清单（写入 --output）

result.json、document.json、blocks.json、sections.json、tables.json、formulas.json、
reading_order.md、sources.json、unreadable.json、uncertainty.json、change_records.json（共 11 个）。

## 包体规模

核心文件 6 个（SKILL.md、pdf_layout_extract.py、section_structure.py、evidence_reconcile.py、
audit_result.py、references/result_contract.md），另加 GITHUB_URL.txt / README.md / SELFTEST.md；
总计约 82 KB（核心约 74 KB），满足 ≤130 KB 约束。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
