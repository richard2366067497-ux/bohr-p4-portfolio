# SELFTEST — slides-author（slides-01 · v9）

> **验证状态**：本包已在本地 Python 3.12（纯标准库，无第三方依赖）上**实跑**
> `scripts/eval_sim.py`，rich / boundary × single / agent **4 次全部 PASS**
> （判定取自 eval_sim 报告的顶层 `status`，`failures=0`、`warnings=0`，逐项检查均 PASS）。
> 正式评测以平台 `/input` 为准；本表只证明本包在本仓库合成用例上的行为一致。

## 1. 复现命令

```bash
python3 scripts/eval_sim.py --pkg work/p4/v9/slides-01 \
  --case work/p4/synth_cases/slides-01/rich     --mode single
python3 scripts/eval_sim.py --pkg work/p4/v9/slides-01 \
  --case work/p4/synth_cases/slides-01/rich     --mode agent
python3 scripts/eval_sim.py --pkg work/p4/v9/slides-01 \
  --case work/p4/synth_cases/slides-01/boundary --mode single
python3 scripts/eval_sim.py --pkg work/p4/v9/slides-01 \
  --case work/p4/synth_cases/slides-01/boundary --mode agent
```

单命令入口实跑（等价于平台调用）：

```bash
python3 -B /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work ; echo "exit=$?"
```

## 2. 实测结果（4/4 PASS）

| 用例 | 模式 | eval_sim 判定 | 契约来源 | 契约回填 |
|-|-|-|-|-|
| rich | single | **PASS** | `case.json:output_contract` | 15/15 键（顶层同名 + 嵌套 `output_contract`） |
| rich | agent | **PASS** | `case.json:output_contract` | 15/15 键 |
| boundary | single | **PASS** | `case.json:output_contract`（缺失时退 SKILL.md） | 15/15 键 |
| boundary | agent | **PASS** | 同上 | 15/15 键 |

逐项检查（4 次运行均为 PASS）：

| 检查项 | 实测 |
|---|---|
| `exit_code` | 单命令 `all` 与 agent 多子命令序列均 exit 0（rich 单次约 0.4s） |
| `result_json` | 合法 JSON |
| `contract_echo` | rich/boundary 均 `all 15 contract keys echoed in output_contract` |
| `contract_values` | 无 empty / placeholder / missing-file |
| `deliverables` | `presentation.pdf`、`result.json`、`deck.md`、`preview.svg`、`outline.md`、`slide_plan.json`、`content_map.json`、`page_gold.json` 等全部存在且 >40 字节 |
| `case_id` | `synth-rich-slides-01` / `synth-boundary-slides-01` 原样透传 |
| `placeholder_sweep` | rich 14 个输出文件、boundary 14 个输出文件，全部 0 命中 |
| `field:status / sources / uncertainties / change_records / limits` | 均存在且非空 |

## 3. 产物有效性（rich 实测）

- **页数**：9 页（workorder 预算 12 页，未超限）；
- **证据**：`content_map.evidence.bullets = verified = 21`，21 条要点全部逐字命中；
- **图表引用**：results 页 `figure_refs = ["Figure 1", "Figure 2", "Table 1"]`；
- **pptx**：`presentation.pptx` 49 个 part，9 张幻灯片 + 9 张备注页，XML 全部可解析；
- **pdf**：`presentation.pdf` 9 页，与页计划同源导出；
- **契约**：`output_contract` 15 个契约键全回填（含扩展键共 44 个非空块），顶层同名键全部存在；
- **占位符**：14 个产物 0 命中；
- **确定性**：两次干净运行 `deck.md` / `outline.md` / `content_map.json` / `page_gold.json` /
  `slide_plan.json` 的 sha256 前缀完全一致（SAME）。

boundary 实测：`status=insufficient_evidence`，1 页诚实说明页，17 个 pptx part（1 幻灯片 + 1 备注页），
1 页 PDF，同上 15/15 契约回填，14 个产物齐备且 `exit 0`，placeholder 0 命中。

## 4. 异常场景处理（设计 vs 实测）

| 场景 | 本包行为 | 证据 / 实测 |
|---|---|---|
| 损坏 JSON 材料 | 不中断；按原文保留，记 `degradations` + `degraded_input` | boundary `broken.json` 实跑：`degradations=['scan']`，`exit 0` |
| 空材料 / 无可用正文 | 产出 1 页诚实说明页，`status=insufficient_evidence` | boundary `empty.md` 实跑：1 页、`exit 0` |
| 材料无图 / 无图注 | 不摆装饰图，记 `no_figure_embedded` 异常，图表引用照常登记 | rich 实跑：`exceptions` 含 `no_figure_embedded`，`figure_refs` 正常 |
| 无目标模板 / 缺字体 | 退回内置 Office 主题，`version_log.theme` 记 `source` / `sha256` / `inherited=false` | boundary 实跑：`inherited=false`，主题 sha256 为空表示内置 |
| 页数超过 workorder 上限 | 不截断内容，记 `page_budget_exceeded` 异常后仍完整交付，`exit 0` | 将 rich `total_slide_count` 改为 3 单独实跑：`exceptions` 含 `page_budget_exceeded`，9 页照常产出，`exit 0` |
| `draft.json` 含非原文引句 | 只保留逐字命中项，其余进 `exceptions`，不编造内容 | agent 模式实跑：合法草稿保留、杜撰草稿被丢弃并记录 |

## 5. 产物清单（运行后输出目录）

`result.json`、`presentation.pptx`、`presentation.pdf`、`deck.md`、`deck.html`、`preview.svg`、
`outline.md`、`slide_plan.json`、`content_map.json`、`page_gold.json`、`compliance_checks.json`、
`version_log.json`、`report.md`（另含内部索引 `index.json`）。
