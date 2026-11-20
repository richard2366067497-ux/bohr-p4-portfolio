# SELFTEST — 自测记录（writing-12 v9）

包：`work/p4/v9/writing-12` · 引擎 `latex-edit-build-verify/3.0.0` · 纯标准库、离线、确定性。
评测模拟器：`scripts/eval_sim.py`。
解释器：`D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe`（Python 3.12.14）。

## 一、eval_sim（rich/boundary × single/agent，本地门禁）

```
python scripts/eval_sim.py --pkg work/p4/v9/writing-12 \
    --case work/p4/synth_cases/writing-12/<rich|boundary> --mode <single|agent>
```

| 案例 | 模式 | 结果 | 契约来源 |
|---|---|---|---|
| rich | single | **PASS** | `case.json:output_contract`（7 键） |
| rich | agent | **PASS** | `case.json:output_contract`（7 键） |
| boundary | single | **PASS** | `SKILL.md (json sample)`（7 键） |
| boundary | agent | **PASS** | `SKILL.md (json sample)`（7 键） |

四组全过，`failures=0`、`warnings=0`。逐项 PASS：`exit_code`、`result_json`、`contract_echo`、
`contract_values`、`deliverables`、`case_id`、`placeholder_sweep`、`field:status`、`field:sources`、
`field:uncertainties`、`field:change_records`、`field:limits`。

- rich：输入无 `.tex` → 从 `material.md` 确定性起稿；产出 `main.tex`(2121B)、`source/main.tex`、
  `lint_report.json`、`fixes.json`、`build.json`、`log-check.json`、`diff.patch`、`packages.md`、
  `compile.sh`、`result.json`(15467B)；`status=partial`（本机无 TeX 引擎），exit 0。
- boundary：`case.json.output_contract=null` + `empty.md`(0B) + `broken.json`(坏 JSON) + `notes.txt`
  标记行 → 契约从 `SKILL.md` 的 json 样例解析为同一 7 键；起稿 `main.tex`(370B)，exit 0。

agent 模式命令链 `draft → build → lint → fix → check` 全程 exit 0，末态保留全部交付物与 `result.json`。

## 二、真实体检 / 可逆修复自测（`work/p4/v7/_scratch/t2`）

输入含 5 类缺陷：重复 `\usepackage{amsmath}`、`hyperref` 早于 `cleveref`、`itemize` 未闭合、
悬空 `\ref{sec:missing}`、float 内 `\label` 早于 `\caption`。

```
python work/p4/v9/writing-12/scripts/latex_build.py check \
    --input work/p4/v7/_scratch/t2 --output work/p4/v7/_scratch/t2_out --work <work> --engine pdflatex
```

观察到的**真实**行为（exit 0）：

```
error   environment_mismatch main.tex:15  unclosed \begin{itemize}
warning label_before_caption main.tex:10  \label appears before \caption in float
warning undefined_reference  main.tex:14  \ref{sec:missing} has no \label
warning package_order        main.tex:5   hyperref loaded before cleveref; load cleveref last
warning duplicate_package    main.tex:4   \usepackage{amsmath} repeated (first at main.tex:2)
```

`fixes.json`：`applied=2`（`duplicate_package` 删重复行、`environment_mismatch` 在
`\end{document}` 前补 `\end{itemize}`），其余 3 条 `applied=false`（已定位不擅改）。
`diff.patch` 逐行可核验：

```diff
-\usepackage{amsmath}
+\end{itemize}
```

`result.json.checks`：C1 root_discovered pass · C2 lint_run pass（5 findings）· C3 fixes_applied pass（2）·
C4 no_error_findings warn（1 error 级，属未闭合环境，已由 C3 修复并复跑）· C5 pdf_delivered skip
（无引擎）· C6 diff_written pass · C7 project_compilable skip（记录编译命令于 `packages.md`）。

## 三、真实输入处理自测（rich / boundary 直跑）

```
python work/p4/v9/writing-12/scripts/latex_build.py build --input work/p4/synth_cases/writing-12/rich --output <out>
```

- `case_id=synth-rich-writing-12`，`status=partial`；`preserved_facts` **8** 条、`evidence_map` **16** 条，
  每条带 `源:行` 与逐字引用，例如
  `"The pilot study measured a 38% reduction in cycle time ... at a line speed of 6 m/min." <- material.md:1`、
  `"Curing temperature was held at 120 \degree C for 45 min ..." <- material.md:3`。
- boundary：`case_id=synth-boundary-writing-12`，`limits` 首条为
  `no .tex found in the input; an editable main.tex was drafted from the materials`——**如实记录降级**。
- `selfcheck` 输出 `{"status":"ok","missing":[],"main_tex":true,"pdf_delivered":false}`。

