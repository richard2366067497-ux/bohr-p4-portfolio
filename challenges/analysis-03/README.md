# figure-publisher（v6 修复包）

把输入的数据表**真正渲染成图表**：矢量 SVG + 矢量 PDF，统计数字与图一一对应，图上的每个元素都能
回溯到源数据单元格。**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 交付物（`/app/output`）

`figure_report.md`、`stats.json`、`figure_data.json`、`figures/figure_1.svg`、
`figures/figure_1.pdf`、`figures/figure_code.py`、`result.json`。

## 为什么这样改

上一版只在**文件体积清单**上画了一张 SVG，从未把输入数据渲染成图：统计与视觉脱节，
图形元素无法回溯到源数据，也没有可运行的绘图代码。本版改为**由数据驱动渲染**并补齐回溯与复现。

## 设计要点

- **数据驱动**：解析 csv/tsv/json/jsonl/sqlite → 选数值列 → 按结构选图型（柱状 / 折线 / 散点）。
- **双矢量输出**：同一份图元同时写 SVG 与 PDF（base-14 Helvetica），`pdftoppm`/`convert` 可栅格化。
- **统计可回算**：`stats.json` 的 n/均值/中位数/标准差/四分位/极值均由图源列重算，与图同一份数据。
- **元素可回溯**：`evidence_map` 逐元素给出 `<file>#row<n>` 定位。
- **可复现**：`figure_code.py` 读 `figure_data.json` 重画 SVG，无外部依赖。
- **优雅降级**：空目录 / 坏 JSON / 无数值列 → 退化为文件字节盘点图并**明确标注**，不伪造科学数值；
  退出码恒 0，仍输出全部交付物与合法 `result.json`。
- **标记不改值**：源文件只读；图表标签只做必要的占位符中和，数值原样保留。

## 目录

```
SKILL.md                     题面式技能说明（第一条即单命令入口）
README.md                    本文件
SELFTEST.md                  自测记录
GITHUB_URL.txt               仓库地址
environment/resources.yaml   运行时与输入/输出资源清单
scripts/engine.py            单命令入口：解析 / 统计 / 渲染 / 回溯 / 降级
references/figure-specs.md   数据→图型选择规则、坐标与输出约定
examples/README.md           一个最小可跑示例
```
