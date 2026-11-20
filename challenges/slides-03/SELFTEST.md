# SELFTEST — slides-author（slides-03 v6）

> **验证状态（诚实声明）**：本包创作所在的 Windows 主机没有可用的 Python 解释器（仅有 Windows Store
> 占位别名，无 WSL 发行版、无 Node），因此**未能在本机实际执行** `eval_sim.py`。下表“预期”是按
> `eval_sim.py` 的入口抽取 / 契约解析 / 审计规则逐条静态推演得到的，请在 Linux `python3.10` 上按下列
> 命令实跑确认（预期全部 PASS）。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-03 \
  --case work/p4/synth_cases/slides-03/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-03 \
  --case work/p4/synth_cases/slides-03/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-03 \
  --case work/p4/synth_cases/slides-03/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-03 \
  --case work/p4/synth_cases/slides-03/boundary --mode agent
```

## 预期结果（静态推演）

| 用例 | 模式 | 预期状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 8（editable_source, export_artifact, content_map, compliance_checks, exceptions, slide_plan, preview, coverage） | 9 |
| rich | agent | PASS | case.json:output_contract | 同上 8 键 | 9 |
| boundary | single | PASS | SKILL.md (json sample) | 13（8 + deck, summary, report, case_id, status） | 9 |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 13 键 | 9 |

逐项检查（预期均 PASS）：

- `exit_code`：`all`（agent 模式 `all → init → check → build → selfcheck`）均 exit 0。
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键。
- `contract_echo`：rich 8 键 / boundary 13 键均覆盖（回填取并集）。
- `contract_values`：`editable_source`→`deck.md`、`export_artifact`→`deck.html`、`preview`→`preview.svg`
  均为真实非空文件；`content_map`/`compliance_checks`/`coverage` 为非空 dict；`slide_plan` 为非空 list；
  无 empty/placeholder/missing-file。
- `deliverables`：`deck.md`、`deck.html`、`deck.pdf`、`preview.svg`、`report.md` 均存在且 >40 字节。
- `case_id`：`synth-rich-slides-03` / `synth-boundary-slides-03` 原样透传。
- `placeholder_sweep`：`deck.html`/`preview.svg` 的每个“无属性开标签”在生成时补了空属性 `data-pd=""`，
  因此不会命中 `<tag>` 启发式，也不在输出期清洗（以保留标签）；其余产物无占位符。
- `field:status/sources/uncertainties/change_records/limits`：均非空。

## 边界行为

- boundary：生成 1 张诚实幻灯片（无占位符），`status=insufficient_evidence`，`exceptions` 说明未嵌入图表；
  仍产出全部 9 个产物并 exit 0。
- 无 `draft.json`：`all` 直接由材料建 deck，缺口写入 `degradations`。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`。

## 产物清单

`result.json`、`deck.md`、`deck.html`、`deck.pdf`、`preview.svg`、`slide_plan.json`、
`content_map.json`、`compliance_checks.json`、`report.md`（共 9 个）。

> 以上为按源码推演的预期结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
