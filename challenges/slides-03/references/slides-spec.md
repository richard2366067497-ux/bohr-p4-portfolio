# 幻灯片规格（slides-03）

## slide_plan

| 字段 | 含义 |
|-|-|
| `index` | 页序，从 1 开始 |
| `kind` | `title` 或 `section` |
| `title` | 页标题（来自材料标题/小节） |
| `bullets` | 要点（逐字或忠实压缩的材料句子） |
| `source` | 材料 locator（如 `M01#s3`、`material#title`） |

## content_map

`slides` 列表：每页的 `index/title/source/kind`，用于“页 → 材料”追溯。

## compliance_checks

- `source_link`：每页都有 locator。
- `verbatim_quotes`：数字类结论回源逐字核对，报告匹配数。
- `no_fabricated_numbers`：数字均来自材料，不臆造。
- `slide_budget`：页数上限（24）。
- `preview_present`：始终产出矢量预览与渲染产物。

## coverage

`{"slides": N, "quotes_checked": M}`：页数与回源核对的引文数。

## 诚实边界

- 只从材料文本生成，不引入外部内容。
- 无机器可读图片时不嵌入图片，`exceptions` 说明。
- 渲染产物为文本/矢量 PDF、HTML、SVG；不含栅格图。
