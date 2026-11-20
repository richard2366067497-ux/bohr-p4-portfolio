# slides-author (slides 赛道) — slides-04

把固定论文 / 研究材料**套用组织方给定的目标模板**，转成证据可追溯、可编辑、可渲染的学术汇报产物
（slides v6 重建包）。

> 模板继承：读取 `target-template.pptx`，复用其**主题与母版**写入幻灯片，成品沿用统一版式与配色，
> 模板继承情况记入例外与结果；图片材料登记为可用图表来源并保留图注定位。

## 一条命令

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

退出码恒为 0；输入为空或损坏时写出合法、诚实的结果文件（`insufficient_evidence`，不编造内容）。

## 它做什么

1. **扫描材料与模板**：逐份登记文本材料（`M01`、`M02` …），识别讲稿工作单与目标模板；
2. **抽取页级主张**：按小节从**实质句子**建立页面，而不是把 markdown 标题直接搬进页面；
3. **保留证据**：每页一个材料定位 + 逐字引用，数字类主张先在原文重新定位；
4. **生成产物**：可编辑源（markdown + OOXML pptx + html）与导出产物（PDF + SVG 预览）；
5. **回填契约**：结果文件同时给出顶层同名键与 `output_contract` 嵌套字典，并透传 `case_id`。

## 产物

| 文件 | 说明 |
|-|-|
| `deck.md` | 可编辑 Markdown 源（每页以 `---` 分隔） |
| `deck.pptx` | 可编辑 OOXML 演示文稿源（带模板主题，每页 1 张幻灯片 + 1 张备注页） |
| `deck.html` | 可直接播放的网页版（SVG / HTML 组合） |
| `preview.svg` | 手写矢量预览 |
| `deck.pdf` | PDF 导出产物 |
| `outline.md` | 幻灯片大纲（页号 / 角色 / 页级主张 / 来源） |
| `slide_plan.json` | 页级主张清单 |
| `content_map.json` | 内容映射（页 → 定位 + 证据引用 + 是否逐字校验） |
| `compliance_checks.json` | 自检合规项（含模板继承） |
| `report.md` | 人读报告 |
| `result.json` | 结果文件（回填输出契约） |

## 结构

- `SKILL.md`：入口与约定（单命令入口在最前）；
- `scripts/main.py`：编排（扫描 / 计划 / 契约回填 / 结果文件）；
- `scripts/deckkit.py`：材料扫描、页级抽取、markdown / HTML / SVG / PDF 渲染；
- `scripts/pptxkit.py`：标准库 OOXML `.pptx` 写入、模板主题复用与结构自检；
- `references/slides-spec.md`：机制说明。

纯 Python 标准库，无第三方依赖。
