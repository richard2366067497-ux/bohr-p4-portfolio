---
name: schematic-trace-studio
description: Turn case materials (task.md, a figure workorder, prose/PDF/CSV sources, an existing SVG baseline) into a source-bound, layered, still-editable scientific schematic — mechanism or relationship diagram, workflow, data panel — with real PNG/PDF exports and a result.json in which every drawn element carries a file/line locator and a verbatim quote. The workflow is agent-first by construction: `init` indexes the case, `show` prints locator-tagged material for you to read, you write the scientific judgement into `/app/work/draft.json`, then `check` verifies every quote and count before `build` renders. Use it when a reviewer must be able to reopen the figure, relabel one element, re-export it, and trace each element back to the sentence it came from.
version: 1.0.0
license: MIT
---

# schematic-trace-studio

科研示意图/机制图/流程图/数据面板的「来源 → 图稿 → 导出 → 台账」流水线。核心主张：**图对不对由证据决定，不由图好不好看决定**。脚本承担确定性的重活与校验，**科学判断必须由你读完材料后写进工作稿**。

## 0. 主路径（先看这一节）

按顺序执行，五条命令，**不要跳步**：

```bash
# ① 建索引：解析 case.json / output_contract / task.md / workorder / 材料，先落一份合法 partial result.json
python3 scripts/main.py init

# ② 打印带 locator 的材料原文与对象清单（工单必需项 + 候选三元组 + 表格 + 基线 SVG 元素）
python3 scripts/main.py show

# ③ ★ 你亲自读 show 的输出（必要时用 Read/Grep 打开原文），把实体、关系、方向、图例、分组、例外
#    写进 /app/work/draft.json —— 这是本题唯一不能被脚本替代的判断环节

# ④ 机械校验：契约字段、quote 逐字命中、覆盖数、关系类型/方向、图例编码一致性
python3 scripts/main.py check

# ⑤ 由图稿生成主产物 + 最终 result.json（无条件 finalize；无工作稿也产出完整降级交付）
python3 scripts/main.py build

# ⑥ 复检（建议）：重算哈希、重解 PNG/PDF、id 对齐、确定性
python3 scripts/main.py selfcheck
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> 只跑 `build` 会得到一份「完整但降级」的交付（`status=partial`、`degradations` 写清缺口），那是兜底分。图里的实体、关系、方向、图例是否成立，取决于你写进 `draft.json` 的判断。

| 路径 | 内容 |
| - | - |
| `/input/case.json`、`/input/task.md`、材料目录 | 输入（只读） |
| `/app/work/index.json` | `init` 的索引：行级 locator、工单对象、候选三元组 |
| `/app/work/draft.json` | **你写的工作稿**（唯一的人工判断载体；字段见 `references/authoring-guide.md` §1） |
| `/app/work/check.json`、`show.txt` | 机器校验报告、`show` 全文转写 |
| `/app/output/figure.svg` | 分层可编辑源文件（文字是活字，未转曲） |
| `/app/output/figure.png` | 真实位图预览（IHDR 可解、非空白） |
| `/app/output/figure.pdf` | 真实矢量导出（页对象齐、文字可抽取） |
| `/app/output/figure_model.json` | 单一中间表示：SVG/PNG/PDF/content_map 全部由它单向派生 |
| `/app/output/edit_record.json` | 编辑类案例：基线 sha256、逐元素改动前后、id 保真审计 |
| `/app/output/result.json` | 结论台账：契约字段全回填 + 逐元素来源 + 机器检查 + 诚实状态 |

通用参数：`--input DIR`（缺省按 `/input`、`/app/input`、`./input`、脚本上级 `input/` 取第一个存在的）、`--work DIR`（缺省 `/app/work`，否则 `./work`）、`--output DIR`（缺省 `/app/output`，否则 `./output`）。所有命令**退出码恒为 0**，失败信息走 `result.json` / `check.json` / `exceptions`。

## 1. 用途与适用条件

**做**：把「科研材料 → 实体—关系中间表示 → 分层可编辑 SVG → 真实 PNG/PDF → 可核验台账」走完，并保证图中每个名称、关系、方向、数值、单位都能回指一句原文或一个表格单元格。

**适用**：工单类型 `editable_relationship_schematic`（关系/机制示意图）、流程链、层级/包含结构图、表驱动数据面板；材料为 PDF 论文片段、md/txt 笔记、CSV/TSV 表、JSON/YAML/TeX 片段；需要「可编辑源文件 + 导出件 + 每元素来源」，或给定既有 SVG 做**保结构局部编辑**。

**不适用**（硬边界）：统计方法选择与数值计算、海报/封面版式与艺术插画、正文写作与文献综述。材料里没有的对象**一律不补造**：进 `exceptions` / `pending_human`，不画进图。

## 2. 触发与不触发

触发：用户给出科研材料并要求「画/改一张示意图、机制图、通路图、流程/装置图、graphical abstract、数据面板」，且要求可编辑、可投稿、可追溯来源。

不触发：只要文字描述、只要配色/审美建议、要求纯装饰插画、要求统计建模或写正文。此时直接回答，不启动本 Skill。

## 3. 运行契约

| 项 | 规定 |
| - | - |
| 输入 | `/input/case.json`（含 `output_contract`、`task_instruction`）、`/input/task.md`、材料与工单；PDF 是真文件，无预抽取答案层 |
| 输出 | `/app/output/result.json`（原样回填 `output_contract` 全部字段，不改名、不漏键，缺值 `null`/`[]`）+ 三件图稿 + 模型 + 编辑记录 |
| 退出码 | 恒 `0`；`init` 先写 partial，`build` 无条件 finalize 覆盖 |
| 依赖 | Python ≥3.8 纯标准库；`pdftotext`、`cairosvg`、`rsvg-convert`、`inkscape`、`convert`、`soffice` 全部按需探测、缺失即降级并记录 |
| 网络 | 不联网；不依赖 CWD（资源以 `Path(__file__).resolve().parent` 定位） |
| 预算 | 64 请求 / 900 秒 / 单回复 16384 token：确定性重活在脚本，模型只读材料 + 写一次工作稿 + 看校验 |

## 4. 五条命令

**`init`** — 解析 `case.json`（`case_id`、`output_contract` 三种写法：`list[str]` / `list[dict]`（取 `name|field|key|id`）/ `dict`、`task_instruction`）；扫描输入树登记每份材料的路径、类型、字节、sha256、行数、页数，建**行级 locator**（文本 `notes.md#L12`、PDF `paper.pdf#p3,L7`、表格 `data.csv#row=4`）；按语义键解析工单；用词表抽**候选**三元组（含被动翻转）；立刻写合法 partial `result.json`。

