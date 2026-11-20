---
name: mechanism-figure-ledger
description: 把生物机制/通路材料画成可逐条回查的分层可编辑机制图。Agent 亲自读原文并写工作稿 draft.json（实体—关系—区室—图例—数值），脚本只做材料索引、逐字引文校验、上下游区室布局、语义箭头渲染、图例与图面一致性断言，导出分层 SVG + 单页矢量 PDF + 真实 PNG + content_map，并原样回填 output_contract 全部字段。适用于机制图、通路图、信号通路示意图、graphical abstract，以及"在既有图上改一个标签再重导"的保源编辑；不适用于统计分析结论、实验方案设计、论文写作与版式美化。
version: 1.0.0
---

# 生物机制图与通路图：可核验绘图台

一张机制图不是插画，而是一份能被逐条质疑的陈述。因此本 Skill 的产物不是"一张好看的图"，
而是**图 + 每个实体/每条边的逐字出处 + 一组能从磁盘重算的一致性断言**。

分工只有一句话：**Agent 判断生物学，脚本当尺子和笔。**

---

## 1 五命令主路径（这是第一件事，务必按序执行）

```bash
python3 scripts/main.py init       # ① 建索引：解析 case.json/output_contract/task.md 与全部材料，建材料清单 + 工单对象表，先写一份合法 partial result.json
python3 scripts/main.py show       # ② 打印带 locator 的原文与对象清单，供你逐字引用
#   ← ③ 你（Agent）在这里亲自读材料，写出工作稿 /app/work/draft.json（字段见 §4）
python3 scripts/main.py check      # ④ 机械校验：契约字段、引文命中、工单覆盖、图例自洽、数值溯源
python3 scripts/main.py build      # ⑤ 由工作稿生成 figure.svg / .png / .pdf / content_map.json 与最终 result.json
python3 scripts/main.py selfcheck  # ⑥ 可选复检：从磁盘重新读产物再断言一遍
```

**脚本不会代替你阅读理解。必须先 `show` 读材料、写 `draft.json`，再 `build`；禁止只跑 `build` 就结束。**
只跑 `build` 时脚本只能给出工单级的降级草图与 `status=partial`，实体类型、箭头语义、区室归属、
图例含义都会退化为"工单字面 + 未判定"，实际效果分与创新分按规则都要扣。

时间紧时的最小闭环：`init` → `show` → 写 4–8 个实体 + 关键边 → `build`（已得可用图）→
补全 `draft.json` → `check` → `build` 覆盖。构建可重入，产物每次覆盖。

所有命令**退出码恒为 0**，且 `init`/`build` 第一步就先写一版合法 `result.json`；
任何异常都会落进 `errors`/`degradations`，不会让你拿到空目录。

---

## 2 用途与适用条件

**用**：材料（机制段落、figure legend、通路描述、工单 JSON、表达量表）里已经写明"谁作用于谁"，
需要产出一张能改标签、能查出处、能重导出的机制图；或对既有图做保源编辑（改一处标签/一条箭头语义）。

**不用**：做统计推断或显著性结论、设计实验、写论文、美化版式——这些属于相邻课题。
本 Skill 只保证"图上每个元素可回溯、图例与图面自洽、源文件可编辑"，不保证作者的生物学结论成立。

**触发词**：机制图 / 通路图 / 信号通路 / 调控网络 / graphical abstract / schematic / pathway figure /
mechanism diagram / 画一张图说明 A 如何调控 B。

---

## 3 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（必需）、`/input/task.md`、`/input/**` 材料（md/txt/csv/json/pdf/docx/xlsx/pptx/png） |
| 工作区 | `/app/work`（`index.json`、`draft.json`、`check_report.json`、`selfcheck.json`） |
| 产物 | `/app/output`（`figure.svg`、`figure.png`、`figure.pdf`、`figure_model.json`、`content_map.json`、`compliance_checks.json`、`result.json`） |
| 调用 | `python3 -B <SKILL>/scripts/main.py <init\|show\|check\|build\|selfcheck> [--input DIR] [--work DIR] [--output DIR]` |
| 依赖 | Python ≥ 3.8 **标准库**；不联网、不读环境变量、不依赖 CWD（用 `__file__` 定位） |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token。确定性重活全在脚本里，模型只做理解与判断 |

