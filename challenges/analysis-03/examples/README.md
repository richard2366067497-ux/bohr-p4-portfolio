# 最小可跑示例

一组最小输入，用来核对「表 → 统计 → 真实图表 → 元素回溯」是否闭环。

## 1. 准备输入

```text
/input/case.json
{"case_id": "demo-figure-01"}

/input/table.csv
sample,removal,ph
S1,95,3
S2,88,5
S3,61,9
```

## 2. 调用

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 3. 得到的图

- 表有 2 个数值列（`removal`、`ph`）→ 生成**散点图** `figures/figure_1.svg` + `figures/figure_1.pdf`，
  点为 (ph, removal)：`(3,95) (5,88) (9,61)`。
- 同时为 `removal` 生成**柱状图** `figures/figure_2.svg` + `.pdf`，类目为 `sample`。

`stats.json`（节选）：

```json
{"figure_1": {"n": 3, "mean": 81.33, "median": 88.0, "min": 61.0, "max": 95.0, "x": "ph", "y": "removal"}}
```

`result.json` 的 `evidence_map`（节选）：

```json
{"figure": "figure_2.svg", "element": "series[0]", "category": "S1", "value": 95.0, "source": "table.csv", "locator": "table.csv#row2"}
```

## 4. 复现

```bash
python3 /app/output/figures/figure_code.py /app/output/figure_data.json /tmp/repro
# → /tmp/repro/figures/figure_1.svg ...
```

## 5. 预览

```bash
pdftoppm -png -r 120 /app/output/figures/figure_1.pdf /tmp/preview
```

## 6. 边界示例

材料只有空文件或坏 JSON 时：无论值列，退化为「文件字节数」盘点柱状图并在 `uncertainties`
说明，`status=partial`，退出码仍为 0。