**`show`** — 打印：案例摘要与契约字段名；材料清单；工单对象表（实体 `[E01]`、关系 `[R01] A -[type]-> B`、图例、画布/导出、基线图与编辑指令）；**带 locator 的材料原文摘录**（优先命中工单实体/候选词的句子及上下文）；候选三元组（标 `<-passive`）；表格表头与前几行；基线 SVG 的 id 与文本；`draft.json` 最小骨架。全文另存 `/app/work/show.txt`。

**写工作稿** — 最小形态（完整字段字典见 `references/authoring-guide.md` §1）：

```json
{"figure": {"title": "...", "kind": "relationship_schematic"},
 "entities": [{"id": "e1", "label": "<逐字来自材料>", "entity_type": "cytokine", "group": "extracellular",
               "col": 0, "row": 0, "evidence": {"locator": "notes.md#L3", "quote": "<该行原文，逐字>"}}],
 "relations": [{"id": "r1", "from": "e1", "to": "e2", "type": "activation", "direction": "forward",
                "evidence": {"locator": "notes.md#L3", "quote": "<该行原文，逐字>"}}],
 "legend": [{"key": "activation", "label": "Activation", "color": "#0072B2", "marker": "arrow"}],
 "groups": [{"label": "Cytoplasm", "members": ["e2", "e3"]}],
 "annotations": [{"text": "<材料里出现的条件/单位>", "evidence": {"locator": "...", "quote": "..."}}],
 "edit": {"mode": "none"}, "exceptions": []}
```

