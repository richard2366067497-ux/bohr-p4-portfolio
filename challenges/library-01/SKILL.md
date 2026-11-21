---
name: library-repair-desk
description: 文件库盘点与修复 —— 扫描、命名规范化、去重、版本链修复、可回溯归档，产出契约化 result.json 与可复跑证据。用于科研文件库/资料库的整理、清洗、去重与版本合并任务。
version: 10.0.0
license: MIT
---

# library-repair-desk · 文件库盘点与修复

把一坨杂乱文件变成**可回溯、可复跑、可复核**的规范化文件库：盘点 → 命名规范 → 去重 → 版本链 → 归档 → 证据打包。

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 执行前必读（强制）

**执行前先阅读 `references/expert_playbook.md`，按其中的专家检查表逐项产出。** 该手册给出评分要点、高频错误→正确做法、量化公式、24 项自查表与完整案例，是产出质量的下限保障。本文件只描述命令接口与契约；方法论以 playbook 为准。

## 交付物与输出契约

每次运行都要在 `/app/output/` 写 `result.json`，并把契约键**原样**回填到 `result.json.output_contract`（不得改名、漏键、合并）：

```json
{
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

`case.json` 提供 `output_contract` 时以它为准；缺省时使用上表 6 键。主要产物：

| 产物 | 内容 |
|---|---|
| `result.json` | 契约信封 + `output_contract` 回填 + 运行状态 |
| `inventory.csv` / `inventory.json` | 逐文件清单：路径、大小、sha256、mtime、类型、可读性 |
| `operations.log` | 每次 copy/mkdir/dedupe/rename 的操作流水（可复跑） |
| `report.md` | 人读摘要：覆盖、重复、版本、跳过与风险 |
| `duplicates.json` / `version_chains.json` | 重复组与版本链（含判据） |
| `directory_plan.json` / `tree.txt` | 目标目录规划与树 |
| `recovery.json` / `self_check.json` | 回滚信息与自检报告 |

## 单命令等价入口（single command — one shot，无 draft，评测入口）

一条命令即完成整条流水线（等价于 init→build→selfcheck），直接产出完整契约与全部交付物；命令见文首「单命令评测入口」。

## Agent 路径（五命令，逐步）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

- `init`：扫描 `/input`（case.json、task.md、materials），写索引与合法的 partial `result.json`。
- `show`：打印文件、哈希、可读性、候选重复/版本；可加 `--notes/--queries` 看细节。
- `check`：校验 `/app/work/draft.json`，输出 FIX/WARN 清单（缺省时按规则表自动补齐）。
- `build`：落地规范化目录树 + 全部产物 + 最终 `result.json`（无 draft 也能跑）。
- `selfcheck`：复验产物、哈希与契约完整性。
- 退出码恒为 0；问题写进 `errors`/`degradations`，绝不伪造结果。

## 单命令等价入口（single command — one shot，无 draft）

见文首「单命令评测入口」——同一条 `all` 命令，一条命令跑完整条流水线。

## 规则要点

- 命名规范、去重与版本链判据见 `references/expert_playbook.md` §3；冲突或不可读文件必须记录原因与恢复方式，不得静默跳过。
- 只使用标准库；不联网；不读取 `/app/output` 之外的作者私有路径。

## 自检清单

- [ ] `result.json` 有效 JSON，且 `output_contract` 含全部契约键、值非空
- [ ] `deliverable` 等路径键指向真实非空产物
- [ ] `inventory.csv` 覆盖全部输入文件，均记录 sha256
- [ ] 重复组、版本链均有判据，无凭空合并
- [ ] 跳过/失败/冲突有记录与恢复方式
- [ ] 全部产物可复跑（命令、哈希、脚本版本齐全）
- [ ] **专家检查表逐项通过**（`references/expert_playbook.md` §6）
