---
name: provenance-gated-methods-writer
description: 把散落在配置、日志、代码、论文片段里的实验材料整理成可执行的方法与实验章节，逐条带来源定位，缺口交作者确认（中文/英文自适应，纯标准库，离线）。Turns scattered configs, logs, code and paper fragments into a reproducible methods-and-experiments manuscript with per-item source locators and explicit gaps (zh/en auto-detected, offline, stdlib only).
---

# 方法与实验章节写作（证据门控版 / provenance-gated methods writer）

**用途**：读入 `case.json` / `task.md` 与材料文件（配置、日志、代码、论文片段），产出
十节式方法与实验章节稿 `manuscript.md`，外加事实台账、参数台账、要素覆盖矩阵、缺口清单、
冲突登记与 `result.json`。每条数字都带 `[S#]` 来源与 `文件#行号` 定位；材料未提供的要素
显式登记为缺口，**不编造数值、单位、引用与实验结果**。

**适用条件**：输入目录含 `case.json`（可含 `output_contract`）、`task.md`、`materials/`；
无网络、无第三方包；`python3 >= 3.8`。**语言自适应**：`case.json.language` 优先，否则按
材料/任务文本的 CJK 占比检测，中英文分别渲染（同一份逻辑，不写死语言）。

## 执行前必读（专家方法论）

开工前完整阅读 `references/expert_playbook.md`，按其六步框架（输入解析 → 事实抽取 → 要素映射 →
章节成稿 → 对齐校验 → 缺口标注与打包）推进，并**按 §5 专家检查表逐项产出**。判分口径、指标公式、
领域陷阱、案例与门控以该手册为准；契约键名与入口命令以本文件为准。

## 单命令入口（一次性全流程；评测入口，无 draft 时执行）

**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` = `init`（材料盘点 + 来源编号 + 候选抽取 + 冲突分组）→ `build`（工作稿校验/兜底抽取、
渲染 7 个产物、finalize `result.json`）→ `selfcheck`（产物齐备与契约字段自检）。退出码恒为 0。

## Agent-first 双路径

- **Agent 路径（推荐）**：先 `init` 看台账，读原文，把判断写入 `${WORK}/draft.json`（要素取舍、数值
  裁决、章节措辞），随后 `check` → `build`。工作稿形状见 `references/guide.md`。
- **无 draft 兜底路径**：`build` 由 init 台账确定性抽取生成实质工作稿（逐字 quote + locator），并如实把
  `AUTO_EXTRACT` 记入 `gaps` 与 `degradations`；两条路径产出同一套产物与同一份 `result.json` 契约。

## 分步子命令

```bash
python3 scripts/main.py init --input /input --work /app/work --output /app/output
python3 scripts/main.py show --work /app/work --grep lr      # 读原文：--file S3 或 --grep 关键词
python3 scripts/main.py check --work /app/work --output /app/output
python3 scripts/main.py build --input /input --work /app/work --output /app/output
python3 scripts/main.py selfcheck --output /app/output
```

## 输入

```
/input/case.json                 # {case_id, language?, output_contract?}
/input/task.md                   # 任务说明与写作约束
/input/materials/*               # 配置/日志/代码/论文片段（最大 400KB/文件，超出截断）
```

## 输出（/app/output）

- `manuscript.md`：十节章节稿（任务与范围、数据与预处理、方法步骤、实验设置、参数与来源、基线对照、
  指标与统计、复现清单、限制条件、缺口清单）。
- `fact_ledger.csv`：事实 statement/value/unit/source_id/locator/quote/status。
- `parameter_ledger.csv`：参数 取值/单位/作用对象/来源/冲突标记。
- `evidence_matrix.csv`：六类要素覆盖矩阵 items/cited/status/locators。
- `gaps.md` / `conflicts.md`：缺口（缺什么/影响/需谁确认/涉及小节/追问）与冲突登记（并列保留）。
- `coverage.json`：覆盖率与逐要素状态。
- `result.json`：契约键**顶层 + 嵌套 `output_contract`** 双回填 + `case_id` 透传 + 信封字段
  `status/sources/uncertainties/change_records/limits/errors/degradations/pending_human`。

## result.json 契约字段

`output_contract` 的每个键都在**顶层**与**嵌套 `output_contract` 对象**中同时出现，值可回溯：

| 字段 | 值 |
|---|---|
| `case_id` | 输入 `case.json` 的 `case_id` 原样回填 |
| `deliverable` | 章节稿路径（`manuscript.md`） |
| `preserved_facts` | 带来源与定位的事实表；无要素可抽时为材料清单（含 sha1） |
| `evidence_map` | 每条要素 → `文件#行号` 的定位映射 |
| `change_log` | 逐条动作/原因，以及 `needs_human` 待确认项 |

`case.json` 未声明 `output_contract` 时使用包内默认契约（同名五键），不输出 null/空壳/占位符。

## 处理规则

1. **六类要素**（步骤 / 实验设置 / 参数 / 数据集与划分 / 基线对照 / 复现与限制）逐类处理：材料支持则
   带源写入；不支持则登记缺口并在章节显式标出，绝不补造。
2. **参数对齐**：正文数值与 `parameter_ledger.csv` 一致；多来源取值不同 → 并列保留 + `conflicts.md` +
   `gaps`，不择一取整。
3. **基线可比性**：`comparable=false` 时正文禁止“优于基线”一类断言。
4. **引文门控**：`facts[].quote` 必须能在来源文件中逐字命中，否则该事实不得进入正文。
5. **语言**：`zh` / `en` 分别渲染标题、标签与套语。

## 异常处理

- 空/坏输入、`case.json` 不可解析：`status=input_error` 或 `insufficient_evidence`，仍写合法
  `result.json`，退出码 0。
- 不可读/二进制/超限材料：登记 `degradations` 与缺口，继续运行。
- 输出目录不可写：回退 `./output`；命令异常：兜底写最小合法 `result.json`（含契约键），退出码 0。

## 自检清单（交付前逐项）

- [ ] `references/expert_playbook.md §5` 专家检查表逐项通过（要素覆盖 / 参数准确 / 可追溯 / 缺口标注 /
      条件一致 / 无补造）。
- [ ] 单命令入口实跑退出码 0，`/app/output` 内 `result.json` 与全部产物齐备、非空。
- [ ] 契约键在**顶层**与**嵌套 `output_contract`** 同时回填，无 null / 空壳。
- [ ] `case_id` 与输入一致；声明路径均指向真实文件；无 TODO / 待补充 / 示例值等占位符。
- [ ] 材料缺口、冲突、降级与待确认项已显式登记，未静默统一或补造。

## 资源与参考

- `references/expert_playbook.md`：专家方法论（判分要点、六步框架、公式、领域知识、检查表、案例）。
- `references/guide.md`：工作稿 schema、要素清单、参数表模板、追问模板。
- `environment/resources.yaml`：入口、运行时目录、预算、必需产物与契约约定。
