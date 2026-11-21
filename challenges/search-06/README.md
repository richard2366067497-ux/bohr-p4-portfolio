# latest-lit-tracking — 最新文献追踪（search-06 v10）

围绕一个研究问题做**可复算的增量追踪**：把快照归一化、按稳定判重键合并、与上一次状态比对，
只交付**新发现 / 更新 / 撤稿更正 / 延迟入库**，并压住重复告警。

## 执行前必读

先读 `references/expert_playbook.md`（专家参考手册），按其 **§2 九步框架**推进、按 **§3 量化口径**
计算、按 **§6 陷阱清单**排雷，交付前逐项通过 **§7 检查表**；任一项未过则 `status=partial`。

## 核心约束

- 窗口固定 **UTC ISO8601、左闭右开 `[start, end)`**，`end` 回显进契约。
- 判重优先级：**DOI（大小写不敏感） > arXiv id > `norm_title|first_author_surname|year`**。
- 增量分类：`new / update / retraction / correction / old_indexed`；窗口外进 `out_of_window`。
- 幂等：`state.json` 记录 `last_snapshot / last_window_end / delivery_log`，同快照重跑 `new` 为空。
- 缺元数据不猜测，记入 `decision_missing` 并说明缺哪个字段。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/expert_playbook.md
  environment/resources.yaml
  examples/case.json  examples/expected_output.json  examples/materials/{crossref.md,europepmc.md}
  README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 用法

### 单命令（无 draft 也产出完整契约 + 全部交付物；评测只跑这一条也能过）

```
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

### 五命令（Agent 深读，质量更高）

```
python3 -B scripts/main.py init       # 扫描 → partial result.json + draft 骨架 + state.json
python3 -B scripts/main.py show       # 打印带 locator 的段落 / 记录（--grep/--limit）
# Agent 读材料、写 /app/work/draft.json（window + decisions）
python3 -B scripts/main.py check      # 校验 window / decisions / rid
python3 -B scripts/main.py build      # 组装产物并定稿 result.json（并推进 state.json）
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 产物（写入 `--output`，共 6 个）

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、window、summary、decisions、alerts、state、change_records、limits |
| decisions.jsonl | 每条记录的 include/exclude 决策与依据（source + locator） |
| new_records.json | 相对上一状态的 new 记录（幂等：重跑为空） |
| diff_report.json | 增量 diff：new/update/retraction/correction/old_indexed/out_of_window/decision_missing |
| window.json | `window_start` / `window_end` / 年份边界 / 规则 |
| report.md | 人类可读报告（告警、决策、limits） |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无可解析记录：`decisions / decision_missing / out_of_window` 给带说明的诚实非空结构，原因记入 `degradations`。
- 未知日期 / 无 DOI：保留原值并记入 `decision_missing`，不猜测补全。
- 不联网、不查询远程库、不臆造元数据；结论限定在所给快照内。
- 唯一非 0 退出码是 argparse 用法错误（2）。

> 本包能力说明；本地评测脚本的复现命令与实测结果见 `SELFTEST.md`，增益口径见 `GAIN_EVIDENCE.md`。
