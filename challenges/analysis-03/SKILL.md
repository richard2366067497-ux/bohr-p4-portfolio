---
name: figure-publisher
description: 把输入的科研数据表真正渲染成图表（SVG 矢量 + PDF 矢量），统计与图一一对应，并可逐元素回溯到源数据。
---

```json
{
  "output_contract": {
    "case_id": "string",
    "deliverable": "string",
    "evidence_map": [],
    "change_log": [],
    "coverage": {},
    "status": "string"
  }
}
```

用例声明的每个键（含嵌套）都会写入 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传，
不重命名、不丢弃。

## 单命令入口

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 交付物（`/app/output`）

`figure_report.md`、`stats.json`、`figure_data.json`、`figure_1.svg`、`figure_1.pdf`、`figure_code.py`、`result.json`。

## 做什么

1. 盘点 `/input`，解析 csv / tsv / json / jsonl / sqlite 表。
2. 对每个数值列计算 n / 均值 / 中位数 / 标准差 / 四分位 / 极值（`stats.json`）。
3. **真的渲染**：把数据画成柱状 / 折线 / 散点图，同时输出矢量 `SVG` 与矢量 `PDF`
   （base-14 Helvetica，`pdftoppm` / `convert` 可直接栅格化为预览图）。
4. 每个图形元素回填 `evidence_map`（`<file>#row<n>` 定位到源单元格）。
5. `figure_code.py` 是可直接运行的复现脚本：读 `figure_data.json` 重画 SVG。

## 边界

空目录、坏 JSON、零字节、无数值列：仍输出全部交付物与合法 `result.json`
（`status=partial` / `input_error`），并以文件字节数盘点图占位（明确标注，不伪造数值），退出码恒 0。
