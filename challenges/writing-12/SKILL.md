---
name: latex-edit-build-verify
description: >-
  LaTeX 写作与编译（writing-12）。单命令即完成「定位工程根 → 逐条静态体检（结构/环境/括号/
  引用/标签/宏包/单位/表格/CJK 字体）→ 最小可逆修复（每条带 before/after 与 locator）→ 真实构建
  → 日志归因（文件:行号:根因）→ 交付 可编辑 main.tex + source/ 工程树 + 统一 diff + 可编译工程
  （宏包说明 + 编译命令）；有引擎则落 main.pdf，缺引擎则如实记 partial 并给出可执行复现命令」。
  支持 agent-first 路径（Agent 读 lint 报告 → 写 draft → fix → check）；纯标准库、离线、确定性。
  Use for LaTeX source editing, failed/unstable builds, cross-reference and citation consistency,
  template migration, and reproducible manuscript builds.
license: MIT
---

# latex-edit-build-verify — LaTeX 写作与编译

本 Skill 做一件事的两面：**把源码改对**，并**用证据证明它能按模板编译**；同时把可继续编辑的
工程与统一 diff 交付出去。它不把未验证的源码冒充成品：没有 TeX 引擎时如实标 `partial` 并给出
**可执行的编译命令**。

安装根目录约定为 `/skills/weekly-skill`；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、7 步求解框架、量化口径与公式（编译成功率 /
修复正确率 / 事实可核验率 / 警告降幅）、领域知识与单位陷阱、交付物清单与专家检查表、完整虚构
案例、交付前门控。执行顺序固定为：先读手册 → 再按求解框架逐阶段落盘冻结产物 → 交付前逐项勾选
手册 §5.2 专家检查表。手册与本文冲突时，契约键名与入口命令以本文为准，方法与判分口径以手册为准。

---

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 逐键回填用例声明的每一个 `output_contract` 键：既放进顶层同名键，也放进
`output_contract` 结构位。每个键都给**真实值**，不用 `"string"`/`"object"` 这类类型占位符。

```json
{
  "case_id": "the input case_id",
  "status": "partial",
  "output_contract": {
    "case_id": "the input case_id",
    "status": "partial",
    "deliverable": {"path": "main.tex", "role": "manuscript", "editable": true,
                    "compiled": false, "pdf": "", "bytes": 2121,
                    "diff": "diff.patch", "source_tree": "source/"},
    "preserved_facts": [{"fact": "38 % reduction in cycle time", "source": "materials/material.md:1"}],
    "evidence_map": [{"segment": "The pilot study measured a 38% reduction ...", "source": "materials/material.md:1"}],
    "change_log": [{"step": "build", "action": "run", "detail": "pdflatex -> missing_tool"}],
    "workorder_receipt": {"engine": "pdflatex", "build_status": "missing_tool",
                          "root": "main.tex", "fixes_applied": 0}
  }
}
```

## 1. 单命令入口（第一条命令；评测入口，无 draft 时执行）

