---
name: slides-author
description: Turn a supplied paper or research material into an evidence-linked academic deck. Extracts one page-level claim per section from the substantive sentences (never just markdown headings), keeps a material locator per page, re-checks numeric claims verbatim in the source span, and writes an editable source plus rendered exports, a slide plan, a content map and compliance checks. Every run backfills the whole output contract and always exits 0.
version: 10.0.0
license: MIT
---

# slides-author（slides 赛道 · v10）

把一个固定论文 / 研究材料组织成**结构清楚、证据可追溯、可编辑、可渲染**的学术汇报产物。
论文是连续的叙述，PPT 是页级的离散表达：本包把**每一节的实质句子**抽成页级要点与来源定位，
而不是把 markdown 标题直接搬进页面，因此不会出现「标题页 / 空页」。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 references/expert_playbook.md**，并按它组织全部产出：

- **判分要点**：按手册 §1 明确「可编辑演示文件 + 页级证据映射 + 渲染与版本记录 + result.json」四件套；
- **流程门控**：按手册 §2 六步（解析→提取→页规划→模板填充→证据映射→渲染校验）推进，前一步未冻结不进入下一步；
- **量化口径**：按手册 §3 的页数符合度 / 证据覆盖率 / 数字一致率 / 模板符合度 / 渲染缺陷率逐项核算；
- **陷阱排雷**：按手册 §4 的错误做法→正确做法逐条自检（数字、单位、图注编号、模板覆盖、导出缺陷）；
- **交付前**：按手册 §6 自查表与 §5 的 locator 规则逐项通过，未过项记 `partial` 并写入不确定性。

## 单命令入口（评测与人工都跑这一条）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

这一条命令扫描输入材料 → 抽取页级要点与来源定位 → 生成可编辑源（markdown / OOXML pptx / html）
与导出产物（PDF / 矢量预览）→ 写 slide plan / content map / compliance checks / 报告 →
把整个输出契约回填进结果文件；`all` 内部等价于 `init → check → build → selfcheck`。
命令始终以退出码 0 结束：即使输入为空或损坏，也写出一个合法、诚实的结果文件（状态为
`insufficient_evidence`），而不是抛错中断。

## Agent 增强路径（同一引擎，多条命令）

```bash
python3 -B /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py show  --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

- `init` 扫描材料、写材料索引 work/index.json 与 work/draft.json 骨架；
- `show` 按 locator（`M01#L12`）打印材料行，可用 `--grep` / `--limit` 过滤；
- 人/Agent 填好 work/draft.json 后 `check` 逐条校验：每页是否有 `title` 与 `source` 定位；
- `build` 生成全部产物并写最终 `result.json`；`selfcheck` 复检产物并刷新自检结果；`all` = 一键全流程。

work/draft.json 的 schema：

```json
{"case_id": "example-case", "slides": [
  {"index": 2, "kind": "section", "title": "Method",
   "bullets": ["an exact sentence copied from the material"],
   "source": "M01#s2",
   "notes": "what to stress out loud on this page"}]}
```

## 输出契约（output_contract）

`case.json` 给出 `output_contract` 时逐键回填那一组键；否则回填下列内建键。每个键在 `result.json`
**顶层**与嵌套 `output_contract` 对象里各写一次、两处一致，并原样透传 `case_id`。

| 键 | 含义 |
|-|-|
| `case_id` | 透传输入案例号 |
| `status` | 运行状态：built / partial / insufficient_evidence / input_error |
| `editable_source` | 可编辑源文件名 |
| `export_artifact` | 导出件文件名 |
| `content_map` | 页 → 材料定位 + 是否逐字校验 |
| `compliance_checks` | 合规自检对象 |
| `exceptions` | 缺料 / 推断 / 丢弃条目清单（永不空数组） |
| `slide_plan` | 页级要点清单（含每页讲解备注与来源定位） |
| `preview` | 矢量预览文件名 |
| `coverage` | 覆盖统计（页数 / 逐字命中数） |
| `deck` | Markdown 源文件名 |
| `summary` | 一句话摘要 |
| `report` | 人读报告文件名 |

