# formula-verification v3.0.0

忠实适配自 P3 `reading-08` 参考包（参考分 65.67）：保留其**扁平入口**
（`scripts/main.py --input /input --output /app/output`）、**产物名**
（`result.json`、`formulas.tex`、`symbol_table.csv`、`verification.md`）与**result 字段**
（`formulas[]`、`variables[]`、`derivations[]`、`numeric_checks[]`、`indicator_checks[]`、
`coverage`、`missing_objects[]`、`definition_source` 的三类取值、数值状态的
computed/example_only/not_computable），实现与文本全部重写。

## 安装

把本目录整体放到 `/skills/weekly-skill` 即可。入口脚本用 `__file__` 自定位，
不依赖当前目录，也不需要安装第三方包。

## 用法

```bash
# 单命令全流程（等价于 main.py build）
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work

# agent-first：先确定性全流程，再让 Agent 补备注，最后过闸门
python3 -B /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work

# 取证：打印已还原公式与 locator
python3 -B /skills/weekly-skill/scripts/main.py show --input /input --output /app/output --work /app/work
```

## 产物

| 产物 | 说明 |
|-|-|
| `result.json` | 契约逐键回填 + `formulas/variables/derivations/numeric_checks/indicator_checks`；`case_id` 透传；无 JSON null |
| `formulas.tex` | 已还原公式（`equation` 环境 + 注释行） |
| `symbol_table.csv` | 符号台账（含出处类型与印刷值） |
| `verification.md` | 人读核验报告（公式/台账/核验/推导/指标/覆盖率） |
| `run.log` | 运行摘要 |
| `work/index.json` | 公式/符号/推导/指标/覆盖快照 |

## 设计要点

- **只用标准库**：`xml.etree.ElementTree`/`csv`/`json`/`re`/`hashlib`/`argparse`。
- **逐节点映射**：`mi/mn/mo/mrow/msup/msub/msubsup/mfrac/msqrt/mroot/mfenced` 各有明确规则，
  希腊字母转 LaTeX 命令，未知标签只拼接子节点。
- **出处分层**：`paper_defined` / `context_inferred` / `common_knowledge` 三选一，写在台账里。
- **不猜值**：缺符号判 `not_computable` 并列 `missing_symbols`；无值公式只用示意值探路并标
  `example_only`。
- **逐字取证**：定义句、赋值句、指标句、推导句都带 `quote` + `locator`。
- **诚实降级**：空目录 → `input_error`；有文件但无公式无文本 → `insufficient_evidence`；
  缺值或示意核验 → `partial`。三条路径都写合法 `result.json` 并 exit 0。

## 限制

- 不做符号代数：只映射还原、代入印刷值，不化简、不约分、不推导新公式。
- 不做单位换算：印的是 `1/h` 就写 `1/h`，印的是 `%` 就写 `%`。
- 复杂 MathML（`mtable` 嵌套、自定义语义）走通用拼接，可能出现不理想的排版。
- 只读取材料本身，不联网、不调用外部模型。

## 维护

- 契约键名冻结；新增键走次版本，阈值与文案走修订号。
- 改动后至少跑：`main.py selfcheck` + `scripts/eval_sim.py` 的 rich/boundary × single/agent
  四组组合，并把结果记入 `SELFTEST.md`。
- 资源与命令声明见 `environment/resources.yaml`；口径细节见 `references/formula_contract.md`。
