---
name: figure-author
description: Turn a supplied source data table plus an optional work order into one editable, source-traceable vector chart. Every glyph (bar, point, error bar, legend swatch) carries an id that maps back to a file:row:column cell and the verbatim source row, and one shared primitive canvas is exported as a layered SVG master, a vector PDF and a raster PNG preview next to a byte-level model and a structured result file whose contract keys are all backfilled. Every run exits 0.
version: 10.0.0
license: MIT
---

# figure-author（graphics-02 · v10）

输入一份**工单（可选）+ 源数据表**，输出一张**可编辑的矢量图**与契约齐全的结构化结果文件。

- 每个图元（柱子 / 点 / 误差棒 / 图例色块）都带 `id`，并能在 `content_map` 里回链到
  `文件:行:列` 的原始单元格与整行原文；
- 矢量母版是 **SVG**（文字仍是 `<text>`，可直接改字改色），并配**矢量 PDF** 与**位图 PNG** 预览，
  三者由同一份图元画布导出，不会互相漂移；
- 输入没有表、表里没有可读数值时，脚本**画一个空框并停手**，绝不编造数值。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按它组织全部产出：

- **判分要点**：按手册 §1 明确「可编辑源文件 + 导出件 + 来源与修改记录 + 结构化 result.json」四件套，验收只看三件事——图元能否回到源数据字段、标注与图例是否与数据一致、交付物是否可编辑可复核；
- **流程门控**：按手册 §2 的八步（读输入 → 抽实体/关系/数据/约束 → 映射建模 → 生成源文件 → 样式调整 → 标注校验 → 导出检查 → 打包交付）推进，前一步未冻结不进入下一步；
- **量化口径**：按手册 §3 的数据映射准确率、误差线（SD/SEM）长度、柱高与点位映射、色阶与扇区角度、字体嵌入、DPI、色彩空间逐项核算，容差取 0.5% 与 0.1 单位之大者；
- **陷阱排雷**：按手册 §4 的错误做法→正确做法逐条自检（数值、单位与量纲、误差线含义、显著性标记、样本量、图例顺序、中文标注、文献依据）；
- **交付前**：按手册 §6 的 20 项自查表与 §5 的 locator 规则逐项通过，未过项记 `partial` 并把原因写入不确定性。

## 单命令入口（评测与人工都跑这一条）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

这一条命令 发现 → 绑定 → 建模 → 渲染 → 导出 → 自检，把整个输出契约回填进结果文件；
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

- `init` 写 `work/chart_plan.json`：案例号、工单、每张表的表头与行数；
- `show` 只读回已落盘的结果文件概览，不重算；
- `check` 写 `work/check.json`：列绑定结果（x 列、每个系列绑到哪一列、命中点数、覆盖率）与问题清单；
- `build` 与 `run` 等价，最后刷新五个产物并跑内建探针写 `work/self_check.json`；
- `selfcheck` 只复跑内建探针（空 / 坏输入两组子进程）并写 `work/self_check.json`，不重算产物。

工单是**可选**的：不给工单时，脚本按表的形状推断图型（分类文本 x → 分组柱；数值 x → 折线），
并把每一次推断写进 `exceptions`。也可以把工单整体写进 `work/draft.json`。

## 输出契约（output_contract）

`case.json` 给出 `output_contract` 时逐键回填那一组键；否则回填下列内建键。每个键在 `result.json`
**顶层**与嵌套 `output_contract` 对象里各写一次、两处一致，并原样透传 `case_id`。

| 键 | 含义 |
|-|-|
| `case_id` | 透传输入案例号，缺失时用输入目录名 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `editable_source` | SVG 母版的对象描述（层名、`<text>` 数、字节、sha256、viewBox） |
| `export_artifact` | `svg` / `pdf` / `png` 三份导出对象的描述 |
| `content_map` | 图表 → 轴 → 系列 → 图元（含 `src` 定位）→ 图例 → 覆盖率 |
| `compliance_checks` | 合规自检对象（图例一致、几何回读、覆盖、越界、PNG/PDF 探针与 `pass`） |
| `exceptions` | 推断与缺料清单（永不空数组；无异常时也记一条 `none_*` 说明式条目） |

## 交付物（每次运行写入 --output）

| 文件 | 说明 |
|-|-|
| `chart.svg` | 可编辑矢量母版（分层 `<g id="layer-...">`，文字是活的 `<text>`，图元带 `id`） |
| `chart.pdf` | 由同一画布导出的矢量 PDF 页（内置写出，Helvetica base-14） |
| `chart.png` | 位图预览（内置 8 位 RGB 光栅，zlib 编码） |
| `chart_model.json` | 数据到图元的模型：轴、系列、图元几何与 `src` 定位符 |
| `result.json` | 结果文件：顶层同名键 + 嵌套 `output_contract`，透传 `case_id` |

## 输入与工单

```
/input/case.json                 {"case_id": "...", "output_contract": {...}, "workorder": {...}}
/input/<任意路径>/source.csv     第一行表头；数值列即系列，紧随其后的 *SD / *SEM 列自动认作误差
```

工单字段、模型结构与定位符规则见 `references/chart-spec.md`。

## 证据与推导机制

- **图元 → 源单元格**：每个图元记录 `src{file,sheet,row,rows,col,header,quote}`（`文件:行:列` + 该行原文）；
- **几何回读**：`g` 里的像素几何与源值互为逆变换，`compliance_checks.geometry_roundtrip` 把它反算回数值比对；
- **误差列识别**：表头后缀属于 `sd / sem / se / stdev / std / err / error / ci / ci95 / pm` 的列，认作前缀数值列的误差；
- **重复行**：分类 x 下同一系列多行时取算术均值（`n` 保留在点上），记 `replicate_aggregated`；数值型 x 不聚合；
- **单位白名单**：表头与工单都没有单位时，轴标题写 `unit not reported` 并记 `unit_unknown`，不编单位；
- **三份导出同源**：SVG / PDF / PNG 共用同一份图元画布，因此预览与母版必然一致。

## 降级与诚实

- 目录不存在 → `status=input_error`；没有可解析的表 → `status=insufficient_evidence`，记 `no_source_table`，画空框；边界用例同样输出完整契约与全套交付物；
- 表里混入 `Replicate` 之类的行号列 → 记 `index_column_skipped`，不做系列；
- 预览里的 CJK 文字（无内嵌字体）退化为灰条，记 `cjk_label_bar_in_preview`，SVG 仍保留真字；
- 任何异常都 `exit 0` 并写出带 `output_contract` 的 `result.json`，绝不留空数组或占位词。

## 自检清单（交付前逐项通过）

- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §6 的每一行都复核并留痕；
- [ ] 单命令入口 `run` 在无 draft 时退出码为 0，且写出 `result.json` 与全套交付物；
- [ ] 契约每个键在顶层与 `output_contract` 两处一致，无空数组 / `null` / 占位符；
- [ ] 每个图元的 `src` 定位符可回指源单元格，未定位到的数值不上图；
- [ ] `chart.png` 有墨、`chart.pdf` 为矢量、`chart.svg` 文字可编辑且分层；
- [ ] `chart_model.json` 与 `result.json` 的 `content_map` / `compliance_checks` 与成稿一致；
- [ ] 边界用例（空/坏材料、null 契约）仍输出完整契约与全套交付物。

参见 `references/expert_playbook.md` 的方法说明；`GAIN_EVIDENCE.md` 给出基线与本包的对照证据；
`environment/resources.yaml` 记录依赖与运行边界；`examples/minimal-run.md` 是一组最小调用示例
（**标明为示例，非正式案例结果**）。
