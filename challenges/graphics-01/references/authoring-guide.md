# schematic-trace-studio · 参考手册

配套 `SKILL.md` 的字典层：工作稿 schema、关系词表、证据规则、`result.json` 字段、校验项、样式与导出预设、故障表。
与脚本冲突时以脚本为准并同步本文（见 SKILL.md §16）。

## 1. 工作稿 `draft.json`

| 顶层字段 | 类型 | 必填 | 说明 |
| - | - | - | - |
| `figure.title` / `figure.kind` | str | 否 | 缺省取工单 `figure_title`，再缺省 `Figure <case_id>` |
| `entities` | list | **是** | 见 1.1，至少 1 个 |
| `relations` | list | 否 | 见 1.2；无关系则退化为并列实体面板 |
| `legend` | list | 否 | 见 1.3；缺项由词表补全并记 `legend_gap` |
| `groups` | list | 否 | `{label, members[]}`，同组 ≥2 个时画分区带（表达包含/边界） |
| `annotations` | list | 否 | `{text, evidence{locator,quote}}`；只写材料里真实出现的条件/单位/时相 |
| `chart` | obj | 否 | `{title, unit, rows:[{label, value, color}]}`；`value` 必须是表里的数值 |
| `edit` | obj | 否 | `{mode:"preserve", operations:[…]}`，见 1.4 |
| `exceptions` | list | 否 | `{type, object, reason, action, locator}`，并入 `result.json` |

### 1.1 `entities[]`

| 字段 | 必填 | 说明 |
| - | - | - |
| `id` | **是** | 图内唯一；自动规范为 XML 安全 id，重复自动加后缀 |
| `label` | **是** | **逐字**取自材料；不写材料里没有的基因名/蛋白名/缩写 |
| `entity_type` | 否 | 短类型（cytokine/kinase/TF），写入 SVG `data-entity-type` |
| `group` | 否 | 分区名（extracellular/membrane/cytoplasm/nucleus） |
| `col` / `row` | 否 | 列号（0 起）/ 同列排序；省略按关系图最长路径分层 |
| `evidence.locator` | **是** | 见 §2.1 |
| `evidence.quote` | **是** | 该行内的连续原文子串（可截断，不可改写） |

### 1.2 `relations[]`

| 字段 | 必填 | 说明 |
| - | - | - |
| `from` / `to` | **是** | 必须指向 `entities[].id`；悬空则该关系不入图并记 `dropped_relations` |
| `type` | **是** | 见 §3 词表；未收录归并 `association` 并记 warning |
| `direction` | 否 | `forward`（默认）/ `reversed`（等价交换 from/to） |
| `condition` | 否 | 材料明确的条件/剂量/时相，会标注在连线中点 |
| `evidence.locator` / `quote` | **是** | 关系依据句所在行与原文 |

### 1.3 `legend[]`

`{key: <关系类型>, label, color:"#RRGGBB", marker:"arrow|tbar|diamond|square|thin|line"}`
规则：**图例项数必须等于图面实际编码类别数**（C10）。多画的类别自动补进图例；未使用的图例项保留但会在 `legend_consistency` 中暴露。

### 1.4 `edit.operations[]`（source-preserving）

`{target_id: <基线 SVG id>, target_text: <原文>, new_text: <新文字>, evidence:{locator,quote}}`
`target_id` 必须在基线 SVG 已存在（C10e）。`build` 写 `edit_record.json`：基线 sha256、逐条 original→revised、`ids_preserved`、`edited_sha256`。只改文字，不增删图元。

### 1.5 `exceptions[].type` 常用值

`missing_in_source`（材料缺该项）、`conflict`（材料矛盾，`reason` 给两处 locator）、`unsupported_source`（docx/图片）、`pending_human`（需人工确认）、`label_unsourced`、`quote_unsourced`。

## 2. 证据规则

### 2.1 locator 格式

| 材料 | 格式 | 例 |
| - | - | - |
| 文本/md/csv/tex… | `<相对路径>#L<行号>` | `artifacts/notes.md#L3` |
| PDF（`pdftotext -layout` 分页） | `<相对路径>#p<页>,L<行>` | `paper.pdf#p3,L12` |
| 表格行 | `<相对路径>#row=<行>` | `data/levels.csv#row=4` |
| 整份文件 | `<相对路径>` | `notes.md` |
| 工单对象 | `workorder#required_entities[i]` | 来源是任务书而非材料 |

行号漂移时 `check` 给出 `suggested_locator`（found at …）。

### 2.2 逐字性

`quote` 与行文本都做 NFKC + 小写 + 空白归一后，`quote` 必须是该行的连续子串。允许截取行内片段、大小写与连字符（`–—−`）差异；不允许跨行拼接、改写语序、翻译。

### 2.3 三类缺口的写法

