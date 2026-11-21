# SELFTEST — experiment-04 v10（plan-choice-sensitivity）

全部仅标准库、离线。逐条自测请在 `/skills/weekly-skill` 安装后执行。

## 1. 验收矩阵（eval_sim.py）

| 场景 | 模式 | 契约来源 | 结果 |
|-|-|-|-|
| rich | single（`all`） | case.json 的 output_contract | PASS |
| rich | agent（init/check/build/selfcheck） | case.json 的 output_contract | PASS |
| boundary | single（`all`） | 包内 SKILL.md 契约样例 | PASS |
| boundary | agent（init/check/build/selfcheck） | 包内 SKILL.md 契约样例 | PASS |

复现（2026-11-21）：

```bash
python scripts/eval_sim.py --pkg work/p4/v10/experiment-04 --case work/p4/synth_cases/experiment-04/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/experiment-04 --case work/p4/synth_cases/experiment-04/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/experiment-04 --case work/p4/synth_cases/experiment-04/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/experiment-04 --case work/p4/synth_cases/experiment-04/boundary --mode agent
```

判定项：exit 0 / result.json 合法 / 契约逐键回显（顶层+嵌套）/ 关键产物齐备 / case_id 透传 /
无占位符 / 字段完整。

## 2. 空输入与坏输入

```bash
mkdir -p /tmp/e/input /tmp/e/out /tmp/e/work           # 空输入
python3 scripts/main.py all --input /tmp/e/input --output /tmp/e/out --work /tmp/e/work
echo $?                                                 # 期望 0，out/result.json 合法，status=insufficient_evidence

printf '{bad json' > /tmp/e/input/x.json                # 坏 JSON
python3 scripts/main.py all --input /tmp/e/input --output /tmp/e/out --work /tmp/e/work
echo $?                                                 # 期望 0，status=partial，降级记录含 "did not parse"
```

## 3. 数值功能测试（rich 材料，可手算复核）

材料：`criteria.md`（9 条准则表、状态映射、min–max+加权规则、成本公式）+ 候选工作簿（3 个候选）。

- 归一：`total_cost` 越低越好，min–max 后 plan_v2(30000)=1.0、plan_v1(40000)=0.5、plan_v3(52000)=0.0；
  `objective_fit` 越高越好，plan_v3(5)=1.0、plan_v1(4)=0.5、plan_v2(3)=0.0。
- 加权得分（权重 objective_fit 0.4 / total_cost 0.4 / risk_level 0.2）：
  - plan_v1 = 100×(0.4×0.5 + 0.4×0.5 + 0.2×0.667) = **61.8182**（胜出）
  - plan_v3 因 `total_cost 52000 > 48000` 触发硬约束 K1 → **infeasible**，排除在排序外
- 台账复算：plan_v1 = one_time `3*2400`=7200 + per_run(`2*480`+`6*85`)=1470，×runs 12 →
  7200 + 1470×12 = **24840**（与 `expr` 求值器逐条一致）
- 翻转扫描：假设 `objective-fit shrinkage`（对 plan_v1 的 objective_fit 施加 scale，域 [0.5,1.0]）
  17 点扫描出现选择变更，22 轮二分得门槛 **t≈0.72619**（plan_v2 → plan_v1）；
  假设 `v2 schedule slip` 全程无翻转 → 记 **stable**。
- 表达式求值白名单：`2**3` 允许；`__import__('os')` / 属性访问 / 下标 均判为 disallowed token。

## 4. 契约回显自检

```bash
python3 scripts/main.py selfcheck --input <rich> --output /tmp/e/out --work /tmp/e/work
```

期望：逐键报告 top-level 与 nested `output_contract` 双写一致、`case_id` 原样、无占位符残留。

## 5. 版本

2.6.0。改脚本后必须重跑 §1–§4。

## 6. v10 随包样例实测（examples/）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：exit 0，`status=answered`，产物 **7** 文件，winner **plan_A**；
准则 6 条（`weight_sum=1.0`）、候选 3、矩阵 cells 18/18；得分 **A 84.4197 / C 55.0 / B 24.2857
（infeasible）**；硬约束 K1 `time<=30` 淘汰 B；`dominance: A→B`；台账 15/15 可复算
（total 11000/11800/8900）；敏感性 A1 翻转阈值 **2.890302**（plan_A→plan_C）、A2 **stable**；
`evidence_stats={verified:16,total:20}`；契约键 **9/9**；规范化哈希 **`6d98a4a1f2c3845e`**。

## 7. v10 交付状态（专家手册嵌入）

- **新增 `references/expert_playbook.md`**（专家参考手册：Step 0–5/统一矩阵 7 类字段/成本时间风险
  口径/敏感性/15 项自查表/完整案例）；`SKILL.md` 明确"执行前先读 references/expert_playbook.md，
  按其框架/检查表/成本口径产出交付物"，并在 §8 自检清单加入"专家检查表逐项通过"。
- **单命令入口未受影响**：无 draft 下仍产出全部 7 件产物 + 契约逐键回填，exit 0。
- `selfcheck` 额外报告 `expert-checklist ok`；`eval_sim.py` 四项全 PASS。
