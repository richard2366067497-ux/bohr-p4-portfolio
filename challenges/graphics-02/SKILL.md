# graphics-02 · 源值图表（可编辑矢量）v6 忠实适配

输入一份**工单（workorder）+ 源数据表**，输出一张**可编辑的矢量图**与契约齐全的 `result.json`。

- 每个图元（柱子 / 点 / 误差棒 / 图例色块）都带 `id`，并能在 `content_map` 里回链到
  `文件:行:列` 的原始单元格与整行原文；
- 矢量母版是 **SVG**（文字仍是 `<text>`，可直接改字改色），并配 **矢量 PDF** 与 **位图 PNG** 预览，
  三者由同一份图元画布导出，不会互相漂移；
- 输入没有表、表里没有可读数值时，脚本**画一个空框并停手**，绝不编造数值。

产物固定为 `chart.svg`、`chart.pdf`、`chart.png`、`chart_model.json`、`result.json`。

## 1. 交付契约（output_contract 逐键回显）

```json
{"output_contract": {"case_id": "透传输入案例号", "status": "ok 或 partial 等状态字",
  "editable_source": "SVG 母版描述对象", "export_artifact": "svg/pdf/png 三份导出对象",
  "content_map": "图元到源单元格的回链对象", "compliance_checks": "合规自检对象",
  "exceptions": "推断与缺料清单（至少一条）"}}
```

这七个键是**缺省契约**；`case.json` 里给了 `output_contract` 时，脚本改为逐键回填那一组键，
并在 `result.json.output_contract` 里原样回显（顶层与嵌套同名键都写实值，不留空数组）。

## 2. 单命令入口（评测与人工都跑这一条）

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

一次跑完 发现 → 绑定 → 建模 → 渲染 → 导出 → 自检，退出码恒为 0；
`init` / `check` / `build` 是同一流程的可分步等价入口（见 §2）。

## 3. Agent 优先路径（四步，可分别重跑）

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# 可选：把工单写进 /app/work/draft.json（字段见 references/chart-spec.md），没有也能继续
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

- `init` 写 `work/chart_plan.json`：案例号、工单、每张表的表头与行数；
- `check` 写 `work/check.json`：列绑定结果（x 列、每个系列绑到哪一列、命中点数、覆盖率）与问题清单；
- `build` 与 `run` 相同，最后刷新五个产物并跑内建探针写 `work/self_check.json`。

## 4. 输入与工单

```
/input/case.json                 {"case_id": "...", "output_contract": {...}, "workorder": {...}}
/input/<任意路径>/source.csv     第一行表头；数值列即系列，紧随其后的 *SD / *SEM 列自动认作误差
```

工单是**可选**的：不给工单时，脚本按表的形状推断图型（分类文本 x → 分组柱；数值 x → 折线），
并把每一次推断写进 `exceptions`。工单字段、模型结构与定位符规则见
`references/chart-spec.md`。

## 5. result.json 字段

| 字段 | 含义 |
|-|-|
| `case_id` | 透传输入案例号，缺失时用输入目录名 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `editable_source` | SVG 母版：层名、`<text>` 数、字节、sha256、viewBox |
| `export_artifact` | `svg` / `pdf`（矢量、页数、MediaBox）/ `png`（尺寸、dpi、唯一色数）三份导出 |
| `content_map` | 图表 → 轴 → 系列 → 每个图元（含像素几何与 `src` 定位）→ 图例 → 覆盖率 |
| `compliance_checks` | 画布、字体、线宽、配色、图例一致、几何回读、覆盖、越界、PNG/PDF 探针与 `pass` |
| `exceptions` | 每一次推断或缺料：`{code, detail, severity, action}`，**永不空数组**（无异常时也记一条 `none_*` 说明式条目） |
| `sources` | 读到的 `case_json` 与每张数据表（表头、行数） |
| `uncertainty` / `uncertainties` | 图型来源、统计口径（只转述不计算）、单位来源 |
| `changes` / `change_records` | `discover` / `bind_table` / `render_export` 逐步记录 |
| `pending_human` | 需要人补的东西（缺表、缺单位、列绑定失败等） |
| `errors` / `degradations` | 输入级错误与能力降级（如预览里 CJK 文字退化成灰条） |
| `coverage` / `limits` / `runtime` | 点数覆盖、能力边界、耗时与解释器版本 |

## 6. 边界与降级

- 目录不存在 → `status=input_error`，仍写合法 `result.json` 与五个产物（空框图）；
- 没有可解析的表 → `status=insufficient_evidence`，`exceptions` 记 `no_source_table`，画空框；
- 表里混入 `Replicate` 之类的行号列 → 记 `index_column_skipped`，不做系列；
- 同一分类多行（重复实验）→ 默认取算术均值，记 `replicate_aggregated`，`n` 保留在点上；
- 表头与工单都没有单位 → 轴标题写 `unit not reported`，记 `unit_unknown`，不编单位；
- 预览里的 CJK 文字（无内嵌字体）退化为灰条，记 `cjk_label_bar_in_preview`，SVG 仍保留真字。

## 7. 资源与安全

纯 Python 3.9+ 标准库；无网络、无第三方包、不调用任何外部渲染器（PDF 与 PNG 由内置导出器写出）；
写范围仅 `--output` 与 `--work`。包内三个脚本各司其职、互不依赖外部环境：

| 脚本 | 职责 |
|-|-|
| `scripts/main.py` | 入口、命令行、契约回填、信封与自检探针 |
| `scripts/chart.py` | 读表 → 绑定 → 建模 → 渲染 → 自检计算 |
| `scripts/draw.py` | 画布图元 → SVG / 矢量 PDF / 位图 PNG 三份导出与探针 |

不读写包外路径、不落 `__pycache__`；所有输出与临时文件都留在 `--output` / `--work` 之内。