| 情况 | 写法 |
| - | - |
| 材料缺对象 | 不画；`missing_in_source`，写明对象与已检索范围 |
| 材料互相矛盾 | 画一处、记另一处；`conflict` + 两个 locator 与原文 |
| 无法判断方向 | 画无向 `association` + `pending_human`，不猜 |

## 3. 关系词表（类型 → 端点 → 颜色 → 中英线索）

| type | 端点 | 颜色 | 英文线索 | 中文线索 |
| - | - | - | - | - |
| `activation` | 实心箭头 | `#0072B2` | activate, stimulate, promote, induce, upregulate, enhance, drive, trigger | 激活、促进、上调、增强、诱导、触发 |
| `inhibition` | T 形横杠 | `#D55E00` | inhibit, suppress, repress, block, reduce, decrease, attenuate, downregulate | 抑制、下调、阻断、降低、减弱、阻遏 |
| `binding` | 空心菱形 | `#009E73` | bind, interact with, associate with, complex with, dock | 结合、互作、相互作用、复合、锚定 |
| `modification` | 细箭头 | `#CC79A7` | phosphorylate, methylate, ubiquitinate, cleave, acetylate | 磷酸化、甲基化、泛素化、剪切、乙酰化 |
| `expression` | 细箭头 | `#56B4E9` | express, encode, transcribe, translate | 表达、编码、转录、翻译 |
| `transport` | 细箭头 | `#E69F00` | transport, translocate, secrete, export, import, release | 转运、易位、分泌、输出、输入、释放 |
| `containment` | 方头 | `#8C8C8C` | contain, comprise, include, consist of, part of, subunit of | 包含、组成、属于、包括、位于 |
| `sequence` | 细箭头 | `#666666` | then, subsequently, followed by | 随后、然后、接着、之后 |
| `association` | 细线（虚线） | `#3C3C3C` | associate, correlate, related to, linked to | 相关、关联、有关 |

选择规则：动词决定类型（材料说 binds 就不能画成 activates）；`X is inhibited by Y` / `X 被 Y 抑制` 方向为 `Y → X`；一句多动词取主句谓语，判不出用 `association` + `pending_human`；超过 6 类合并为 `association`/`containment` 并记 `legend_merged`。

## 4. `result.json` 字段

| 字段 | 内容 |
| - | - |
| `case_id` | 原样回填；无则 `null` |
| `status` | `ok` / `partial` / `input_error`（判定见 §5） |
| `editable_source` | `path, format="svg", editable, text_live, layers[], text_count, element_count, marker_types[], sha256, coordinate_system, mode` |
| `export_artifact.png` | `path, engine, width, height, dpi, bytes, probe{ok,nonwhite_ratio,bit_depth,color_type}, attempts[]` |
| `export_artifact.pdf` | `path, engine="builtin-vector-pdf", pages, vector, bytes, text_extracted, label_hits, probe{header,eof,page_objects,media_box}` |
| `content_map.entities/relations/legend/groups[]` | 每条 `id…` + `svg_ids[]` + `source{kind,locator,quote}` + `verified` |
| `content_map.coverage` | `required_/mapped_ entities, relations, *_coverage, legend_items, encodings_used, entities_with_locator, entities_verified, relations_verified, unmapped_required[]` |
| `content_map.svg_ids_expected[]` | 应与 SVG 实际 id 双向全等 |
| `compliance_checks` | 见 §6.2，含 `pass`、`failures[]` |
| `exceptions[]` / `degradations[]` / `errors[]` / `pending_human[]` / `uncertainty[]` | 缺口、降级、输入错误、待人工、不确定性 |
| `sources[]` | `rel, kind, sha256, bytes, lines, role` |
| `changes[]` | 编辑类逐条改动（来自 `edit_record.json`） |
| `runtime` | `elapsed_s, engines{png,pdf,pdf_text_probe}, contract_fields, draft_used, check_blocking, input_dir, output_dir` |
| `output_contract_echo` | `case.json` 里 `output_contract` 的原始写法 |

`output_contract` 每个键在根节点占位：能产出就填，不能产出保持 `null` 并记 `unknown_contract_field`。不改名、不漏键。

## 5. 状态判定

| status | 条件 |
| - | - |
| `ok` | 三件产物探针通过 + `compliance_checks.pass` + 工单必需项全覆盖 + 全部实体 `verified` + 用工作稿（非兜底） |
| `partial` | 任意已记录缺口：检查失败、必需项未覆盖、存在未溯源实体、无工作稿走兜底 |
| `input_error` | 无 `case.json` 且无可读材料（仍写合法 `result.json` 与占位产物） |

有缺口就写 `partial`；`status` 与 `compliance_checks` 必须自洽。

## 6. 校验项

### 6.1 工作稿规则（`check` / `build` 共用）

