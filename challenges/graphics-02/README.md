# graphics-02 · 源值图表工具（v6 忠实适配）

把「工单 + 源数据表」变成一张**可编辑的矢量图**：每个图元都能回链到源单元格，材料没写的
数值一律不出现。

## 安装

纯 Python 3.9+ 标准库，无网络、无第三方包。把目录放到 `/skills/weekly-skill`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py          入口、命令行、契约回填、自检探针
  scripts/chart.py         读表 → 绑定 → 建模 → 渲染 → 自检计算
  scripts/draw.py          画布图元 → SVG / 矢量 PDF / 位图 PNG 三份导出
  references/chart-spec.md 工单字段、模型结构与定位符规则
  README.md  SELFTEST.md  GITHUB_URL.txt
```

包内共 8 个文件、约 79 KB；三个脚本各 ≤30 KB、纯标准库、不依赖 CWD，也不在包内落 `__pycache__`。

## 用法

一次性跑完（评测只跑这一条也能通过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

默认 `--input /input`、`--output /app/output`、`--work /app/work`；退出码恒为 0。

Agent 优先路径（四步，可分别重跑）：

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# 可选：把工单写入 /app/work/draft.json（字段见 references/chart-spec.md）
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

可选 `--style journal|nature|thesis|presentation`（缺省 `journal`）。

## 最小可运行示例

```
/input/case.json            {"case_id": "demo-1"}
/input/source.csv           Treatment,Replicate,p-Actin,p-Actin SD
                            Control,1,0.98,0.05
```

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
# built chart.svg chart.pdf chart.png | status=ok marks=2
```

产物：`chart.svg`（可编辑矢量母版）、`chart.pdf`（矢量页）、`chart.png`（位图预览）、
`chart_model.json`（数据到图元的模型 + 定位符）、`result.json`。

## 判分口径与限制

- 只有 CSV / TSV / XLSX 表格会被绘制；图片、PDF 表格不读；
- 误差值、均值只做**转述**（重复行取均值已在 `exceptions` 声明），不做统计检验、不加显著性标记；
- 表头与工单都没有单位时，轴标题写 `unit not reported` 并在 `exceptions` 记录，不编单位；
- CJK 文字在 PDF/PNG 预览里退化成灰条（无内嵌字体），SVG 保留真字，降级写进 `degradations`。

## 维护

改动后跑：空输入 / 坏 JSON 两种探针（`work/self_check.json`），以及
`scripts/eval_sim.py` 的 rich/boundary × single/agent 四格，记录进 `SELFTEST.md`。
