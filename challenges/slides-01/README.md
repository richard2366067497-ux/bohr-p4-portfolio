# slides-author（slides 赛道 · slides-01 · v9 包）

把一篇论文 / 研究材料转成**证据可追溯、可编辑、可渲染**的学术汇报产物：

**主线 + 页级主张 + 逐字证据（locator + quote）+ 模板继承 + 导出渲染**，
每次运行把整个输出契约回填进 `result.json`（顶层同名键 + 嵌套 `output_contract`）。

## 一条命令（评测入口）

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work ; echo "exit=$?"
```

单命令等价入口：不写工作稿也产出**完整契约 + 全部交付物 + result.json**，恒 `exit 0`。

Agent 增强路径（需要逐条人工挑选页级主张时）：

```bash
python3 -B scripts/main.py init --input /input --output /app/output --work /app/work
python3 -B scripts/main.py show --input /input --output /app/output --work /app/work
#   读 show 的逐条原文，写 /app/work/draft.json（schema 见 SKILL.md）
python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

## 交付物

| 文件 | 说明 |
|---|---|
| `result.json` | 契约回填（顶层 + 嵌套 `output_contract`）+ `status` / `sources` / `uncertainties` / `change_records` / `limits` |
| `presentation.pptx` | 可编辑 OOXML 演示源（每页 1 张幻灯片 + 1 张讲解备注页；49 个 part） |
| `presentation.pdf` | 同一页计划导出的 PDF（页数 = 幻灯片数） |
| `deck.md` | 可编辑 Markdown 源（每页 `---` 分隔，带 role / notes / source 注释） |
| `deck.html` / `preview.svg` | 可直接播放的网页版 / 逐页矢量预览 |
| `outline.md` / `slide_plan.json` | 幻灯片大纲 / 页级主张清单 |
| `content_map.json` | 内容映射：每页 `source_locator` + `evidence_quote` + `figure_refs` + `origin` + 逐条 `verified` |
| `page_gold.json` | 页级金标准：每页必需要素、定位、逐字引文、图表引用 |
| `compliance_checks.json` / `version_log.json` | 自检合规项 / 字体·模板·修改记录（含主题与产物 sha256） |
| `report.md` | 人读报告 |

## 与基线的差别

基线把论文按段落顺序贴进页面、图表编号错位、数字被就地改写。本包：
**页级主张取自实质句子（不在小数点处断句）**、每页保留 locator 与逐字引文、
含数字的要点先在原文重新定位后才上页、图表编号登记为 `figure_refs`、
页级金标准与模板主题哈希可复核。异常场景（坏 JSON / 空材料 / 无图注 / 无模板 / 页数上限）
统一降级为 `insufficient_evidence` 并恒 `exit 0`。详见 `GAIN_EVIDENCE.md` 与 `SELFTEST.md`。

## 不做

论文精读结论生成、科研绘图本身的美化、学术写作润色、数据库运维。本包只对
「论文内容如何变成可讲、可核验、可编辑的学术 PPT」负责。

## 结构

- `SKILL.md`：入口与契约（单命令入口在最前）；
- `scripts/main.py`：编排（扫描 / 计划 / draft 折叠 / 契约回填 / 结果文件）；
- `scripts/deckkit.py`：材料扫描、页级抽取、content_map / page_gold、markdown / HTML / SVG / PDF 渲染；
- `scripts/pptxkit.py`：标准库 OOXML `.pptx` 写入与结构自检；
- `references/slides-spec.md`：机制说明；`templates/slide-plan-template.json`：可复用页级大纲模板 + 证据映射字段；
- `examples/minimal-run.md`：最小调用示例（**标明为示例**）；`environment/resources.yaml`：环境与资源声明。

纯 Python 标准库，无第三方依赖。作品集：见 `GITHUB_URL.txt`。