写作纪律：`label` **逐字**取自材料；方向按**句子语义**定（`X is inhibited by Y` / `X 被 Y 抑制` → `Y → X`）；类型只从词表取（`activation / inhibition / binding / modification / expression / transport / containment / sequence / association`）；材料没有的名称、浓度、时间点、单位**不写**，缺什么写进 `exceptions`；编辑类用 `edit.mode="preserve"` + `operations[]`（`target_id` 必须是基线 SVG 已有 id）。

**`check`** — 逐条 `PASS/FAIL` 与计数，写 `/app/work/check.json`。致命项：`quote` 在声明 locator 上找不到、工单必需实体/关系未覆盖、关系端点悬空、图例缺编码类别、编辑目标 id 不存在。修 `draft.json` 到 `blocking` 为空再 `build`。

**`build`** — 读工作稿；**缺失/损坏/残缺时走兜底**（`auto_draft`：工单 + 候选重建，`degradations` 记 `draft_missing|draft_invalid|draft_incomplete`）；合并去重、补 id、定层级（有向图最长路径，环按 DFS 回边断开）；写 `figure_model.json`；**单向**渲染 `figure.svg` → `figure.png` → `figure.pdf`；生成 `content_map` 与 `compliance_checks`；无条件写最终 `result.json`。

**`selfcheck`** — 重算产物 sha256、重解 PNG/PDF、比对 SVG id 与 `content_map`、由模型重渲染比对字节、`pdftotext` 反抽证明文字是活的；打印 `verdict=ok|partial`。

## 5. 输入发现（语义识别，不假设固定键名）

1. `case.json`：优先 `/input/case.json`，否则输入树任意 `case*.json`；损坏也继续（`case_id=null`，错误进 `errors`）。
2. `output_contract` 原样透传到根：键名不改、未知键保留、缺值 `null`。
3. 工单候选：`case.json` 的 `organizer_workorder / organizer_edit_workorder / workorder / figure_workorder / figure_spec`；输入树任意 `*workorder*.json`；`material.json` 内的工单块。
4. 字段按语义键匹配（同义命中即可）：`figure_title|title|caption`、`required_entities|entities|nodes|objects`、`required_relations|relations|edges|links`、`legend_requirements|legend`、`canvas|size|dimensions`、`export|export_formats|dpi`、`source_artifact|baseline|edit_target`、`edit_operations|edits|changes`、`style|font_family|palette`、`required_annotations|must_include`。
5. 材料按**真实内容**读：`.md/.txt/.csv/.tsv/.json/.yaml/.tex/.xml/.svg/.log/.r/.py` 直读；`.pdf` 只走 `pdftotext -layout`（无文本层记 `no_text_layer`，绝不用文件名猜内容）；`.docx/.xlsx/图片` → `unsupported_source` + `pending_human`。
6. 编辑基线：输入树里的 `*.svg`（优先工单指向的），登记 sha256 与元素 id 表，作为 source-preserving 编辑对象。

## 6. 输出契约 `result.json`

