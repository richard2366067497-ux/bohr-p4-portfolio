---
name: structured-reading
description: 把 PDF 或多份 md/txt 读成按阅读顺序排列的页面对象，派生标题/作者/摘要/章节/表格/公式/图表题注/参考文献，每项带 locator 与逐字引文可核回原文；纯标准库离线，读不出的内容诚实降级为 unreadable。
---

# structured-reading

结构化阅读（提得全 / 排得对 / 拆得清 / 核得回）：把一个 PDF 或多份 md/txt 读成
**按阅读顺序排好的页面对象**，再派生出标题、作者、摘要、章节、表格网格、公式、图表题注、
参考文献、脚注；每一项都带 `locator`（`file pN object type`）和**逐字**引文，都能核回原文。

纯标准库、离线。文本层用 zlib + 对象扫描自建（不依赖 xref），可选加速器 `pymupdf` 只在环境里
已安装时才用。读不出来的东西一律进 `unreadable`，绝不猜字。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 七步框架（含门控）** 推进——锁定契约 → PDF 预检 → 原始提取 → 版面与阅读顺序
  → 特殊结构 → 完成案例任务 → 定向核验 → 原子交付；前一步未冻结不进入下一步。
- **口径**：按其 **§3 文本与阅读顺序口径** 与 **§4 表格/公式/证据口径** 逐项核验，原始层与规范化层分开保存。
- **门槛**：按其 **§5 建议内部门控** 判定字符准确率、阅读顺序、表格 F1 与证据覆盖率；扫描件不设脱离图像质量的统一承诺。
- **陷阱**：按其 **§6 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过其 **§9 防扣分自查表（24 项）**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainty`，绝不静默提升为完整成功。

## 1. 适用输入

| 输入 | 处理 |
|-|-|
| PDF（有文本层） | 重建页面对象 → 阅读顺序 → 结构 → evidence |
| md / txt / tex / rst / html | 作为单页正文处理；说明"无版面几何，列/表格不可恢复" |
| 空文件 / 只有笔记的文件 / 坏 JSON | 记 `empty-file` / `note-only` / `invalid-json`，不冒充正文 |
| PNG / DOCX / 扫描件 / 含 NUL 的文件 | 记 `unparsed-binary`，不猜字 |

## 2. 评测契约（`output_contract` 示例，10 键）

契约来自 `case.json`（有则优先），否则取本文件这段示例；`result.json` 顶层与
`output_contract` 内各回填一份，值都非空（没有可读材料时是
`{"count": 0, "items": [...], "note": "读不到的原因"}`，仍然是完整字段）。

```json
{
  "output_contract": {
    "document": "value",
    "blocks": "value",
    "sections": "value",
    "tables": "value",
    "formulas": "value",
    "reading_order_notes": "value",
    "unreadable": "value",
    "sources": "value",
    "uncertainty": "value",
    "change_records": "value"
  },
  "case_id": "value"
}
```

字段含义：

- `document` — 依据的文件、页数、使用的引擎、字符数、标题。
- `blocks` — 阅读顺序中的页面对象（`count` / `by_type` / 每行 `locator` + 逐字引文 + sha）。
- `sections` / `tables` / `formulas` — 章节（含层级）、表格网格（行列数与表头）、公式（含编号）。
- `reading_order_notes` — 每页的分栏/栏沟决策、被排除的页眉页脚带。
- `unreadable` — 读不到的文件与原因；`sources` — 输入目录里所有文件（读没读都列）。
- `uncertainty` — 本次阅读的边界；`change_records` — 每一步顺序或字段改动（可逆、带 locator）。

## 3. 草稿模式（`work/draft.json`，可选）

```json
{
  "source_file": "value",
  "items": [
    {"field": "title", "value": "value", "locator": "value", "why": "value"}
  ]
}
```

`field` ∈ title / authors / abstract / section / table / formula / caption / reference。
`value` 为空、或 `locator` 不是本文件的页面对象 → 该条被拒并写进 work/check_report.json；
接受的条目会额外产生一条 `draft_override_applied` 的 `change_record`。没有草稿时全部字段由
程序自己派生，产出完全一致。

## 4. 单命令（等价入口，one-shot，评测入口）

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` = `build` + `selfcheck`。**不需要任何草稿**：没有 `work/draft.json` 时它自己给出全部
契约字段与全部交付物，退出码 0。材料不可读时同样退出 0，把原因写进 `unreadable` / `sources`
/ `uncertainty`，契约字段仍然完整非空。

