# SELFTEST — sci-mindmap-builder（writing-14）

本文件记录**可复跑**的自测证据：包内探针（空输入 / 坏 JSON）与本地评测模拟器
`scripts/eval_sim.py` 的 rich/boundary × single/agent 四格。全部为真实运行输出，未手工编造。

## 0. 环境

- Python 3.12（Windows 本机路径）；纯标准库；离线。
- 包根：`work/p4/v6/writing-14`；用例根：`work/p4/synth_cases/writing-14/{rich,boundary}`。

## 1. 包内探针（`main.py run` 的 C8/C9，来自 `self_check.json`）

`self_check.json` 在每次 `run/build` 时自动跑两个子进程探针，并汇总 C1–C10：

| 检查 | 期望 | rich 实测 | boundary 实测 |
|-|-|-|-|
| C1 契约完整性 | 契约键逐键回填 | pass（5 个契约键已映射） | pass（5 个契约键已映射） |
| C2 节点覆盖 | 节点 12–35 且有主分支 | pass（节点 16，主分支 5） | pass（无可判材料：not applicable） |
| C3 层级结构 | 深度 ≤ 4，父子链无环 | pass（深度 2，错误 0） | pass（not applicable） |
| C4 证据逐字 | 每条 quote 逐字命中 | pass（16/16 条证据命中） | pass（not applicable） |
| C5 关系语义 | 只允许 9 类方向语义 | pass（1 条关系，丢弃 0 条） | pass（0 条关系，丢弃 0 条） |
| C6 数字落证 | 节点数字可在 quote 中找到 | pass（12 个数字台账项） | pass（0 个台账项） |
| C7 渲染产物 | SVG 有 node id，PNG 存在 | pass（SVG 节点 16 个） | pass（not applicable） |
| C8 空输入兜底 | exit 0 + 合法 result.json | pass（exit=0，result 合法=True，status=insufficient_evidence，11 个文件） | 同左 |
| C9 坏 JSON 兜底 | exit 0 + 合法 result.json | pass（exit=0，result 合法=True，status=partial，11 个文件） | 同左 |
| C10 契约与边界 | 契约冻结，缺口逐条写明 | pass（契约 5 项，未覆盖单元 1 个） | pass（契约 5 项，未覆盖单元 0 个） |

boundary 用例的降级记录（`result.json.degradations`，真实输出）：

```
broken.json: invalid-json (material registered, text unavailable)
notes.txt:¶1 marker-only unit skipped
work draft missing or empty: deterministic extraction used
```

## 2. 本地评测模拟器四格（`scripts/eval_sim.py`）

复跑命令（在仓库根执行，`$PY` 为本机 python）：

```bash
for c in rich boundary; do for m in single agent; do
  $PY scripts/eval_sim.py --pkg work/p4/v6/writing-14 \
      --case work/p4/synth_cases/writing-14/$c --mode $m \
      --out work/p4/_t14/eval/$c-$m --json-out work/p4/_t14/eval/$c-$m.json
done; done
```

结果（四格全 PASS，无 warning、无 suggestion）：

| 用例 | 模式 | eval_sim | result.status | 输出文件 | 契约键 | self_check |
|-|-|-|-|-|-|-|
| rich | single | **PASS** | `ok` | 11 | 5/5 回填（来源 `case.json:output_contract`，echo 必需） | pass |
| rich | agent | **PASS** | `ok` | 11 | 5/5 回填 | pass |
| boundary | single | **PASS** | `insufficient_evidence` | 11 | 5/5 回填（来源 `SKILL.md (json sample)`） | pass |
| boundary | agent | **PASS** | `insufficient_evidence` | 11 | 5/5 回填 | pass |

四格共同通过的关键检查：`exit_code`、`result_json`、`contract_echo`（5 个键全部回填）、
`deliverables`（10 个期望产物齐全：`mindmap.svg`/`mindmap.json`/`content_map.json`/`mindmap.png`/
`structure.md`/`golden_standard.json`/`diff_report.md`/`version_history.md`/`self_check.json`/`result.json`）、
`case_id`（`synth-rich-writing-14` / `synth-boundary-writing-14`）、`placeholder_sweep`（11 个文件无占位符）、
`field:status|sources|uncertainties|change_records|limits`。

agent 模式实际执行链（来自 `eval_sim` 的 `run[]`）：`run → init → (写入 /app/work/draft.json，空对象)
→ check → build`，五步全部 exit 0；`draft.json` 为空对象时按设计读取 `init` 落下的
`/app/work/mindmap.json` 工作稿成稿（本次工作稿由确定性抽取生成，`model_source=work/mindmap.json`）。

## 3. 确定性与体积

- 连续两次 `run --no-probe` 的产物对比：11 个顶层文件中 9 个 sha1 完全一致；
  `result.json`（`runtime.seconds`）与 `run.log`（耗时列）随运行时间变化，已在 README/limits 写明。
- 包体积：8 个源文件；最大单文件 `scripts/verify.py` 26.6KB（< 30KB）；整包 ≈ 97KB（< 150KB）。
  脚本内设置 `sys.dont_write_bytecode`，运行不会在包内落下 `__pycache__`。

## 4. 已知边界

- 节点匹配按 NFKC 归一 + 严格包含判定；人工认可的等价改写可能被判未命中，逐条证据会列出命中情况。
- 只有标记行的文件按 `marker-only unit skipped` 记降级，不产生节点。
- 图片材料只登记存在性、不做 OCR；PDF 优先 `pdftotext` 取文本层，缺失时用内置 flate 解码，扫描件仍不可读（记降级）。
- `mindmap.png` 是标准库绘制的几何缩略（标签文字在 SVG/JSON 中）；带字预览需 `rsvg-convert`/`inkscape`。
