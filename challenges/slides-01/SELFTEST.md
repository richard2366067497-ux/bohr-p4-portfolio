# SELFTEST — slides-author（slides-01 v6）

> **验证状态**：本包已在本地 Python 3.12（标准库）上**实跑** `scripts/eval_sim.py`，rich / boundary ×
> single / agent **12 次全部 PASS**（判定取自 eval_sim 报告的顶层 `status`，且逐项检查均为 PASS）。
> 正式案例以平台 `/input` 为准，本表不代表平台正式分数。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-01 \
  --case work/p4/synth_cases/slides-01/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-01 \
  --case work/p4/synth_cases/slides-01/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-01 \
  --case work/p4/synth_cases/slides-01/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-01 \
  --case work/p4/synth_cases/slides-01/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 |
|-|-|-|-|
| rich | single | **PASS** | case.json:output_contract（15 键） |
| rich | agent | **PASS** | case.json:output_contract（15 键） |
| boundary | single | **PASS** | SKILL.md default artifacts（10 键） |
| boundary | agent | **PASS** | SKILL.md default artifacts（10 键） |

逐项检查（12 次运行均为 PASS）：

- `exit_code`：单命令入口 `all` 与 agent 模式多子命令序列均 exit 0；
- `result_json`：合法 JSON；
- `contract_echo`：契约键全部出现在 `result.json.output_contract`（同时给出顶层同名键）；
- `contract_values`：无 empty / placeholder / missing-file；
- `deliverables`：`deck.md` / `deck.html` / `deck.pdf` / `preview.svg` / `outline.md` / `deck.pptx` /
  `slide_plan.json` / `content_map.json` / `compliance_checks.json` / `report.md` / `result.json` 均存在且 >40 字节；
- `case_id`：`synth-rich-slides-01` / `synth-boundary-slides-01` 原样透传；
- `placeholder_sweep`：全部产物（含二进制 `deck.pptx`）无占位符 token；
- `field:status / sources / uncertainties / change_records / limits`：均非空。

## 产物有效性

- rich：9 页，23 条证据要点**全部逐字校验通过**；`deck.pptx` 为合法 OOXML（49 个 part，`[Content_Types].xml`
  与 `ppt/presentation.xml` 齐全，9 张幻灯片 + 9 张备注页，XML 全部可解析）；`deck.pdf` 为合法 PDF-1.4（含 xref / trailer / %%EOF）。
- boundary：1 页诚实说明页，`status=insufficient_evidence`，`exceptions` 记录降级输入与未嵌入图表；
  11 个产物齐备并 exit 0。

## 边界行为

- 空 / 损坏材料（`broken.json`、`empty.md`、`notes.txt`）：不中断，写合法结果文件并诚实声明；
- 无 `draft.json`：`all` 直接由材料建 deck（agent 模式下 draft 为空对象，build 全量重建）；
- 缺 `case.json`：仍写出合法 `result.json`。

## 产物清单（运行后输出目录）

`result.json`、`deck.md`、`deck.pptx`、`deck.html`、`deck.pdf`、`preview.svg`、`outline.md`、
`slide_plan.json`、`content_map.json`、`compliance_checks.json`、`report.md`。