| 字段 | 内容 |
| - | - |
| `case_id` | 原样回填（无则 `null`，不编造） |
| `status` | `ok`（三件产物探针通过 + 检查全过 + 必需项全覆盖 + 用工作稿）/ `partial`（有已记录缺口）/ `input_error`（无 case.json 且无可读材料） |
| `editable_source` | `{path, format:"svg", editable, text_live, layers[], text_count, element_count, marker_types[], sha256, coordinate_system, mode}` |
| `export_artifact` | `{png:{path,engine,width,height,dpi,bytes,probe}, pdf:{path,engine,pages,vector,bytes,text_extracted,probe}}`；缺件给 `{path:null,status:"missing"}` |
| `content_map` | `{entities[],relations[],legend[],groups[],data_points[],coverage{},svg_ids_expected[],svg_sha256}` |
| `compliance_checks` | `canvas / svg_wellformed / id_map / labels_verbatim / style / markers / legend_consistency / layout / text_live / pixel_probe / pdf_probe / determinism / pass / failures` |
| `exceptions` | `[{type, object, reason, action, locator}]` |
| 信封 | `errors[]`、`degradations[]`、`uncertainty[]`、`pending_human[]`、`sources[]`、`changes[]`、`runtime{}`、`output_contract_echo` |

`content_map` 每条带 `source:{kind, locator, quote}`：实体 → 材料行；关系 → 依据句；数据点 → `table#row=R,col=C` 且 `quote` 为单元格原文。`svg_ids_expected` 与 SVG 实际 id 必须双向全等（`id_map`）。逐字段说明见 `references/authoring-guide.md` §4。

## 7. 方法说明：证据如何变成图面

1. **抽取**：工单对象优先；工单缺失时用 `show` 的候选三元组作线索，由你在工作稿里定稿。
2. **校核**：`label`/`quote` 做 NFKC + 小写 + 空白归一后，先在**声明的 locator 行**逐字查找（`quote_here`），再查全语料（`quote_anywhere`）；只有前者成立才 `verified`。
3. **建模**：有向图最长路径定列（左→右），同层按 `row`/声明序；节点尺寸由标签换行决定；画布自适应并留标题/图例/注释区。
4. **成图**：单一几何 `geom` 同时喂 SVG / PNG / PDF 三个渲染器，结构上排除「三套几何各自手写导致对不上」。
5. **导出**：PNG 走 `cairosvg → rsvg-convert → inkscape → convert → soffice → 内置光栅器`，每个候选都过探针（PNG magic、尺寸、宽高比、非白像素比例），不合格自动降级；PDF 由内置矢量写入器生成（单页、页面=画布、base-14 Helvetica），并用 `pdftotext` 反抽证明未转曲。
6. **记账**：`compliance_checks` + `content_map` + `exceptions` 同源生成，`status` 由事实决定。

## 8. 视觉规范（内置，非审美偏好）

| 项 | 值 | 理由 |
| - | - | - |
| 字体栈 | `Arial, Helvetica, 'DejaVu Sans', sans-serif` | 不嵌字体、不转曲，换机可编辑 |
| 字号阶梯 | 图题 15 / 实体 11 / 注释·图例 9.3 px（≈11/8.5/7 pt） | 单栏 85 mm 仍可读 |
| 线宽 | 帧 1.0、连线 1.1、分区带 0.8 | 印刷不糊 |
| 端点语义 | 箭头=activation；T 杠=inhibition；菱形=binding；方头=containment；细箭头=其余 | 正负/方向一眼可辨，不靠颜色 |
| 分类上限 | 图例关系类型 ≤6 类 | 超出合并并记 `legend_merged` |
| 配色/间距 | Okabe–Ito 子集；列距 64、行距 34、外边距 26 px | 色盲安全、连线不穿框 |

导出：PNG 目标宽 1800 px（≈192 dpi，写入 `export_artifact.png.dpi`）；PDF 单页、页面=画布；两者都由探针复核。

## 9. 校验规则

工作稿：C1 合法 JSON、C2 实体≥1/id 唯一/label 非空、C3 quote 在声明行逐字命中、C4 quote 全语料可查、C5 端点已声明、C6 类型在词表、C7 被动语态方向提示、C8 工单覆盖率、C9 label 逐字可查、C10 图例覆盖全部编码、C10e 编辑目标 id 存在。

