# graphics-04 · 装置与工艺路线图（可编辑矢量）v6 忠实适配

输入一份**装置/工艺材料**（Markdown、纯文本、OOXML、XLSX、PDF 皆可），
输出一张**可编辑的矢量图**：左边一栏是装置与连接，下面一栏是工艺步骤，
外加契约齐全的 `result.json`。

- 每个**部件**、每条**连接**、每道**步骤**都带 `id`，并在 `content_map` 里回链到
  `S<文档>:L<行>` 的原始行与**逐字原文**（quote）；有源可查的条目逐个核验，查不到就记异常，绝不补内容；
- 矢量母版是 **SVG**（文字仍是 `<text>`，可改字改色改线），并配**矢量 PDF** 与**位图 PNG** 预览，
  三者由同一份图元画布导出，不会互相漂移；另出一份 `figure_model.json` 存档布局模型；
- 材料里既没有装置清单也没有编号步骤时，脚本**画一个空框并停手**，绝不编造装置、管路或步骤；
- 半截连接（"A -> ？"）与端点不在部件表里的连线**不画**，只记异常，避免凭空补管路。

产物固定为 `figure.svg`、`figure.pdf`、`figure.png`、`figure_model.json`、`result.json`。

## 1. 交付契约（output_contract 逐键回显）

```json
{"output_contract": {"case_id": "透传输入案例号", "status": "ok 或 partial 等状态字",
  "editable_source": "SVG 母版描述对象", "export_artifact": "svg/pdf/png/model 四份导出对象",
  "content_map": "部件/连接/步骤到源行的回链对象", "compliance_checks": "合规自检对象",
  "exceptions": "推断与缺料清单（至少一条）"}}
```

这七个键是**缺省契约**；`case.json` 里给了 `output_contract` 时，脚本改为逐键回填那一组键，
并在 `result.json.output_contract` 里原样回显（顶层与嵌套同名键都写实值，不留空数组、不写占位词）。

## 2. 单命令入口（评测与人工都跑这一条）

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

一次跑完 发现 → 读段 → 建模 → 布局 → 渲染 → 导出 → 自检，退出码恒为 0；
`init` / `check` / `build` / `show` 是同一流程的可分步等价入口。

## 3. Agent 优先路径（四步，可分别重跑）

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# 可选：把工单写进 /app/work/draft.json（字段见 references/figure-spec.md），没有也能继续
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

- `init` 写 `work/figure_plan.json`：案例号、可读文档清单（id、名字、类型、字符数）、工单与读取问题；
- `check` 写 `work/check.json`：抽到的部件 / 连接 / 步骤（含可画性与逐字核验结果）与异常清单；
- `build` 与 `run` 相同；`show` 只读回已落盘的 `result.json` 概览，不重算。

## 4. 输入与工单

```
/input/case.json                     {"case_id": "...", "output_contract": {...}, "workorder": {...}}
/input/<任意路径>/<材料>              装置清单、连接关系、工艺步骤（Markdown 标题分段落最省事）
```

工单是**可选**的。不给工单时，脚本按材料的**标题段落**推断：`装置清单` 段 → 部件表，
`连接关系` 段 → 连接，`工艺步骤` 段 → 步骤；每一次推断都写进 `exceptions`。
工单字段、段落识别规则、定位符与介质分类见 `references/figure-spec.md`。

## 5. result.json 字段

| 字段 | 含义 |
|-|-|
| `case_id` | 透传输入案例号，缺失时用输入目录名 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `editable_source` | SVG 母版：层名、`<text>` 数、viewBox、字节、sha256、字体栈 |
| `export_artifact` | `svg` / `pdf`（矢量、页数、MediaBox）/ `png`（尺寸、dpi、唯一色数）/ `model` 四份导出 |
| `content_map` | 部件 → 连接 → 步骤 → 图例 → 面板 → 每个条目的几何与 `source` 定位 → 覆盖率 |
| `compliance_checks` | 画布、字体、线宽、悬空连接、步骤编号、越界、逐字核验、id 覆盖、图例一致、PDF/PNG 探针、确定性、`pass` |
| `exceptions` | 每一次推断或缺料：`{code, message, severity, action}`，**永不空数组**（无异常时也记一条 `none_*` 说明式条目） |
| `sources` | 读到的每份材料（id、路径、类型、字符数、行数），`case.json` 单列一条 |
| `uncertainty` / `uncertainties` | 图型来源、布局口径、介质分类口径（只转述不计算） |
| `changes` / `change_records` | 逐步记录：ingest / bind / layout / render_export 的目标、依据与定位符 |
| `pending_human` | 需要人补的东西（缺工单、缺数量、半截连接、无逐字来源的条目） |
| `errors` / `degradations` | 输入级错误与能力降级（读取失败的文档、无 CJK 字体的预览灰条） |
| `coverage` / `limits` / `runtime` | 部件/连接/步骤计数与核验率、能力边界、耗时与解释器版本 |

## 6. 边界与降级

- 输入目录不存在 → `status=input_error`，仍写合法 `result.json` 与五个产物（空框图）；
- 没有可解析的材料，或材料里没有装置清单也没有编号步骤 → `status=insufficient_evidence`，
  `exceptions` 记 `no_drawable_entities`，画空框；
- 材料给了部件但没给数量 → 图上标注 `quantity not reported`，记 `qty_missing`，不补数；
- 连接没写介质 → 按物料呈现并记 `medium_missing`；连接只有一端 → 记 `conn_one_end` 且不画箭头；
- 端点不在部件表 → 记 `conn_dangling`，不画，避免凭空补管路；编号与顺序不符 → 记 `step_order_mismatch` 后按正文顺序重排；
- 预览里的 CJK 文字（无内嵌字体）退化为灰条，记在 `limits` 与 `compliance_checks.fonts`，SVG 仍保留真字。

## 7. 资源与安全

纯 Python 3.9+ 标准库，三个脚本各司其职：`scripts/main.py`（入口、契约与信封）、
`scripts/sheet.py`（材料 → 结构 → 画面）、`scripts/draw.py`（画布 → SVG/PDF/PNG 与探针）；
无网络、无第三方包、不调用任何外部渲染器；写范围仅 `--output` 与 `--work`（见 `README.md`）。
