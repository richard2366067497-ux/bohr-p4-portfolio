# 字段字典、locator 语法、评分对照与失败处置

本文件是 `SKILL.md` 的展开细节。与脚本冲突时，以脚本输出（`show --workorder`、`check`、
`compliance_checks.json`）为准，并按版本记录同步文档。

## 1. workorder 里会被读取的键

`case.json` 的 `organizer_workorder`（或 `/input/*workorder*.json`）里，脚本按语义找下列键；名字不固定，
找不到就用默认值并把说明写进 `result.json.runtime.spec_defaults`。

| 语义 | 可接受的键名 | 取值 | 缺省 |
|-|-|-|-|
| 画布 | `canvas` / `figure_size` / `canvas_size` / `dimensions` | `{width,height,unit,dpi}`、`[w,h]`、`"180x112 mm"` | 180×112 mm, 300 dpi |
| 阅读方向 | 由画布长宽比推断 | 宽画布一行四栏，竖画布一列四段 | 自动 |
| 必需面板 | `required_panels` / `panels` / `panel_order` / `narrative` | `[{order,role}]` 或 `["problem",...]` | problem→method→results→implication |
| 必需元素 | `must_include` / `required_elements` / `required_labels` | 字符串或 `{label}` | 无 |
| 禁用内容 | `must_exclude` / `forbidden` | 字符串 | 无 |
| 编码通道 | `encodings` / `visual_encodings` / `channels` | `[{channel}]` | 无强制 |
| 图例 | `legend_requirements` / `legend` | `{max_items,require_units}` | 8 项、要求单位 |
| 字号 | `style.min_font_pt` / `min_font_size` | 数值 pt | 7 pt |
| 配色 | `style.palette` / `colorblind_safe` / `grayscale_safe` | 字符串 / 布尔 | Okabe-Ito 子集，均为 true |
| 导出 | `export.formats` / `export.dpi` / `export.color_space` | 列表 / 数值 | svg+pdf+png, 画布 dpi, RGB |
| 待编辑原图 | `source_artifact` / `source_figure` / `original_figure` | 相对 `/input` 的路径 | 自动取 `/input` 下第一个 `.svg` |

单位换算在 `core.canvas_spec`：mm/in 按 72 pt/in 换算，px 按 `dpi` 换算，最终统一成 pt；模型坐标就是 pt。

## 2. `work/draft.json`（Agent 手写，脚本不代写）

```jsonc
{
  "title": "≤140 字，研究对象 + 结论",          // 必填
  "subtitle": "方法或意义一行",                  // 可选
  "caption": "图注：材料名 + 核对入口",          // 可选，两行内
  "panels": [                                    // 2–4 个，顺序 = 阅读顺序
    {"id": "P1", "role": "problem", "heading": "≤6 词", "flow": "how?",
     "claim": "≥12 字的一句判断（不是整段照抄）",   // flow 可选：与上一面板的关系词
     "items": [{"id": "E1", "kind": "text",       // text | value | chart
                "label": "≤8 词", "detail": "条件/方向/限定", "value": "2.4-fold",
                "evidence": {"source": "note.md", "locator": "para.4", "quote": "逐字原文"}}]}
  ],
  "encodings": [
    {"id": "enc1", "channel": "length",        // color|length|area|brightness|shape
     "meaning": "条形长度 = 相对活性", "unit": "% of WT", "panel": "P3",
     "data": {"path": "results.csv", "x": "variant", "y": "flux"},
     "categories": [{"label": "WT", "value": "100", "num": 100, "color": "#0072B2",
                     "evidence": {"source": "results.csv", "locator": "para.2",
                                  "quote": "WT,100,reference"}}]}
  ],
  "legend": [{"label": "WT", "meaning": "wild type"}],
  "edits":  [{"target_id": "panel3_label", "original": "旧文本",
              "revised": "新文本", "reason": "workorder 指定"}]
}
```

规则：

- `role` 建议直接用 `problem` / `method` / `results` / `implication`；`conclusion`、`question`、`approach`、
  `findings` 会被归一化，但写规范值最省事。
- 坐标一律不写。所有几何由 `layout.compose()` 从画布推导，写坐标会破坏确定性。
- `kind: "chart"` 指该图元使用本面板绑定的编码；不写 `chart` 时编码块自动追加到面板末尾。
- `encodings[].data` 存在时，脚本按表头取 `x`/`y` 两列，**每行原文**写入该分类的 `quote`，
  `locator` 用该行的 `para.N`。这样柱长和柱上数值都能逐行回查。
- `edits[]` 只在编辑既有图稿时写：`target_id` 是原图 `<text id>`，`build` 会就地替换并产出
  `graphical_abstract_source_kept.svg`，原图 sha256、保留的 id 数量都进 `edit_record.json`。

## 3. locator 语法

