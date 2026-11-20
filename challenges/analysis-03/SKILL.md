---
name: figure-spec-publisher
description: 把科研数据表做成可投稿图件与可复核证据链。以声明的 figure_specs 为唯一事实源（数据选择→清洗口径→统计聚合→图型选型与拒绝理由→编码映射→标注图注→导出规格），渲染器只执行规格，产出真实 SVG、绘图代码、图注、元素级数据溯源表、审计报告与 result.json。用于"科研数据可视化""出图""柱状图/箱线图/散点拟合/折线/热图""期刊图件导出""图表选型"等任务；每个视觉元素都能回算到源数据行，缺失/异常/冲突必须显式说明。
version: 2.0.0
tags: [scientific-visualization, figure-spec, publication-export, evidence-traceability]
---

# 科研数据 → 投稿级图件（figure-spec 规格驱动）

本包是 `analysis-03` 的 v6 修复形态：**单命令即可跑完整条流水线**，无需先初始化再手写工作稿；
Agent 仍可阅读证据后补充判断，但评估器只跑第一条命令也能拿到全部产物与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 同时把每个契约键放进 `output_contract` 结构位与顶层同名键。用例声明的键总是合并
进来、绝不改名或丢弃；用例未声明契约时使用下列默认键（与 SKILL 本样例一致）：

```json
{
  "case_id": "string",
  "status": "success | partial | failed",
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

- `case_id` 原样透传（来自 `/input/case.json`）；取不到时回退为输入目录名。
- 路径类键指向真实存在且非空的交付物；无法直接映射的键写成结构信封
  `{"kind","items","count","note"}`，而不是占位符。
- 本引擎在写出前统一做占位符清理：不出现 `待写` / `待补充` / `none` / `null` / `pending` /
  `N/A` / `TBD` 等令牌。

## 1. 单命令全流程（single-command entry）

一条命令跑完发现输入 → 解析数据表 → 统计口径 → 图型选型（含拒绝理由）→ 渲染真实 SVG →
写图注/绘图纸/审计/报告 → 回填全部 `output_contract` 键 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=failed` 或 `partial`，降级但不编造测量值）。
- 输入目录没有表格时，仍输出真实 SVG（输入盘点图）与全部文本/JSON 交付物，绝不写空壳占位符。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `figure_report.md` | 五节报告：输入盘点、数据口径与清洗、图件规格、统计覆盖、审计与限制 |
| `figure_specs.json` | 每张图的规格（data / chart / encoding / stats / annotation / export，含 ≥2 条拒绝理由） |
| `data_to_figure.json` | 字段角色与「图元素 → 源列」映射 |
| `stats.json` | 每列描述统计（连续列给 n/mean/sd/min/median/max，分类列给 distinct） |
| `cleaning_log.json` | 每条解析/跳过动作的记录；无动作时写 `no_op` 记录 |
| `audit.json` | 机械校验清单与通过数 |
| `captions.md` | 可脱离正文阅读的图注 |
| `case_materials.json` | 输入文件盘点（路径、字节、sha256、类型）与题面摘录 |
| `overview.svg` | 真实矢量图（有数据时为统计草图，无数据时为输入盘点柱图） |
| `figure_code.py` | 依据规格生成的绘图脚本骨架（可编辑） |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、`status`、证据、不确定性、变更记录、限制 |

`figure_report.md` 与 `overview.svg` 是主交付；其余文件是可复核的中间证据。

## 3. 子命令与参数（可选，供人工/Agent 分步复核）

| 子命令 | 作用 | 写盘 |
|---|---|---|
| all | 全自动流水线（推荐，单命令等价入口） | 是 |
| init | 仅盘点输入与写部分 result.json | 是 |
| show | 打印输入清单与计划规格 | 否 |
| check | 复核已有输出与契约键 | 否 |
| build | 同 all（保留旧入口名） | 是 |
| selfcheck | 重开输出目录复核 | 否 |

公共参数：`--input`（别名 `--in`）、`--output`（别名 `--out`）、`--work`、`--case`。所有子命令都
接受这组参数并始终退出 0，便于在不同 harness 下注入路径。

## 4. 图型选型与统计口径

- **分布** → 直方图 / 箱线图；**比较** → 柱状（组均值 + SD 误差线）；**相关** → 散点 + OLS；
  **趋势** → 折线；**多变量** → 相关热图。每份规格必须列出至少两种被拒绝的图型及理由。
- 误差线默认 SD（分母 n−1）；组内 n<3 不画误差线并注明；显著性只在可算时给出。
- 导出：矢量 SVG 为主交付，89 mm 单栏、≥300 dpi 位图、正文 ≥7 pt、Okabe–Ito 色盲友好配色。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 递归找材料继续；用默认契约 | `degradations: case_json_unreadable` |
| 无表格材料 | 输入盘点图 + 全部诚实交付物，status=partial | `uncertainties: no_tabular_data` |
| 空文件 / 坏 JSON | 记入盘点并跳过解析 | `change_records: skipped` |
| 某列全空 / 类型混杂 | 按分类列处理并记录 | `stats.json` 的 categorical 列 |
| 无字体/光栅器 | 只交付 SVG，不声称 PNG | `figure_code.py` 注明 |

## 6. 边界与限制

只做描述统计 + 计划性检验；不判断科研结论正确与否，只保证图与数据一致、口径透明、可复跑。
纯标准库、无网络、无时钟读取：重复运行同一输入，交付物字节稳定。运行中断时保留已写的
部分 `result.json`，异常写入 `errors[]`，退出码仍为 0。
