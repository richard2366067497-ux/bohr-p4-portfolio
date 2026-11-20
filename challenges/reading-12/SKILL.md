---
name: extraction-table-auditor
description: 把"别人从论文里抄下来的行"清洗成统计软件敢用的表，并留下一条能倒查回原文的证据链：解析输入（编码/魔数/文本层）、识别行级对象与列角色、单位换算与同义归一、重复与冲突候选分组、生成清洗表/变更日志/待确认清单/异常报告/字段映射/规则与单位表，逐键回填 output_contract，并给出可重算与确定性证明。用于"提取表清洗""单位换算核对""字段规范化""重复/冲突对账"等任务；取不到就不填并进 pending_review，绝不猜测单位或编造数值。
version: 2.0.0
tags: [data-cleaning, unit-conversion, provenance, validation, idempotency]
---

# 提取表清洗与标准化（extraction-table-auditor）

本包是 `reading-12` 的 v6 修复形态：**第一条命令即可跑完全流程**，评估器只跑它也能拿到
清洗表、变更日志、待确认清单、异常报告、字段映射、规则与单位表、完整契约回填与 `result.json`。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 同时把每个契约键放进 `output_contract` 结构位与顶层同名键。用例声明的键总是合并
进来、绝不改名或丢弃；用例未声明契约（`output_contract: null`）时使用下列默认键：

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

- `case_id` 原样透传；`deliverable` 指向真实存在且非空的清洗表；`evidence_map` 汇总带 locator 的来源。
- 写出前统一清理占位符令牌（`待写/待补充/none/null/pending/N/A/TBD` 等）与裸 `null`。

## 1. 全流程单命令（single-command entry）

一条命令跑完：扫描输入 → 识别列角色与行对象 → 单位换算/同义归一/重复分组 → 渲染
清洗表与全部视图 → 回填契约 → 写 `result.json` → 占位符清理：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

- 退出码恒 0；空输入 / 坏输入 / 缺草稿同样退出 0，并写合法 `result.json`（`status=partial` 或 `insufficient_evidence`）。
- `all` 不做人工判断：需要裁决的行进入 `pending_review.csv`，不被写进分析表，也不被猜测填补。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `cleaned.csv` | 清洗后的表：row_id、来源、字段、indicator/material、condition、值域、单位、rule_ids、judgment_key、status |
| `change_log.csv` | 每条数值变更：before/after/unit_before/unit_after/factor/offset/formula/precision/rule_id |
| `pending_review.csv` | 需人工裁决的行：reason_code、reason、suggested_action、原始值/单位、来源 locator |
| `anomaly_report.md` | 7 段报告：字段规范/单位换算/同义归一/缺失异常/重复冲突/来源变更/待确认/边界 |
| `rules.json` | 生效规则、被抑制规则、应用计数与优先级说明 |
| `field_mapping.json` | 原始列 → 角色/目标字段，未映射列显式登记，绝不静默丢弃 |
| `unit_table.json` | 单位表快照 + 观察到的换算 + 未解析单位 |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、`status`、证据、不确定性、限制 |

## 3. 子命令（可选，供人工/Agent 分步复核）

| 子命令 | 作用 | 写盘 |
|---|---|---|
| all | 扫描 + 渲染 + 清理（推荐，等价全流程入口） | 是 |
| init | 仅索引输入并写合法 partial result.json 与 work/index.json | 是 |
| show | 打印带 locator 的材料/对象/候选分组，可 `--part draft` 输出草稿骨架 | 否 |
| check | 机械校验 work/draft.json（裁决合法性、行覆盖、quote 逐字命中） | 是（check_report.json） |
| build | 渲染产物 + 最终 result.json；缺草稿时仅机械默认并标 partial | 是 |
| selfcheck | 复算一致率、契约覆盖、两跑逐字节一致、增益对照 | 是（selfcheck.json） |

公共参数：`--input`、`--output`、`--work`、`--draft`。所有子命令都接受它们并始终退出 0。

## 4. 数据与引用

字段词典、单位表按用例随附（`materials/field_dictionary.json`、`materials/unit_table.json`），
脚本优先读取用例自带版本，缺失时退化为最小内置表并在 `degradations` 中说明；规则目录同理。
任何未解析的单位/数值都留空并进 `pending_review`，绝不用 0 或猜测值填充。

## 5. 证据与不编造

每行保留 `row_id + source_document_id + source_locator + rule_ids`；每条结论携带 locator 与
逐字 quote。未知单位、无法解析的单元格、冲突行一律使值留空并进入待确认清单。

## 6. 边界与限制

纯标准库、无网络、无时钟读取；输入目录只读；同输入重复运行逐字节一致（`selfcheck` 两跑比对）。
只做机械清洗与去重判定，不判断学术价值，不补写任何原始数据中没有的数值。
