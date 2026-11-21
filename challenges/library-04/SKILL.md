---
name: kb-version-qa
description: 科研知识库盘点、元数据/版本管理与带来源引用的问答 —— 生成可回链证据的答案与契约化 result.json。用于跨文件检索问答、证据定位、缺证判断与版本/重复识别的任务。
version: 10.0.0
license: MIT
---

# kb-version-qa · 科研知识库版本问答与证据回链

把一批科研文件变成**可问答、可回链、可复核**的知识库：盘点 → 元数据 → 版本/去重 → 检索问答 → 证据回链 → 不确定性分级 → 打包。

## 执行前必读（强制）

**执行前先阅读 `references/expert_playbook.md`，按其中专家检查表逐项产出。** 手册给出五维判分、错误做法→正确做法、量化公式、locator 五元组与 24 项自查表，是质量下限；本文件只描述接口与契约。

## 交付物与输出契约

向 `/app/output/` 写 `result.json`，并把契约键**原样**回填 `result.json.output_contract`：

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

`case.json` 给出 `output_contract` 时以它为准。主要产物：`result.json`、`LIBRARY_REPORT.md`、`inventory.csv`、`kb_index.json`、`kb_stats.json`、`answers.json`、`operations.json`。

## Agent 路径（五命令，注意输出参数是 `--out`）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --out /app/output
```

- `init`：扫描 `/input`，建索引，写合法 partial `result.json`。
- `show`：列出文档、元数据、重复/版本候选与问答草稿依据。
- `check`：校验 `/app/work/draft.json`（无则按规则表补齐）。
- `build`：落地知识库索引、问答、证据、统计与最终 `result.json`（无 draft 也可跑）。
- `selfcheck`：复验产物与契约完整性。退出码恒 0，异常写入 errors/degradations。

## 单命令等价入口（single command — one shot，无 draft）

一条命令跑完 init→build→selfcheck，直接产出完整契约与全部交付物：

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --out /app/output
```

## 规则与约束

- 引用必须是五元组 locator：`file_id + version + page + para + quote`，quote 逐字一致。
- 版本/重复按 SHA-256 + 内容 diff 判定；扫描件无文本层标 `text_extractable=false`，不伪造。
- 无依据的问题必须回答「知识库中未找到依据」，说明缺什么、建议补什么。
- 仅标准库；不联网。

## 自检清单

- [ ] `result.json` 有效，`output_contract` 含全部契约键且非空
- [ ] 路径键指向真实非空产物
- [ ] 每个文件有 SHA-256，权限/不可读已记录
- [ ] 重复与版本关系有哈希/diff 依据
- [ ] 每个关键论断有 locator 且 quote 逐字匹配
- [ ] 无依据问题明确判缺证并说明
- [ ] 跳过/失败/冲突/恢复均有记录
- [ ] **专家检查表逐项通过**（`references/expert_playbook.md` §6）
