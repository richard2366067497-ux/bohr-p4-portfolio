---
name: annotation-ledger
description: 阅读批注抽取与知识沉淀 —— 提取 PDF/扫描件批注，结构化笔记，建立可回溯的知识关联与可检索索引，产出契约化 result.json。用于阅读批注整理、笔记沉淀、跨版本批注归并与检索入库的任务。
version: 10.0.0
license: MIT
---

# annotation-ledger · 阅读批注抽取与知识沉淀

完成闭环：**批注提取 → 笔记结构化 → 知识关联 → 检索入库 → 可核验交付**。每条批注可回到原文件具体页与位置；每条笔记可找到支撑原文；每条关联有依据；整条流程可复跑。

## 执行前必读（强制）

**执行前先阅读 `references/expert_playbook.md`，按其中专家检查表逐项产出。** 手册给出判分要点、错误做法→正确做法、量化公式、20 项自查表与完整案例，是质量下限；本文件只描述接口与契约。

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

`case.json` 给出 `output_contract` 时以它为准。主要产物：`result.json`、`files.json`、`annotations.jsonl`、`notes.jsonl`、`links.json`、`provenance.json`、`ledger.md`、`index.json`、`queries.json`。

## Agent 路径（五命令）

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

- `init`：扫描 `/input`，建索引，写合法 partial `result.json`。
- `show`：打印文档/页/批注与 locator（可加 `--doc --page --chars --ann`）。
- `check`：校验 `/app/work/draft.json`（无则按规则表补齐）。
- `build`：抽取批注、结构化笔记、建关联与检索索引，写最终 `result.json`（无 draft 也可跑）。
- `selfcheck`：复验产物与契约完整性。退出码恒 0，异常写入 errors/degradations。

## 单命令等价入口（single command — one shot，无 draft）

一条命令跑完 init→build→selfcheck，直接产出完整契约与全部交付物：

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output
```

## 规则与约束

- 每条批注须带 `file_hash + page + rect/quad + type + color + raw_text`；区分 highlight/underline/margin_note/handwritten/sticky_note。
- 每条笔记须有 `note_id + type + claim + source_annotation_ids + locator`。
- 关联须写明依据（same_doi / text_similarity / version_chain / same_entity + context_overlap）。
- 重复文件按 sha256；版本按 DOI/标题建链；OCR 低置信度标 `low_confidence`。
- 仅标准库；不联网。

## 自检清单

- [ ] `result.json` 有效，`output_contract` 含全部契约键且非空
- [ ] 路径键指向真实非空产物
- [ ] 每条批注有页/坐标/类型/颜色/原文
- [ ] 每条笔记有 source_annotation_ids 与 locator
- [ ] 每条关联有 basis 依据
- [ ] 重复/版本已归并，低置信度已标记
- [ ] 跳过/失败/权限不足/恢复均有记录
- [ ] **专家检查表逐项通过**（`references/expert_playbook.md` §6）
