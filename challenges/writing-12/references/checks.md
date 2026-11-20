# checks.md — 判据表、契约字段字典、draft.json 交接格式

## 1. 静态体检判据（`lint_project`）

| kind | severity | 判据 | 定位 |
|---|---|---|---|
| `document_structure` | error | 有 `\begin{document}` 无 `\end{document}` | `\begin{document}` 行 |
| `environment_mismatch` | error | `\begin/\end` 栈不配对（含 EOF 未闭合） | 该 `\begin`/`\end` 行 |
| `unbalanced_braces` | error | 去掉 verbatim 与 `\{`/`\}` 后 `{`≠`}` | 文件第 1 行 |
| `undefined_reference` | warning | `\ref`/`\cref`… 的键无对应 `\label` | 引用行 |
| `duplicate_label` | warning | 同一 `\label` 键第二次出现 | 重现行 |
| `unresolved_citation` | warning | `\cite` 键不在任何 `.bib`/`\bibitem` 中 | 文件第 1 行 |
| `no_bibliography_database` | warning | 有 `\cite` 但工程内无 `.bib` 且无 `\bibliography` | 文件第 1 行 |
| `duplicate_package` | warning | 同一 `\usepackage` 逐字重复 | 重现行 |
| `label_before_caption` | warning | float 内 `\label` 出现在 `\caption` 之前 | float 起始行 |
| `missing_input` | warning | `\input`/`\includegraphics` 目标不存在 | 该行 |
| `unit_spacing` | warning | 数字紧贴单位（如 `6m/min`、`120°C`）未用 `\SI{}{}` | 该行 |
| `tabular_columns` | warning | 行 `&` 数 + 1 超过 `\begin{tabular}{...}` 列数 | tabular 起始行 |
| `package_order` | warning | `hyperref` 早于 `cleveref`（后者应最后加载） | hyperref 行 |
| `font_missing` | error | 正文含 CJK 且引擎非 OpenType（非 xelatex/lualatex） | 文件第 1 行 |

`verbatim`/`lstlisting`/`minted` 内容先被清空再判定，避免其花括号/引号污染计数。

## 2. 可逆修复判据（`apply_fixes`）

- **auto-applied（`applied=true`）**：`missing_end_document`、`environment_mismatch`
  （在 `\end{document}` 前或 EOF 补齐 `\end{...}`，外层先闭）、`duplicate_package`（保留首次）、
  `duplicate_label`（重现项改 `name:dupN`）。
- **locate-only（`applied=false`）**：其余全部——已定位并给整改动作，但**不擅改科学语义**
  （引用、单位、表格列数、包序、字体）。
- 每条 fix 形状：`{id, kind, file, line, before, after, applied, locator, reason}`。
- `fixes.json` 同时给 `applied` / `reported` 计数与 `diff`（→ `diff.patch`）。

## 3. 构建与日志判据（`build.json` / `log-check.json`）

| kind | severity | 含义 |
|---|---|---|
| `missing_input` | error | 找不到 `\input`/图片 |
| `font_missing` | error | 字体不可用 / CJK 字体缺失 |
| `undefined_command` | error | 未定义控制序列 |
| `syntax` | error | `! ...` 语法错（含 `! LaTeX Error`） |
| `build_error` | error | 通用构建失败（非 0 退出 / 无 PDF） |
| `unresolved_reference` | warning | `Reference ... undefined` |
| `unresolved_citation` | warning | `Citation ... undefined` |
| `duplicate_label` | warning | `Label ... multiply defined` |
| `rerun_required` | warning | 需要再跑一遍（交叉引用/目录） |
| `layout` | warning | `Overfull/Underfull \hbox` 等排版告警 |

`build.json` 形状：`{engine, engine_requested, engine_switched, tool, status, exit, pdf, pages,
bytes, errors, warnings, root, limits}`；`status ∈ {passed, missing_tool, failed, timeout}`。
`log-check.json` 形状：`{status, errors:[{kind,severity,file,line,message}], warnings:[...], root_cause}`。

## 4. result.json 字段字典

| 键 | 类型 | 说明 |
|---|---|---|
| `case_id` | str | 输入 `case.json` 的 `case_id`（坏 JSON 时回退输入目录名） |
| `status` | str | `success` / `partial` / `failed`（见 SKILL.md §8） |
| `runtime` | obj | `{mode:"offline-deterministic", network:false}` |
| `deliverable` | obj | 见下（契约键 `deliverable`） |
| `output_contract` | obj | 逐键回填用例声明的每一个 `output_contract` 键 |
| `preserved_facts` | arr | 材料中须保真的数值/结论，每条带 `source`（`文件:行`） |
| `evidence_map` | arr | 材料段落 → 产出段落，带逐字 `segment`/`quote` 与 `source` |
| `change_log` | arr | `{step, action, detail}` 逐条工序流水 |
| `workorder_receipt` | obj | `{engine, build_status, root, fixes_applied}` |
| `sources` | arr | 本次读取的输入文件（相对路径 + 字节） |
| `uncertainties` | arr | 未决/需人工确认项（非空，至少含离线未验证说明） |
| `change_records` | arr | 源码改动记录（`file/line/before/after/applied`） |
| `limits` | arr | 能力边界（缺引擎、无网络、CJK 字体等，可执行复现命令） |
| `checks` | obj | 自查结果（`{ok, problems:[]}` / `selfcheck`） |

`deliverable` 形状：`{path, role, editable, compiled, pdf, bytes, diff, source_tree}`。

**空集合**一律用诚实信封 `{"kind": ..., "items": [], "count": 0, "note": "..."}`
（非空对象，`contract_values` 判为有值）；顶层不再出现裸 `null`。

## 5. draft.json（Agent → 脚本的交接格式）

Agent 读 `lint_report.json` 后，可在 `--work` 写一份 `draft.json` 覆盖「按材料确定性起稿」的正文。
脚本优先读它；缺省或坏 JSON 一律回退，不报错。

```json
{
  "title": "Cooling-Rate Control in Fill Compositing",
  "abstract": "One-paragraph abstract written by the Agent from the case materials.",
  "sections": [
    {"heading": "Results", "paragraphs": ["The pilot run measured a 38 % reduction in cycle time."]}
  ]
}
```

字段：`title`（str，可选）、`abstract`（str，可选）、`sections`（数组，每项 `{heading, paragraphs[]}`）。
其余键（如 `bibliography`、`packages`）忽略。脚本据此生成 `main.tex` 草稿，再走
`fix → check → build` 全链；**Agent 决定写什么，脚本负责体检/修复/构建/证据落盘**。
