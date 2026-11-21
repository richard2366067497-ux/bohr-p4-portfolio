# GAIN_EVIDENCE — writing-08 v10 可核验记录

本文件只记录**本包内可重跑**的检查与实跑结果；不含未经对照的增益自评分，也不含预制正式案例答案。

## 1 能力面（对应判分要点）

| 能力 | 落点 | 可核验方式 |
|---|---|---|
| 要素齐全 | `evidence_matrix.csv` + `coverage.json` | 查看 `coverage.json` 逐要素状态 |
| 参数一致 | 正文与 `parameter_ledger.csv` 同源渲染，冲突标 `conflict_flag` | 对照 `manuscript.md` 与台账取值 |
| 来源可追溯 | 事实带 `source_id` + `locator` + 逐字 `quote` | `fact_ledger.csv` 的 locator 可在材料中命中 |
| 缺口显式 | `gaps.md`（缺什么 / 影响 / 需谁确认 / 追问） | `gaps.md` 与 `result.json.uncertainties` |
| 冲突不静默 | 冲突并列保留并写 `conflicts.md` | 构造同一参数两个取值即可复现 |
| 诚实信封 | `status/sources/uncertainties/change_records/limits/errors/degradations` | `result.json` 逐键存在且非空壳 |

## 2 实跑记录（2026-11-21，本机）

- 单命令 `python3 scripts/main.py run ...` → exit 0；rich 案例 `status=partial`（工作稿缺失，自动抽取
  兜底），7 产物 + `result.json`，自检 `PASS 产物齐备、JSON 合法、契约字段齐全（顶层 + 嵌套）`。
- `scripts/eval_sim.py`：rich/boundary × single/agent **4/4 PASS**，exit_code、result_json、contract_echo、
  deliverables、case_id、placeholder_sweep、field:* 全 PASS，无 FAIL / WARN。

## 3 对照口径

使用增益须由外部评测以同输入、同约束、同计时口径对照基础 Agent 产生，本包不自报分数；此处列出的
是可复跑的行为证据（产物齐备、定位可命中、缺口可复现），供评测方做独立对照。