`case.json` 的键名可能有变体，脚本按语义识别：`output_contract`/`outputContract`/`required_fields`；
工单 `organizer_workorder`/`workorder`/`figure_workorder`/`drawing_order`；`case_id`/`caseId`/`id`。

**`result.json` 信封**：`output_contract` 里声明的字段**原样回填**（不改名、不漏键、缺值 `null`/`[]`），
再带 `case_id`、`status`（`ok`/`partial`/`input_error`）、`sources`、`uncertainty`、`pending_human`、
`errors`、`degradations`、`changes`、`runtime`、`skill`、`contract_fields`（含 `null_fields` 自查清单）。

---

## 4 工作稿 `draft.json` 契约（Agent 唯一必写文件）

写到 `/app/work/draft.json`（若你习惯写 `plan.json`，脚本同样读取）。完整字段字典见
`references/mechanism-drawing-contract.md` §3；最小形态：

```json
{
  "title": "EGF–EGFR–STAT3 激活与 SOCS3 负反馈",
  "subtitle": "实体、边与区室位置均引自 note.md 与 workorder",
  "compartments": [
    {"id": "extracellular", "label": "Extracellular", "order": 0},
    {"id": "membrane", "label": "Plasma membrane", "order": 1},
    {"id": "cytoplasm", "label": "Cytoplasm", "order": 2},
    {"id": "nucleus", "label": "Nucleus", "order": 3}
  ],
  "entities": [
    {"id": "egf", "name": "EGF", "entity_type": "ligand", "species": "human",
     "compartment": "extracellular", "italic": false,
     "source": {"locator": "note.md#para1", "quote": "EGF 结合 EGFR 的胞外结构域"}},
    {"id": "stat3_gene", "name": "STAT3", "entity_type": "gene", "species": "human",
     "compartment": "nucleus", "italic": true, "sublabel": "transcript",
     "source": {"locator": "note.md#para3", "quote": "STAT3 转录本上调"}}
  ],
  "relations": [
    {"id": "r1", "from": "egf", "to": "egfr", "relation_type": "binding",
     "direction": "forward", "evidence_strength": "stated", "label": "binds",
     "source": {"locator": "note.md#para1", "quote": "EGF 结合 EGFR 的胞外结构域"}}
  ],
  "legend": [
    {"channel": "color", "meaning": "entity type", "mapping": {"gene": "#F6E7C1"},
     "source": {"locator": "case.json#workorder.legend_encodings", "quote": "color: entity type"}}
  ],
  "data_values": [
    {"entity": "stat3_gene", "metric": "fold change", "value": 2.4, "unit": "FC",
     "source": {"locator": "data.csv#para2", "quote": "STAT3,2.4"}}
  ],
  "edits": [],
  "gaps": ["SOCS3 是否入核材料未写，未画。"]
}
```

要点（写错会直接进 `check` 的 rejected）：

1. **`name` 用材料原文写法**，不改写、不翻译、不补常见分子。`TP53`（基因）与 `p53`（蛋白）不合并。
2. **每个实体、每条关系、每个图例编码都必须有 `source.locator` + `source.quote`**，
   quote 是材料里的**连续逐字切片（≥6 字符）**。改写、拼接、翻译都不算命中，该条会被拒绝绘制。
3. `relation_type` 取 `activation|inhibition|binding|modification|transport|recruitment|indirect|unspecified`；
   判不准写 `unspecified`，图上是无箭头点划线，并在 `gaps` 说明——**宁可少画，不可错画**。
