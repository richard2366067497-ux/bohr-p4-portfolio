---
name: figure-author
description: Turn a supplied apparatus / process material (Markdown, plain text, OOXML, XLSX or PDF) into one editable, source-traceable vector sheet where every part, connection and numbered step carries an id that maps back to a source line and its verbatim quote, laid out as a layered SVG master with a vector PDF and a raster PNG preview plus a layout model and a structured result file whose contract keys are all backfilled. Every run exits 0.
version: 10.0.0
license: MIT
---

# figure-author（graphics-04 · v10）

输入一份**装置/工艺材料**（Markdown、纯文本、OOXML、XLSX、PDF 皆可），
输出一张**可编辑的矢量图**：左边一栏是装置与连接，下面一栏是工艺步骤，
外加契约齐全的结构化结果文件。

- 每个**部件**、每条**连接**、每道**步骤**都带 `id`，并在 `content_map` 里回链到
  `S<文档>:L<行>` 的原始行与**逐字原文**（quote）；有源可查的条目逐个核验，查不到就记异常，绝不补内容；
- 矢量母版是 **SVG**（文字仍是 `<text>`，可改字改色改线），并配**矢量 PDF** 与**位图 PNG** 预览，
  三者由同一份图元画布导出，不会互相漂移；另出一份 `figure_model.json` 存档布局模型；
- 材料里既没有装置清单也没有编号步骤时，脚本**画一个空框并停手**，绝不编造装置、管路或步骤；
- 半截连接（“A -> ？”）与端点不在部件表里的连线**不画**，只记异常，避免凭空补管路。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按它组织全部产出：

- **判分要点**：按手册 §1 明确「可追溯、可编辑、可复跑的科研图稿 + 结构化中间产物」，验收看五件事——实体/连接/步骤能否回到材料、结构清晰度、布局与自检是否成体系、异常是否处置、文档是否可复用；
- **流程门控**：按手册 §2 的七步（读输入 → 证据抽取 → 结构化 IR → 布局与图元映射 → 生成可编辑 SVG → 导出与校验 → 自检与 result.json）推进，前一步未冻结不进入下一步；
- **量化口径**：按手册 §3 的实体覆盖率 EC、关系方向正确率 RDA、步骤编号对齐率 SAR、可追溯率 TR、导出检查通过率 EPR、自检通过率 SPR 逐项核算（目标 100%，可接受 ≥ 95%）；
- **陷阱排雷**：按手册 §4 的错误做法→正确做法逐条自检（实体名称逐字引用、连接方向有文本依据、回流与废料出口不断头、同类部件区分编号、图例与图形一致、单位与量纲）；
- **交付前**：按手册 §6 的 20 项自查表与 §5 的 locator 规则逐项通过，未过项记 `partial` 并把原因写入不确定性。

## 单命令入口（评测与人工都跑这一条）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

这一条命令 发现 → 读段 → 建模 → 布局 → 渲染 → 导出 → 自检，把整个输出契约回填进结果文件；
退出码恒为 0：即使输入为空或损坏，也写出一个合法、诚实的结果文件（状态为 `insufficient_evidence`，
并画一个空框），而不是抛错中断。

## Agent 增强路径（同一引擎，多条命令）

