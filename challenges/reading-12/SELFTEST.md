# SELFTEST — extraction-table-cleaner（reading-12 v9）

本文件记录 **2026-11-20** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带语料的本地功能用例。所有评测均为
**PASS（0 WARN，0 FAIL）**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v9/reading-12 \
  --case work/p4/synth_cases/reading-12/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-12 \
  --case work/p4/synth_cases/reading-12/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/reading-12 \
  --case work/p4/synth_cases/reading-12/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-12 \
  --case work/p4/synth_cases/reading-12/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 6 键（case_id, deliverable, evidence_map, change_log, coverage, status） | 11 | insufficient_evidence |
| rich | agent | PASS | case.json:output_contract | 同上 6 键 | 11 | insufficient_evidence |
| boundary | single | PASS | SKILL.md (json sample) | 6 键（case_id, status, deliverable, evidence_map, change_log, coverage） | 11 | insufficient_evidence |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 6 键 | 11 | insufficient_evidence |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

> rich 用例的材料是字段字典 + 规则目录 + 单位表三份 JSON，**不含提取记录**：清洗器据此诚实降级为
> `insufficient_evidence`，仍写出全部 11 件产物（每件带结构化 no-data 记录与检索位置），不臆造任何数值。
> boundary 用例（空文件 + 坏 JSON + 占位文本 + 契约置空）同样降级，并回落到 SKILL.md 的默认契约键；
> 占位符扫描 0 命中。

## 功能用例（本地，验证「真解析 + 真换算 + 真分组」而非模板）

`examples/`（`case.json` + `params.json` + `records.json`）复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = partial`，产物 **11** 文件。
- 覆盖：`records_in 22 / rows_out 22`；`converted 4`、`missing 1`、`needs_review 4`、
  `merged_duplicate 1`、`replicate 9`、`conflict 4`；`changes 24`、`queued_for_review 9`、
  `unmapped_columns 0`、`rules_available 17`、`units_available 11`。
- 单位换算逐行可复算（`change_log.csv`，误差只缩放不加偏移）：
  - `P2-01` 1.5 M → 1500.0 mM（×1000.0 + 0.0）
  - `P2-03` 1.49e6 uM → 1490.0 mM（×0.001 + 0.0）
  - `P3-02` 1074 K → 800.85 C（×1.0 − 273.15）
  - `P4-01#2` 35900 mg → 35.9 g（×0.001 + 0.0）
- 同义归一（精确命中才改）：`table salt → NaCl`、`sodium chloride → NaCl`、`potassium chloride → KCl`、
  `melting point → melting_point`；`NaCl`/`KCl` 本就规范的行不再记为变更。
- 判断键分组：j1 完全相同 → `merged_duplicate`（`duplicate_of=P1-01`）；j1b/j2/j3 容差内 → `replicate`
  （逐条保留、不取平均）；j1d（13.0%）与 j2c（28.6%）超容差 → `conflict`（双方保留并挂起）。
- 解析边界：`800 to 802` 拆成 low/high（点值留空）；`1.50 ± 0.02` 误差单独成列并缩放；
  `~`/`+/-`/千分位/科学计数均解析；`a.u.`（未知单位）、`%`（歧义）、空单位（`R013`）、
  `about 36`（不可解析，`R006`）、`n/a`（缺失，`R008`）一律**挂起**且清空数值，不臆造。
- 标识：缺 `row_id` 的行派生 `derived-21`（`R002`）；重复标识 `P4-01` 追加为 `P4-01#2`（`R002`），两行不合并。
- 契约键 **6/6** 逐键回填（顶层 + `output_contract`）；占位符扫描 **0**。
- 规范化哈希（`result.json` 删除 `runtime` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`1228dc54cbe7b180`**。

## 边界行为核对（异常处理）

- `boundary`（空文件 + 坏 JSON + 占位文本）：无提取记录、无字段字典/单位表可解析，
  `status=insufficient_evidence`；`cleaned.csv`/`change_log.csv`/`pending_review.csv`/`evidence_map.json`/
  `coverage.json` 用带原因的诚实 no-data 结构（CSV 也写说明行而非空文件）。
- 坏 JSON：`parse_status=parsed` 但解析失败 → 不作素材，不被引用。
- 占位文本（`notes.txt`）：`parse_status=placeholder-only`，跳过且净化，不出现在任何产物。
- 指令文件（`task.md`）：显式排除在提取记录来源之外。
- 有数值但单位未知/歧义/缺失 → 该行 `needs_review` 并清空数值，写 `pending_review.csv`（`R012`/`R013`）。
- 量纲不符（质量 vs 物质的量）：挂起为 `dim_mismatch`（`R020`），不硬换。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`；顶层异常也保全 `result.json`。
- 无 `draft.json`：`build`/`all` 使用确定性清洗规则，仍产出全部产物；`draft_used=false`。

## 产物清单（每次运行写入 --output）

result.json、cleaned.csv、change_log.csv、pending_review.csv、anomaly_report.md、rules.json、
field_mapping.json、unit_table.json、evidence_map.json、coverage.json、run_log.txt。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
