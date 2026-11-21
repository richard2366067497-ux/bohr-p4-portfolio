# SELFTEST — experiment-05 v10（experiment-interpretation-dossier）

全部仅标准库、离线。逐条自测请在 `/skills/weekly-skill` 安装后执行。

## 1. 验收矩阵（eval_sim.py）

| 场景 | 模式 | 契约来源 | 结果 |
|-|-|-|-|
| rich | single（`all`） | case.json 的 output_contract（12 键） | PASS |
| rich | agent（init/check/build/selfcheck） | case.json 的 output_contract（12 键） | PASS |
| boundary | single（`all`） | 包内 SKILL.md 契约样例（12 键） | PASS |
| boundary | agent（init/check/build/selfcheck） | 包内 SKILL.md 契约样例（12 键） | PASS |

判定项：exit 0 / result.json 合法 / 契约逐键回显（顶层+嵌套）/ 9 个产物齐备 / case_id 透传 /
无占位符 / 字段完整（status·sources·uncertainties·change_records·limits）。

## 2. 空输入与坏输入

```bash
mkdir -p /tmp/e/in /tmp/e/out /tmp/e/work          # 空输入
python3 scripts/main.py all --input /tmp/e/in --output /tmp/e/out --work /tmp/e/work
echo $?                                           # 期望 0；status=insufficient_evidence

printf '{bad json' > /tmp/e/in/x.json             # 只有坏 JSON
python3 scripts/main.py all --input /tmp/e/in --output /tmp/e/out --work /tmp/e/work
echo $?                                           # 期望 0；status=insufficient_evidence（坏文件只影响自身盘点记录）
```

## 3. 定义性复算台账（可手算核对）

夹具 `[1, 2, 3, 4, 100]`，定义取自 `rules-units-and-grading.md` §1：

| 量 | 公式 | 复算值 | 期望 |
|-|-|-|-|
| 均值 | sum(x)/n | 22.0 | 22.0 |
| 样本 SD | sqrt(Σ(x-m)²/(n-1)) | 43.617657 | 43.617657 |
| 中位数 | quantile(p=0.5) | 3.0 | 3.0 |
| MAD | median(\|x-median\|) | 1.0 | 1.0 |
| 修正 z(100) | 0.6745·(x−median)/MAD | 65.4265 | 65.4265 |
| IQR 栅栏 | [Q1−1.5·IQR, Q3+1.5·IQR] | [-1.0, 7.0] | [-1.0, 7.0] |
| 相对偏差 | (calc−rep)/\|rep\| | 0.09 | 0.09 |

`recompute.json` 的 `checks.stats_definition_self_test` 报 `7 of 7`。

## 4. 端到端功能测试（数值列 → 规则候选 → 案卷）

用随包样例（`examples/readout.csv` 8 点时间序列，t=20 min 为 148.3 mg/L）复跑：

- **单命令 `all`**（无 draft）：`status=partial`，`rules=6`、`thresholds=7`、`units=6`、`series=2`、
  候选 `R1 @ M03#L6 high`（修正 z=216.96 ≫ 3.5）、`checks 4/4`、`evidence 19/19`、契约 12/12；
  两条降级如实记"未声明趋势/未声明档案"。
- **`build` + draft**：`status=answered`，`trends=1`（TR-01 @ `M03#L6`）、`dossiers=1`
  （A-001 · outlier · high · confirmed · data_quality · B）、`causes=1`（B），并渲染出
  `dossiers/anomaly-A-001.md`（8 节固定）。

## 5. draft 最小形态（专家路径）

```json
{"case_id": "example-experiment-interpretation-dossier",
 "trends": [{"trend_id": "TR-01", "scope": "Cat-X / 苯酚 / 0–35 min", "statement": "稳定 100 mg/L，t=20 单点背离",
             "locator": "M03#L6", "quote": "20,148.3", "strength": "A"}],
 "dossiers": [{"id": "A-001", "anomaly_type": "outlier", "target": "Cat-X t=20min R3",
               "locator": "M03#L6", "observed": "148.3 mg/L", "expected_or_rule": "R1 修正 z 3.5",
               "rule_id": "R1", "severity": "high", "judged": true, "verdict": "confirmed",
               "attribution": "data_quality", "attribution_basis": "修正 z=216.96≫3.5 且违反质量守恒",
               "evidence_quote": "20,148.3", "strength": "B"}],
 "causes": [{"candidate": "录入/稀释倍数错误", "support": "修正 z=216.96", "exclusion": "其余 7 点一致", "strength": "B"}]}
```

## 6. 契约回显自检

```bash
python3 scripts/main.py selfcheck --input <case> --output /tmp/e/out --work /tmp/e/work
```

期望：逐键报告 top-level 与 nested `output_contract` 双写一致、`case_id` 原样、无占位符残留，
并报 `expert-checklist ok (references/expert_playbook.md present; SC-01..SC-20 to pass)`。

## 7. v10 随包样例实测（examples/）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：exit 0，**9 件产物**，`status=partial`；
`rules=6 / thresholds=7 / units=6 / series=2`；候选 **1**（`R1 @ M03#L6 high`，修正 z 216.96）；
`checks 4/4`；`evidence 19/19（rate 1.0）`；契约键 **12/12**；规范化哈希 **`738d10527bbf27e1`**。
`build` + draft 路径：`status=answered`，`trends=1 / dossiers=1 / causes=1`，哈希 **`15fee2b8145dde03`**。

## 8. v10 交付状态（专家手册嵌入）

- **新增 `references/expert_playbook.md`**（S1–S6 六步法与门控 / §3 统计口径（趋势指标、Z·修正 Z·IQR·Grubbs
  阈值体系、功效重复数、证据强度 A/B/C）/ §4 领域陷阱与单位 / §5 交付物与自查表 SC-01…SC-20 / §6 完整案例 /
  §7 专家注意点）；`SKILL.md` 明确"执行前先读 references/expert_playbook.md，按其框架/检查表/成本口径
  产出交付物"，并在 §8 自检清单加入"专家检查表逐项通过"。
- **单命令入口未受影响**：无 draft 下仍产出全部 9 件产物 + 契约逐键回填，exit 0。
- `selfcheck` 额外报告 `expert-checklist ok`；`eval_sim.py` 四项全 PASS。

## 9. 版本

2.6.0。改脚本后必须重跑 §1–§7。
