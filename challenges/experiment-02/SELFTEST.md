# SELFTEST — plan-feasibility-review（experiment-02 v6）

本文件记录在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带资源台账与三版本候选方案的本地
功能用例。所有评测均为 **PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v6/experiment-02 \
  --case work/p4/synth_cases/experiment-02/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v6/experiment-02 \
  --case work/p4/synth_cases/experiment-02/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v6/experiment-02 \
  --case work/p4/synth_cases/experiment-02/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v6/experiment-02 \
  --case work/p4/synth_cases/experiment-02/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | 说明 |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 11 键（case, case_id, plan, equipment, material, booking, budget, domains, approval, source, task） | 9 | 材料为规则与统计规范，无具体资源对象，诚实降级 `insufficient_evidence` |
| rich | agent | PASS | case.json:output_contract | 同上 11 键 | 9 | init → draft → check → build → selfcheck 全部 exit 0 |
| boundary | single | PASS | SKILL.md (json sample) | 同上 11 键 | 9 | 空文件 + 坏 JSON + 10 字节文本，exit 0 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 11 键 | 9 | 同上，draft 为 `{}` 仍全流程通过 |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 数值功能用例（本地，验证"真实推导"而非模板）

用一个自带资源与三版本候选方案的用例跑 `scripts/main.py all`：

- 资源：设备 `centrifuge`（已具备）、`sequencer`（需采购，货期 21 d）；耗材 `kit` 单价 120、
  用量 2、货期 5 d；机时 `sequencer slot` 日费 200、窗口 3 d；预算 500。
- 参数域：temperature 60–180 step 10 ℃。
- 三版本：v1（temperature 150）单次成本 240+600=… 可行；v2（temperature 190）越界被标 blocked；
  v3（temperature 150，步骤更多）成本更高但可行。
- 七大项 × 3 版本逐项判定；排序键 = 可行 → 不可行项数 → 单次成本；胜出为成本最低的可行版本。
- 自检：步骤行之和 = 单次时长；成本行之和 = 单次成本；预算上限出现；版本数 > 0；胜出可行。

该用例与 rich/boundary 均通过 `eval_sim`（single / agent）。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`，不编造资源或域；
  `checks.json/estimate.json/risks.json/confirmations.json` 给带原因的非空结构，`limits` 说明
  检索范围与降级原因。
- 无 `draft.json`：`build`/`all` 使用规则化路径，仍产出全部 9 个产物；`degradations` 与
  `uncertainties` 提示需人工复核。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单（每次运行写入 --output）

result.json、feasibility_review.md、checks.json、estimate.json、risks.json、
confirmations.json、evidence.json、version_diff.md（共 8 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
