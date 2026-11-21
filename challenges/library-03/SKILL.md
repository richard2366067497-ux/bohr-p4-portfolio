---
name: library-curator
description: 科研文献库编目、命名规范、去重与版本修复 —— 实际重构文件系统，产出可回滚、可复跑、幂等的分类目录与契约化 result.json。用于文献库整理、元数据补全、预印本/正式版版本合并等任务。
version: 10.0.0
license: MIT
---

# library-curator · 文献库编目与版本修复

把一批科研文献变成**规则驱动、可回滚、幂等**的规范化库：盘点 → 元数据 → 分类/标签 → 命名/去重/版本 → 执行 → 交付证据。

## 执行前必读（强制）

**执行前先阅读 `references/expert_playbook.md`，按其中专家检查表逐项产出。** 手册给出判分要点、错误做法→正确做法、量化公式与 17 项自查表，是质量下限；本文件只描述接口与契约。

## 交付物与输出契约

每次运行向 `/app/output/` 写 `result.json`，并把契约键**原样**回填 `result.json.output_contract`（不改名、不漏键）：

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

`case.json` 给出 `output_contract` 时以它为准。主要产物：`result.json`、`inventory.csv`、`classification.jsonl`、`renames.json`、`dedupe_versions.json`、`rollback.json`、`operations.log`。

## 单命令等价入口（single command — one shot，无 draft，评测入口）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

一条命令即跑完 init→build→selfcheck，直接产出完整契约与全部交付物：

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
```

## Agent 路径（五命令）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

- `init`：扫描 `/input`，建索引，写合法 partial `result.json`。
- `show`：列出文件、哈希、可读性、文本质量与候选归类依据。
- `check`：校验 `/app/work/draft.json`（无则按规则表补齐），输出 FIX/WARN。
- `build`：落地规范化库 + 全部产物 + 最终 `result.json`（无 draft 也可跑）。
- `selfcheck`：复验产物、回滚脚本与契约完整性。
- 退出码恒 0；异常写入 errors/degradations，不伪造。

## 单命令等价入口（single command — one shot，无 draft）

见文首「单命令等价入口（评测入口）」——同一条 `build` 命令，一条命令跑完整条流水线。

## 规则与约束

- 元数据只取原文文本层、PDF 元数据或 DOI，缺失标 `UNKNOWN`，不得凭文件名补造。
- 去重按 SHA-256；版本按 DOI/标题+作者区分，预印本与正式版并存；禁止无记录覆盖。
- 幂等：先查目标是否存在，存在则跳过并记录；重复运行不新增变更。
- 仅标准库；不联网。

## 自检清单

- [ ] `result.json` 有效，`output_contract` 含全部契约键且非空
- [ ] 路径键指向真实非空产物
- [ ] 每个文件有 SHA-256，缺失字段标 `UNKNOWN`
- [ ] 区分预印本/正式版并保留、建立版本关系
- [ ] 提供回滚记录/脚本，原路径可恢复
- [ ] 重复运行幂等（新增变更=0）
- [ ] 跳过/失败/冲突/无权限均有记录
- [ ] **专家检查表逐项通过**（`references/expert_playbook.md` §6）
