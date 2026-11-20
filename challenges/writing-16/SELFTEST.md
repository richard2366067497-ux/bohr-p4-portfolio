# SELFTEST — 自查记录（可复算）

本文件记录本包在本机对 `scripts/eval_sim.py` 模拟器的四组合复检结果，以及空/坏输入的鲁棒性验证。
**所有结论均由命令复算得到，非文字自述。**

## 1. 环境

- 解释器：Python 3.12（仅标准库；`PYTHONDONTWRITEBYTECODE=1`）
- 模拟器：`scripts/eval_sim.py`（把本包装到 `/skills/weekly-skill`，把案例放到 `/input`，跑文档化的入口命令后审计）
- 案例：`work/p4/synth_cases/writing-16/rich`（含材料 + `output_contract`）与 `.../boundary`（坏/空材料，`output_contract: null`）

## 2. 复算命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-16 --case .../rich     --mode single  --json-out rich_single.json
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-16 --case .../rich     --mode agent   --json-out rich_agent.json
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-16 --case .../boundary --mode single  --json-out boundary_single.json
python3 scripts/eval_sim.py --pkg work/p4/v6/writing-16 --case .../boundary --mode agent   --json-out boundary_agent.json
```

## 3. 结果（四组合全 PASS）

| 案例 / 模式 | status | 入口命令 | 契约键 | FAIL | WARN |
|---|---|---|---|---|---|
| rich / single | **PASS** | `python3 scripts/main.py all` | dropped, retained, errors | 0 | 0 |
| rich / agent | **PASS** | `all` →（draft）→ check → build → selfcheck | dropped, retained, errors | 0 | 0 |
| boundary / single | **PASS** | `python3 scripts/main.py all` | dropped, retained, errors | 0 | 0 |
| boundary / agent | **PASS** | `all` →（draft）→ check → build → selfcheck | dropped, retained, errors | 0 | 0 |

四组合共同满足：`exit_code` PASS、`result_json` PASS、`contract_echo` PASS（`result.json.output_contract` 三键齐全且同名）、
`contract_values` PASS（键值为真实非空内容）、`deliverables` PASS（5 个主产物均 ≥40 字节）、`case_id` PASS、`placeholder_sweep` PASS。

## 4. 产物与契约值抽样（rich / single）

| 产物 | 字节 |
|---|---|
| `deliverable.md` | 9064 |
| `retained_facts.json` | 5239 |
| `diff_map.md` | 3577 |
| `glossary.csv` | 126 |
| `result.json` | 26058 |

- `status = "partial"`（单命令无 Agent 工作稿 → 逐字摘录兜底，稿首已标注"未完成受众改写"）。
- `case_id = "synth-rich-writing-16"`（原样透传）。
- `output_contract.retained` 为**真实台账**（非占位）：形如
  `{"id": "R1", "kind": "number", "value": "100", "locator": "M1:P2", "quote": "题面 100 分分五维。", "where": "F1", "treatment": "kept", "note": "兜底抽取"}`。
- `output_contract.dropped` = `["0 项冗余被删除：…"]`；`output_contract.errors` 列出兜底原因（如 `draft.json 不存在`）。

## 5. 空 / 坏输入的鲁棒性（退出码恒 0）

| 输入 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 坏 `case.json`（非法 JSON）+ 空材料 | `python3 scripts/main.py all --input … --output … --work …` | **0** | `status=insufficient_evidence`，`case_id=UNKNOWN-CASE`，`output_contract` 含全部契约键，5 个产物齐全 |
| 空输入目录（无 `case.json`） | 同上 | **0** | `status=insufficient_evidence`，产物齐全 |

`python3 scripts/main.py --help` 退出码 **0**。

## 6. 结论

- 单命令入口 `python3 scripts/main.py all` 在 Linux（纯标准库）下跑完整条流水线并**恒退出 0**；
- `result.json` 的 `output_contract` 键（顶层 + 嵌套回显）按原样回填，`retained` 为真实台账，`case_id` 原样透传；
- rich/boundary × single/agent 四组合经 `scripts/eval_sim.py` 复检 **全部 PASS**（0 FAIL / 0 WARN）。

*本自查记录为构造验证，非平台正式评测结果。*
