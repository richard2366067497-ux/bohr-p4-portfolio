---
name: latest-lit-tracking
description: Track the latest literature for a research question inside a configured UTC window. Reads a supplied snapshot, normalizes and de-duplicates records (DOI > arXiv id > normalized title+first author+year), performs an incremental diff (new / update / retraction / correction / old-indexed), suppresses alerts, updates state idempotently, and echoes the output contract key by key. Offline, standard library only.
---

# latest-lit-tracking (v10)

Keep a running subscription over a literature snapshot: decide what is **new**, what is an
**update / retraction / correction**, what was **indexed late**, what falls **outside the window**,
and emit an alert list you can defend line by line. No network, no third-party packages.

## 随包方法论（执行前必读）

**执行前阅读 `references/expert_playbook.md`**，按其九步框架推进、按其中的量化口径计算、
按陷阱清单排雷，交付前逐项通过其检查表。
- 归一化：NFKC → 小写 → 去标点 → 折叠空白（`norm_title`）。
- 判重优先级：**DOI（大小写不敏感） > arXiv id > `norm_title|first_author_surname|year`**；命中判重即合并并保留依据。
- 窗口：UTC ISO8601，**左闭右开 `[start, end)`**；`end` 必须回显进契约。
- 增量分类：`new / update / retraction / correction / old_indexed`；窗口外的记录进入 `out_of_window`。
- 幂等：重跑同一快照，`new` 应为空（对比 `state.json` 的 `last_snapshot`）。
- 阈值：new 准确率 ≥ 95%，重复率 ≤ 5%，漏检 ≤ 10%，窗口覆盖 100%，幂等重跑 100%，告警压缩 ≥ 2。

## 输入

- `--input`：快照目录（一个文件 = 一个来源/订阅源）。`case.json` / `task.md` 可选。
- `--work`：状态与草稿目录（`index.json`、`state.json`、`draft.json`）。
- `--output`：产物目录。

## 用法

### 单命令（评测入口；无 draft 也产出完整契约 + 全部交付物）

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

等价于 `all`：解析 → 订阅配置 → 读状态 → 检索 → 归一化/判重 → 增量 diff → 告警合并/抑制 →
幂等状态更新 → 写 `result.json` + 全部产物。退出码 0。

### 五命令（Agent 深读，质量更高）

```
python3 -B scripts/main.py init       # 扫描 → partial result.json + draft 骨架 + state.json
python3 -B scripts/main.py show       # 打印带 locator 的段落 / 记录（--grep/--limit）
# Agent 读材料、写 /app/work/draft.json（window + decisions）
python3 -B scripts/main.py check      # 校验 window / decisions / rid
python3 -B scripts/main.py build      # 组装产物并定稿 result.json（并推进 state.json）
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 输出契约（`result.json`）

`case.json` 的 `output_contract` 存在时逐键照抄键名、回填真实值；否则回退到下面的样例键：

```
{
  "output_contract": {
    "case_id": "the case identifier echoed verbatim",
    "status": "completed | partial | insufficient_evidence | input_error",
    "end": "window end, UTC ISO8601",
    "decisions": "per-record include/exclude decisions with reason",
    "decision_missing": "records whose decision/metadata could not be determined",
    "out_of_window": "records outside [start, end)"
  }
}
```

顶层同时写出同名键与 `output_contract` 回显（`fill_contract`）。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、window、summary、decisions、alerts、state、change_records、limits |
| decisions.jsonl | 每条记录的 include/exclude 决策与依据（locator + source） |
| new_records.json | 相对上一状态的 new 记录（幂等：重跑为空） |
| diff_report.json | 增量 diff：new/update/retraction/correction/old_indexed/out_of_window/decision_missing |
| window.json | `window_start` / `window_end` / 年份边界 / 规则 |
| report.md | 人类可读报告（告警、决策、limits） |

## 状态与幂等

`state.json` = `{last_snapshot, last_window_end, delivery_log}`。同一快照重跑，`last_snapshot`
已含全部判重键 → `new` 为空、`alerts` 不重复；`last_window_end` 单调推进。

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无可解析记录：`decisions` / `decision_missing` / `out_of_window` 给带说明的**非空**结构，原因记入 `degradations`。
- 未知日期 / 无 DOI：保留原值并记入 `decision_missing`，不猜测补全。
- 不联网、不查询远程库、不臆造元数据；结论限定在所给快照内。
- 唯一非 0 退出码是 argparse 用法错误（2）。

## 交付前自查清单

- [ ] `result.json` 可解析，`case_id` 原样透传
- [ ] `case.json:output_contract` 每键已回填；无 `output_contract` 时回退样例键
- [ ] 6 个产物全部写出（含 `report.md`）
- [ ] `status` / `sources` / `uncertainties` / `change_records` / `limits` 非空
- [ ] 判重依据可回查；`window` 规则为 `[start, end)`
- [ ] 幂等：同快照重跑 `new` 为空
- [ ] 无占位符（`null` / `N/A` / `TBD` / `待填写` / `<...>`）
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` 的检查表逐项核对，任一项未过则 `status=partial`

> 本包能力说明；本地评测脚本复现命令与实测结果见 `SELFTEST.md`，增益口径见 `GAIN_EVIDENCE.md`。
