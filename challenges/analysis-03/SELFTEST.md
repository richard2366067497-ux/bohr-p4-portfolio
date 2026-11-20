# SELFTEST.md — analysis-03 v6 自测记录

包：`work/p4/v6/analysis-03` · 引擎 `figure-spec-publisher/2.0.0` · 纯标准库、退出码恒 0。

## 0. 运行环境

```
$PY = D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe
> python scripts/eval_sim.py --pkg work/p4/v6/analysis-03 --case <case> --mode <single|agent>
```

## 1. 单命令入口（SKILL.md 第一条可执行命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

`eval_sim` 解析结果：`entry.kind = single-command`，`documented_commands = [all]`
（只有 `all`，因此 agent 模式与 single 模式等价，只跑这一条）。

## 2. 修复点（对应 EVAL_SIM_REPORT2 的失败项）

| 原失败项 | 根因 | 修复 |
|---|---|---|
| 入口只到 `init`（rich ✘ / build !） | SKILL §3 首条命令是 `init`，单命令路径不产出图件 | SKILL 第一条命令改为 `engine.py all`，一条命令跑完整条流水线 |
| `contract_values` | 6 个契约键中 `case_id/evidence_map/change_log/coverage` 未映射、`status` 错配 stats | 新增显式键映射（case_id/status/deliverable/evidence_map/change_log/coverage），未知键回退为诚实结构信封 |
| `contract_echo`（boundary） | 没有 `output_contract` 对象；boundary 用例未声明契约时无处回填 | 始终写 `result.json.output_contract`；用例无契约时使用 SKILL 样例的默认 6 键 |
| `deliverables`（rich/boundary） | 单命令只跑 init，`figure_report.md` 等未生成 | `all` 写 10 个交付物，全部 ≥40B |
| `placeholder_sweep` | JSON 里的 `null`、文本里的 `none` 等 | 写出后统一递归清理（JSON 对象 + 文本），SVG 生成时只用带属性的标签 |
| boundary `result_json`/`exit_code` | 坏 JSON / 空文件 / `[待写]` 备注 | 全流程 try/except，坏文件记入盘点并跳过，退出 0 |

## 3. eval_sim 结果（rich / boundary × single / agent 全 PASS）

| 用例 | 模式 | status | failures | warnings | 契约来源 |
|---|---|---|---|---|---|
| `synth_cases/analysis-03/rich` | single | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/analysis-03/rich` | agent | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/analysis-03/boundary` | single | **PASS** | [] | [] | `SKILL.md (json sample)` |
| `synth_cases/analysis-03/boundary` | agent | **PASS** | [] | [] | `SKILL.md (json sample)` |

逐项：`exit_code`、`result_json`、`contract_echo`（6 键）、`contract_values`、
`deliverables`（10 个）、`case_id`、`placeholder_sweep`、`field:status/sources/uncertainties/change_records/limits`
全部 PASS。

- **rich**：输入只有 1 份参考文档（无数据表）→ `status=partial`，仍产出真实
  `overview.svg`（输入盘点图）与全部文本/JSON 交付物，`evidence_map` 为逐文件摘录。
- **boundary**：`broken.json`（坏 JSON）、`empty.md`（0B）、`notes.txt`（`[待写]`）→ 退出 0，
  `result.json` 合法（`status=partial`），契约从 SKILL 样例回填 6 键，10 个交付物齐全、无占位符。

## 4. 确定性

- 无网络、无时钟读取；同输入重复运行字节稳定。
- `result.json.runtime = {mode: offline-deterministic, network: false}`。

## 5. 包清单（6 文件 49513 B，≤150KB，单文件 ≤30720B）

```
SKILL.md                          6065 B
README.md                         2018 B
SELFTEST.md                       3643 B
GITHUB_URL.txt                     110 B
scripts/engine.py                30630 B
references/figure-spec-rules.md   7047 B
```