单命令即可产出完整契约与全部关键产物（评测只跑这一条也能过）。**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/latex_build.py build --input /input --output /app/output --work /app/work --engine pdflatex
```

- 省略根文件时自动扫描输入树选唯一根 `.tex`（`documentclass` + 命名 main/paper + 路径最短）；
  输入没有 `.tex` 也不空手而归：从科研材料确定性起一份可编辑 `main.tex`。
- 默认 `--output /app/output`、`--work /app/work`、`--engine pdflatex`。退出码恒为 0（含全部降级）；
  仅 argparse 用法错误返回 2。

## 2. Agent-first 增强路径（lint → draft → fix → check）

脚本机械校验 + Agent 判断不可相互替代：

```bash
python3 /skills/weekly-skill/scripts/latex_build.py lint  --input /input --output /app/output --work /app/work
# Agent 读 /app/output/lint_report.json（error 必修，warning 视是否影响输出），按需写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/latex_build.py fix   --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/latex_build.py check --input /input --output /app/output --work /app/work
```

`draft.json` 形状为 `{"title","abstract","sections":[{"heading","paragraphs":[...]}]}`（见
`references/checks.md`）；缺省或坏 JSON 一律回退到「按材料确定性起稿」，不报错。
**Agent 决定写什么，脚本负责体检/修复/构建/证据落盘。**

## 3. 子命令

| 子命令 | 作用 | 关键参数 |
|---|---|---|
| `build` | 全链：发现 → 体检 → 修复 → 构建 → 归因 → 写产物 | `--input --output --work --engine` |
| `lint` | 只做静态体检，写 `lint_report.json`（不调用引擎） | 同上 |
| `fix` | 应用可逆修复（含 Agent 的 `draft.json` 改动），写 `fixes.json` | 同上 |
| `check` | 把 build 作为「通过/需人工」闸门，写全部产物与 `checks` | 同上 |
| `selfcheck` | 校验结果契约形状，写 `selfcheck.json` | 同上 |

## 4. 静态体检（逐条定位到 文件:行号:根因）

`lint_report.json` 每条 `{id, severity, kind, message, file, line}`。判据表见 `references/checks.md`，
覆盖：`document_structure`（缺 `\end{document}`）、`environment_mismatch`（`\begin/\end` 栈不配对）、
`unbalanced_braces`、`undefined_reference`、`duplicate_label`、`unresolved_citation` /
`no_bibliography_database`、`duplicate_package`、`label_before_caption`、`missing_input`、
`unit_spacing`（数字紧贴单位 → 建议 `\SI{}{}`）、`tabular_columns`、`package_order`
（`hyperref` 早于 `cleveref`）、`font_missing`（CJK 非 OpenType 引擎）。

## 5. 可逆修复（每条 `before/after/locator`，写入 `fixes.json` 与 `diff.patch`）

| kind | 动作 | applied |
|---|---|---|
| `missing_end_document` | 文末补 `\end{document}` | true |
| `environment_mismatch` | 在 `\end{document}` 之前补齐未闭合的 `\end{...}` | true |
| `duplicate_package` | 删除后续逐字重复的 `\usepackage`（保留首次） | true |
| `duplicate_label` | 重复 `\label` 的重现项改名为 `name:dupN` | true |
| `undefined_reference` / `unresolved_citation` / `no_bibliography_database` | 报告差集并给人工处置点 | false |
| `missing_input` / `unit_spacing` / `tabular_columns` / `label_before_caption` / `package_order` / `font_missing` | 已定位，给整改动作，不擅改科学语义 | false |

`applied=false` 表示**已定位但不擅改**；`fixes.json` 同时给出 `applied`/`reported` 计数。

## 6. 真实构建与日志归因

- 构建固定 `latexmk -pdf -interaction=nonstopmode -halt-on-error -no-shell-escape`，或直接用
  `--engine pdflatex|xelatex|lualatex`。产物写入临时构建目录，**仅当产出合法 PDF（头 `%PDF-`）
  才复制到输出目录 `main.pdf`** 并计页数。
- 日志按 `kind → severity` 分类（`missing_input`/`font_missing`/`undefined_command`/`syntax`/
  `build_error` 为 error；`unresolved_*`/`duplicate_label`/`rerun_required`/`layout` 为 warning）。
- **归因原则**：日志报错点常晚于真正根因（宏展开、`\end`、EOF 处报错）；遇 error 先看 `l.<n>`
  上下文，取最早一条可指认来源者为根因，其余列为独立问题。

## 7. 输出交付物（写入 `--output`）

| 文件 | 内容 |
|---|---|
| `main.tex` | **修复后的可编辑根源码**（安全修复已应用；输入原文件不被改写） |
| `source/` | 复制进输出目录的工程树（子文件、`.bib`、本地 `.cls/.sty`、图片） |
| `main.pdf` | **编译成功时**从临时构建目录复制来的合法 PDF（`%PDF-` 校验通过才交付） |
| `diff.patch` | 统一 diff：输入源码 → `main.tex`（before/after 逐行可核验） |
| `lint_report.json` / `fixes.json` / `build.json` / `log-check.json` | 体检、修复清单、构建报告、日志检查 |
| `packages.md` | 所需宏包说明 + **固定编译命令** + 引擎选择（ASCII→pdflatex，CJK→xelatex+ctex） |
| `comparison_report.md` | 对照实验记录：基础 Agent（无 Skill）vs 加载本 Skill 的**确定性自评表**（明确标注非官方 A/B） |
| `compile.sh` | 可执行编译脚本（他人按此可复现同一产物） |
| `result.json` | 契约回填 + 结构化结果（见 §0） |

## 7.5 对照实验记录（使用增益证据）

每次运行都会额外写出 `comparison_report.md`：把**同一输入、同一环境**下「基础 Agent（不加载本 Skill）」
与「加载本 Skill」的差异逐项并排，全部取自本次真实运行的 `lint_report.json` / `fixes.json` /
`build.json` / `log-check.json` / `result.json`：

- 是否有可编辑 `.tex` 源文件树、是否有 `diff.patch` 原值快照、是否保留编译日志；
- 静态检查条数（error / warning）、真实落地（applied）的修复条数（每条带 `locator`）；
- 是否取得**真实 PDF**（无引擎时如实写「未验证」，不冒充通过）；
- `result.json` 是否逐键回填契约键。

报告首行显式声明这是**确定性自评表，不是官方 A/B 结果**，也不引用任何外部对照数据。

## 8. 诚实规则与降级（每次都必须 exit 0 且留下合法 result.json）

- `success`：真实构建产出合法 PDF，且无 error 级诊断、无 `unresolved_*`、无 `duplicate_label`。
- `partial`：源码已体检/修复（或已按材料起稿）但**未取得可用构建**（缺引擎、超时、仅静态）——「未验证」。
- `failed`：找不到根 `.tex` 且无法起稿、源码不可读，或构建产生 error 级诊断 / 无合法 PDF。

| 情况 | 处置 |
|---|---|
| 无 TeX 引擎 / 无 latexmk | `status=partial`，`build.status=missing_tool`，`limits` 含「build unverified」+ 可执行的编译建议 |
| CJK + 非 OpenType 引擎 | 自动切 `xelatex`（请求值记 `engine_requested`），`limits` 给 ctex/xeCJK 建议 |
| 材料也没有 | 起「缺口」骨架并记 `limits`，`partial` |
| 坏 `case.json` | 仍体检/起稿，`case_id` 回退为输入目录名 |
| 输出目录不可写 | 回退 stderr 打印，退出码仍 0 |

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §5.2 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 在，`output_contract` 逐键回填且无类型占位符。
- [ ] `comparison_report.md` 已写出，且明确标注为自评（非官方 A/B）。
- [ ] `main.tex` 存在且非空；`lint_report.json`/`fixes.json`/`build.json`/`diff.patch` 结构合法。
- [ ] 有引擎时 `main.pdf` 落在 `--output` 且头为 `%PDF-`；无引擎时 `status=partial` 且 `limits` 含编译建议。
- [ ] `fixes[]` 每条有 `before`/`after`/`locator`/`applied`；`diff.patch` 可逐行核验改动。
- [ ] 空输入 / 坏 JSON / 坏日志三条路径各跑过一次，均 exit 0。

## 10. 最小调用示例（示意，非正式案例结果）

输入 `main.tex`（当前目录）：

```
\documentclass{article}
\begin{document}
\begin{equation}\label{eq:sum} 1+1=2 \end{equation}
See equation~\ref{eq:sum}.
\end{document}
```

```bash
python3 /skills/weekly-skill/scripts/latex_build.py build --input INPUT_DIR --output /app/output --work /app/work
```

有引擎时：`status=success`，`build.status=passed`，`main.pdf` 落在输出目录，`checks` 全 pass。
**无引擎时**：`status=partial`，`build.status=missing_tool`，`limits` 含「build unverified」+ 编译建议，
`main.tex`/`source/`/`diff.patch`/`packages.md` 照常落盘——这是「未验证」，不是「通过」。

## 11. 文件清单

```
SKILL.md                        本文件：入口、agent-first、体检/修复、构建、契约、降级
scripts/latex_build.py          入口：build / lint / fix / check / selfcheck
scripts/latexcheck.py           静态体检 + 可逆修复（纯函数，无引擎）
references/expert_playbook.md   专家方法论：判分要点、7步框架、公式、检查表、虚构案例
references/checks.md            体检判据表 + result.json 字段字典 + draft.json 交接格式
environment/resources.yaml      资源入口声明（命令、预算、无网络、纯标准库）
README.md  SELFTEST.md  GITHUB_URL.txt   安装、用法、自测记录、仓库地址
```

依赖：Python 3.9+ 标准库；`build/check/fix/selfcheck` 需要 `latexmk`（或直接引擎）与所选 TeX 发行版；
中文稿需 `xelatex` + `ctex`/`xeCJK` + CJK 字体。

## 随包文件（v8 新增）

```
environment/resources.yaml   运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                    最小可复跑样例（case.json + main.tex），评审可直接复跑
GAIN_EVIDENCE.md             无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
