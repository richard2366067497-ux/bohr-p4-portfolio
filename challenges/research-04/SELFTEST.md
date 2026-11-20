# SELFTEST — research-frontier-event-timeline（research-04 v6）

本文件记录 **2026-11-19** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果。所有 4 组均为 **PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/research-04 \
  --case work/p4/synth_cases/research-04/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/research-04 \
  --case work/p4/synth_cases/research-04/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/research-04 \
  --case work/p4/synth_cases/research-04/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/research-04 \
  --case work/p4/synth_cases/research-04/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | case_id, deliverable, evidence_map, change_log, coverage, status | 12 |
| rich | agent | PASS | case.json:output_contract | 同上 6 键 | 12 |
| boundary | single | PASS | SKILL.md (json sample) | research_summary, events, trend_stats, stage_division, turning_points, gaps, evidence_matrix, uncertainty | 12 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 8 键 | 12 |

逐项检查（每组均 PASS）：

- `exit_code`：入口 `scripts/main.py all` 退出 0（约 0.5–2 s）。
- `result_json`：合法 JSON（rich 约 43 KB），含 `output_contract` 与顶层同名键。
- `contract_echo`：`output_contract` 覆盖全部契约键。
- `contract_values`：无 empty / placeholder / missing-file；`deliverable` 指向真实 `trend_report.md`，
  `evidence_map`/`change_log`/`coverage` 为真实派生结构，`case_id`/`status` 为实际值。
- `deliverables`：`trend_report.md`、`timeline.md`、`result.json` 均存在且非空。
- `case_id`：`synth-rich-research-04` / `synth-boundary-research-04` 原样透传。
- `placeholder_sweep`：12 个产物无 `[待写]`/`null`/`pending`/`TODO` 等占位符。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 10 字节文本）：`status=partial`，不编造年份；
  `events/stage_division/turning_points/gaps` 用带 `search_scope`/`basis` 的诚实 no-data 结构，
  `limits` 4 条说明检索范围与降级原因。
- 无 `draft.json`：`all` 自动使用规则化候选台账（`auto=true`、`confidence=low`），仍产出全部 12 个产物；
  `degradations` 与 `pending_human` 提示需人工复核。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单（每次运行写入 --output）

result.json、events/event_ledger.jsonl、events/event_sources.json、timeline.md、trend_report.md、
derived/trend_stats.json、derived/stage_division.json、derived/turning_points.json、derived/gaps.json、
derived/representative_works.json、figures/timeline.svg、figures/figure_specs.json（共 12 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
