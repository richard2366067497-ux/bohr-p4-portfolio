# 思维导图规格（writing-17）

## 契约五键（也是五命令）

| 键 / 命令 | 阶段 | 结构（始终非空 dict） |
|-|-|-|
| `init` | 建索引 | `stage, scanned_materials, scanned_sections, status, note` |
| `show` | 预览 | `stage, locators, sample, status` |
| `check` | 校验 | `stage, issues, passed, branches, status` |
| `build` | 构图 | `stage, nodes, edges, artifacts, status` |
| `selfcheck` | 复检 | `stage, passed, fails, status` |

五个键既作为 `total`/`result.json` 的顶层字段，也出现在 `output_contract` 中，值相同。

## 大纲与图

- `outline.json`：`{root, branches:[{title, material, level}]}`；root 取 task 的一级标题或首个小节。
- `mindmap.json`：`{root, nodes, edges, case_id}`；
  - node：`{id, label, parent, kind: root|branch|leaf, source}`
  - edge：`{from, to}`
- `mindmap.md` / `report.md`：分支 + 叶子（忠实摘录）+ 来源 `locator` + 局限。

## 来源 locator

`<material_id>#s<k>`，例如 `M01#s3`，表示第 1 份材料的第 3 个小节；根部来源为 `task` 或 `none`。

## 诚实边界

- 只映射给定材料，不联网、不添加外部事实。
- 分支优先取一级/二级标题；正文句子只做叶子摘录，不改写为结论。
- 无材料时仅保留根节点，`degradations` 记录原因，`status=insufficient_evidence`。