```bash
python3 -B /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py show  --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

- `init` 写 `work/figure_plan.json`：案例号、可读文档清单（id、名字、类型、字符数）、工单与读取问题；
- `show` 只读回已落盘的结果文件概览，不重算；
- `check` 写 `work/check.json`：抽到的部件 / 连接 / 步骤（含可画性与逐字核验结果）与异常清单；
- `build` 与 `run` 等价；最后跑内建探针写 `work/self_check.json`；
- `selfcheck` 只复跑内建探针（空 / 坏输入两组子进程）并写 `work/self_check.json`，不重算产物。

工单是**可选**的：不给工单时，脚本按材料的**标题段落**推断：`装置清单` 段 → 部件表，
`连接关系` 段 → 连接，`工艺步骤` 段 → 步骤；每一次推断都写进 `exceptions`。
也可以把工单整体写进 `work/draft.json`。

## 输出契约（output_contract）

`case.json` 给出 `output_contract` 时逐键回填那一组键；否则回填下列内建键。每个键在 `result.json`
**顶层**与嵌套 `output_contract` 对象里各写一次、两处一致，并原样透传 `case_id`。

| 键 | 含义 |
|-|-|
| `case_id` | 透传输入案例号，缺失时用输入目录名 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `editable_source` | SVG 母版的对象描述（层名、`<text>` 数、viewBox、字节、sha256、字体栈） |
| `export_artifact` | `svg` / `pdf` / `png` / `model` 四份导出对象的描述 |
| `content_map` | 部件 → 连接 → 步骤 → 图例 → 面板 → 几何与 `source` 定位 → 覆盖率 |
| `compliance_checks` | 合规自检对象（悬空连接、步骤编号、逐字核验、id 覆盖、图例一致、PDF/PNG 探针、确定性、`pass`） |
| `exceptions` | 推断与缺料清单（永不空数组；无异常时也记一条 `none_*` 说明式条目） |

## 交付物（每次运行写入 --output）

| 文件 | 说明 |
|-|-|
| `figure.svg` | 可编辑矢量母版（分层 `<g id="layer-...">`，文字是活的 `<text>`，每个部件/连接/步骤带 `id`） |
| `figure.pdf` | 由同一画布导出的矢量 PDF 页（内置写出，Helvetica base-14） |
| `figure.png` | 位图预览（内置 8 位 RGB 光栅，zlib 编码，96 dpi） |
| `figure_model.json` | 布局模型：部件、连接、步骤、阶段、面板与它们的 `source` 定位 |
| `result.json` | 结果文件：顶层同名键 + 嵌套 `output_contract`，透传 `case_id` |

## 输入与工单

```
/input/case.json                     {"case_id": "...", "output_contract": {...}, "workorder": {...}}
/input/<任意路径>/<材料>              装置清单、连接关系、工艺步骤（Markdown 标题分段落最省事）
```

工单字段、段落识别规则、定位符与介质分类见 `references/figure-spec.md`。

## 证据与推导机制

- **条目 → 源行**：每个部件/连接/步骤记录 `source.locator`（`S<文档>:L<行>`）与 `source.quote`（该行原文，最长 240 字符），核验率写进 `content_map.coverage.verified_rate`；
- **分层布局**：把连接看作有向图取**最长路径**分层，同层按材料出现顺序；检测到环时整图退回材料顺序并在自检里报告；
- **介质分类**：介质词按原文归类为 `material`（实线）/ `energy`（虚线 `9,4`）/ `information`（点线 `2.5,3.5`），原文介质词留在 `medium_raw`，不翻译；
- **只画能闭合的连接**：两端都解析到部件才画，半截连接与悬空连接记异常不画；
- **三份导出同源**：SVG / PDF / PNG 共用同一份图元画布，`determinism` 复核两次导出逐字节一致。

## 降级与诚实

- 输入目录不存在 → `status=input_error`；没有可解析的材料、或材料里没有装置清单也没有编号步骤 → `status=insufficient_evidence`，记 `no_drawable_entities`，画空框；
- 材料给了部件但没给数量 → 图上标注 `quantity not reported`，记 `qty_missing`，不补数；
- 连接没写介质 → 按物料呈现并记 `medium_missing`；连接只有一端 → 记 `conn_one_end` 且不画箭头；端点不在部件表 → 记 `conn_dangling`，不画；
- 预览里的 CJK 文字（无内嵌字体）退化为灰条，记在 `limits` 与 `compliance_checks.fonts`，SVG 仍保留真字；
- 任何异常都 `exit 0` 并写出带 `output_contract` 的 `result.json`，绝不留空数组或占位词。

## 自检清单（交付前逐项通过）

- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §6 的每一行都复核并留痕；
- [ ] 单命令入口 `run` 在无 draft 时退出码为 0，且写出 `result.json` 与全套交付物；
- [ ] 契约每个键在顶层与 `output_contract` 两处一致，无空数组 / `null` / 占位符；
- [ ] 每个部件/连接/步骤都有 `source.locator` 与逐字 `quote`，未核验到的条目已记入 `exceptions` / `pending_human`；
- [ ] 半截连接与悬空连接不画，只记异常；
- [ ] `figure.svg` 分层且文字可编辑、`figure.pdf` 为矢量、`figure.png` 可解；
- [ ] `figure_model.json` 与 `result.json` 的 `content_map` / `compliance_checks` 与成稿一致；
- [ ] 边界用例（空/坏材料、null 契约）仍输出完整契约与全套交付物。

参见 `references/expert_playbook.md` 的方法说明；`GAIN_EVIDENCE.md` 给出基线与本包的对照证据；
`environment/resources.yaml` 记录依赖与运行边界；`examples/minimal-run.md` 是一组最小调用示例
（**标明为示例，非正式案例结果**）。