4. `from`/`to` 必须是 `entities[].id`；方向按原文语序（"A 被 B 激活" → `B → A`）。
5. 图例是数据驱动的：`channel` 取 `color|line_width|size|shape|line_style|marker`，
   `mapping` 里的每个取值必须真的出现在图面上，否则 `check` 报 orphan。
6. 任何数字（表达量/显著性/置信度）只有给了 `data_values[].source.quote` 才允许画；没有出处不画。

---

## 5 方法说明

### 5.1 关系语义 → 图元（图元即论断）

| `relation_type` | 画法 | 典型原文词 |
|---|---|---|
| `activation` | 实线 + 实心箭头 | activates / promotes / induces / 激活 / 促进 / 上调 |
| `inhibition` | 实线 + **T 形端** | inhibits / suppresses / blocks / 抑制 / 下调 / 阻断 / 负反馈 |
| `binding` | 实线 + 空心箭头 | binds / interacts / 结合 / 结合于 |
| `modification` | 实线 + 实心箭头 + `P`/`Ub` 徽标 | phosphorylates / ubiquitinates / 磷酸化 / 泛素化 |
| `transport` | 粗线 + 双箭头 | translocates / exports / 转运 / 转位 / 分泌 |
| `recruitment` | 细实线 + 小圆端 | recruits / assembles / 募集 |
| `indirect` | 虚线 + 箭头 | implies / presumably / 推测 |
| `unspecified` | 点划线、无箭头 | 原文未说明类型或方向 |

一句话多动词时按 `modification > transport > inhibition > activation > binding > recruitment` 取更具体的一层。
完整中英动词表、被动语态与方向判定规则见 `references/mechanism-drawing-contract.md` §1。

### 5.2 区室与跨膜布局

- 区室按 `order` 自上而下排布（默认 胞外 → 胞膜 → 胞质 → 核内 → 其他），层高与层内实体数成比例。
- `compartment == "membrane"` 或实体类型为 `receptor`/`transmembrane` 时，节点**压在磷脂双分子层中心线**上
  （自检断言 `box.y < membrane_y < box.y+box.h`）。
- 跨区室的边必须真的穿过层界（路径上有越过边界的点），悬在层内即判失败。
- 材料只写两层就只画两层，不为了"看起来完整"补一层。

### 5.3 命名与实体类型

`entity_type` ∈ `gene|protein|complex|ligand|receptor|cell_type|compartment|metabolite|mirna|phenotype|unspecified`。
基因名斜体、蛋白正体（SVG 用 `font-style="italic"`，PDF 用 Helvetica-Oblique），脚本按 `italic` 与
`entity_type == "gene"` 双向断言。复合物整体画（`complex`），不把成员拆成边。同名异义（胞质 STAT3 / 核内 STAT3）
拆成两个实体并用 `sublabel` 区分。

### 5.4 图例与数据编码一致性

图例不手写：脚本按图面**实际出现**的实体类型、关系类型、显式 `legend` 声明生成图例，
并做双向断言——图面用到的每个编码值都在图例里（缺失时记 `unsourced`，提示补出处），
图例里的每一项都在图面上出现（不出现记 `orphan`，直接判失败）。
颜色只编码实体类型，线型 + 端点编码关系类型，同一通道不表达两件事。

---

## 6 证据、定位与可核验

材料被切成带 locator 的块：文本 `文件#paraN`、PDF `文件#streamN`、表格 `文件#paraN`、DOCX/XLSX/PPTX `文件#paraN`。

`quote` 状态四档，写进 `content_map` 与 SVG 的 `data-quote-status`：

| 状态 | 含义 | 是否进图 |
|---|---|---|
| `verbatim` | 原文逐字命中（空白归一后） | 是 |
| `verbatim_loose` | 去空白与标点后命中（吸收 PDF 抽字噪声） | 是 |
| `declared` | 引自工单条目（`case.json#workorder...`），不是材料正文 | 是，单独计数 |
| `unverified` | 找不到 | **否**，进 `content_map.pending` 与 `pending_human` |

