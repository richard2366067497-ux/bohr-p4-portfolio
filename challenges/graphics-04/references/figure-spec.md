# 图规格：工单、段落识别、定位符与自检（graphics-04）

## 1. 工单字段（全部可选，写在 `case.json.workorder` 或 `work/draft.json`）

| 字段 | 类型 | 说明 |
|-|-|-|
| `title` | string | 图题；缺省取材料第一个一级标题 |
| `figure_kind` / `figure_type` | string | `apparatus` 装置图 / `process` 流程图 / `route` 技术路线 / `combo` 组合；缺省按材料推断 |
| `required_parts` | list | 部件；元素可为 `"厌氧反应器"` 或 `{"name": "厌氧反应器", "qty": "1"}` |
| `required_connections` | list | 连接；元素为 `"进料储罐 -> 蠕动泵（物料）"` 或 `{"from": ..., "to": ..., "medium": ...}` |
| `steps` | list | 步骤；元素可为字符串或 `{"title": ...}`，顺序即正文顺序 |
| `stages` | list | 技术路线阶段；本版只登记不绘制 |

工单里给到的条目优先，材料只做补位；两者都没有的条文不会凭空出现。

## 2. 段落识别（无工单时）

脚本按 Markdown 标题（`#` 到 `######`）切段，标题里命中下列关键词即认作该段：

| 段 | 关键词（任一命中） |
|-|-|
| 装置 | 装置、部件、设备、器材、清单、equipment、apparatus、parts、components |
| 连接 | 连接、管路、连线、connection、piping、links |
| 步骤 | 步骤、工艺、工序、操作、procedure、step、process |
| 阶段 | 阶段、路线、里程碑、stage、phase、route、milestone |

段落缺失时退化为**全文扫描**，命中即用，并在 `exceptions` 里记
`parts_from_material` / `connections_from_material` / `steps_from_material`。

## 3. 行语法

- 部件（列表项）：`- 名称：说明`，说明里的 `1 个 / 2 台 / 3 套 …` 被认成数量；
  也接受表格行 `| 名称 | 数量 | 说明 |`；
- 连接：`A -> B（介质）`，箭头也接受 `→ --> => ⇒`，缺介质时按物料呈现；
- 步骤：`1. 文字` 或 `1、文字`；编号与顺序不符时按正文顺序重排并记 `step_order_mismatch`。

## 4. 定位符

每个抽到的条目都在材料里回查**逐字**原文，得到：

```
locator  S<文档序>:L<行号>     例如 S1:L12（第 1 份材料的第 12 行）
quote    该行去掉前缀标记后的原文（最长 240 字符）
file     来源文件名
verified true / false          false 时同时记 source_not_located 异常
```

`S<文档序>` 与 `result.json.sources[].id` 一一对应，核验率写在 `content_map.coverage.verified_rate`。

## 5. 介质分类

| 键 | 图上线型 | 颜色 | 命中词（不区分大小写） |
|-|-|-|-|
| `material` | 实线 | `#1f5fa8` | 缺省；物料、material、feed、stream |
| `energy` | 虚线 `9,4` | `#c1440e` | 能量、energy、heat、power、热、电 |
| `information` | 点线 `2.5,3.5` | `#2f7d4f` | 信息、信号、information、signal、data、数据 |

介质判定只做**归类**，原文介质词留在 `content_map.connections[].medium_raw`，不翻译、不改写。

## 6. 分层布局

连接构成有向图（`from_id → to_id`），取**最长路径**作为层号：入度为 0 的部件在第 0 列，
逐边推进；同层按材料出现顺序自上而下排列；检测到环时整图退回材料顺序，并在自检里报告。
列宽 190、列距 86、行高 74，全部居中于 1440 宽画布。

## 7. 自检项（`compliance_checks`）

| 检查 | 通过条件 |
|-|-|
| `canvas` | 宽 ≥ 800、高 ≥ 300，所有图元落在画布内（`overflow` 另行记录实测极值） |
| `fonts` / `line_widths` | 字体栈含通用回退；最小线宽 ≥ 1.2 |
| `dangling_connections` | 每条画出的连线两端都贴合部件边框；不画的连接记入 `not_drawn` |
| `flow_direction` | 已绘制数 + 未解析数 = 连接总数 |
| `step_numbering` | 步骤号连续 `1..n`，原编号留在 `source_order` |
| `quote_verification` | 每个条目的 `source.locator` 都非空且 `verified=true` |
| `id_coverage` | `content_map` 里每个 id 都能在 SVG 里找到 |
| `legend_consistency` | 图例键序 = 图上周到的介质首次出现序 |
| `pixel_probe` / `pdf_probe` | PNG 有墨且可解 IDAT；PDF 魔数正确、矢量（无 `/Subtype /Image`）、页数与 MediaBox 可读 |
| `determinism` | 同一画布两次导出的 SVG 逐字节一致 |
| `pass` | 以上全部通过且 `failures` 为空 |

## 8. 失败与降级

| 情形 | 处置 |
|-|-|
| 输入目录不存在 | `status=input_error`，空框图 + 合法 `result.json` |
| `case.json` 坏 / 缺失 | 记 `case_json_unreadable` / `case_json_missing`，仍按材料继续 |
| 材料读不出（编码/格式） | 记 `material_unreadable:<名>:<原因>`，该文件跳过 |
| 无装置清单且无编号步骤 | `status=insufficient_evidence`，空框，记 `no_drawable_entities`，不猜测 |
| 连接端点不在部件表 | 记 `conn_dangling`，不画该连接 |
| 半截连接（只有一端） | 记 `conn_one_end`，不画 |
| 无逐字来源 | 记 `source_not_located`，保留条目并在 `pending_human` 请人确认 |
| 预览 CJK 灰条 | 记在 `limits` 与 `fonts.preview_cjk_bars`，SVG 真字不受影响 |
