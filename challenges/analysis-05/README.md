# analysis-05 — sci-analysis-dag (v6)

把科研材料里的数据表做成一条可复核的分析流水线：**导入 → 清洗（行数守恒）→ 描述与推断统计
→ 真实 SVG 图件 → 报告**。所有打印出来的数字都来自同一套登记表（`verification.json`），
报告文本、`stats.json` 与图件共享同一事实源。

## 包内文件

| 文件 | 字节 | 作用 |
|---|---|---|
| `SKILL.md` | 契约样例、单命令入口、产物清单、降级矩阵 |
| `scripts/main.py` | CLI 与编排：跑 DAG、回填契约、写 `result.json` |
| `scripts/engine.py` | 引擎库：导入 / 清洗 / 统计 / 渲染 SVG |
| `references/method-notes.md` | 统计口径与清洗规则的说明 |
| `README.md` / `SELFTEST.md` / `GITHUB_URL.txt` | 说明与自检 |

纯标准库（csv, json, math, sqlite3, hashlib, re, pathlib）；无网络、无时钟，重复运行字节稳定。

## 单命令入口

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

退出码恒为 0。`init / show / check / build / selfcheck` 是等价的复核入口，均接受
`--input / --output / --work / --case`。

## 关键推导示例（真实可复算）

用一张 12 行三组实验表（`group, yield_pct, temp_c, duration_min`）跑同一条命令，引擎从原始行
现算得到：

- 清洗：rows_in=12，rows_out=12，重复 0，填补 0，丢弃 0，行数守恒成立。
- 描述：`yield_pct` mean=68.1083，sd=3.5897，median=68.8；`temp_c` mean=190.3333。
- 单因素 ANOVA：F=49.6602，df=(2,9)，p≈1.4e-5，η²=0.9169（组间差异大）。
- Pearson：r=−0.8962，p≈8e-5（`yield_pct` 与 `temp_c` 强负相关）。
- 简单 OLS：`yield_pct = 326.42 − 1.998·temp_c`，R²=0.8031。
- 图件：`figures/figure_01.svg`（组均值±SD 柱图）、`figures/figure_02.svg`（散点+拟合线）。

上述数字均写在 `stats.json` 并经 `verification.json` 登记；用同一输入复跑得到相同结果。

## 契约回填

`result.json` 的 `output_contract` 逐键回填，并在顶层同名键回显；`case_id` 原样透传。
用例声明的键优先，未声明的用 SKILL 默认键；无法直接映射的键写成结构信封
`{"kind","items","count","note"}`。写出前统一做占位符清理。

## 降级

空输入 / 坏 JSON / 无数据表 → 仍然退出 0、写出合法 `result.json`（`status=partial|input_error`）
与全部交付物；无数据表时只画输入盘点图并显式声明 `no_tabular_data`，绝不编造测量值。
