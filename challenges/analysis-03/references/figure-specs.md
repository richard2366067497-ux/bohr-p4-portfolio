# 数据 → 图型选择规则与输出约定

## 1. 判定顺序

对每张可解析的表，先识别「数值列」：该列至少有 `max(2, ⌊行数/2⌋+1)` 个单元格能解析为数字
（支持 `1,234`、`95%`、`~3.2`、科学计数法；剥离单位后缀）。

| 条件 | 图型 | x | y |
|---|---|---|---|
| ≥2 个数值列 | 散点（scatter） | 数值列 1 | 数值列 2，仅保留成对观测 |
| 恰有 1 个数值列 + 存在非数值列 | 柱状（bar） | 该非数值列（前 12 类） | 数值列 |
| 恰有 1 个数值列、无分类列 | 柱状（bar） | 行号 | 数值列 |
| 无任何数值列 / 无表 / 输入损坏 | 盘点柱状（bar, fallback） | 文件路径 | 文件字节数 |

同一张表若数值列 ≥2，会先画散点；若还有单数值列，再为该列画柱状。最多 12 个点/类目。

## 2. 坐标约定

- 画布 640×400，绘图区 `x ∈ [70, 616]`、`y ∈ [42, 336]`（SVG 左上原点）。
- 值轴下限取 `min(0, 数据最小值)`，上限取 `max(0, 数据最大值)`；跨度为 0 时取 1 避免除零。
- PDF 使用左下原点，`y_pdf = 400 − y_svg`；字体 base-14 `Helvetica`，无需嵌入。

## 3. 输出约定

| 文件 | 内容 |
|---|---|
| `figures/figure_N.svg` | 矢量图（`<rect>` 柱 / `<polyline>` 折线 / `<circle>` 点） |
| `figures/figure_N.pdf` | 同一图元的矢量 PDF（`re f` / `l S` / `arc f` 算子） |
| `stats.json` | 每个序列的 n/均值/中位数/标准差/q1/q3/min/max/sum |
| `figure_data.json` | 抽取出的 categories/values，供 `figure_code.py` 复现 |
| `evidence_map`（在 `result.json`） | 元素 → `<file>#row<n>` 或 `<file>#bytes` |
| `figures/figure_code.py` | 可独立运行的 SVG 复现脚本 |

## 4. 一致性约束

- `stats.json` 与图**共用同一份** `values`，任何数字都能从图源列重算。
- 图上标注的类目数 = `stats.n` = `evidence_map` 中该图的元素数。
- 退化（fallback）图必须带 `fallback_inventory_figure: true` 并在 `uncertainties` 说明，禁止伪装成科学数值图。

## 5. 预览（可选）

```bash
pdftoppm -png -r 120 /app/output/figures/figure_1.pdf /tmp/figure_1
# 或
convert -density 120 /app/output/figures/figure_1.pdf /tmp/figure_1.png
```
