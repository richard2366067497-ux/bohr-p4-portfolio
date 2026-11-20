# SELFTEST — academic-writing-benchmark-builder（writing-13）

本文件记录**可复跑**的自测证据：包内探针（空输入 / 坏 JSON）与本地评测模拟器
`scripts/eval_sim.py` 的 rich/boundary × single/agent 四格。全部为真实运行输出，未手工编造。

## 0. 环境

- Python 3.12.14（Windows 本机路径，见下）；纯标准库；离线。
- 包根：`work/p4/v6/writing-13`；用例根：`work/p4/synth_cases/writing-13/{rich,boundary}`。

## 1. 包内探针（`main.py run` 的 C7/C8，来自 `self_check.json`）

`self_check.json` 在每次 `run/build` 时自动跑两个子进程探针，并汇总 C1–C10：

| 检查 | 期望 | rich 实测 |
|-|-|-|
| C1 契约完整性 | 契约键逐键回填 | pass（5 个契约键已映射） |
| C2 题面字段 | 每题六字段齐全 | pass（3 题，字段齐全=True） |
| C3 锚点阶梯 | 每题 ≥5 条锚点 + 0/1/2 档 | pass（锚点 15 条） |
| C4 双评与一致性 | 每题双评 + kappa | pass（双评 3 题，kappa=1.0） |
| C5 证据可追溯 | 要点带 locator 与逐字引用 | pass（12/12 要点已核验） |
| C6 校准对照 | 正控通过、负控拒绝 | pass（3 组对照，通过=True） |
| C7 空输入兜底 | exit 0 + 合法 result.json | pass（exit=0，result 合法=True，status=insufficient_evidence，13 个文件） |
| C8 坏 JSON 兜底 | exit 0 + 合法 result.json | pass（exit=0，result 合法=True，status=ok，14 个文件） |
| C9 退出码 | 全部入口为 0 | pass |
| C10 降级记录 | 降级逐条写明对象与原因 | pass（rich 无降级项） |

boundary 用例的降级记录（`result.json.degradations`，真实输出）：

```
broken.json: invalid-json (material registered, text unavailable)
notes.txt: marker-only file skipped (template, not material)
```

## 2. 本地评测模拟器四格（`scripts/eval_sim.py`）

复跑命令（在仓库根执行，`$PY` 为本机 python）：

```bash
for c in rich boundary; do for m in single agent; do
  $PY scripts/eval_sim.py --pkg work/p4/v6/writing-13 \
      --case work/p4/synth_cases/writing-13/$c --mode $m \
      --out work/p4/_t13/eval/$c-$m --json-out work/p4/_t13/eval/$c-$m.json
done; done
```

结果（四格全 PASS，无 warning、无 suggestion）：

| 用例 | 模式 | eval_sim | result.status | 输出文件 | kappa | 契约键 | self_check |
|-|-|-|-|-|-|-|-|
| rich | single | **PASS** | `ok` | 16 | 1.0 | 5/5 回填 | pass |
| rich | agent | **PASS** | `ok` | 16 | 1.0 | 5/5 回填 | pass |
| boundary | single | **PASS** | `insufficient_evidence` | 13 | 1.0 | 5/5 回填 | pass |
| boundary | agent | **PASS** | `insufficient_evidence` | 13 | 1.0 | 5/5 回填 | pass |

四格共同通过的关键检查：`exit_code`、`result_json`、`contract_echo`（5 个键全部回填）、
`deliverables`（11 个期望产物齐全）、`case_id`（`synth-rich-writing-13` / `synth-boundary-writing-13`）、
`placeholder_sweep`（16/13 个文件无占位符）、`field:status|sources|uncertainties|change_records|limits`。

agent 模式实际执行链（来自 `eval_sim` 的 `run[]`）：`run → init → (写入 /app/work/draft.json，空例)
→ check → build`，四步全部 exit 0；`draft.json` 为空对象时按设计回退到抽取式参考答案（`answer_source=auto_extract`）。

## 3. 确定性与体积

- 连续两次 `run` 的产物对比：14 个顶层文件中 12 个 sha1 完全一致，仅 `run.log` 与
  `self_check.json` 因时间戳变化（已在 `reproducibility.md` 写明）。
- 包体积：8 个文件，最大单文件 `scripts/verify.py` ≈ 28KB（< 30KB），整包 < 100KB（< 150KB）。

## 4. 已知边界

- 改写类答案按字符串/词袋口径判定，人工认可的等价改写可能被低估；逐题证据会列出命中项供人工复核。
- 材料仅含模板标记时按 `marker-only file skipped` 记降级，不造题。
- PDF 材料优先用 `pdftotext` 取文本层；无该工具时用内置 flate 解码，扫描件仍不可读（记降级）。