| 材料 | locator | 例 | 索引方式 |
|-|-|-|-|
| md / txt | `para.<段号>`（空行分段） | `para.4` | 空行切块 |
| csv / tsv | `para.<行号>`（第 1 行是表头） | `para.3` | 逐行 |
| PDF（`pdftotext` 可用） | `p.<页> b.<块>` | `p.3 b2` | 页 + 空行块 |
| PDF（抽不出文本） | `p.<页>`，quote 靠人工读页 | `p.5` | 不产出段落 |

取 locator 的唯一正确方式：`show` / `show --grep` 打印什么就抄什么。句子对而位置写偏时，脚本会把
locator 改成实际的并标 `relocated`，同时在 `exceptions` 留记录。

## 4. `result.json` 键位

| 键 | 内容 |
|-|-|
| `output_contract` 的每个键 | 原样保留，顺序不变；语义匹配到产物，匹配不到为 `null` |
| `case_id` | `case.json` 的 `case_id`/`id`/`case_name`，否则 case 文件名 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `editable_source` | `{path,format,editable,layers,text_count,sha256,viewbox_pt}` |
| `export_artifact` | `{pdf{pages,vector,page_pt,sha256}, png{px,dpi,engine}, svg{...}}` |
| `content_map` | 见 §5 |
| `compliance_checks` | 见 §6 |
| `edit_record` | `{mode,source_artifact,patched_artifact,changes,parameters,determinism,materials,exports}` |
| `figure_model` | `{path,digest,panels,elements}` |
| `exceptions[]` | `{code,where,detail,action}`：`plan_missing` / `element_dropped` / `locator_corrected` |
| `sources[]` | `{id,name,kind,bytes,sha256,paragraphs,method}` |
| `uncertainty[]` / `pending_human[]` | 无法确定、需要人确认的事项 |
| `errors[]` / `degradations[]` | 运行异常与降级事件 |
| `changes[]` | `{what,detail}` 构建流水 |
| `runtime` | 工具、python、耗时、`contract_keys_total/filled`、`unmatched_contract_fields`、`spec_defaults` |

## 5. `content_map.json` 结构

```
figure   {title, canvas_pt, direction, digest}
panels[] {id, order, role, heading, claim, flow, bbox, elements[], source{source,locator,quote,status}}
elements[]{element_id, panel, role, kind, text, svg_id, bbox, evidence{source,locator,quote,status}}
encodings[]{id, channel, meaning, unit, panel, marks[{mark_id,label,value,num,color}],
            source{source,locator,quote,per_mark[{mark_id,locator,quote}]}}
legend[] {label, meaning, color}
coverage {panels, elements, encoding, numbers_traced}
numbers  {drawn[], untraced[]}
```

`evidence.status`：`verified`（locator 与引文都对上）/ `relocated`（句子对、位置被改正）/
`no_quote`（缺引文）/ `unverified`（任何段落都找不到该逐字片段）。只有前两种会出现在图上。

## 6. `compliance_checks.json` 结构

```
canvas{...matches_workorder}   fonts{min_pt,spec_min_pt,ok}
reading_order{direction,panel_roles,spec_order,ok}
encoding_consistency{encodings,ok,issues}
colourblind{palette,redundant_coding}
grayscale_contrast{distinct_luminances,min_delta,threshold,ok}
overflow{inside_canvas,dropped_count,dropped,ok}
numbers{drawn,untraced,ok}
svg{layers,editable_text,bytes}  pdf{pages,vector,page_pt,fonts,bytes}  png{engine,px,dpi,note}
spec{required_roles,must_include,must_exclude,required_channels,defaults}
warnings[]  failures[]  pass
```

`failures` 非空时 `status` 一定不是 `ok`；`warnings` 只说明降级与可读性提醒。

## 7. 评分维度与失败处置

维度→产物的完整对照见 `SKILL.md` §12，失败处置见 §11；本文件只给字段级细节：
`compliance_checks` 的 `failures` 非空时 `status` 一定不是 `ok`，`warnings` 只记降级与可读性提醒。
`check` 报 `unverified` 时用 `show --grep` 取回整段原文；报 `number(s) [...] not in its quote` 时
换成含该数字的句子或删掉数字；报 `must_include not covered` 时补图元或用词。

数字识别规则：只有**独立数字**才算数据值（`78 %`、`2.4-fold`、`p<0.01`）。嵌在标识符里的数字
（`SLC26A9`、`E203Q`、`p53`）按名称处理，不参与来源校验——否则基因名会不断触发假报错。
`build` 时任何引文不成立、或图元数字不在自己引文里的元素都会被剔除并写进 `exceptions`；
claim 里没有来源的数字会被从图面文本中删掉并记 `number_untraced`。

## 8. 复现与复用

- 复现：同一 `/input` + 同一 draft 连跑两次 `build`，`graphical_abstract.svg` 与 `.pdf` 字节一致
  （`selfcheck` 会用 `figure_model.json` 重算 SVG 并比对 sha256）。
- 复用：换材料只改 draft，不改脚本；需要新画布或新字号时改 workorder，而不是改坐标。
- 对照：报告里同时给 `check` 的 PASS 行、`content_map.coverage`、`exceptions` 清单，
  比只贴一张图更能说明“图是可核验的”。