## 交付物（每次运行写入 --output）

| 文件 | 说明 |
|-|-|
| `deck.md` | 可编辑 Markdown 源（每页以 `---` 分隔，带 kind / notes / source 注释） |
| `deck.pptx` | 可编辑 OOXML 演示源（每页 1 张幻灯片 + 1 张讲解备注页） |
| `deck.html` | 可直接播放的网页版 |
| `preview.svg` | 逐页矢量预览（标题、要点、来源定位） |
| `deck.pdf` | 同一页计划导出的 PDF（页数 = 幻灯片数，含 xref / trailer / %%EOF） |
| `slide_plan.json` | 页级主张清单（含每页讲解备注与来源定位） |
| `content_map.json` | 内容映射（页 → source locator + kind + 是否逐字校验） |
| `compliance_checks.json` | 自检合规项（来源链接、逐字引用、无编造数字、页数预算、预览与导出） |
| `report.md` | 人读报告 |
| `result.json` | 结果文件：顶层同名键 + 嵌套 `output_contract`，透传 `case_id` |

## 输入

- 输入根目录下的文本材料（`.md` / `.txt` / `.tex` / `.csv` 等）逐份抽取为材料 `M01`、`M02` …；
- 第一份「论文 / 研究材料 / 参考说明」作为主材料，其标题与各级小节成为页面骨架；
- `case.json` / `challenge.json` 提供 `case_id` 与权威 `output_contract`；`task.md` 提供受众与时长约束。

## 证据与推导机制

- **页级要点**：每个小节取其**实质句子**（而非把 markdown 标题搬进页面）组成页面；空小节丢弃；
- **locator**：每页记录材料 id 与章节序号（如 `M01#s2`），页面上打印来源行供复核；
- **数字白名单**：含数字的要点在进入页面之前先在原文 span 内重新定位，找不到的数字不打印；
- **讲解备注**：每页一条 ≥20 字符、与页面文字**不同**的讲解，提示该页的强调点与指向的来源；
- **模板继承**：存在目标模板时复用其主题 / 母版并记录主题哈希，保证套用统一版式。

## 降级与诚实

- 空 / 不可读 / 坏 JSON 材料：不中断，逐条登记进 `errors` / `degradations` / `exceptions`，状态转
  `insufficient_evidence`，产物仍是**带原因的合法非空结构**；边界用例同样输出完整契约与全套交付物；
- 读不了的图片、抽取不到的图表编号、模板缺失：如实记录，不放装饰性替身，也不编造数值 / 单位；
- 任何异常都 `exit 0` 并写出带 `output_contract` 的 `result.json`（状态 `partial` / `input_error`）。

## 自检清单（交付前逐项通过）

- [ ] **专家检查表逐项通过**：references/expert_playbook.md §6 的每一行都复核并留痕；
- [ ] 单命令入口 `all` 在无 draft 时退出码为 0，且写出 `result.json` 与全套交付物；
- [ ] 契约每个键在顶层与 `output_contract` 两处一致，无空数组 / `null` / 占位符；
- [ ] `deck.pptx` 可解析（OOXML part 完整，幻灯片数 = 备注页数），`deck.pdf` 含 xref/trailer/%%EOF；
- [ ] 每页有 locator，数字类要点已在原文 span 内复核；
- [ ] `slide_plan.json` / `content_map.json` / `compliance_checks.json` 与成稿一致；
- [ ] 边界用例（空/坏材料、null 契约）仍输出完整契约与全套交付物。

参见 references/expert_playbook.md 的方法说明；GAIN_EVIDENCE.md 给出基线与本包的对照证据；
environment/resources.yaml 记录依赖与运行边界；examples/minimal-run.md 是一组最小调用示例
（**标明为示例，非正式案例结果**）。
