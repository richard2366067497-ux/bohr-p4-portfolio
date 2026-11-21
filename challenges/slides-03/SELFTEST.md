# SELFTEST — slides-author（slides-03 v10）

> **验证状态**：本包已在本地 Python 3.12（仅标准库）上**实跑** `scripts/eval_sim.py`，
> rich / boundary × single / agent **4 个用例全部 PASS**（判定取自 eval_sim 报告的顶层 `status`，
> 且逐项检查均为 PASS）。正式案例以平台 `/input` 为准，本表不代表平台正式分数。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-03 \
  --case work/p4/synth_cases/slides-03/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-03 \
  --case work/p4/synth_cases/slides-03/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-03 \
  --case work/p4/synth_cases/slides-03/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v10/slides-03 \
  --case work/p4/synth_cases/slides-03/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键数 |
|-|-|-|-|-|
| rich | single | **PASS** | case.json:output_contract | 8 |
| rich | agent | **PASS** | case.json:output_contract | 8 |
| boundary | single | **PASS** | SKILL.md (result schema table) | 12 |
| boundary | agent | **PASS** | SKILL.md (result schema table) | 12 |

逐项检查（4 次运行均为 PASS）：

- `exit_code`：单命令入口 `all` 与 agent 模式多子命令序列均 `exit 0`；
- `result_json`：合法 JSON，含 `output_contract` 与顶层同名键；
- `contract_echo` / `contract_values`：契约键全部回填，无 empty / placeholder / missing-file；
- `deliverables`：全部产物存在且 > 40 字节；
- `case_id`：原样透传（`synth-rich-slides-03` / `synth-boundary-slides-03`）；
- `placeholder_sweep`：全部产物（含二进制 `deck.pptx`）无占位符 token；
- `field:status / sources / uncertainties / change_records / limits`：均非空。

## 产物有效性（本次实测）

- rich：6 页；`deck.pptx` 为合法 OOXML（37 个 part、6 张幻灯片 + 6 张备注页）；`deck.pdf` 为合法 PDF-1.4。
- boundary：2 页（材料里只有极少可读文本），逐条 `degradations` 记录，仍产出全部 10 个产物，并 exit 0。

## 产物清单（运行后输出目录，共 10 个）

`result.json`、`deck.md`、`deck.pptx`、`deck.html`、`deck.pdf`、`preview.svg`、`slide_plan.json`、`content_map.json`、`compliance_checks.json`、`report.md`

> 以上为本地实跑结果；正式案例以平台 `/input` 为准。
