# SELFTEST — experiment-05 v6（experiment-interpretation-dossier）

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
echo $?                                           # 期望 0；status=insufficient_evidence，降级含 "did not parse"
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

输入加入一份 8 行读数列 `readings.csv`（run 1–8，response_mV 平坦在 10 mV，run 7 为 120 mV），
工作稿给出一条 A-001 案卷。运行 `init → check → build`：

- 序列统计：`response_mV` n=8，median 10.15，MAD 0.15，IQR 栅栏 [9.475, 10.875]；
- 规则候选：`R1 @ M04#L8 value=120.0 severity=high`（修正 z ≈ 494 ≫ 3.5）、
  `R5 value=10.0 medium`（run 1 与 run 8 同值）；
- 案卷渲染出 `dossiers/anomaly-A-001.md`（8 节固定），`dossier_index.json` 记其 issue；
- `status=answered`（材料可读、案卷已判断、无不可读文件），逐字命中 68/68。

## 5. 契约回显自检

```bash
python3 scripts/main.py selfcheck --input <case> --output /tmp/e/out --work /tmp/e/work
```

期望：逐键报告 top-level 与 nested `output_contract` 双写一致、`case_id` 原样、无占位符残留。

## 6. 版本

2.6.0。改脚本后必须重跑 §1–§5。
