---
name: slides-author
description: Turn a supplied paper, research note or reference guide into an evidence-linked academic deck. Extracts one page-level claim per section (never just the markdown headings), keeps a material locator and a verbatim quote per page, and writes an editable source plus rendered exports, a content map and compliance checks. Every run backfills the whole output contract.
version: 6.0.0
---

# slides-author (slides 赛道 v6)

把一个固定论文 / 研究材料 / 参考说明组织成**结构清楚、证据可追溯、可编辑、可渲染**的学术汇报产物。
论文与参考文档是连续的叙述，PPT 是页级的离散表达：本包把**每一节的实质句子**抽成页级主张与要点，
而不是把 markdown 标题直接搬进页面，因此不会出现“标题页 / 空页”。

## 单命令入口 / single command

下面这一条命令就是**等价入口**：扫描输入材料 → 抽取页级主张与证据 → 生成可编辑源与导出产物 →
写出内容映射与合规检查 → 把整个输出契约回填进结果文件。`all` 内部等价于
`init → check → build → selfcheck`：

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

命令始终以退出码 0 结束：即使输入为空或损坏，也会写出一个合法、诚实的结果文件（状态为
`insufficient_evidence`），而不是抛错中断。

## 输入

- 输入根目录下的文本材料（`.md` / `.markdown` / `.txt` / `.tex` / `.csv` 等）逐份抽取为材料 `M01`、`M02` …；
- 第一份「论文 / 研究材料 / 参考文档」作为主材料，其标题与各级小节成为页面骨架；
- 若存在 slide-workorder.json（讲稿工作单），模式、页数预算、受众、时长、语言、必需小节、备注要求、输出格式会被回显；
- 若存在 target-template.pptx（目标模板），其主题与母版会被复用，保证成品套用统一版式；
- 图片材料登记为可用图表来源。

## 输出（可编辑源 + 导出产物）

每次运行都会在输出目录写出：

- `deck.md` —— 可编辑 Markdown 源，每页以 `---` 分隔，携带 role / notes / source 注释；
- `deck.pptx` —— 可编辑 OOXML 演示文稿源，每页一张幻灯片并配一张讲解备注页；
- `deck.html` —— 可直接播放的网页版（SVG / HTML 组合之一）；
- `preview.svg` —— 手写矢量缩略预览，逐页列出标题、要点与来源定位；
- `deck.pdf` —— 由同一份页计划生成的 PDF 导出产物；
- `outline.md` —— 幻灯片大纲（页号 / 角色 / 页级主张 / 来源定位）；
- `slide_plan.json` —— 页级主张清单；
- `content_map.json` —— 内容映射（页 → 原文定位 + 逐条证据引用 + 是否逐字校验）；
- `compliance_checks.json` —— 自检合规项（来源链接、逐字引用、无编造数字、页数预算、预览、导出渲染等）；
- `report.md` —— 人读报告；
- `result.json` —— 结果文件：回填整个输出契约（顶层同名键 + 嵌套 `output_contract`），透传 `case_id`。

## result.json 约定

结果文件同时提供顶层键与 `output_contract` 嵌套字典，二者同名同值；`output_contract` 覆盖契约中出现的
每一个键，并把输入里的 `case_id` 原样透传。状态字段为 `ok`（材料充分）或 `insufficient_evidence`
（材料不足，诚实声明且不编造内容）。

## 分步子命令（可选，便于调试）

```bash
python3 -B scripts/main.py init       # 扫描材料，写索引
python3 -B scripts/main.py show       # 打印索引
python3 -B scripts/main.py check      # 抽取页计划与合规检查
python3 -B scripts/main.py build      # 生成全部产物并回填契约
python3 -B scripts/main.py selfcheck  # 复检产物并刷新结果文件
```

## 约定与边界

- 纯 Python 标准库实现（`zipfile` 写 OOXML、手写 SVG、简单 PDF 生成器），无第三方依赖；
- 页面内容**逐条来自输入材料**：每页保留材料定位与逐字引用；数字类主张在进入页面之前会先在原文里重新定位；
- 不编造内容：材料不足时输出 `insufficient_evidence` 并给出诚实的例外说明；
- 参考说明见参考资料目录。