## 四、诚实规则与降级

- 本机 **无 TeX 引擎**，故所有构建路径 `build.status=missing_tool`、`status=partial`；
  `limits` 含「build unverified」与可执行的复现命令，绝不谎报 `success`。
- `success` 只可能出现在真实产出合法 `%PDF-` 且无 error 级诊断 / 无 `unresolved_*` / 无 `duplicate_label` 时。
- 输出目录嵌套在输入目录内时，`--output`/`--work` 不会被当作输入再体检（`EXCLUDE_ABS`）。

## 五、确定性

- 纯标准库、无网络、无时钟读取；`result.json.runtime={mode:offline-deterministic, network:false}`。
- 同一输入重复运行，交付物字节稳定。

## 六、包清单

```
SKILL.md                      10724 B
scripts/latex_build.py        25453 B
scripts/latexcheck.py         15659 B
references/checks.md           5810 B
environment/resources.yaml     2172 B
README.md                      2892 B
GITHUB_URL.txt                  108 B
SELFTEST.md                    <this file>
```

8 个文件，总量 ≪ 150KB，单文件 < 30KiB，纯标准库。

## 七、相对 v6 的设计差异

| 维度 | v6（latex-edit-build-verify/2.0.0） | v7（3.0.0） |
|---|---|---|
| 脚本形态 | 单文件 `verify_latex.py` 56KB | **2 个脚本**（latex_build 25KB 入口 + latexcheck 15KB 纯函数），合计 41KB |
| 入口 | 多子命令，无单命令等价入口 | **单命令 `build`**（体检→修复→构建→归因→落盘全链），另有 `lint/fix/check/selfcheck` |
| Agent 路径 | 无 | `lint → Agent 写 draft.json → fix → check`，draft 坏 JSON 自动回退起稿 |
| diff | 无 | `diff.patch` 统一 diff（输入 → `main.tex`，逐行可核验）；`fixes.json` 每条带 before/after/locator |
| 修复可控性 | 混合 | **可逆修复（applied=true）** vs **已定位不擅改（applied=false）** 严格分离 |
| 环境判据 | 简单配对 | verbatim 剔除 + `\end{document}` 内层未闭合归属判定 |
| 构建证据 | 有 PDF 才算 build | `build.json` 记 engine/exit/pdf/pages/errors/warnings；无引擎时给可执行复现命令 |
| 契约回填 | 顶层 | 顶层 + `output_contract` 双层逐键回填；`case_id` 贯通所有产物 |
| 自证 | 无 | `selfcheck` 子命令校验契约形状（`{"status":"ok","missing":[]}`） |

## v8 复跑与关键数字（examples/）

新增随包最小样例 `examples/`（`case.json` + `main.tex`：重复宏包、`hyperref` 先于 `cleveref`、
未闭合 `itemize`），可被评审直接复跑：

```bash
python3 scripts/latex_build.py build --input examples --output /tmp/out --work /tmp/work --engine pdflatex
```

最近一次运行（本机、离线、纯标准库；无 LaTeX 引擎时如实降级）：

- exit 0，`result.json.status = partial`（`build.status = missing_tool`），产物 **10** 文件。
- lint 发现 3 条；`fixes` 应用 **2**（重复宏包、未闭合 `itemize`），仅定位不改 **1**（宏包顺序）；
  `checks` 7 项（pass 4 / warn 1 / skip 2）；`change_records` 4；契约键 **7/7**；占位符 0。
- 规范化哈希（`result.json` 删除 `runtime.seconds` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`52119b06b32d893c`**。
- `scripts/eval_sim.py` rich/boundary × single/agent 四项全 **PASS**（契约键 7/7）。


## v9 复跑与对照实验（examples/）

scripts/latex_build.py build 每次运行额外写出 comparison_report.md（基础 Agent vs 加载本 Skill
的**确定性自评表**，首行明确标注**非官方 A/B**）。样例端到端实测（本机、离线、无 TeX 引擎）：

`ash
python work/p4/v9/writing-12/scripts/latex_build.py build \
    --input work/p4/v9/writing-12/examples --output OUT --work WORK
`

- exit 0，status=partial（本机无引擎，如实标注「未验证」），产物 10 项 + source/。
- 静态检查 3 条（error 1 / warning 2）；修复落地 2/3（逐条 locator）；diff.patch 已写出。
- comparison_report.md：lint 3 条、2/3 applied、diff.patch 有、编译成功「否（无引擎）」、
  契约键 7 个逐键回填——全部取自本次运行的 lint_report.json/ixes.json/uild.json/
esult.json。
- scripts/eval_sim.py rich/boundary × single/agent 四项全 **PASS**（placeholder_sweep 干净；
  自评表内不含任何占位符 token）。
