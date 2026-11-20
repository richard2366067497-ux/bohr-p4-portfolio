# 机制图绘制契约（词表 / 字段字典 / 质量闸门）

本文件是 `SKILL.md` 的规则附录，`scripts/` 里的实现与这里逐条对应。改词表要同时改
`ledger.py:VERBS` 与本文件 §1；改画法要同时改 `render.py:EDGE_STYLE` 与 §1.3。

---

## 1 关系语义词表（文字 → 图元）

### 1.1 中英动词 → `relation_type`

匹配方式：小写后做**子串**匹配，命中即取该组类型；一句多动词按
`modification > transport > inhibition > activation > binding > recruitment` 取更具体的一层。

| `relation_type` | 英文词干 | 中文词 | 端点画法 |
|---|---|---|---|
| `activation` | activat, promot, induc, upregulat, stimulat, enhanc, driv | 激活, 促进, 上调, 诱导, 增强, 启动 | 实心箭头 |
| `inhibition` | inhibit, suppress, repress, block, downregulat, reduc, attenuat, restrain | 抑制, 下调, 阻断, 阻遏, 负反馈, 减弱 | **T 形端** |
| `binding` | bind, bound, interact, dimeriz | 结合, 结合于, 互作, 相互作用 | 空心箭头 |
| `modification` | phosphorylat, ubiquitin, acetyl, methylat, sumoylat, cleav | 磷酸化, 泛素化, 乙酰化, 甲基化, 切割 | 实心箭头 + `P`/`Ub` 徽标 |
| `transport` | translocat, transport, export, import, secrete, internaliz | 转运, 转位, 入核, 出核, 分泌, 内吞 | 粗线 + 双箭头 |
| `recruitment` | recruit, assembl | 募集, 组装, 形成复合物 | 细线 + 菱形端点 |
| `indirect` | —（由 `draft` 显式声明） | 推测, 推断 | 虚线 + 箭头 |
| `unspecified` | —（未命中或判不准） | — | 点划线、**无箭头** |

### 1.2 方向判定（三条规则，按序）

1. **语序**：`X 动词 Y` / `X <verb> Y` → `X → Y`（`X` 是主语，`Y` 是宾语）。
   因此 "A 被 B 激活" 是 `B → A`，不是 `A → B`。
2. **被动句**：英文 `Y is/are/was/were <verb>ed by X` → `X → Y`；中文 `X 被 Y 动词` → `Y → X`。
3. **判不出**：一方缺失、动词不在词表、或两个名字之间夹了从句导致位置不可靠 →
   `direction: "undirected"`，图上画无箭头点划线，并在 `pending_human` 写"需要确认方向的原文位置"。

`check` 会用第 1、2 条对 `draft` 里已声明的方向做**冲突扫描**：若材料里同一句同时出现两个名字且
语序指向相反方向，该边在 `build` 时降级为无箭头，两侧引文都写进 `uncertainty` 与 `exceptions`。

### 1.3 端点与颜色的复用规则

- 颜色只编码**实体类型**（11 类固定色），线色只编码**关系类型**；同一通道不表达两件事。
- 激活（实心箭头）与抑制（T 形端）的端点形状必须不同——这是 `markers` 闸门的硬判据。
- 线宽只区分 `transport`（3.4）与其余（1.6–2.4）；虚线只用于 `indirect`/`unspecified`。

---

## 2 实体命名与区室

### 2.1 `entity_type` 取值

`gene | protein | complex | ligand | receptor | cell_type | compartment | metabolite | mirna | phenotype | unspecified`

写入规则：

- **基因斜体、蛋白正体**。`italic` 可由 `entity_type == "gene"` 推导，也可显式写 `"italic": true`。
- **`TP53`（基因）与 `p53`（蛋白）不合并**：同名异义拆成两个实体，用 `sublabel` 区分（如 `transcript` / `protein`）。
- **复合物整体画**（`complex`），不把成员拆成独立节点再互连；成员关系写在 `gaps` 或 `edits`。
- **不得补常见分子**：材料里没有的实体一律不画；确有必要时进 `pending_human`。

### 2.2 区室归一

| 归一 id | 同义写法 | 中文 |
|---|---|---|
| `extracellular` | extracellular space, secreted, lumen | 胞外, 细胞外, 培养基 |
| `membrane` | plasma membrane, cell membrane, surface | 细胞膜, 质膜, 膜 |
| `cytoplasm` | cytosol, cytosolic | 胞质, 胞内, 细胞质 |
| `nucleus` | nuclear, chromatin | 细胞核, 核内 |

