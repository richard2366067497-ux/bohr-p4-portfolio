# SELFTEST — citation-trace（search-04 v6）

> **验证状态（诚实声明）**：本包创作所在的 Windows 主机没有可用的 Python 解释器（仅有 Windows Store
> 占位别名，无 WSL 发行版、无 Node），因此**未能在本机实际执行** `eval_sim.py`。下表“预期”是按
> `eval_sim.py` 的入口抽取 / 契约解析 / 审计规则逐条静态推演得到的，请在 Linux `python3.10` 上按下列
> 命令实跑确认（预期全部 PASS）。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/search-04 \
  --case work/p4/synth_cases/search-04/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/search-04 \
  --case work/p4/synth_cases/search-04/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/search-04 \
  --case work/p4/synth_cases/search-04/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/search-04 \
  --case work/p4/synth_cases/search-04/boundary --mode agent
```

## 预期结果（静态推演）

| 用例 | 模式 | 预期状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 2（show, build） | 6 |
| rich | agent | PASS | case.json:output_contract | 同上 2 键 | 6 |
| boundary | single | PASS | SKILL.md (json sample) | 10（show,build,citations,edges,seed,paths,gaps,network,summary,report） | 6 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 10 键 | 6 |

逐项检查（预期均 PASS）：

- `exit_code`：`all`（agent 模式 `all → init → check → build → selfcheck`）均 exit 0。
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键。
- `contract_echo`：rich 2 键 / boundary 10 键均被覆盖（回填取并集）。
- `contract_values`：`show/build` 为结构化 dict；`edges/paths/gaps` 为空时给带 `status/note` 的非空 list；
  `network` 为非空 dict；`report` 指向真实非空 `report.md`；无 empty/placeholder/missing-file。
- `deliverables`：`report.md`、`citation_network.json`、`traced_paths.json` 等存在且 >40 字节。
- `case_id`：`synth-rich-search-04` / `synth-boundary-search-04` 原样透传。
- `placeholder_sweep`：无占位符。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为

- boundary（空文件 + 坏 JSON + 10 字节文本）：`status=insufficient_evidence`，网络/路径/缺口给诚实非空结构。
- 无 `draft.json`：`all` 自动建网，仍产出全部 6 个产物，缺口写入 `degradations`。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单

`result.json`、`citation_network.json`、`edges.jsonl`、`traced_paths.json`、`gaps.json`、`report.md`（共 6 个）。

> 以上为按源码推演的预期结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
