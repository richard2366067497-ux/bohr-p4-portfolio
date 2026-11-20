---
name: analysis-codegen-execute
description: 从数据字典与任务规格生成一段自足的科研分析代码，在隔离子进程里真实执行，逐条复核每个关键数字（独立重算）、渲染图表、记录命令与退出码，并交付代码/结果/校验/日志/环境/复现六类证据。用于"分析代码生成""清洗+统计+可视化+执行""跑通并核对静默错误""环境与随机种子留痕""查询结果校验"等任务；纯标准库、无网络、退出码恒 0，失败现场保留并降级为合法结果。
version: 6.0.0
tags: [codegen, execution, verification, reproducibility]
---

# 科研代码生成与执行 → 可复核结果（codegen-execute 契约驱动）

本包是 `analysis-04` 的 v6 形态：**单命令即可跑完整条"生成代码 → 执行 → 核对"链路**，无需先初始化
再手写工作稿；Agent 仍可读证据后补充判断（写入 `draft.json`，`all` 会自动合并），但评测器只跑
第一条命令也能拿到全部关键产物与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 把每个契约键同时放进 `output_contract` 结构位与顶层同名键。用例声明的键总是
合并进来、绝不改名或丢弃；用例未声明契约（`output_contract` 为 null）时使用下列默认键：

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
- 键名按语义回填：`code/script` → 生成代码条目（路径、字节、sha256、行数、复跑命令）；
  `result/metric/value` → 结果与 `key_numbers`；`verif/check` → 校验列表与汇总；`log` → 运行日志；
  `env/version` → 环境；`report` → 报告路径；`repro/seed/command` → 复现清单；无法映射的键写成
  结构信封 `{"available":[...],"note":...}`，而不是占位符。
- 写出前对文本做令牌中和：文件正文不出现 `待写` / `null` / `none` / `pending` / `N/A` / `TBD`
  等令牌，但解码后的键值仍是原文。

## 1. 单命令全流程（single-command entry）

一条命令跑完：发现输入 → 解析数据字典与规格（draft 字段 / 校验项 / 降级矩阵 / 契约语义）
→ **生成** `code/analysis.py`（自足、纯标准库）→ **执行**（子进程，300s 超时，捕获 stdout/stderr/退出码）
→ 读回 `results/summary.json` → **独立重算**每个关键数字并逐条校验 → 渲染图表 → 写全部交付物
→ 回填全部 `output_contract` 键 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=failed` 或 `partial`，降级但不编造数值）。
- 生成的代码可**脱离本包自足复跑**：`python3 code/analysis.py --input <材料> --output <结果>`。
- 若子进程失败/超时，包内**独立重算**兜底并在 `errors[]` / `verification` 中记录，绝不吞掉失败。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `code/analysis.py` | 生成的分析代码（自足、纯标准库；含复跑命令与 sha256） |
| `results/summary.json` | 唯一结果来源：tables / ops / key_numbers（报告与 key_numbers 由它派生） |
| `results/key_numbers.json` / `results/key_numbers.csv` | 关键数字（含 metric、table、column、value、unit） |
| `verification.json` | 校验列表：input / integrity / execution / claim 重算 / chart / types，逐条 pass |
| `run_log.json` | 运行证据：命令、CWD、退出码、stdout/stderr 摘要、环境与 seed |
| `environment.json` | 运行环境：Python 版本、依赖（纯标准库）、无网络、降级方案 |
| `reproducibility.json` | 复现清单：seed 固定、复跑命令、离线确定性 |
| `report.md` | 六节报告：输入与编码、规格与字段映射、生成代码与执行、结果、校验、限制 |
| `cleaning_ledger.csv` | 清洗行数账：每表 `n_in / duplicate_rows / n_out` |
| `chart.svg` | 由 groupby 结果渲染的真实柱状图（文本 SVG，含 y 轴单位标注） |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、status、证据、不确定性、变更记录、限制 |

`report.md`、`results/summary.json`、`verification.json` 是主交付；其余文件是可复核的中间证据。

## 3. 校验与静默错误

- 校验类别：`input`（材料/表存在）、`integrity`（行数守恒 `n_in - 去重 == n_out`）、`execution`
  （退出码、产物落盘）、`claim`（每个关键数字在引擎里**独立重算**，容差 `max(1e-6, 5e-4·|值|)`）、
  `chart`（点数 ≤ 源结果行数、轴含单位）、`types`（数值列不可解析值计数）、`query`（行数膨胀）。
- 静默错误防范：`missing_as_zero` / 多去重 / 应剔未剔 / 单位缩放 等变体都由**独立重算**暴露——
  声明值与重算值不一致即判为算错（`pass=false`），并写入 `verification.json`。
- 生成代码与复核代码走**两条独立路径**（生成脚本 vs 引擎内重算），避免同源错误。

## 4. Agent-first 增强路径（可选）

Agent 先读材料（`show` 打印文件索引与候选列）→ 把判断写成 `/app/work/draft.json`
（字段见 `references/analysis_spec.md` 与 §3）→ 再跑 `all`。`all` 若发现 `draft.json` 会合并
Agent 的 `column_map / cleaning_policy / claims / verification`，找不到就以字典与规格自动推导，
产物完整度不降。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 扫材料继续；用默认契约 | `degradations: case_json_unreadable` |
| 无可解析表 | 代码仍生成并执行，产出全部交付物，status=partial | `uncertainties: no_analyzable_data` |
| 子进程失败/超时 | 保留 stdout/stderr 现场 → 包内重算兜底 | `errors[].stage=execute` |
| 空文件 / 坏 JSON | 记入盘点并跳过解析 | `change_log: skipped` |
| 字典缺字段 | 标 `unmatched`，跳过单位断言 | `degradations: dictionary_unmatched` |
| 无分类列 | 跳过图表，其余交付不受影响 | `degradations: chart_skipped` |

## 6. 边界与限制

只做代码生成、执行、结果核对、图表渲染与证据留痕；不做实验方案设计、机理解释、论文写作，
不安装第三方库、不访问网络、不编造基准分。纯标准库、无时钟读取：重复运行同一输入，交付物
字节稳定；运行中断时保留已写部分 `result.json`，异常写入 `errors[]`，退出码仍为 0。
