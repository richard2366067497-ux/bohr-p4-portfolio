---
name: evidence-first-pdf-reader
description: 布局感知的论文阅读技能。单条命令把输入解析成"页/区域锚点 + 阅读顺序 + 章节结构 + 表格候选 + 公式线索 + 待 OCR 页"的证据化 result.json；只依据文本层与几何布局作答，不臆造、不转述图像页。无 PDF 时如实降级为"文本逐行锚点"并写明 limits。
---

# evidence-first-pdf-reader — 证据优先的论文阅读

**任务族**：reading-01 · 文献内容解析（页/区域锚点、阅读顺序、章节/表格/公式清点）。
**形态**：离线、纯标准库、确定性。没有 PDF 时可读文本时**逐行锚定**并诚实标注缺失的版面信息。

核心原则：每条结论都能回溯到具体 locator（`p01-l003` 或 `<file>:L12`）并附原文 `quote`；
读不到的页/文件进入 `unreadable` 与 `limits`，绝不编造文字或把类型串当结果。

## 0. result.json 契约样例（output_contract 逐键回填，顶层 + 嵌套）

`result.json` 把**用例声明的每一个 `output_contract` 键**写进 `output_contract` 对象，
并在顶层写入同名键。每个值都是**真实推导结果**、真实产物路径或诚实的结构信封
`{"kind","status","items","count","note"}`——绝不写 `"value"` / `"array"` 这类类型串。
用例未给契约时使用下列默认 10 键：

```json
{
  "case_id": "synth-example-reading-01",
  "status": "partial",
  "output_contract": {
    "document": {"pdf_present": false, "title": "paper title", "scope": "text-only", "page_count": 0},
    "blocks": [{"id": "b0001", "locator": "task.md:L1", "source": "task.md", "order": 1, "text": "verbatim line"}],
    "sections": [{"text": "Introduction", "level": 1, "locator": "task.md:L12", "source": "task.md"}],
    "tables": [{"kind": "markdown_table", "locator": "materials/x.md:L4 .. L8", "headers": ["a", "b"], "row_count": 3, "rows": [["1", "2"]]}],
    "formulas": [{"locator": "materials/x.md:L20", "text": "E = mc^2", "confidence": "candidate"}],
    "reading_order_notes": "documents in task -> materials -> case order; ascending line number inside each",
    "unreadable": [{"item": "pdf", "reason": "no PDF present in the input tree", "locator": "input"}],
    "sources": [{"source_id": "S01", "path": "task.md", "locator": "task.md:L3", "quote": "verbatim text", "sha256": "hex"}],
    "uncertainty": [{"item": "no-pdf", "reason": "layout unavailable", "manual_check": "attach the PDF"}],
    "change_records": [{"step": "blocks", "change": "anchored 42 line(s)", "reason": "line-level provenance"}]
  }
}
```

- `sources` **必须非空**：至少一条逐字引文 + `locator`（无 PDF 时来自 `task.md`/材料文本）。
- 空列表不会被写成 `[]` 占位，而是换成带 `note` 的结构信封，并记入 `unreadable`/`uncertainty`。
- `case_id` 从 `case.json`（`case_id`/`caseId`/`id`/`task_id`）透传。

## 1. 单命令入口（single-command entry，一次性跑完）

```bash
python3 pdf_layout_extract.py all --input /input --out /app/output --work /app/work
```

这一条命令完成：输入清单 → PDF 布局抽取（无 PDF 则文本逐行抽取）→ 阅读顺序 → 章节/表格/公式清点
→ 写 `result.json` 与全部结构化产物。无草稿、无多阶段人工介入；空输入/坏输入同样 **exit 0**。

历史别名（等价，仍支持）：

```bash
python3 pdf_layout_extract.py --input /input --out /app/output --work /app/work --full
```

单阶段布局 JSON（调试用）：

```bash
python3 pdf_layout_extract.py /input/paper.pdf --output /app/work/paper.layout.json
```

