# graphics-04 · 装置与工艺路线图（可编辑矢量）

把一份“装置 + 连接 + 工艺步骤”的材料，画成一张**可编辑的矢量图**：
左栏是带数量的装置块与带介质的连接箭头，下栏是带编号的工艺步骤块，
外加一份逐键回填契约的 `result.json`。

## 一条命令

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`init` / `check` / `build` / `show` 是同一流程的可分步等价入口（见 `SKILL.md` §3）。

## 产物

| 文件 | 说明 |
|-|-|
| `figure.svg` | **可编辑矢量母版**：分层 `<g>`，文字是活的 `<text>`，每个部件/连接/步骤都有 `id` |
| `figure.pdf` | 矢量 PDF（内置写出，Helvetica base-14，无外部渲染器） |
| `figure.png` | 8 位 RGB 位图预览（内置 zlib 光栅化，96 dpi） |
| `figure_model.json` | 布局模型：部件、连接、步骤、面板与它们的源定位 |
| `result.json` | 交付结果：契约回显、`content_map` 回链、自检、异常、来源 |

## 它是怎么画的

一份**图元画布**同时喂给三个导出器，所以预览永远不会和母版打架：

```
材料 → 段落切分 → 部件/连接/步骤 → 最长路径分层布局 → Canvas ─┬→ figure.svg（分层、id、活文字）
                                                              ├→ figure.pdf（内置矢量）
                                                              └→ figure.png（内置位图）
```

- 布局：把连接看作有向图，最长路径分层决定左右列序，同层按材料出现顺序；有环时退回材料顺序；
- 连线：两端都解析到部件才画；同层直连、跨层折线，箭头与虚线由**介质**决定
  （物料实线、能量虚线 `9,4`、信息点线 `2.5,3.5`），介质词按原文归类；
- 图例：只列**图上真用到**的介质，颜色与线型与图上逐一致；
- 文字：SVG 里中文是活字；PDF/PNG 无内嵌 CJK 字体，非 Latin-1 标签退化为灰条（记在 `limits`）。

## 不编造

- 材料没给装置清单 / 没给编号步骤 → 画空框，`status=insufficient_evidence`，绝不虚构装置或管路；
- 数量、介质、步骤文字全部**逐字转述**；缺数量写 `quantity not reported`，缺介质按物料呈现并记异常；
- 每个条目都带 `source.locator`（`S<文档>:L<行>`）与 `source.quote`（该行原文），核验率写进 `coverage`。

## 包内文件

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 用途、调用方式、契约、边界与降级 |
| `references/figure-spec.md` | 工单字段、段落识别、行语法、定位符、介质表、自检与失败清单 |
| `scripts/main.py` | 入口与子命令、契约逐键回填、result 信封、空/坏输入探针 |
| `scripts/sheet.py` | 材料读取 → 部件/连接/步骤 → 分层布局 → 画面与自检 |
| `scripts/draw.py` | 图元画布 → 分层 SVG / 矢量 PDF / 位图 PNG + 探针 |

## 运行与安全

读：`/input`（含 `case.json` 与任意材料）与 `/app/work/draft.json`；
写：`/app/output`（五个产物）与 `/app/work`（`figure_plan.json`、`check.json`、`self_check.json`、
两组探针目录 `_probe_empty`、`_probe_bad`）。
纯标准库、离线、不依赖 CWD、不调用 shell 与外部渲染器；退出码恒为 0。

## 边界

空目录、坏 `case.json`、空材料、只有 `[待写]` 备忘 → 退出码仍为 0，仍写五个产物与合法 `result.json`。
