# 自测记录 · figure-publisher v7

## 1. 运行环境

- Python 3.12（纯标准库：csv / json / sqlite3 / re / pathlib）。
- 入口：`python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work`。
- 渲染无第三方依赖：SVG 直接拼装；PDF 由内置写入器生成（base-14 Helvetica，无嵌入字体需求）。

## 2. 验收矩阵（`scripts/eval_sim.py`）

| 案例 | 模式 | 结果 | 失败 | 警告 | 契约来源 |
|---|---|---|---|---|---|
| rich | single | PASS | 0 | 0 | case.json:output_contract |
| rich | agent | PASS | 0 | 0 | case.json:output_contract |
| boundary | single | PASS | 0 | 0 | SKILL.md (json sample) |
| boundary | agent | PASS | 0 | 0 | SKILL.md (json sample) |

交付物：`figure_report.md`、`stats.json`、`figure_data.json`、`figures/figure_1.svg`、
`figures/figure_1.pdf`、`figures/figure_code.py`、`result.json`。

## 3. 真实出图演练（7 行样例表）

输入 `iris.csv`（`species,sepal_length,petal_length`，7 行）：

- 两个数值列 → 散点图 `figure_1.svg` + `figure_1.pdf`，7 个点 `(sepal_length, petal_length)`。
- 单数值列 + 分类列 → 柱状图 `figure_2.svg` + `figure_2.pdf`，类目为 `species`。
- `stats.json`：`n=7`、均值 4.142857、中位数 4.7、标准差 1.810175、min 1.4、max 6.0（散点序列），
  数字与图共用同一份取值，可逐点回算。
- `evidence_map`：`figure_2.svg` 元素 `series[0]` = 5.1 ← `iris.csv#row2`。

渲染产物的机械校验：

| 检查 | 结果 |
|---|---|
| SVG 中 `<circle>` 数 | 7（散点，与观测数一致） |
| SVG 中柱形数 | 7（柱状） |
| PDF 文件头尾 | `%PDF-1.4` … `%%EOF` |
| PDF xref 偏移 | 逐条指向 `N 0 obj`，全部有效 |
| PDF 点算符 | 7 个 `arc f`（与散点数一致） |
| 复现脚本 | `python3 figure_code.py figure_data.json out` 退出 0，重画 7 圆 / 7 柱 |

预览（可选）：`pdftoppm -png -r 120 figures/figure_1.pdf preview`。

## 4. 边界行为（boundary 案例）

材料为坏 JSON、零字节文件与含占位符笔记：无数值列可解析 → 退化为按文件字节数的盘点柱状图，
在 `uncertainties` 与 `coverage.fallback_inventory_figure` 中明确标注，未伪造科学数值；
`status=partial`，退出码 0，全部交付物齐备。

## 5. 已知限制

- 图型只覆盖柱状 / 折线 / 散点；箱线、热图等在 `references/figure-specs.md` 中列为未实现。
- 每图最多 12 个类目/点，超出部分截断并在报告说明。
- PDF 文本使用 base-14 字体，中文标签在 PDF 中降级为 ASCII 占位（SVG 保留原文）。
- 不生成 PNG：PNG 由外部 `pdftoppm` / `convert` 从矢量 PDF 栅格化得到。