| ID | 规则 | 级别 |
| - | - | - |
| C1 | 工作稿存在且为合法 JSON 对象 | blocking（否则兜底） |
| C2 | 实体 ≥1、`id` 唯一、`label` 非空 | blocking |
| C3 | 每条 `quote` 在声明 locator 行逐字命中 | blocking |
| C4 | 每条 `quote` 至少全语料可查（行号漂移提示） | warning |
| C5 | 关系两端已声明 | blocking |
| C6 | 类型在词表内 | warning → 归并 `association` |
| C7 | 抑制类被动语态方向提示 | warning |
| C8 | 工单覆盖率 100% | 未覆盖进 `unmapped_required` |
| C9 | `label` 材料中逐字出现 | 未命中 → `label_unsourced` |
| C10 | 图例覆盖全部编码类别 | blocking |
| C10e | 编辑目标 id 存在于基线 | blocking |

### 6.2 产物检查（`compliance_checks`）

| 键 | 通过条件 |
| - | - |
| `canvas` | 宽高 > 40 |
| `svg_wellformed` | XML 可解析、有 `<svg>`、≥1 `<text>`、有 id、分层组 |
| `id_map` | `svg_ids_expected ⊆ SVG 实际 id` |
| `labels_verbatim` | 实体标签全部可溯源 |
| `style` | 字号 ≥ 6.5 px、线宽 ≥ 0.5 |
| `markers` | 端点种类 ≥ 编码类别数（≥2 类时 ≥2 种） |
| `legend_consistency` | 编码集合 == 图例集合 |
| `layout` | 无重叠、无越界 |
| `text_live` | SVG 文字节点数达标；记录 PDF 反抽命中比例 |
| `pixel_probe` | PNG 可解、非白像素比例 ∈ (0.0005, 0.98) |
| `pdf_probe` | `%PDF-` + `%%EOF` + 页对象 + 无位图 |
| `determinism` | 两次渲染 sha256 相同且等于产物 sha256 |
| `pass` / `failures[]` | 以上全真 / 失败键名 |

## 7. 样式与导出预设

| 项 | 值 |
| - | - |
| 画布 | 默认 960×560 px（viewBox 同尺寸，y 向下）；工单 canvas 为下限，内容更大时自动扩展 |
| 间距 | 外边距 26、列距 64、行距 34 px |
| 实体框 / 分区带 | 圆角 7、填充 `#F4F7FA`、描边 `#33404D` 1.0 / 虚线 `5 4`、填充 `#FBFBF7`、描边 `#9AA3AB` 0.8 |
| 字号阶梯 | 图题 15 / 实体 11 / 注释·图例 9.3 / 条件 8.3 px（≈11/8.5/7/6.2 pt） |
| 字族 | `Arial, Helvetica, 'DejaVu Sans', sans-serif`（不嵌字体、不转曲） |
| `figure.svg` | 分层 `<g id="layer-*">`、`<text>`+`<tspan>`、`<marker>` 按 (语义, 颜色) 生成 |
| `figure.png` | 目标宽 1800 px（≈192 dpi）；引擎链 cairosvg → rsvg-convert → inkscape → imagemagick → libreoffice → 内置光栅器 |
| `figure.pdf` | 单页、页面尺寸 = 画布 × 0.75 pt、base-14 Helvetica、真实文本 |

降级记录：`png.attempts[]`（每次引擎与失败原因）、`png.degradation`、`pdf.degradation_text`（非 Latin 在 PDF 文本层被替换）。

## 8. 故障与处置

| 现象 | 处置 |
| - | - |
| C3 FAIL | 看 `suggested_locator`，改 locator 或截取行内子串 |
| C8 FAIL | 补实体/关系（附 quote）；材料确无则记 `missing_in_source` |
| C10 FAIL | 补图例项（`build` 也会自动补并记 `legend_gap`） |
| `draft_missing` | 先 `show` 读材料，写工作稿再 `check`/`build` |
| PNG `engine=builtin-raster` | 无 SVG 转换器，位图字渲染；装 librsvg/cairosvg/imagemagick 可恢复 |
| `pdf_label_hits < 1` | 非 Latin 被替换；SVG 仍为权威，记 `degradation_text` |
| `layout.overlaps` | 减少同层实体、缩短 label 或调大画布 |
| `id_map.missing` | 别手改 SVG（派生件），回到 `build` 重建 |
| 编辑目标找不到 | 用 `show` 打印的基线 id 表校对，或改用 `target_text` |

## 9. 复用

把新案例做成冒烟测试：`/input` 放 `case.json` + `task.md` + 一份材料，跑五命令，`check` 的 `verdict=PASS` 即模板可用。改词表 → `casekit.REL` + §3；改样式 → `draw.STY` + §7；加导出引擎 → `render.export_png`；加检查 → `verify` + `main.build_figure` + §6.2，三处同名。
