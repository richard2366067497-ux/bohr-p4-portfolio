# 工单字段、模型结构与定位规则（graphics-02 v6.0.0）

本文件是 `scripts/main.py` 的字段参考。凡是「没有内容」的地方，写一条**结构化说明**，
不要留空串或空数组——空值在评测里会被当作未回填。

## 1. 工单（可选）

放在 `case.json` 的 `workorder` 键、或 `/app/work/draft.json`（整体当作工单）。
下面用 `text` 代码块给出字段，方便照抄；它不是样例数据。

```text
{
  "chart_type": "bar | line | auto",
  "title": "图题；缺省时由「系列名 by x 表头」拼出",
  "x": "分类或横轴列的表头（精确或子串匹配）",
  "y": ["要画的数值列表头", "..."],
  "x_label": "横轴标题", "x_unit": "横轴单位",
  "y_label": "纵轴标题", "y_unit": "纵轴单位",
  "error_mode": "误差来源文字说明（脚本只转述，不计算）",
  "style": "journal | nature | thesis | presentation",
  "width_mm": 170, "height_mm": 105.4, "dpi": 96,
  "source_table": "指定用哪张表（文件名精确或子串匹配）"
}
```

## 2. 列绑定规则

1. **误差列**：表头去符号小写化后，若以某数值列的表头为前缀、后缀属于
   `sd / sem / se / stdev / std / err / error / ci / ci95 / pm`，则该列是那一列的误差列。
2. **x 列**：工单 `x` 命中优先；否则取数值占比最低的一列；再否则用行号。
3. **系列列**：数值覆盖率 > 0、不是 x、不是误差列的列；`Replicate / Sample / ID / No` 一类
   行号列被排除并记 `index_column_skipped`。
4. **重复行**：分类 x 下同一系列多行时取算术均值（`n` 保留），记 `replicate_aggregated`；
   数值型 x 不聚合，按行成点。

## 3. chart_model.json 结构（要点）

- `chart_type` / `title` / `canvas{w_px,h_px}` / `plot{x0,y0,x1,y1}`；
- `axes.x{label,unit,scale,categories,source}`、`axes.y{label,unit,min,max,ticks,source}`；
- `series[]{id,name,column,color,points[]{id,x,y,yr,n,err,eraw,src{file,sheet,row,rows,col,col_index,header,x_header,x_col,quote},g{...像素几何...}}}`；
- `legend[]{id,series_id,label,color,xy}`；
- `coverage{required,mapped,missing,missing_count,ratio}`；
- `source_table{file,sheet,header_row,data_rows,headers}`。

`g` 里的像素几何与源值互为逆变换，`compliance_checks.geometry_roundtrip` 就是把它反算回数值比对。

## 4. 定位符

`文件:L行`（`src.row`）与列字母（`src.col`，如 `C`）。`src.quote` 是该行原文（分隔符拼回），
`src.rows` 给出聚合用到的全部行号。跨行引号或换行单元格可能带来 ±1 行偏移，属正常范围。

## 5. 状态与合规判定

- `input_error`：输入目录不存在；
- `insufficient_evidence`：没有可解析的数据表，或列绑定失败；
- `ok`：合规自检 `pass` 且无 `errors`、无 `degradations`；
- `partial`：其余情况。

`compliance_checks.failures` 取值：`legend_series_mismatch`、`geometry_mismatch`、
`coverage_incomplete`、`canvas_overflow`、`png_blank`、`pdf_missing`、`pdf_not_vector`。

## 6. 导出实现

- SVG：分层 `<g id="layer-...">`，文字是活的 `<text>`，图元带 `id`；
- PDF：内置写出的 PDF 1.4 向量页（Helvetica base-14，96 dpi 换算成 pt），不需要外部渲染器；
- PNG：内置 8 位 RGB 光栅（zlib 编码），ASCII 用 5×7 点阵字体，非 ASCII 退化为灰条。

三份导出共用同一份图元画布，因此预览与母版必然一致。
