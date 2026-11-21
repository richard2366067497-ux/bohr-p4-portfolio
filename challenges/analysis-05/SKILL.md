---
name: sci-analysis-dag
description: 把科研材料表做成可复核的数据分析交付：导入→清洗（行数守恒）→描述与推断统计→真实 SVG 图件→报告，全部数字来自同一套登记表。用于"数据分析""统计检验""数据清洗""相关性/方差分析""出图并写报告""复跑流水线"等任务；每个打印出来的数字都能回算到源列与源行，缺失/异常/冲突必须显式说明。
version: 6.0.0
tags: [data-analysis, statistics, data-cleaning, pipeline-dag, evidence-traceability]
---

# sci-analysis-dag（数据分析流水线）

本包是 `analysis-05` 的 v10 形态：**单命令即可跑完整条 DAG**，无需先初始化再写工作稿；
Agent 仍可补充清洗口径，但评估器只跑第一条命令也能拿到全部产物与完整契约回填。

## 随包方法论（执行前必读）

执行任何命令前**先完整阅读 `references/expert_playbook.md`**，并按它组织全部产出：按其 §2 八步流程推进
（读取→导入→审计→清洗→统计→可视化→报告→打包），按其 §4 公式核算缺失率/效应量/t/CI，按其 §5 逐条排雷，
按其 §7 自查表交付。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 同时把每个契约键放进 `output_contract` 结构位与顶层同名键。用例声明的键总是合并
进来、绝不改名或丢弃；用例未声明契约时使用下列默认键（与 SKILL 本样例一致）：

```json
{
  "case_id": "string",
  "status": "string",
  "output_contract": {
    "case_id": "string",
    "status": "string",
    "deliverable": "string",
    "statistics": "string",
    "figures": "string",
    "cleaned_data": "string",
    "change_log": "string"
  }
}
```

- `case_id` 原样透传（来自 `/input/case.json`）；取不到时回退为输入目录名。
- 路径类键（含 `/` 或 `.json` / `.csv` / `.md` / `.svg` 等后缀）指向真实存在且非空的交付物；
  无法直接映射的键写成结构信封 `{"kind","items","count","note"}`，而不是占位符。
- 写出前统一做占位符清理：不出现 `待写` / `待补充` / `none` / `null` / `pending` / `N/A` / `TBD`。

## 1. 单命令全流程（single-command entry）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。一条命令跑完
导入 → 清洗 → 统计 → 出图 → 报告 → 回填全部 `output_contract` 键 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=partial` 或 `input_error`，降级但不编造测量值）。
- 输入没有数据表时，仍输出真实 SVG（输入盘点图）与全部文本/JSON 交付物，绝不写空壳占位符。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `analysis_report.md` | 五节报告：导入与字段、清洗与行数守恒、统计结果、图件、数字溯源与局限 |
| `stats.json` | 每列描述统计（连续列 n/mean/sd/min/max/median/q1/q3/outliers，分类列 distinct）与全部推断检验 |
| `cleaned/data_clean.csv` | 清洗后的真实数据表（每张表一份） |
| `checkpoint_ledger.jsonl` | 每个 checkpoint 一行：method、rows_in/out、checks、provenance |
| `pipeline_dag.json` | S1..S5 节点与依赖边（导入→清洗→统计→出图→报告） |
| `field_mapping.json` | 字段角色表：name/table/kind/unit/locator |
| `data_quality.json` | 文件数、空文件、重复/填补/丢弃/离群标记计数与逐条动作记录 |
| `verification.json` | 数字登记表：报告里每个数字的取值与来源步骤 |
| `code/reproduce.md` | 复跑说明（同一输入字节稳定） |
| `figures/figure_01.svg`、`figures/figure_02.svg` | 真实矢量图（均值±SD 柱图 / 直方图 / 散点拟合；无数据时为盘点柱图） |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、`status`、证据、不确定性、变更记录、限制 |

`analysis_report.md` 与 `figures/figure_01.svg` 是主交付；其余文件是可复核的中间证据。

## 3. 子命令与参数（可选，供人工/Agent 分步复核）

| 子命令 | 作用 | 写盘 |
|---|---|---|
| all | 全自动流水线（推荐，单命令等价入口） | 是 |
| init | 写入草稿骨架并按默认口径跑一遍全流程 | 是 |
| show | 打印输入清单与将要执行的步骤 | 是 |
| check | 复核已有输出与契约键 | 是 |
| build | 同 all（保留旧入口名） | 是 |
| selfcheck | 重开输出目录复核 | 是 |

公共参数：`--input`（别名 `--in`）、`--output`（别名 `--out`）、`--work`、`--case`。所有子命令都
接受这组参数并始终退出 0，便于在不同 harness 下注入路径。`--work/draft.json` 的
`decisions`（如 `{"dedupe": false, "missing": {"required": ["yield"]}}`）会覆盖默认清洗口径。

## 4. 统计口径

- 描述统计全部在清洗后的行上重算；均值/SD/分位数与离群界（IQR 1.5）一目了然。
- 推断检验：两组的 Welch t 检验（附 Cohen's d）、多组的单因素 ANOVA（附 η²）、连续列两两的
  Pearson r、二元简单 OLS（斜率/截距/R²）；p 值由正则化不完全 Beta 函数算出，无第三方依赖。
- 显著性只在检验可算（n 足够、方差非零）时给出；样本不足时报告为"仅指示性"并写出 n。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 递归找材料继续；用默认契约 | `degradations: case_json_unreadable` |
| 无数据表 | 盘点图 + 全部诚实交付物，status=partial | `uncertainties: no_tabular_data` |
| 空文件 / 坏 JSON / 坏 sqlite | 记入盘点并跳过解析 | `degradations: material_unreadable` |
| 分组样本 < 3 | 不出该检验，标注指示性 | `uncertainties: group_too_small` |
| 某列全空 / 类型混杂 | 按分类列处理并记录 | `stats.json` 的 categorical 列 |

## 6. 边界与限制

只做描述统计 + 计划性检验；不判断科研结论正确与否，只保证报告与数据一致、口径透明、可复跑。
纯标准库、无网络、无时钟读取：重复运行同一输入，交付物字节稳定。运行中断时保留已写的部分
`result.json`，异常写入 `errors[]`，退出码仍为 0。

交付前须**逐项通过 `references/expert_playbook.md` §7 的专家检查表**（原始快照/字段映射/质量审计/清洗与行数
守恒/统计前提/效应量与 CI/图表同源/逐字一致/locator 与复算）；任一未过记 `partial` 并写入不确定性。
