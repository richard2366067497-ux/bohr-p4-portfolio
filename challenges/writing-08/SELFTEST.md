# SELFTEST — writing-08 v10（可复现自测）

全部离线、纯标准库（`python3 >= 3.8`）。基线 v6；v10 新增 `references/expert_playbook.md`、README、
GAIN_EVIDENCE、`examples/`，并把超出 30KB 的脚本切分为 `engine.py`+`engine_tail.py`、
`flow.py`+`flow_tail.py`（行为不变）。

## 1 eval_sim 四格（rich / boundary × single / agent）

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/writing-08 \
    --case work/p4/synth_cases/writing-08/<rich|boundary> --mode <single|agent>
```

| case | mode | status | 要点 |
|---|---|---|---|
| rich | single | **PASS** | 契约取 `case.json:output_contract`；contract_echo 5/5；8 产物；exit 0 |
| rich | agent | **PASS** | init→draft→check→build→selfcheck；同套产物与契约 |
| boundary | single | **PASS** | `output_contract: null` → 回退包内默认五键；顶层与嵌套同时回填；exit 0 |
| boundary | agent | **PASS** | 同上；`insufficient_evidence` 且诚实 limits / uncertainties |

四格 `failures=0 / warnings=0`：无占位符、`case_id` 透传、产物齐备非空、信封字段
`status / sources / uncertainties / change_records / limits` 均非空。

## 2 单命令实跑（无 draft）

```bash
python3 scripts/main.py run --input work/p4/synth_cases/writing-08/rich \
    --output <OUT> --work <WORK>
```

结果：**exit 0**；`[build] status=partial reason=降级完成：工作稿缺失/为空，已自动抽取；六要素覆盖
4/6`；`artifacts=7`（`manuscript.md`、`fact_ledger.csv`、`parameter_ledger.csv`、`evidence_matrix.csv`、
`gaps.md`、`conflicts.md`、`coverage.json`）+ `result.json`；`[selfcheck] PASS 产物齐备、JSON 合法、
契约字段齐全（顶层 + 嵌套）`。`case_id=synth-rich-writing-08`，契约 5 键双层回填。

## 3 行为检查

- **真实抽取**：rich 抽出 7 个参数（含 locator，如 `initial concentration = 12.5 mg/L @
  materials/paper.md#L5`）、8 个有序步骤与设置/限制/复现条目，均带 `[S#]` + `文件#行号`。
- **六要素诚实**：rich 覆盖 4/6（步骤、设置、参数、复现与限制）；`datasets`/`baselines` 材料未命名 →
  `gap`，写 `gaps.md` 并以 `[needs input: …]` 呈现；boundary = 0/6 全登记缺口。
- **冲突不静默**：跨来源取值不同 → `conflicts.md` 并列保留 + `parameter_ledger.csv` 标
  `unresolved_detected(...)`。
- **语言自适应**：`case.json.language` 优先，否则按 `task.md`+材料 CJK 占比；zh/en 共用同一渲染逻辑。

## 4 退化输入

- 空/缺输入 → `input_error`（材料在但无要素可抽为 `insufficient_evidence`），仍写合法 `result.json`，
  `limits`/`uncertainties`/`sources` 非空，**exit 0**。
- Agent 路径写空 `draft.json`（`{}`）→ 视同缺失，走确定性抽取，不渲染空壳。
- 不可读/二进制/超限（>400KB）→ `degradations` + 缺口，继续运行；输出目录不可写 → 回退 `./output`；
  异常兜底写含全部契约键的最小 `result.json`，exit 0。

## 5 清单

共 14 个文件：`scripts/` 5 个（engine / engine_tail / flow / flow_tail / main）+ `SKILL.md`、`README.md`、
`GAIN_EVIDENCE.md`、`SELFTEST.md`、`GITHUB_URL.txt`、`references/expert_playbook.md`、
`references/guide.md`、`environment/resources.yaml`、`examples/case.json`；无 `__pycache__`，单文件 ≤30KB。

共 14 个文件：`scripts/` 5 个（engine / engine_tail / flow / flow_tail / main）+ `SKILL.md`、`README.md`、
`GAIN_EVIDENCE.md`、`SELFTEST.md`、`GITHUB_URL.txt`、`references/expert_playbook.md`、
`references/guide.md`、`environment/resources.yaml`、`examples/case.json`；无 `__pycache__`，单文件 ≤30KB。