产物：`canvas`、`svg_wellformed`（分层组/活文字/marker）、`id_map`（期望 id 全中）、`labels_verbatim`、`style`（最小字号线宽）、`markers`、`legend_consistency`（编码集合==图例集合）、`layout`（无重叠/无越界）、`text_live`（SVG 文字节点 + PDF 反抽命中）、`pixel_probe`（IHDR、非白像素比例）、`pdf_probe`（头/尾/页/矢量）、`determinism`（两次渲染同哈希）。逐条含义见 `references/authoring-guide.md` §6。

## 10. 评分维度 → 实现落点

| 维度 | 落点 |
| - | - |
| 完成度 | `figure.svg/png/pdf` 三件存在且探针通过；编辑类另有 `edit_record.json` |
| 正确性 | 类型→端点语义；被动句翻转；`labels_verbatim`；每条 `quote` 可在声明行复现 |
| 完整性 | `content_map.coverage` 与工单逐项比对；图例、分区、单位、注释齐备 |
| 可核验性 | 每元素 locator+quote；`id_map` 双向全等；`sources[]` 带 sha256 |
| 质量增益 | 字号阶梯/线宽/避让/自适应画布 + 导出前合规检查，减少返工 |
| 效率增益 | `init→check→build` 三条命令走完链路，`runtime.elapsed_s` 与 `check` 计数可对照 |
| 可验证性 | `determinism` 双哈希 + 同 draft 重跑字节一致 + `check` 前后差异可查 |
| 创新 | `quote_here` 证据锚定、单一几何多渲染器、端点语义词表、`pdftotext` 反抽证明文字活 |
| 可靠性 | 恒 0 退出；partial 先行；引擎降级矩阵；`check` 给可执行修正提示 |
| 生态 | 本文件 + `references/authoring-guide.md` + 最小示例（标注示例） |

## 11. 失败处理与降级

| 情况 | 处置 | 记录 |
| - | - | - |
| 无 `/input`、无材料 | 仍写合法 `result.json`（`status=input_error`），产物为可打开的占位空画布 | `no_input_dir` |
| `case.json` 损坏 | `case_id=null` 继续跑，契约用默认五字段 | `case_json_invalid_json` |
| 工单缺失/不全 | 用候选三元组 + `task_instruction` 推断；无依据的对象不进图 | `workorder_missing` |
| 工作稿缺失/损坏/残缺 | **兜底**：`auto_draft` 重建，仍出三件产物 + 完整 result.json | `draft_missing/invalid/incomplete` |
| `quote` 不在声明行 | `check` FAIL；`build` 仍画但 `verified=false` | `quote_unsourced` |
| 端点缺失/方向矛盾 | 不入图，进 `pending_human` | `dropped_relations` |
| PDF 无文本层 | 记 `no_text_layer`，不猜内容 | `no_text_layer` |
| 无 SVG 转换器 | PNG 走内置光栅器（位图字，非 ASCII 跳过并记录） | `png_builtin_raster` |
| 无 `pdftotext` | 跳过 PDF 反抽，其余检查不变 | `pdf_text_probe_skipped` |
| 未捕获异常 | 顶层 try/except：写 `errors.traceback_unhandled`，仍 finalize，退出 0 | — |

## 12. 自查

```bash
python3 -B scripts/main.py init      # 确认 case_id 与契约字段
python3 -B scripts/main.py show      # 读完材料再动笔
# ... 写 /app/work/draft.json ...
python3 -B scripts/main.py check     # blocking 必须为空
python3 -B scripts/main.py build
python3 -B scripts/main.py selfcheck # VERDICT
python3 -B scripts/main.py --help    # 退出码 0
```

人工复核三件事：① 打开 `figure.png` 看实体与箭头方向是否与材料语义一致；② 在 `figure.svg` 改一个 `<text>` 文字，用同一渲染器重导出，PNG 应同步变化（可编辑性）；③ 抽 3 条 `content_map` 的 `locator`，用 Read 打开原文核对 `quote` 逐字一致。

## 13. 最小调用示例（示例，非正式案例结果）

`/input/case.json`：