## 2. 状态语义（诚实，由产物推导）

| status | 触发 |
|-|-|
| `success` | 有 PDF 文本层、每页文本量达标、无待 OCR 页，且有 answer + evidence |
| `partial` | 有文本材料但无 PDF；或有待 OCR 页；或仅有启发式产出 |
| `cannot_determine` | 有 PDF 但整篇无可读文本层（疑似扫描件） |
| `failed` | 无 PDF 且除题面外无可读材料；或输入不可读 |

无 PDF 时输出 `limits`，逐条说明"版面/图/扫描页不可读、不做 OCR 转述"。

## 3. 工作流（脚本内部步骤）

1. **manifest**：枚举输入，记录相对路径/字节/sha256，定位 PDF、`task.md`、`case*.json`。
2. **layout**：`pdftotext -layout` → PyMuPDF → **stdlib 流解析器**依次探测，失败原因记入 `layout.attempts`。
3. **reading_order**：有坐标时按页宽/列间距切分双栏；无坐标时保持抽取顺序。
4. **text fallback**：无 PDF 时按 `task.md → materials → case 元数据` 顺序逐行读取，跳过空行与
   未填写/空值类标记行（记入 `unreadable`），产出真实 `blocks/sections/tables/formulas`。
5. **sections/tables/formulas**：编号标题 + 标准章节名；markdown 管道表逐格复制；TeX 线索只标候选。
6. **result**：回填契约（顶层 + `output_contract`）、逐字 `sources`、`uncertainty`、`change_records`、`limits`。

## 4. 输出产物（写入 `--out`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：契约逐键回填（顶层 + `output_contract`）、`case_id`、`status`、证据、来源、不确定性、变更记录、limits |
| `document.json` | 文档级信息：是否含 PDF、标题、页数、文本文件清单、输入文件 sha256 |
| `blocks.json` | 逐行区块与 locator（`<file>:L<n>` 或 `p01-l003`） |
| `sections.json` | 章节/标题层级 |
| `tables.json` | 表格（PDF 候选 / markdown 逐字表） |
| `formulas.json` | 公式线索（candidate，需人工核对） |
| `reading_order.md` | 阅读顺序说明（列切分规则或文本顺序规则） |
| `sources.json` | 逐字引文 + locator + sha256 |
| `unreadable.json` | 读不到的文件/页/被跳过的标记行及原因 |
| `uncertainty.json` | 需人工确认的点 |
| `change_records.json` | 本次运行做过的步骤与原因 |

## 5. 异常与降级（始终 exit 0）

| 情形 | 处置 |
|-|-|
| 无 PDF | 文本逐行锚定；`status=partial`（有材料）或 `failed`（仅题面），`limits` 说明版面缺失 |
| 空文件 / 坏 JSON | 记入 `unreadable`，继续处理其余输入，仍写全部产物 |
| PDF 加密 / 损坏 | `status=failed`，原因写入 `answer`/`change_records`，仍写合法 result.json |
| 图像页（无文本层） | 列入 `pages_needing_ocr` / `unreadable`，`status=partial` 或 `cannot_determine`，**不转述** |
| 任意内部异常 | 顶层兜底，写出最小合法 result.json 并 **exit 0** |

## 6. 文件索引

| 文件 | 角色 |
|-|-|
| `pdf_layout_extract.py` | 入口与主编排（PDF/文本双路径、阅读顺序、表格/公式/OCR、result 组装） |
| `section_structure.py` | 章节/标题识别（可独立运行） |
| `evidence_reconcile.py` | 证据—区域对账（PDF 路径） |
| `audit_result.py` | 契约审计，驱动 status 降级（PDF 路径） |
| `references/result_contract.md` | 字段字典、状态规则、回填示例 |

安装与自测见同目录 README.md 与 SELFTEST.md；仓库地址见 GITHUB_URL.txt。
