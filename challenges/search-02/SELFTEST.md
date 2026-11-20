# SELFTEST — rq-driven-retrieval（search-02 v6）

本文件给出用仓库根目录 `scripts/eval_sim.py` 对 **rich / boundary** 两个合成用例 × **single / agent**
两种模式的复现命令，以及按 `eval_sim.py` 源码逐项推演的**预期**结果。

> **验证状态（诚实声明）**：本包创作所在的 Windows 主机没有可用的 Python 解释器（仅有 Windows Store
> 占位别名，且无 WSL 发行版、无 Node），因此**未能在本机实际执行** `eval_sim.py`。下表的“预期”
> 是按 `eval_sim.py` 的入口抽取、契约解析、审计规则逐条静态推演得到的；请在 Linux `python3.10` 上
> 按下列命令实跑确认（预期全部 PASS）。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/search-02 \
  --case work/p4/synth_cases/search-02/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/search-02 \
  --case work/p4/synth_cases/search-02/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/search-02 \
  --case work/p4/synth_cases/search-02/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/search-02 \
  --case work/p4/synth_cases/search-02/boundary --mode agent
```

## 预期结果（静态推演）

| 用例 | 模式 | 预期状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 16（contract_overrides…reason） | 8 |
| rich | agent | PASS | case.json:output_contract | 同上 16 键 | 8 |
| boundary | single | PASS | SKILL.md (json sample) | 23（含 subquestions/candidates/evidence/coverage/search_log/stop_decision/report） | 8 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 23 键 | 8 |

逐项检查（预期均 PASS）：

- `exit_code`：`scripts/main.py all`（agent 模式按 `all → init → check → build → selfcheck` 顺序）均 exit 0；无 Python 异常外泄。
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键。
- `contract_echo`：`result.json.output_contract` 覆盖 rich 的 16 键 / boundary 的 23 键（回填取二者并集）。
- `contract_values`：无 empty / placeholder / missing-file；`text/quote/reason` 等标量经去路径化处理，
  `report` 指向真实非空 `report.md`，结构化键为非空 list/dict。
- `deliverables`：`report.md`、`subquestions.json`、`evidence_ledger.json` 等均在输出目录且 >40 字节。
- `case_id`：`synth-rich-search-02` / `synth-boundary-search-02` 原样透传。
- `placeholder_sweep`：输出产物无 `[待写]`/`null`/`pending`/`TODO`/`N/A` 等占位符。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为

- boundary（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`；候选给带说明的诚实空结构；
  `limits` 说明检索范围与降级原因；仍产出全部 8 个产物并 exit 0。
- 无 `draft.json`：`all` 用规则化候选，仍产出全部产物，缺口写入 `degradations`。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单（每次运行写入 --output）

`result.json`、`subquestions.json`、`candidates.jsonl`、`evidence_ledger.json`、`coverage.json`、
`stop_decision.json`、`search_log.json`、`report.md`（共 8 个）。

> 以上为按源码推演的预期结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
