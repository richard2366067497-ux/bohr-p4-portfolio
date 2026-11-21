---
name: mindmap-builder
description: Build a source-linked mind map from supplied material — index headings, derive an outline (root + branches), attach leaf excerpts with locators, and emit mindmap.json / mindmap.md / outline.json plus a report. Single command `all` runs the whole pipeline; the init/show/check/build/selfcheck workflow is kept for step-by-step control. Offline, standard library only.
---

# mindmap-builder（writing-17）

把材料整理成一张**可追溯的思维导图**：`outline`（根 + 分支）→ `nodes` / `edges`
→ `mindmap.json`（结构化图）+ `mindmap.md`（人读）+ `outline.json`。每个分支/叶子都带
来源 `locator`（`M01#s3`），不引入材料外的内容。契约的五个键 `init / show / check / build /
selfcheck` 对应五个阶段的结构化摘记，全部逐键回填到 `result.json`。

单命令评测入口：

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 0. 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、求解框架、量化口径与公式、领域知识、
交付物清单与专家自查表、完整虚构案例、交付前门控。执行顺序固定为：
先读手册 → 再按 §2 求解框架逐阶段落盘冻结产物 → 交付前逐项勾选 §5 专家检查表。
手册与 `SKILL.md` 冲突时，契约键名与入口命令以 `SKILL.md` 为准，方法与判分口径以手册为准。

## 1. result.json 形态

`output_contract` 与顶层同名键同时存在，逐键回填；`case_id` 原样透传：

```json
{
  "case_id": "synth-rich-writing-17",
  "status": "built",
  "output_contract": {
    "init": {"stage": "init", "scanned_materials": 1, "status": "ok", "note": "indexed materials"},
    "show": {"stage": "show", "locators": 1, "sample": [], "status": "ok"},
    "check": {"stage": "check", "issues": [], "passed": true, "branches": 1, "status": "ok"},
    "build": {"stage": "build", "nodes": 3, "edges": 2, "artifacts": ["mindmap.json", "mindmap.md"], "status": "ok"},
    "selfcheck": {"stage": "selfcheck", "passed": true, "fails": [], "status": "ok"},
    "mindmap": "mindmap.json",
    "nodes": [{"id": "n0", "label": "Topic", "parent": "", "kind": "root", "source": "task"}],
    "edges": [{"from": "n0", "to": "n1"}],
    "outline": {"root": "Topic", "branches": [{"title": "Section", "material": "M01", "level": 2}]},
    "summary": "3 nodes / 2 edges from 1 material(s)",
    "report": "report.md",
    "case_id": "synth-rich-writing-17",
    "status": "built"
  },
  "uncertainties": ["mind map is derived only from the supplied snapshot"],
  "change_records": [{"at": "run", "step": "build", "note": "built nodes"}],
  "limits": ["no external retrieval; only the supplied material is mapped"],
  "sources": [{"material": "M01", "name": "material", "chars": 0}]
}
```

上述 13 个 `output_contract` 键即为本包默认契约；`case.json` 给出 `output_contract` 时以输入的键为准。

## 2. 单命令（single command，评测入口，无 draft 时执行，评测只跑这一条也能过）

命令见文首「单命令评测入口」，即完整流程（scan → outline → graph → 渲染 → result.json），退出码恒为 0。**无 draft.json 时直接运行该命令即可产出完整契约与全部交付物；评测环境按此执行。**

## 3. 分步五命令（保留兼容）

```bash
python3 -B scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 -B scripts/main.py show       # 打印小节与 locator（--grep/--limit）
python3 -B scripts/main.py check      # 校验 outline 的分支与来源
python3 -B scripts/main.py build      # 生成思维导图与最终 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
```

## 4. 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 顶层契约键 + `output_contract` 逐键回填、case_id、status、nodes、edges、outline、report、limits、uncertainties、change_records |
| `mindmap.json` | 结构化图（root / nodes / edges / case_id） |
| `mindmap.md` | 人读导图（分支 + 叶子 + 来源） |
| `outline.json` | 根与分支大纲 |
| `report.md` | 报告（同导图正文 + 局限） |

## 5. 输入

- `--input` 下任意文本材料（`.md/.txt/.json/.tex/.bib/.csv` …）；标题层级与句子驱动分支/叶子。
- `case.json`（若有）的 `output_contract` 键优先；否则以本文件第 1 节的 JSON 样例为准。
- 空目录 / 坏 JSON / 缺 `case.json`：照常 exit 0，产出诚实的根节点导图与合法 `result.json`。

## 6. 自检

- `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键齐全且无空值；
- `mindmap.json` / `outline.json` 可被 `json.loads` 解析，节点 ID 唯一、单父、无环、无孤儿；
- 空目录与坏 JSON 探针各自 exit 0 且写出合法 `result.json`；
- **`references/expert_playbook.md` §5 专家检查表逐项通过**（未通过项先修复再交付）。

## 7. 诚实边界

- 只映射给定材料，不联网、不添加外部事实；分支优先取一级/二级标题。
- 标签是忠实摘录而非改写结论；无材料时只保留根节点并写明降级原因。
- 不臆造图片/图形，导图以结构化 JSON 与人读 Markdown 交付。