SVG 里每个实体组带 `data-quote`/`data-locator`/`data-entity-type`/`data-compartment`，
每条边组带 `data-relation-type`/`data-from`/`data-to`/`data-direction`——这就是"改标签 + 查出处"的最小接口。

**冲突检测（本包增量）**：若工单声明 `A→B`，而材料里同一句能同时找到 A、B 与动词且语序指向 `B→A`，
`check` 记为 `conflict`，`build` 把该边降级为无箭头并进 `pending_human`，两侧引文都写进报告。

---

## 7 output_contract 字段覆盖

`case.json.output_contract` 可能是数组或对象；脚本取全部字段名，逐字段回填，**一个都不许改名或漏掉**。

| 字段 | 回填内容 |
|---|---|
| `case_id` | 原样来自 `case.json`；缺失时 `null` 并记 `errors` |
| `status` | `ok`（无 rejected、无缺口）/ `partial`（有降级）/ `input_error`（case.json 缺失或坏） |
| `editable_source` | `{path,format:"svg",editable:true,layers:[...],text_count,bytes,sha256}` |
| `export_artifact` | `{png:{path,width,height,dpi,engine,non_uniform},pdf:{path,pages,vector,engine,header,eof,bytes}}` |
| `content_map` | `{entities[],relations[],compartments[],legend_encodings[],pending[],coverage{...}}`，逐条 `locator`+`quote`+`quote_status`+`svg_id` |
| `compliance_checks` | `{canvas,font_style,markers,compartment_containment,cross_lane_edges,legend_consistency,overflow,pixel_probe,pdf,pass,failures}` |
| `exceptions` | 降级/待人工项合并列表（每条 `{kind,detail,impact,action}`） |

未在表中出现的声明字段（隐藏案例可能新增）会被填成 `null` 并写进 `degradations`，绝不静默丢弃。

---

## 8 产物清单

| 文件 | 内容 | 完成标准 |
|---|---|---|
| `figure.svg` | 可编辑源：`layer-compartments/entities/edges/labels/legend/title`，文字全为 `<text>`，逐元素 `data-*` | 改一个标签即可重导 |
| `figure.png` | 1600×1000 RGB 真实位图，IHDR 可解、非纯色 | 可直接预览 |
| `figure.pdf` | 单页矢量，base-14 Helvetica 正/粗/斜，xref 可用，`%%EOF` 收尾 | 可在阅读器打开、文字可选中 |
| `figure_model.json` | 布局后的实体—边—区室模型（含 box 坐标、路径点） | 可复查布局决策 |
| `content_map.json` | 与 `result.json.content_map` 同源 | 逐条可回溯 |
| `compliance_checks.json` | 与 `result.json.compliance_checks` 同源 | 断言可重算 |
| `result.json` | 契约全字段 + 信封 | 合法 JSON、字段齐 |

---

## 9 边界与限制

- **科学判断不在脚本里**：脚本只断言"是否有出处、是否自洽、是否可编辑"，不判断机制是否成立。
- PNG 文字用内置 5×7 拉丁点阵（汉字画等宽占位框）；**正字以 SVG/PDF 为准**，PNG 只作检视件。
- PDF 只吃 WinAnsi：中文留在 SVG，PDF 侧丢弃并计数（`pdf.chars_dropped`），是有意取舍不是静默失败。
- 布局是启发式：层内网格 + 邻近择优，元素极多时降为多列网格并报 `overflow`。
- 剂量/时间序列、热图、单细胞 UMAP 等非机制图形不在本包范围。
- 不内置任何案例答案：隐藏案例必须靠真实读取 `/input` 得到。

---

## 10 失败处理与降级矩阵