## 5. agent 增强路径（与 `all` 同源，同一引擎）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work --find table
python3 /skills/weekly-skill/scripts/main.py check     --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

- `init`：写 work/source_index.json、work/draft_template.json，并**自动生成候选**
  work/draft_candidates.json（title / authors / abstract / section / table / formula / caption /
  reference 每一项都带 `locator` 与依据）。
- `show`：按 `--find` 打印对象和候选；`--mat` 只看某个文件。
- `check`：只接受 locator 能解析到本文件页面对象的条目；其余写进 work/check_report.json，原文不变。
- `build`：确定性路径，与单命令产出完全一致；`selfcheck` 复核文件、契约与占位符清扫。

## 6. 交付物

| 文件 | 内容 |
|-|-|
| `parsed.md` | 人读的阅读结果：标题/作者/摘要/章节/阅读顺序正文/表格/公式/题注/参考文献/排序说明 |
| `structure.json` | 结构化字段，每项带 `locator` 与逐字 `quote` |
| `evidence.json` | 逐字证据行：`claim_id` `kind` `page` `locator` `quote` `sha256_16` |
| `coverage.json` | 每个检查项做了没有 + `missing` 列表 |
| `page_map.json` | 每页尺寸、分栏数、栏沟、对象 bbox |
| `output/layout_objects.jsonl` | 原始层：每个对象一行（含被排除的页眉页脚） |
| `unreadable.json` | 读不到的文件与原因 |
| `result.json` | 契约回填 + `status` / `sources` / `uncertainty` / `change_records` / `draft_candidates` |
| `output/self_check.json` | 文件齐全、契约回填、占位符清扫的自检 |

work 目录另外留 source_index.json、draft_template.json、draft_candidates.json、
check_report.json、compare_report.json、analysis_state.json。

## 7. 规则与边界

- 版式：列起点聚类找第二栏左边缘（表格加宽不会移动左边缘，所以表格伪装不了分栏）；栏沟 =
  左栏末端到右栏左边缘；同一行跨沟但字距 < 9pt 的视为整行（标题/摘要不会被切碎）。
- 阅读顺序：先按栏带（0..左栏末 / 右栏起..页宽），栏内自上而下；跨满宽的对象结束当前栏带。
- 页眉页脚：页外带内、且在 ≥3 页（≤3 页的文件取 ≥2 页）重复出现的行标为 running matter，
  保留在 layout_objects.jsonl 但排除出阅读顺序。
- 诚实边界：自由排版没有栏沟时按自上而下排序；无文本层的扫描件不可读；纯文本材料没有版面几何；
  表格从连续行对象重建，合并单元格会被拆开；公式按"含数学符号且有运算符"的行识别。

完整的规则、测试矩阵与已知失败模式见本目录的 SELFTEST.md 与 README.md。

## 8. 降级与失败注入

| 情形 | 结果 |
|-|-|
| 输入目录不存在 / 空 | `status=insufficient_evidence`，契约 10 键齐全，交付物全部写出，退出 0 |
| 有文件但都读不了 | 同上，`sources` 列出每个文件与原因，`unreadable` 给原因 |
| 部分可读 | `status=partial`，可读的照常解析 |
| 单文件 > 500KB | 截断并在 `uncertainty` 与 `sources.reason` 中说明 |
| 目录 > 60 个文件 | 读前 60 个，其余记入 `errors` |
| 运行中任何异常 | 仍写出 `result.json`（`status=input_error`），退出 0 |

## 9. 参考

- README.md — 安装、快速开始、文件清单、维护顺序。
- SELFTEST.md — 实测数字、单命令/agent 双路径、边界降级、测试矩阵。
- GAIN_EVIDENCE.md — 同输入同契约下，基线与本 skill 的质量/效率对照（`compare` 命令复现）。
- `examples/case.json` — 契约样例（材料由平台隐藏案例提供）。
- `environment/resources.yaml` — 资源入口声明。

## 10. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符。
- [ ] `blocks` / `sections` / `tables` / `formulas` 中每项都带 `locator` 与逐字引文。
- [ ] `unreadable` / `uncertainty` 如实记录读不到的文件与原因，不猜字。
- [ ] `parsed.md` / `structure.json` / `evidence.json` / `coverage.json` / `page_map.json` 均非空且可互相核对。
- [ ] 空输入 / 全是坏文件两条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的 24 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainty`，绝不静默提升为完整成功。
