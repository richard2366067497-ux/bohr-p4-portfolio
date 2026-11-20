# SELFTEST — 自测记录（writing-05 v9）

包：`work/p4/v9/writing-05` · 引擎 `writing-05-evidence/1.1.0` · 纯标准库、离线、确定性。
评测模拟器：`scripts/eval_sim.py`。
解释器：`D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe`（Python 3.12.14）。

## 一、eval_sim（rich/boundary × single/agent，本地门禁）

```
python scripts/eval_sim.py --pkg work/p4/v9/writing-05 \
    --case work/p4/synth_cases/writing-05/<rich|boundary> --mode <single|agent>
```

| 案例 | 模式 | 结果 | 契约来源 |
|---|---|---|---|
| rich | single | **PASS** | `case.json:output_contract`（5 键） |
| rich | agent | **PASS** | `case.json:output_contract`（5 键） |
| boundary | single | **PASS** | `case.json(SKILL 默认键)`（5 键） |
| boundary | agent | **PASS** | `case.json(SKILL 默认键)`（5 键） |

四项全过，无 `FAIL`、无 `WARN`、无 `suggestions`。逐项检查均 PASS：`exit_code`、`result_json`、
`contract_echo`、`deliverables`、`case_id`、`placeholder_sweep`、`field:status`、`field:sources`、
`field:uncertainties`、`field:change_records`、`field:limits`。

- rich：稿件 `manuscript.md` + 来源 `refs.md` → 引擎产出 10 个文件；契约 5 键真实回填；exit 0，无占位符。
- boundary：`case.json.output_contract=null`、`empty.md`(0B)、`broken.json`(坏 JSON)、`notes.txt`(标记行)
  → 契约回落到 `references/method.md` 的默认 5 键；引擎 exit 0，写出合法 `result.json`
  （`status=failed`，`claims=0/rows=0`，`limits`/`uncertainties` 说明"无可读材料"），10 个交付物齐全。

agent 模式下 `WRITE draft.json` 步骤为可选项（本包自动读取 `$WORK/draft.json`）；无 draft 时与 single 等价，仍 exit 0。

## 二、样例端到端复跑（`examples/`，真实处理）

```
python work/p4/v9/writing-05/scripts/main.py \
    --input work/p4/v9/writing-05/examples --output <out> --work <work>
```

实测（exit 0，`status=success`）：产物 **10** 个（含 `diff_report.md`）；`metrics = {claims:3, evidence_rows:3,
rows_with_source:3, references:4, downgrades:1, verified_quote_rate:1.0, claim_coverage:1.0,
pending_human_count:1, overclaim_flags:1}`；契约 5/5；占位符 0。过度推断 "causes …" 被降级为
相关性表述并记入 `change_log`。

## 三、确定性与异常

- 纯标准库、无网络、无时钟读取；`result.json.runtime = {network: disabled}`。同一输入重复运行交付物字节稳定。
- 输入目录不存在 / 无可读材料：exit 0，`status=failed`，仍写合法 `result.json`（`_fail` 兜底）。
- 坏 JSON / 空文件 / 二进制：记入 `degradations`，不阻断。

## 四、包清单

```
SKILL.md
scripts/main.py
scripts/kit.py
references/method.md
environment/resources.yaml
examples/case.json
examples/materials/manuscript.md
examples/materials/refs.md
README.md
SELFTEST.md
GITHUB_URL.txt
GAIN_EVIDENCE.md
```

12 个文件，总量 < 150KB，单文件 < 30KB，纯标准库。
