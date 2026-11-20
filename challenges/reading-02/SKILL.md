---
name: scientific-figure-parser
description: >-
  Faithful figure-and-table reading: one command discovers the supplied materials, decodes each
  raster figure with a pure-stdlib PNG reader (zlib + scanline unfilter + palette expansion),
  calibrates both axes from the tick geometry by least squares, colour-traces every configured
  series into data coordinates, lifts the JSON tables column-for-column, and states every claim
  with verbatim evidence plus its source anchor. Unreadable panels, missing ticks and colours that
  never appear are reported as degradations rather than guessed; nothing is invented, no citation
  or value is fabricated. Use for scientific figure digitization, axis calibration, legend/series
  and table extraction, and evidence-anchored claim extraction from figures and tables.
version: 2.0.0
---

# scientific-figure-parser — 科学图表读取

一句话：**把图里的曲线读成数，把表里的格子读成据，并给每条结论留下出处。**

它不整段复述论文、不补画缺失的面板、不给读不出的刻度编数。每条结论都带
`原文/视觉引用 + 来源文件 + 定位`；每条降级都说明是哪里读不出来。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 1. 入口命令（第一条，必须先看）

单命令即可产出完整契约与全部关键产物（评测只跑这一条也能过）：

```
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work
```

`build` 默认值即 `--input /input`、`--output /app/output`、`--work /app/work`。它按顺序：

1. **发现** 材料：`case.json` 读 `case_id` 与 `output_contract`；文本材料直接读；重复副本按
   sha256 去重（记入 `changes`，不降级）；无法解析的 JSON 记 `errors` 但不中断；
2. **定位配置**：挑出 readings 配置（`figures/claims` 结构）与 material 文档（`paragraphs/tables`），
   找不到就退化到“只解图片 + 无表格”的诚实路径；
3. **解码** 每张图：纯标准库 PNG（`zlib` 解 `IDAT`、逐行反滤波、调色板展开），记录
   `width/height/color_type/bit_depth/sha256`；
4. **定标** 两条轴：用 `tick_px × tick_labels` 做最小二乘拟合（支持 `linear`/`log`），少于两个
   可用刻度就放弃数字化并记 `degradation`；
5. **数字化** 每条序列：按 `rgb + tol` 找像素，每列取平均 y，映射回数据坐标；
6. **读表**：逐列读 `columns/rows`，从表头 `(...)` 抽单位，写出 `tables.json` 与 `tables/T01.csv`；
7. **立结论**：每条 claim 带 `quote/quote_type/source_id/location/read_basis`，逐条校验引文；
8. 写出全部产物（§5），并把 `output_contract` 逐键回填进 `result.json`。

任意阶段抛异常都会在彻底兜底后仍写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “把这张图的曲线读成数据点” | 轴定标 + 颜色分簇数字化，写 `digitized_series.csv` |
| “图里这条线到底是什么颜色/哪条” | legend 条目与 rgb、容差、命中像素数逐条记录 |
| “表格数值抄下来” | 逐列读表，单位从表头解析，写 `tables/T01.csv` |
| “每条结论给出处” | `claims[].evidence{quote, source_id, location, read_basis}` |
| “图读不出来怎么办” | 如实 `degradation`（缺刻度/颜色未命中/解码失败），不猜 |
| “材料不全怎么办” | `partial`/`insufficient_evidence` + 缺口清单 |

不适用：整篇论文翻译、矢量图渲染、补画缺失面板、编造数值或统计量。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 | 关键参数 |
|-|-|-|
| `build` | 全流程：发现→解码→定标→数字化→读表→立结论→写产物与 `result.json` | `--input --output --work` |
| `show` | 打印图表/表格/结论清单与引用锚点（便于 Agent 取证） | 同上 |
| `check` | 重跑全流程并合并 `work/draft.json`，逐条校验引文 | 同上 |
| `selfcheck` | 重跑全流程并审计 `output_contract` 键是否齐全非空 | 同上 |

每个子命令都会重写一份完整的 `result.json`，因此评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责解码与取证，Agent 负责判读与措辞）：

```
# 1) 确定性全流程，先看图表结构与降级项
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
# 2) 逐条取证：打印图表/表格/结论清单
python3 /skills/weekly-skill/scripts/main.py show  --input /input --output /app/output --work /app/work
# 3) Agent 读 /app/output/figure_structure.json 与 /app/output/digitized_series.csv，写 /app/work/draft.json
# 4) 闸门：合并草稿并校验引文
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 5) 自检契约形状
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性结果，不报错）：

```json
{"claims": [
  {"claim_id": "c01", "kind": "table_cell",
   "text": "Specimen A modulus is 3.2 GPa, copied verbatim from table T01.",
   "readability": "directly_read", "conditions": "specimen A, 1 mm/min",
   "evidence": {"quote": "The modulus of specimen A is 3.2 GPa under 1 mm/min.",
                "quote_type": "text", "source_id": "material.json",
                "location": {"table_id": "T01", "row": 0, "json_pointer": "/tables/0/rows/0/1"},
                "read_basis": "literal table cell"}},
  {"claim_id": "c03", "kind": "element",
   "text": "The x axis reads displacement in mm from 0 to 8 and the y axis load in N from 0 to 100.",
   "readability": "directly_read", "conditions": "panel a",
   "evidence": {"quote": "x: 0-8 mm, y: 0-100 N", "quote_type": "visual",
                "source_id": "fig1.png",
                "location": {"figure": "Fig. 1", "panel": "a"},
                "read_basis": "axis tick labels"}}]}