未在表中的区室会新建泳道并排在其后（`degradations` 记一条）。
`compartment == "membrane"` 的实体压在磷脂双分子层中心线上——闸门要求
`box.y < membrane_y < box.y + box.h`。

---

## 3 `draft.json` 字段字典

写到 `/app/work/draft.json`（`plan.json` 同义）。除 `entities`/`relations` 外都可省略。

### 3.1 顶层

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `title` | string | 建议 | 写清机制，不写 "Figure 1" |
| `subtitle` | string | 否 | 一句范围说明（材料、版本、降级） |
| `compartments` | array | 否 | `{id,label,order,kind?}`；缺省用胞外/胞膜/胞质/核内四条泳道 |
| `entities` | array | **是** | 见 3.2 |
| `relations` | array | **是** | 见 3.3 |
| `legend` | array | 否 | 见 3.4；不写时图例按图面自动生成 |
| `data_values` | array | 否 | 见 3.5；有数字就必须有 |
| `edits` | array | 否 | 保源编辑：`{element_id,before,after,reason,locator}` |
| `gaps` | array[string] | 否 | 材料未说明、因此没画的东西 |

### 3.2 `entities[]`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` | string | 建议 | 关系里引用它；缺省由 `name` 生成 |
| `name` | string | **是** | 材料原文写法，逐字不改写 |
| `entity_type` | enum | 建议 | 见 2.1；缺省 `unspecified`（灰色） |
| `species` | string | 否 | `human` / `mouse` / 空 |
| `compartment` | string | 建议 | 见 2.2；缺省按名称与类型猜 |
| `sublabel` | string | 否 | 同名异义的区分词、修饰状态（如 `phosphorylated`） |
| `italic` | bool | 否 | 基因名必须为真 |
| `source.locator` | string | **是** | `note.md#para3` / `case.json#workorder.required_entities[0]` |
| `source.quote` | string | **是** | 逐字连续切片 ≥6 字符 |

### 3.3 `relations[]`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` | string | 建议 | 缺省 `r1..rn` |
| `from` / `to` | string | **是** | 必须是 `entities[].id`（也接受实体名，脚本会解析） |
| `relation_type` | enum | **是** | 见 §1；判不准写 `unspecified` |
| `direction` | `forward`/`undirected` | 否 | 缺省 `forward` |
| `evidence_strength` | string | 否 | `stated` / `inferred` / `declared` / `mined` |
| `label` | string | 否 | 画在线上，≤24 字符 |
| `badge` | string | 否 | `P` / `Ub`，画在端点旁 |
| `source.locator` / `source.quote` | | **是** | 同上 |

### 3.4 `legend[]`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `channel` | enum | **是** | `color \| line_width \| size \| shape \| line_style \| marker` |
| `meaning` | string | **是** | 该通道表达什么（如 `entity type`、`expression level`） |
| `mapping` | object | 否 | 取值 → 视觉值；每个 key 必须真的出现在图面上，否则记 `orphan` |
| `source_column` | string | 否 | 表格列名（数据编码用） |
| `source.locator` / `source.quote` | | 建议 | 图例依据；缺失只记 `unsourced`，不判失败 |

### 3.5 `data_values[]`

`{entity, metric, value, unit, source:{locator,quote}}`。硬规则：

- `value` 必须是数字；
- `quote` 必须能逐字命中，且**数字字面量出现在 quote 里**（`2.4` 或 `2.40`）；
- 二者任一不满足 → 该值不画，进 `rejected`/`pending`。**不编造数值**。

---

## 4 `output_contract` 字段字典

`case.json.output_contract` 可能是数组、对象或逗号串。脚本取全部字段名，逐字段回填：

| 字段 | 结构 |
|---|---|
| `case_id` | 原样来自 `case.json`；缺失 `null` + `errors` |
| `status` | `ok` / `partial` / `input_error` |
| `editable_source` | `{path,format:"svg",editable:true,layers[],text_count,bytes,sha256}` |
| `export_artifact` | `{png:{path,width,height,dpi,engine,bytes,non_uniform}, pdf:{path,pages,vector,engine,header,eof,bytes}}` |
| `content_map` | `{entities[],relations[],compartments[],legend_encodings[],pending[],coverage{}}` |
| `compliance_checks` | `{svg_xml,canvas,font_style,markers,gene_italics,compartment_containment,cross_lane_edges,legend_consistency,overflow,layers,text_nodes,png,pdf,pass,failures}` |
| `exceptions` | `[{kind,detail,impact,action}]` |

