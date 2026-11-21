# GAIN_EVIDENCE — reading-02 / figure-data-extractor（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一图/表输入上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**（见 `SELFTEST.md`），可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。对照的公平性在于：两组使用**同一**输入（`examples/params.json` +
> `fig1.md`）、**同一**任务（把图与表读成结构化数据并给证据）与**同一**评估口径（§3）。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（一图两系列 + 一表）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **散文而非数据** —— 输出「图中两条曲线随位移下降、红色高于蓝色」这类总结，无 CSV、无逐点。
2. **无轴标定** —— 不报告坐标轴类型、刻度起点/间隔与单位，读点靠目测。
3. **无图例↔系列绑定** —— 颜色与系列名对应靠猜，红色/蓝色与 A/B 常对错。
4. **无 locator** —— 数值与结论不给 `table_id`/`json_pointer`/`bbox_px`，不可复核。
5. **不区分可读/推断/无法确定** —— 缺失的误差线被当作「无」或被编造。
6. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/10。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把图形说明与表格合并成一段通读文字，不建轴、不数字化、不定位
import json, pathlib
p = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))
paras = p["material"].get("paragraphs", [])
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text("图表综述：\n" + "\n".join(paras) + "\n", encoding="utf-8")
# 无 digitized_series.csv / figure_structure.json / tables.json / evidence_map.json / result.json，
# 无轴标定、无颜色匹配、无 locator、无逐字核验
```

模拟结果：产物 **1** 件、轴标定 **0**、数字化点 **0**、表 **0**、locator 证据 **0**、契约键 **0/10**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 实测值 |
|---|---|
| 产物文件数 | **9**（含 `tables/T01.csv`） |
| 图形 | **1**（`Fig. 1` panel a，caption 命中） |
| 轴标定 | **x: 0–8 mm 线性；y: 0–100 N 线性** |
| 系列（图例↔颜色绑定） | **2**（A=rgb(220,30,30)，B=rgb(30,60,200)） |
| 数字化点 `digitized_series.csv` | **81**（每点带 `x_px, y_px` 与颜色匹配说明） |
| 表 | **1**（`T01`，单元格逐字抄录，单位取自表头） |
| 文本引文逐字命中 | **2/2**（`anchor_hit_rate = 1.0`） |
| 契约键覆盖 | **10/10**（顶层 + `result.output_contract`） |
| 占位符扫描 | **0** |
| `result.json` 规范化哈希 | `sha256=808a12c84e60d762`（剔除 `runtime`） |

关键产物：`readings.md`（轴/图例/表/带 locator 的 claim）/ `figure_structure.json`（轴、图例、元素、系列）/
`digitized_series.csv`（系列, x, y, x_px, y_px）/ `tables.json` + `tables/T01.csv` / `evidence_map.json`
（每 claim 的 locator、quote_type、read_basis、verbatim）。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接文字 | 9 件成套产物（轴/图例/CSV/表/证据/覆盖） | **实际效果（15 分）** |
| 结果正确性 | 单位/刻度靠目测，图例对应靠猜 | 由 `tick_px`+`tick_labels` 现算标定，颜色 rgb 指纹绑定系列 | **实际效果（15 分）** |
| 结果完整性 | 漏误差线/显著性/比例尺，或臆造 | 轴/图例/系列/数据点/误差线/显著性/比例尺/子图编号逐一交代，缺失写 `undetermined` | **实际效果（5+5 分）** |
| 结果可核验性 | 无 locator、无引文 | 每 claim 带 `table_id`/`json_pointer`/`bbox_px` + 引文 + `verbatim` | **实际效果（5 分）** |
| 使用增益 | 无对照、无法复核 | `compare_report.json` 给「基线文字 vs 结构化条目」的可核验差；同输入同口径（§1） | **使用增益（25 分）** |
| 创新增益 | 直接目测读图 | 像素→数据坐标标定 + 颜色数字化 + 双通道引文核验（README §9，含价值边界） | **创新增益（15 分）** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；无图/无刻度 → `partial` 记 `digitize_note`；`SELFTEST.md` 有证据 | **可靠体验（10 分）** |
| 生态贡献 | 无文档、无模板 | README/SELFTEST + 契约骨架 + 读数模板 + 误差口径，可换成新图复跑 | **生态贡献（10 分）** |

**为什么这些差异对应 rubric**：实际效果＝「真的把一张图与表读成与轴/图例对应、可继续统计的数值」；
使用增益＝「同一图、同一口径下，结构化与可核验性优于基线，且给出可复算差」；创新增益＝「轴标定、
颜色数字化、双通道核验的方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实读数」；
生态贡献＝「说明、模板、示例可被他人直接复用」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 9 个文件；result.json.status=answered；
#       图形 1；轴 x:0-8 mm / y:0-100 N；数字化点 81；表 1；anchors 2/2（hit_rate 1.0）
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime` 后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`808a12c84e60d762`。
