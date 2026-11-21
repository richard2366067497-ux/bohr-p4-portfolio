---
name: formula-verification
description: >-
  Faithful formula restoration and verification for supplied artifacts: read every MathML
  node and restore it to LaTeX with an explicit tag-by-tag mapping, record structural
  complexity (fractions/radicals/scripts), build a symbol ledger with provenance
  (paper_defined / context_inferred / common_knowledge), mine the printed assignments,
  numeric indicators and substitution/assumption sentences, then run numeric checks that
  substitute printed values only and are left not computable rather than guessed. Every
  restored object carries a verbatim quote and a locator; empty or unreadable input still
  yields a legal result.json with an explicit gap list.
version: 3.0.0
---

# formula-verification — 公式还原与核验

一句话：**把 MathML 一节点一节点翻成 LaTeX，并证明每个符号的定义与取值都有出处。**

它不重排公式、不猜没印的取值、不替作者补一步推导。每个还原对象都带
`原文引用 / locator / 出处类型`；算不了的检查就写 `not_computable`，只用示意值探路就写
`example_only`，两者都不冒充“算出来的结果”。

安装根目录约定为 **/skills/weekly-skill**；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 1. 入口命令（第一条，必须先看）

单命令即可跑完整流程并产出全部产物（评测只跑这一条也能过）：

```
python3 -B /skills/weekly-skill/scripts/main.py \
  --input /input --output /app/output --work /app/work
```

该命令等价于 `main.py build`，按顺序执行：

1. **read**：读 `--input` 下全部材料（`case.json`/`task.md` 除外），按 sha1 去重；
   含 `<math` 的 XML 走 MathML 解析，其余按文本读入；
2. **restore**：对每个 `disp-formula/equation` 下的 `mml:math`，按
   `mi/mn/mo/mrow/msup/msub/msubsup/mfrac/msqrt/mroot/mfenced` 映射表翻成 LaTeX，
   并统计分数/根号/上下标结构；
3. **ledger**：收集符号，逐个给出 `definition_source`（material 明确写 = `paper_defined`，
   只推得取值 = `context_inferred`，其余 = `common_knowledge`）；
4. **mine**：从段落里挖 `X is ...` 定义与 `X = 值 单位` 赋值；从笔记里挖数值指标
   （温度/压力/空速/转化率/时长）与代入、假设句；
5. **check**：逐个公式做数值核验——符号齐全就用印刷值代入（`computed`），
   缺符号就 `not_computable`，源里没有任何值就只用单位示意值（`example_only`）；
6. **emit**：写 `formulas.tex`、`symbol_table.csv`、`verification.md` 与 `result.json`。

任意阶段抛异常都会兜底写出合法 `result.json` 并 exit 0。

---

## 2. 用途与适用条件

| 用户诉求 | 本 Skill 的动作 |
|-|-|
| “把这些 MathML 公式翻出来” | 逐节点映射 → LaTeX + 结构统计 |
| “这个符号是什么意思、取的多少” | 符号台账 + `definition_source` + 逐字出处 |
| “帮我把公式代进去算一下” | 只用印刷值；缺值判 `not_computable`，不猜 |
| “材料里的关键数值有哪些” | 印刷指标表（温度/压力/空速/转化率/时长） |
| “材料不全怎么办” | `insufficient_evidence` / `input_error` + 缺口清单 |

不适用：符号代数化简、量纲分析代写、补造实验数据、渲染图片。

---

## 3. 子命令与 agent-first 双路径

| 子命令 | 作用 | 关键参数 |
|-|-|-|
| `build` | 全流程（默认）：read→restore→ledger→mine→check→emit | `--input --output --work` |
| `show` | 打印已还原公式与 locator | 同上 |
| `check` | 重跑全流程，并合并 `/app/work/draft.json` 里的 Agent 备注 | 同上 |
| `selfcheck` | 重跑全流程并审计 `output_contract` 键 | 同上 |

每个子命令都会重写一份完整 `result.json`，评测跑哪一条都拿得到完整契约。

推荐 **agent-first** 流程（脚本负责还原与核验，Agent 负责判读与措辞）：

```
# 1) 确定性全流程，先拿到公式与符号台账
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
# 2) Agent 读 /app/output/symbol_table.csv 与 verification.md，补 /app/work/draft.json
# 3) 复核并交付
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`/app/work/draft.json` 约定（可缺省；缺省或坏 JSON 一律回退到确定性结果，不报错）：
顶层 `notes` 数组，每条形如 `symbol` 指向台账里的符号、`definition_source` 与 `text`；
合并时只接受 `symbol` 命中台账且 `text` 非空的条目，其余逐条丢弃并记入 `degradations`。

---

## 4. 映射与核验口径

- **MathML→LaTeX**：`mi/mn/mo` 取文本（希腊字母转 `\alpha` 等）；`msup→^{}`、`msub→_{}`、
  `msubsup→_{}^{}`、`mfrac→\frac{}{}`、`msqrt→\sqrt{}`、`mroot→\sqrt[]{}`、
  `mfenced→\left(...\right)`；未知标签只拼接子节点，不吞内容。
- **符号收集**：下标/上标按其父节点整体记为一个符号（如 `N_{0}^{2}`），
  指数里的字母单独收集（如 `e^{kt}` 记出 `e`、`k`、`t`），去重后保持出现顺序。
- **出处类型**：`paper_defined`（材料有 `X is ...` 定义句）/ `context_inferred`
  （只有赋值无定义）/ `common_knowledge`（材料未定义，属通用符号）。
- **数值核验**：`computed`（符号都有印刷值）、`not_computable`（缺符号，列进
  `missing_symbols`）、`example_only`（源里没有值，仅用单位示意值探路）。
- **locator**：公式 `{文件}#{formula_id}`、定义句 `{文件}#p{序}`、
  指标 `{文件}#L{行}`；不使用尖括号形式。