未在契约里声明的字段一律不臆造；契约里声明了但脚本没有生产者的字段填 `null` 并写进
`degradations`（`contract_fields.null_fields` 列出）。

`content_map` 每条：实体含 `svg_id/name/entity_type/species/compartment/italic_required/source/quote_status`；
关系含 `svg_id/from/to/relation_type/direction/evidence_strength/source/quote_status`；
`coverage` 给出 workorder 声明数、覆盖数、缺失清单与 `ratio`。

---

## 5 质量闸门（`selfcheck` 从磁盘重算）

| 闸门 | 判据 | 失败后果 |
|---|---|---|
| `svg_xml` | 可解析；宽高 1600×1000；≥5 个 `layer-*`；`<text>` > 0 | 不可编辑 |
| `canvas` | 画布 1600×1000，正文外边距 48 | 导出尺寸不符 |
| `markers` | 8 类关系的（端点, 虚线, 线宽）三元组互不相同；激活≠抑制 | 语义不可区分 |
| `gene_italics` | 斜体文本数 ≥ 基因实体数 | 基因/蛋白混用 |
| `compartment_containment` | 每个框在所属泳道内；膜实体压线 | 区室错位 |
| `cross_lane_edges` | 跨区室边的路径越过层界 | 通路方向不可信 |
| `legend_consistency` | 图例项数 == 图面编码种类数（无重复）；`orphan == 0` | 图例与图面矛盾 |
| `content_map_1to1` | `ent-*` + `rel-*` 数量 == content_map 条目数 | 追溯链断裂 |
| `evidence` | `content_map.pending` 为空 | 有未溯源元素 |
| `png` | PNG 魔数、1600×1000、颜色 > 2 | 预览不可用 |
| `pdf` | `%PDF-`、≥1 页、`%%EOF`、`Tj` > 0 | 矢量导出不可用 |
| `contract` | `null_fields` 为空 | 契约缺项 |

`result.json.compliance_checks.pass` 只反映图面自洽与导出可用；**科学判断由人/评测模型完成**，
脚本通过不代表机制成立。

---

## 6 降级矩阵

| 情况 | 行为 | 落点 |
|---|---|---|
| `/input` 不存在或空 | 合法 `result.json` + 空画布三件套，`status=input_error` | `errors` |
| `case.json` 坏 JSON | 正则抢救 `case_id` 与契约字段名，继续跑 | `errors` |
| 无 `draft.json` | 工单条目 + "A 动词 B" 明写句 → 降级图，`status=partial` | `degradations` |
| 引文找不到 | 该条不画，进 pending | `content_map.pending` |
| 方向冲突 | 该边无箭头，双引文记录 | `uncertainty` |
| 关系端点是未知 id | 丢弃该边并记名 | `degradations` |
| 位图/扫描 PDF | 只记缺口，不进正文 | 材料 `note` |
| 导出异常 | 其余产物照常，`engine` 与错误落盘 | `errors`、`compliance_checks` |
| 元素过多 | 多列网格 + 14px 下限，溢出计数 | `overflow` |

---

## 7 最小调用示例（示例，非正式案例结果）

```bash
python3 -B <SKILL>/scripts/main.py init  --input /input --work /app/work --output /app/output
python3 -B <SKILL>/scripts/main.py show  --input /input --work /app/work
#   ← 读原文，写 /app/work/draft.json
python3 -B <SKILL>/scripts/main.py check --input /input --work /app/work --output /app/output
python3 -B <SKILL>/scripts/main.py build --input /input --work /app/work --output /app/output
python3 -B <SKILL>/scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

示例 `draft.json`（虚构示意，真实运行换成材料逐字引文）：

```json
{"title": "示例：A 结合 B，B 激活 C，C 抑制 B（负反馈）",
 "compartments": [{"id": "extracellular", "label": "Extracellular", "order": 0},
                  {"id": "membrane", "label": "Plasma membrane", "order": 1, "kind": "membrane"},
                  {"id": "cytoplasm", "label": "Cytoplasm", "order": 2}],
 "entities": [{"id": "a", "name": "A", "entity_type": "ligand", "compartment": "extracellular",
               "source": {"locator": "note.md#para1", "quote": "<原文连续片段≥6字符>"}},
              {"id": "b", "name": "B", "entity_type": "receptor", "compartment": "membrane",
               "source": {"locator": "note.md#para1", "quote": "<原文片段>"}}],
 "relations": [{"id": "r1", "from": "a", "to": "b", "relation_type": "binding",
                "source": {"locator": "note.md#para1", "quote": "<原文片段>"}}],
 "gaps": ["C 的亚细胞定位原文未写，未画。"]}
```
