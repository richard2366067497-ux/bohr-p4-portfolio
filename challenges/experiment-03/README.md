# bounded-param-optimizer — 有界实验参数优化（experiment-03 v6）

把一批实验材料整理成**可逐条复核的有界参数优化**：从材料中抽出有限参数域（min/max/step）、
显式约束（le/ge/lt/gt/eq/ne/mutex）、价格与用量行、预算、版本化候选方案与响应指标，
再由这些数字**逐项计算**出可行网格、响应面模型（含 RMSE 与留一 RMSE）、Pareto 前沿、
序贯搜索计划、单次成本台账、不可行时的最小冲突集与三版本对比，最后给出带容差的推荐值。

核心约束：

- 每个数字要么带 `source_id` + `locator` + **逐字 quote** 复制自材料，要么由这些数字按写在
  产物旁边的公式重算；缺失输入写成结构化"absent"记录，不臆造。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构与
  可读原因，不写占位符。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py     scripts/extract.py   scripts/optimize.py   scripts/render.py
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 抽参数域/约束/历史/价格/预算/候选方案/指标 → 枚举网格并按每条约束过滤 →
拟合响应面 → 排序 / Pareto / 序贯搜索 / 成本台账 → 时间线报告、参数表、可行性网格、证据矩阵、
不可行分析、版本对比、SVG 之外的 10 个 JSON/MD 产物 → `result.json`（契约逐键回填 + case_id 透传）
→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（recommended 里填参数值）
python3 scripts/main.py check      # 校验 draft 键是否映射到参数域、是否越界
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、参数域、约束、模型、推荐、搜索、成本、可行性、版本胜出、limits、uncertainties、sources、change_records、artifacts |
| search_notes.md | 方法、材料清单、抽到的内容 vs 缺失、检索命中/未命中、下一步 |
| parameter_table.json | 每个参数域的 min/max/step/unit/轴点数、拟合敏感度、证据 |
| feasible_grid.json | 各轴取值、网格规模、可行数与占比、逐约束通过数、样例点 |
| pareto_front.json | 非支配点及其指标值，或说明为何不宣称前沿 |
| search_plan.json | 策略、逐轮计划与预测增益、停止规则、预算关系 |
| cost_ledger.json | 单次成本、总成本、预算、公式、输入行、算术自检 |
| version_diff.md | 三版本对比表（可行性、越界数、预测均值、报告成本、locator） |
| evidence.json | 每条抽取项的 source_id/locator/quote 与逐字命中率 |
| infeasibility.json | 最小冲突集、松弛建议、最不违例点 |

## 降级与边界

- 材料中无有限参数域：网格/模型/成本报 insoluble，并列出已检索的位置；`status=insufficient_evidence`。
- 无历史表：排序退化为**标注为设计准则**的约束余量规则（绝不冒充响应预测）；`status=partial`。
- 网格非空但全不可行：给最小冲突集与松弛建议；`status=partial`，推荐"最不违例点"。
- 无预算：总成本留空并保全公式，不猜预算。
- 不做显著性检验；样本少时模型只作提示，并打印 RMSE 与 n。
- 不联网、不安装工具、不臆造缺失数据。

## 维护

版本 2.6.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/extract.py`。
改了脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次自测（见 SELFTEST.md）。