---

## 5. 输出契约

写入 `--output`（默认 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + 结构化结果（见下） |
| `formulas.tex` | 已还原公式的 LaTeX 列表（含 `%` 注释行） |
| `symbol_table.csv` | 符号台账：`symbol_id,symbol,plain,formula_ids,role,definition_source,definition,value,units,locator` |
| `verification.md` | 人读核验报告（公式/台账/数值核验/推导/指标/覆盖率） |
| `run.log` | 运行摘要 |

`--work` 下另有 `index.json`（公式/符号/推导/指标/覆盖快照）。

`result.json` 顶层键（键名冻结；case 给几个 `output_contract` 键就回填几个，并逐一浅拷贝到顶层）：

- `case_id` / `status` / `summary`
- `output_contract`：逐键回填真实值，不写 `string`/`object` 类型占位符
- `result`：`{formulas[], variables[], derivations[], numeric_checks[], indicator_checks[],
  coverage, missing_objects[], notes, method}`
- `claims[]`（公式/定义/取值/推导/指标各一条，带 `evidence[]` 逐字引文 + locator）
  / `sources[]`（每条任务级 source 至少带一条逐字 quote + locator）
  / `uncertainties[]`（镜像 `uncertainty`）/ `change_records[]`（镜像 `changes`）
- `errors[]` / `degradations[]` / `pending_human[]` / `limits[]` / `counts` / `runtime`

**回填样例**（未给契约时回填标准五键）：

```json
{"case_id": "synth-rich-reading-08",
 "status": "partial",
 "output_contract": {
   "case_id": "synth-rich-reading-08",
   "status": "partial",
   "result": {"coverage": {"formulas": 2, "symbols": 7, "numeric_computed": 0}},
   "claims": [{"claim_id": "c01", "kind": "formula", "formula_id": "fd-1",
               "text": "restored fd-1 (1) to N_{0}^{2}=e^{kt}", "verified": true,
               "evidence": [{"source_document_id": "D1",
                             "quote": "We model growth where k is the specific growth rate in 1/h and t is time in h.",
                             "locator": "source-formulas.xml#p1"}]}],
   "uncertainties": [{"item": "symbol_without_value",
                      "detail": "N_{0}^{2} has no printed value; its formula stays not computable"}]}}
```

**status 诚实规则**（由产物推导，不靠自述）：

- `partial`：有公式或笔记被还原/挖出，但存在缺值、示意核验或未定义符号；
- `insufficient_evidence`：有文件但既无公式也无可用文本；
- `input_error`：`--input` 不存在或没有任何材料文件。

---

## 6. 异常与降级（每次都必须 exit 0 且留下合法 result.json）

| 情况 | 检测 | status |
|-|-|-|
| `--input` 不存在 / 空目录 | 无材料 | 缺口报告，`input_error` |
| 只有空文件 / 坏 XML / 碎片笔记 | 无公式无文本 | `insufficient_evidence` |
| `case.json` 缺失或坏 JSON | 解析异常 | 仍工作，`case_id` 退回目录名并记 `degradations` |
| `output_contract` 缺失或为 null | 无契约键 | 回填标准键（`case_id/status/result/claims/uncertainties`） |
| MathML 解析失败 | 解析异常 | 记 `degradation`，不猜公式 |
| 符号缺印刷值 | 核验判定 | `not_computable` + `missing_symbols`，不猜值 |
| 输出目录不可写 | OSError | 回退 stderr，退出码仍 0 |

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

---

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符、无 JSON `null`。
- [ ] `formulas.tex` 与 `result.formulas[]` 的 LaTeX 逐条一致；`symbol_table.csv` 行数与 `variables` 一致。
- [ ] 每个 `numeric_checks[]` 条目的 `status` 与 `missing_symbols` 自洽；无“猜出来的数值”。
- [ ] 每个还原对象都有 `quote` 与 `locator`；`verification.md` 可逐表对照。
- [ ] 空输入 / 坏 XML / 无公式三条路径各跑过一次，均 exit 0 且有缺口报告。

---

## 8. 文件清单与维护

```
SKILL.md                       本文件：入口、双路径、映射口径、契约、降级、自查
scripts/main.py                入口：build / show / check / selfcheck，还原编排与契约组装
scripts/mathcore.py            MathML→LaTeX、符号收集、定义/赋值/指标/推导挖掘、数值核验
references/formula_contract.md result 键语义、映射表、出处类型与核验状态口径
environment/resources.yaml     资源入口声明（命令、路径、预算、无网络、纯标准库）
README.md                      安装、用法、产物、限制、维护
SELFTEST.md                    自测记录：eval_sim rich/boundary × single/agent
GITHUB_URL.txt                 仓库地址与子目录
```

- 依赖：Python 3.9+ 标准库（`xml.etree.ElementTree`/`csv`/`json`/`re`/`hashlib`/`argparse`）；无第三方、无网络、无外部模型。
- 版本 3.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
- 每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py`（四组组合），结果记入 `SELFTEST.md`。

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
