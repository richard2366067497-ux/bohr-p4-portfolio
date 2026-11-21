# SELFTEST — plan-forge-experiment（experiment-01 v10）

本文件记录 **2026-11-21** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带数值域的本地功能用例。所有评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v10/experiment-01 \
  --case work/p4/synth_cases/experiment-01/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/experiment-01 \
  --case work/p4/synth_cases/experiment-01/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/experiment-01 \
  --case work/p4/synth_cases/experiment-01/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/experiment-01 \
  --case work/p4/synth_cases/experiment-01/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | 说明 |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 2 键（init, build） | 8 | 从材料 fenced JSON 与散文抽出参数域/对照/风险，`status=partial`（无候选方案与预算，已如实记账） |
| rich | agent | PASS | case.json:output_contract | 同上 2 键 | 8 | init → show → check → build → selfcheck 全部 exit 0 |
| boundary | single | PASS | SKILL.md (json sample) | case_id, status, plan_report, plan_revised, validation_report, arithmetic_ledger, evidence, uncertainties | 8 | 空文件 + 坏 JSON + 10 字节文本，exit 0 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 8 键 | 8 | 同上，`status=insufficient_evidence` |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

## 数值功能用例（本地，验证“真实推导”而非模板）

自带 3 参数域 × 3 版候选方案（v1 120/30/1.5、v2 200/45/2.5、v3 160/55/0.5），
材料含 3 条显式约束、3 项资源（catalyst-A 12 CNY/g 库存 30 g、vial 1.5 CNY/个、reactor-R2 有预约窗口）、
预算 200 CNY、期限 3 天、5 步工序（S3/S4 并行组 hold）与 notes.md 散文界。

- 参数域：temperature 60–180 step 10 °C、time 10–60 step 5 min、catalyst 0.5–2.5 step 0.5 g；
  散文里的三条界与 case.json 里的重复项去重后各留一条，证据各带 locator+quote。
- 工序工时：串行 20+30+15 = 65 min，并行组 hold 取 max(45, 60) = 60 min，合计 **125 min**；
  期限 3 天（按 8 h/天折 0.26 天）自检通过。
- 成本：v1 单次 4 g×12 + 6 个×1.5 = **57**，×6 次 = 342 → 超预算 → 重复数降到 3 → **171**；
  v2 单次 12 g×12 + 6×1.5 = 153，×6 = 918 → 降到 1 次 → 153；
  v3 用量 34 g 超库存 30 g → 裁到 30 g，单次 30×12 + 9 = 369 → 单次已超预算 200，如实标为不可行。
- 修订动作：v1 `reduce_replicates 6→3`；v2 `clamp 200→180`（越域）→ `satisfy C01 180→160` →
  `satisfy C03 2.5→2.0` → `reduce_replicates 6→1`；v3 `reduce_replicates 4→1` + `trim_usage 34→30`，
  每条带 `from → to` 与原因。
- 胜出：**v1（temperature=120、time=30、catalyst=1.5，3 次重复，总成本 171，工时 125 min）**，
  来源 `material`，容差带 ±1 step；四条算术自检（成本对账、预算、工时对账、日历适配）全部 ok。
- `status=answered`；`check` 对 draft（150/40/1.5）报 3/3 落在参数域内、0 个未映射键。
- 该用例 `eval_sim` single / agent 均 PASS。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`，不编造参数域；
  六要素与版本表全部给带原因的诚实记录，`limits` 说明检索范围与降级原因。
- 无 `draft.json`：`build`/`all` 用规则化候选，仍产出全部 8 个产物。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单（每次运行写入 `--output`）

result.json、plan_report.md、plan_revised.json、validation_report.json、arithmetic_ledger.json、
evidence.json、version_diff.md、reproduce.md（共 8 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。

## v10 复跑与示例数字（examples/）

随包最小样例 `examples/`（`case.json` + `params.json`：3 域 / 1 约束 / 4 资源 / 3 候选 / 2 对照 /
5 步 / risk+confirm / budget 15000 / deadline 5）可直接复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：exit 0，`status=answered`，产物 **8** 文件；
参数域 3、约束 1、资源 4、候选 3（全可行，0 硬违规 0 警告）；单次 2080、×5 = **10400** ≤ 15000，
工时 **1035** min（2.16 天 ≤ 5）；4 项算术自检全过；`evidence_stats={total:19, hits:19, rate:1.0}`；
推荐 **v1**（naoh=7, temperature=100, time=10）带 ±1 step 容差带；契约键 **8/8**；占位符 0；
规范化哈希 **`e0b5c4f9a2ece55e`**。`eval_sim` rich/boundary × single/agent 四项全 **PASS**
（rich 键 2/2 partial；boundary 8/8）。

## v10 交付状态（专家手册嵌入）

- **新增 `references/expert_playbook.md`**（专家参考手册：六步法/量化口径/风险等级/陷阱与单位/
  自查表 C01–C17/完整案例）；`SKILL.md` 明确"执行前先读 references/expert_playbook.md，按其框架/
  检查表/成本口径产出交付物"，并在 §9 自检清单加入"专家检查表逐项通过"。
- **单命令入口未受影响**：无 draft 下仍产出全部 8 件产物 + 契约逐键回填，exit 0。
- **`eval_sim.py` 四项全 PASS**；`selfcheck` 额外报告 `expert-checklist ok`。