| 情况 | 行为 | 落点 |
|---|---|---|
| `/input` 不存在或为空 | 仍产出合法 `result.json` + 最小 SVG/PNG/PDF，`status=input_error` | `errors`、`degradations` |
| `case.json` 坏 JSON | 正则抢救 `case_id`/`output_contract`，继续跑 | `errors` |
| `draft.json` 缺失/不合法 | 兜底：工单条目 + 材料里 "A 动词 B" 明写句 → 降级草图 | `degradations`、`status=partial` |
| 引文找不到 | 该条**不画**，进 pending | `content_map.pending`、`pending_human` |
| 方向/类型无法判定 | 画无箭头点划线 | `gaps`、`pending_human` |
| 工单与材料方向冲突 | 降级为无箭头 + 双引文 | `uncertainty`、`pending_human` |
| 位图/扫描 PDF | 不进正文，只列缺口 | 材料 `note`、`gaps` |
| 无 PNG/PDF 渲染器 | 内置光栅器与 PDF 生成器兜底，`engine` 记 `stdlib` | `export_artifact.*.engine` |
| 图面元素过多 | 多列网格 + 14px 下限，溢出计数 | `overflow` |

无法判断的一律写进 `pending_human` 并说明"要人确认什么"，**不要写成事实，不要补造数据**。

---

## 11 自查（`selfcheck` 从磁盘重算的 12 条）

`svg_xml`（可解析、分层 ≥5、`<text>`>0、最小字号 ≥14）/ `canvas`（1600×1000）/
`markers`（8 类关系端点形状互不撞车，激活 vs 抑制必须不同）/ `gene_italics` /
`compartment_containment`（框在泳道内、膜实体压线）/ `cross_lane_edges`（跨区室边越界）/
`legend_consistency`（每编码一条、orphan=0）/ `content_map_1to1`（`ent-*`/`rel-*` 数 == 条目数）/
`evidence`（rejected=0）/ `png`（魔数、尺寸、非纯色）/ `pdf`（`%PDF-`、页数、`%%EOF`、`Tj`>0）/
`contract`（声明字段无缺失，缺的已在 `degradations` 说明）。

---

## 12 最小调用示例（**示例，非正式案例结果**）

输入：`/input/case.json`（7 项契约 + workorder）+ `/input/task.md` + 一份 4 句机制笔记。

```bash
python3 -B /skills/weekly-skill/scripts/main.py init  --input /input --work /app/work --output /app/output
python3 -B /skills/weekly-skill/scripts/main.py show  --input /input --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --output /app/output
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
```

示意输出（示例）：

```
init  → materials 3 | contract 7 fields | partial result.json written
show  → note.md#para1..4 | workorder: 6 entities, 6 relations, 4 compartments
check → entities 6 (verified 6) | relations 6 (verified 6) | coverage 6/6 | CLEAN
build → status=ok | figure.svg 24KB | figure.png 61KB | figure.pdf 11KB | checks pass=True
```

---

## 13 文件、维护与复用

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：契约、方法、失败处理、自查 |
| `scripts/main.py` | CLI：init/show/check/build/selfcheck、材料索引、引文校验、契约回填、兜底 |
| `scripts/draw.py` | 布局（区室泳道/跨膜/正交布线）、显示列表、SVG 渲染、一致性断言 |
| `scripts/export.py` | 显示列表 → 单页矢量 PDF（base-14）与 zlib 手写 PNG（5×7 点阵） |
| `references/mechanism-drawing-contract.md` | 中英动词→关系类型→端点、方向判定、命名与区室归一、`draft.json` 字段字典、`output_contract` 字段字典、12 条质量闸门、降级矩阵 |

复用方式：换题库只改 `draft.json` 层；改语义画法改 `draw.py` 的 `EDGE_STYLE`；
改词表同时改 `ledger.py:VERBS` 与 `references/mechanism-drawing-contract.md` §1（两处必须一致）。
回退：整个目录覆盖上一版即可，产物每次 `build` 重新生成，无外部状态。
