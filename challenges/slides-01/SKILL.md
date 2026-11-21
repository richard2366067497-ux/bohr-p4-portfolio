---
name: slides-author
description: Turn a supplied paper or research material into an evidence-linked academic deck. Extracts one page-level claim per section with a material locator and a verbatim quote, honours an optional slide workorder, and writes an editable source, a rendered export, a content map, a page-level gold standard and compliance checks. Every run backfills the whole output contract and always exits 0.
version: 9.0.0
---

# slides-author (slides 赛道 · v9)

把一个固定论文 / 研究材料组织成**结构清楚、证据可追溯、可编辑、可渲染**的学术汇报产物。
论文是连续的叙述，PPT 是页级的离散表达：一页一个主张，主张背后挂着一张图 / 一张表 / 一段结论。
本包只做「论文 → 可讲、可核验、可编辑的学术 PPT」这条链路，不负责论文精读、不负责科研绘图本身的美化、
也不负责学术写作润色。

## 契约（output_contract）

`case.json` 给出 `output_contract` 时以它为准；否则用下列内建键（边界用例同样输出这套键）。
每个键在 `result.json` **顶层**与嵌套 `output_contract` 对象里各回填一次，两处完全一致：

```json
{
  "output_contract": {
    "case_id": "string",
    "input_error": "string",
    "editable_source": "string",
    "export_artifact": "string",
    "content_map": "string",
    "compliance_checks": "string",
    "exceptions": "string",
    "errors": "string",
    "degradations": "string",
    "uncertainty": "string",
    "pending_human": "string",
    "changes": "string",
    "sources": "string",
    "runtime": "string",
    "partial": "string"
  }
}
```

## 单命令入口 / single command

下面这一条命令就是**等价入口**（one-shot）：扫描输入材料 → 抽取页级主张与逐字证据 → 复用目标模板
→ 生成可编辑源与导出产物 → 写内容映射 / 页级金标准 / 合规检查 / 版本记录 → 把整个输出契约回填进结果文件。
一条命令即可完整复现，`all` 内部等价于 `init → check → build → selfcheck`：

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

命令始终以退出码 0 结束：即使输入为空或损坏，也会写出一个合法、诚实的结果文件（状态为
`insufficient_evidence`），而不是抛错中断。**无 `work/draft.json` 也照常跑完**，仍产出完整契约与全部交付物。

## 分步命令（agent 增强路径）

```bash
python3 -B scripts/main.py init  --input /input --output /app/output --work /app/work
python3 -B scripts/main.py show  --input /input --output /app/output --work /app/work
python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

- `init` 扫描材料、写材料索引，并写出 `work/draft.json` 骨架（供人填写页级主张与逐字引文）；
- `show` 打印材料索引（材料、章节、可用句子、图表清单）；
- 人填好 `work/draft.json` 后 `check` 逐条校验：每条 `quote` 是否在材料里**逐字命中**、是否都有 `locator`；
  未命中的草稿条目会被丢弃并记入 `exceptions`，**不伪造**内容；
- `build` 用 `work/draft.json`（若存在且逐字命中）优先成稿，否则由材料自动抽取；`all` = `build` + `selfcheck`；
- `selfcheck` 在 `build` 之后复检产物并刷新 `result.json`。

`work/draft.json` 的 schema（顶层键 `sections`，每条一个页级条目）：

```json
{
  "sections": [
    {"index": 2, "role": "methods", "title": "Method",
     "quote": "the exact sentence copied verbatim from the material",
     "locator": "M01#s2",
     "notes": "explain the emphasis for this page, worded differently from the slide",
     "bullets": ["a second exact sentence from the material", "a third exact sentence"]}
  ]
}
```

## 交付物（每次运行写入 --output）

| 文件 | 说明 |
|-|-|
| `presentation.pptx` | 可编辑 OOXML 演示源（每页 1 张幻灯片 + 1 张讲解备注页，继承模板母版 / 主题） |
| `presentation.pdf` | 同一页计划导出的 PDF（页数 = 幻灯片数） |
| `deck.md` | 可编辑 Markdown 源（每页以 `---` 分隔，带 role / notes / source 注释） |
| `deck.html` | 可直接播放的网页版 |
| `preview.svg` | 逐页矢量预览（标题、要点、来源定位） |
| `outline.md` | 幻灯片大纲（页号 / 角色 / 页级主张 / 来源定位） |
| `slide_plan.json` | 页级主张清单 |
| `content_map.json` | 内容映射（页 → source_locator + evidence_quote + figure_refs + origin + 是否逐字校验） |
| `page_gold.json` | 页级金标准（每页必需要素、定位、逐字引文、图表引用） |
| `compliance_checks.json` | 自检合规项（来源链接、逐字引用、无编造数字、页数预算、预览、导出渲染…） |
| `version_log.json` | 字体 / 模板 / 修改记录（含主题哈希与产物 sha256） |
| `report.md` | 人读报告 |
| `result.json` | 结果文件：顶层同名键 + 嵌套 `output_contract`，透传 `case_id` |

工作区（`--work`）另写材料索引 `index.json`、工作稿骨架 `draft.json` 与错误记录；它们不是交付物。

## 证据与推导机制

- **页级主张**：每个小节取其**实质句子**（而非把 markdown 标题搬进页面）组成页；空小节丢弃；
- **locator + 逐字引文**：每页记录材料 id 与章节序号（如 `M01#s2`），每个要点保留其原始句子用于复核；
- **数字白名单**：含数字的要点在进入页面之前先在原文 span 内重新定位，找不到的数字**不打印**；
- **图表引用**：材料里的图表编号（`Figure N` / `Table N`）被登记为该页 `figure_refs`，对齐正文；
- **讲解备注**：每页一条 ≥20 字符且与页面文字**不同**的讲解，用于提示强调点与指向的 span；
- **模板继承**：存在目标模板时复用其主题 / 母版并记录主题哈希，保证套用统一版式；
- **页级金标准**：`page_gold.json` 给出每页的必需要素与定位，供评审直接对照复核。

## 降级与诚实

- 空 / 不可读 / 坏 JSON 材料：不中断，逐条登记进 `errors` / `degradations` / `exceptions`，状态转
  `insufficient_evidence`，产物仍是**带原因的合法非空结构**；边界用例同样输出完整契约与全套交付物；
- 读不了的图片、抽取不到的图表编号、模板缺失：如实记录，不放装饰性替身，也不编造数值 / 单位；
- 任何异常都 `exit 0` 并写出带 `output_contract` 的 `result.json`（状态 `input_error`）。

## top_fix → 实现

| top_fix | 实现 |
|-|-|
| GITHUB_URL.txt（两行） | 提交目录根路径 `GITHUB_URL.txt`：仓库目录 URL + `challenges/slides-01` |
| 对照实验记录 | `GAIN_EVIDENCE.md`：baseline vs skill 的连接 / 使用增益逐项证据与复现命令 |
| 最小调用示例真实输出样例 | `examples/minimal-run.md`：一组输入 + 调用 + 示意输出（**标明为示例**） |
| 异常场景测试记录 | `SELFTEST.md` §3：坏 JSON / 空材料 / 无图注 / 无模板 / 页数上限 的处置与实测 |
| 创新证据文档 | `GAIN_EVIDENCE.md` §创新：相对通用 python-pptx 生成与手工排版的边界（数字白名单、逐字命中、模板哈希、页级金标准） |
| 可复用模板 / 页级大纲模板 / 证据映射表样例 | `templates/slide-plan-template.json`（页级大纲模板 + 证据映射字段） |

参见 `references/slides-spec.md` 的机制说明。