```json
{"case_id": "demo-alpha",
 "output_contract": ["editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions"],
 "organizer_workorder": {"workorder_type": "editable_relationship_schematic",
  "figure_title": "Demo: signal relay",
  "required_entities": ["LIGAND-A", "RECEPTOR-B", "KINASE-C", "TARGET-D"],
  "required_relations": [{"from": "LIGAND-A", "to": "RECEPTOR-B", "type": "binding"},
   {"from": "RECEPTOR-B", "to": "KINASE-C", "type": "activation"},
   {"from": "KINASE-C", "to": "TARGET-D", "type": "activation"},
   {"from": "TARGET-D", "to": "KINASE-C", "type": "inhibition"}]}}
```

`/input/artifacts/notes.md`：`LIGAND-A binds RECEPTOR-B at the membrane.` / `RECEPTOR-B activates KINASE-C.` / `KINASE-C activates TARGET-D.` / `TARGET-D feeds back to inhibit KINASE-C.`

```bash
python3 scripts/main.py init && python3 scripts/main.py show
# 写 draft.json：4 实体 + 4 关系（每条带 notes.md#L2..L5 的 quote）+ 4 类图例
python3 scripts/main.py check   # blocking=[] ; quote_here 8/8 ; coverage 1.0
python3 scripts/main.py build
```

示意输出（**示例，非正式案例结果**）：`figure.svg` 4 个 `<g id="layer-*">`、≥9 个 `<text>`、箭头/菱形/T 形三种端点；`figure.png` 真实 IHDR、非白像素比例 > 0.01；`figure.pdf` 1 页且文字可抽取；`result.json` 中 `status=ok`、`entity_coverage=1.0`、`compliance_checks.pass=true`。

## 14. 文件清单与依赖

| 文件 | 作用 |
| - | - |
| `SKILL.md` | 本说明（用途、调用、契约、方法、边界、失败处理、自查） |
| `scripts/main.py` | 五命令入口：编排、契约回填、content_map/compliance 组装、兜底与 finalize |
| `scripts/casekit.py` | 输入发现、材料读取与 locator、工单归一化、候选抽取、覆盖统计、兜底工作稿 |
| `scripts/draw.py` | 模型归一、分层布局、单一几何、SVG 序列化 |
| `scripts/render.py` | PNG 光栅化（引擎链 + 内置）、矢量 PDF 写入、编辑保真记录 |
| `scripts/verify.py` | PNG/PDF 探针、SVG 审计、布局与确定性检查、工作稿规则引擎 |
| `references/authoring-guide.md` | 工作稿 schema、关系词表、证据规则、字段字典、校验项、样式/导出预设、故障表 |

依赖：Python ≥3.8（3.12 实测），仅标准库。可选外部程序（缺一即降级，不会崩）：`pdftotext`（读 PDF / 反抽 PDF 文字）、`cairosvg`、`rsvg-convert`、`inkscape`、`convert`、`soffice`。

## 15. 已知限制

- 关系抽取是词表 + 句法启发式，不建模剂量/时序/概率；长句可能抽错端点，故每条关系须由你在工作稿里给 quote 定稿，脚本只校验不代判。
- 布局是确定性分层启发式，不是期刊手工排版；实体 >18 个时建议在工作稿里显式给 `col/row`。
- 内置 PNG 光栅器只支持 ASCII 位图字（CJK 跳过并记录）；PDF 文本层仅支持 Latin，非 Latin 在 PDF 中替换为 `?` 并记 `degradation_text`，SVG 仍为权威源。
- `.docx/.xlsx` 与图片材料不解析，只登记缺口；编辑模式只改文字与既有属性，不新增图元。

## 16. 维护

改词表 → `casekit.REL` + 手册 §3；改样式 → `draw.STY` + 手册 §7；加导出引擎 → `render.export_png` 引擎链；加检查项 → `verify.py` + `main.build_figure` + 手册 §6，保持「检查项 ↔ 字段 ↔ 文档」三处同名。
