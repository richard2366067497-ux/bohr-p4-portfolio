# SELFTEST — slides-author（slides-02 v6）

> **验证状态**：本包已在本地 Python 3.12（标准库）上**实跑** `scripts/eval_sim.py`，rich / boundary ×
> single / agent **12 次全部 PASS**（判定取自 eval_sim 报告的顶层 `status`，且逐项检查均为 PASS）。
> 正式案例以平台 `/input` 为准，本表不代表平台正式分数。

## 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-02 \
  --case work/p4/synth_cases/slides-02/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-02 \
  --case work/p4/synth_cases/slides-02/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-02 \
  --case work/p4/synth_cases/slides-02/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v6/slides-02 \
  --case work/p4/synth_cases/slides-02/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 |
|-|-|-|-|
| rich | single | **PASS** | case.json:output_contract（3 键：quote / structural / notes） |
| rich | agent | **PASS** | case.json:output_contract（3 键） |
| boundary | single | **PASS** | SKILL.md default artifacts（10 键） |
| boundary | agent | **PASS** | SKILL.md default artifacts（10 键） |

逐项检查（12 次运行均为 PASS）：

- `exit_code`：单命令入口 `all` 与 agent 模式多子命令序列均 exit 0；
- `result_json`：合法 JSON；
- `contract_echo` / `contract_values`：契约键全部回填且无 empty / placeholder / missing-file；
- `deliverables`：全部产物存在且 >40 字节；
- `case_id`：`synth-rich-slides-02` / `synth-boundary-slides-02` 原样透传；
- `placeholder_sweep`：全部产物（含 `deck.pptx`）无占位符 token；
- `field:status / sources / uncertainties / change_records / limits`：均非空。

## 关于“deck 内容偏薄”的针对性修复

本包不把 markdown 标题当作页面内容：按**小节内的实质句子**建立页面（标题只作页面标题），
每页抽出一句页级主张 + 至多四条要点，并保留材料定位与逐字引用；代码块与表格行被排除在页面文本之外。
rich 用例实测：6 页、20 条证据要点**全部逐字校验通过**。

## 产物有效性

- rich：`deck.pptx` 为合法 OOXML（37 个 part，6 张幻灯片 + 6 张备注页，XML 全部可解析）；
  `deck.pdf` 为合法 PDF-1.4（含 xref / trailer / %%EOF）。
- boundary：1 页诚实说明页，`status=insufficient_evidence`，11 个产物齐备并 exit 0。

## 产物清单（运行后输出目录）

`result.json`、`deck.md`、`deck.pptx`、`deck.html`、`deck.pdf`、`preview.svg`、`outline.md`、
`slide_plan.json`、`content_map.json`、`compliance_checks.json`、`report.md`。