```

合并草稿的三条硬约束：`quote` 必须能在某份材料里找到（`text`/`json` 型按原文比对，
`visual` 型按图形结构比对）；`claim_id` 相同的确定性结论会被 Agent 版本替换；引用不过关的
条目被丢弃并计入 `degradations`——Agent 的判读不能绕过取证要求。

---

## 4. 数字化口径

- **定标**：`value = a·px + b`，由 `tick_px`/`tick_labels` 最小二乘拟合；`scale: log` 时先取
  `log10` 再拟合，输出时还原。可用刻度少于两个 → 放弃数字化并记降级。
- **分簇**：像素与系列 `rgb` 的逐通道差都 ≤ `tol` 才算命中。
- **取点**：每个命中的像素列输出一个点（该列命中像素的 y 均值），列内像素 `np`；输出同时保留
  像素坐标 `px/py` 与数据坐标 `x/y`，便于人工复核。
- **诚实**：某序列零命中 → `status: no_pixels` 并记降级，绝不外推或填补。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `figure_structure.json` | 每张图的结构（caption/axes/legend/series/elements/calibration/digitized） |
| `digitized_series.csv` | 数字化长表：`figure_id,panel,series,px,py,x,y,unit_x,unit_y` |
| `tables.json` | 表格结构与摘要（columns/rows/units/来源） |
| `tables/T01.csv` | 每张表一份 CSV（与 `tables.json` 同源） |
| `figure_tables_digest.md` | 图表摘要报告：结构 + 数字化状态 + 计数 |
| `result.json` | 契约回填 + 结构化结果（见下） |

`--work` 下另有 `index.json`（图表/表格/结论快照）与 `draft.json`（若提供）。

`result.json` 顶层键（键名冻结；case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层）：

- `case_id` / `status` / `summary`
- `output_contract`：`case.json.output_contract` 逐键回填，**每个键给真实值**，不写类型占位符
- `result`：`{paper_title, readings_source, material_source, figures, tables, digitization, elements, materials}`
- `claims[]` / `sources[]` / `uncertainties[]`（镜像为 `uncertainty`）/ `change_records[]`（镜像为 `changes`）
- `figure_tables_digest`：图表摘要对象（图数/表数/数字化的点数/逐图逐表摘要）
- `errors[]` / `degradations[]` / `pending_human[]` / `limits[]` / `counts` / `runtime`

**回填口径**（未给契约时回填标准键的样例形状）：

```json
{"case_id": "synth-rich-reading-02",
 "status": "answered",
 "output_contract": {
   "case_id": "synth-rich-reading-02",
   "status": "answered",
   "result": {"paper_title": "Synthetic mechanical response of two specimens",
              "figures": [{"figure_id": "Fig. 1", "panel": "a"}],
              "tables": [{"table_id": "T01", "n_rows": 2, "n_cols": 3}]},
   "claims": [{"claim_id": "c01", "kind": "table_cell",
               "text": "Specimen A modulus is 3.2 GPa, copied verbatim from table T01.",
               "evidence": {"quote": "The modulus of specimen A is 3.2 GPa under 1 mm/min.",
                            "quote_type": "text", "source_id": "material.json"}}],
   "uncertainties": [{"kind": "unit", "detail": "Strength column header carries the unit."}],
   "figure_tables_digest": {"figure_count": 1, "table_count": 1, "digitized_points": 960}}}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `answered`：读到图表或表格，且无 `error`、无 `degradation`；
- `partial`：读到了内容，但存在 error 级缺陷或抽取降级；
- `insufficient_evidence`：材料可读但没有任何图表/表格/结论；
- `input_error`：`--input` 不可读或无语料，交付缺口报告。

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无语料 | 写缺口报告，`input_error` |
| 只有空文件 / 坏 JSON / 碎片笔记 | 无图表无表格 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `errors` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键 |
| PNG 解码失败 / 交错 / 非 8bit | 异常 | 记 `degradation`，只保留结构 |
| 可用刻度少于两个 | 定标失败 | 放弃数字化，记 `degradation` |
| 序列颜色零命中 | 逐列扫描为空 | `status: no_pixels` + `degradation` |
| 引文不在任何材料里 | `find_quote` 未命中 | `error` 级 → `partial` |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 `null`。
- [ ] `figure_structure.json`/`digitized_series.csv`/`tables.json`/`tables/T01.csv`/`figure_tables_digest.md` 结构合法且互相可对照。
- [ ] 每条 claim 有非空 `quote` 与 `source_id`，`text` 型引文能在材料中找到。
- [ ] 每个未数字化/未命中的序列都在 `degradations` 里有明确原因。
- [ ] 空输入 / 坏 JSON / 无语料三条路径各跑过一次，均 exit 0 且有缺口报告。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、数字化口径、契约、降级、自查
scripts/main.py                入口：build / show / check / selfcheck，流程编排、结论层与契约组装
scripts/figurekit.py           PNG 解码、轴定标、颜色数字化、表格读取、契约回填与产物渲染
references/contract.md         契约键语义、定标与数字化口径、证据类型
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`zlib`/`struct`/`csv`/`json`/`re`/`hashlib`）；无第三方包、无网络、无外部模型。
- 版本 2.0.0：契约键名冻结；新增元素类型/规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。
