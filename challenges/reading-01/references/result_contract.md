# result.json 契约与字段字典

`all`（或 `--full`）结束时写 `<out>/result.json`（UTF-8，缩进 2）。字段名冻结。契约回填规则：

- **用例声明的每一个 `output_contract` 键**都写进 `output_contract` 对象，并在**顶层写入同名键**；
- 每个值必须是**真实推导结果**、真实产物路径，或诚实的结构信封
  `{"kind","status","items","count","note"}`；**绝不写** `"value"`/`"array"` 这类类型串；
- 空列表不写成 `[]` 占位，而是换成带 `note` 的结构信封，并在 `unreadable`/`uncertainty` 说明缺口；
- 用例未提供契约时使用本技能默认的 10 键（下节示例）。

## 顶层字段

| 字段 | 类型 | 说明 |
|-|-|-|
| `case_id` | string | 取自 `case.json`（`case_id`/`caseId`/`id`/`task_id`），取不到为空串，绝不编造 |
| `status` | enum | `success` \| `partial` \| `cannot_determine` \| `failed`（规则见下） |
| `answer` | string | 人类可读结论摘要（无 PDF 时说明为什么缺、缺什么） |
| `result` | object | `{answer, structured[], document_structure[], claims[], relations[]}` |
| `evidence` | array | `{claim, source, page, region, quote, type, confidence}`，逐条可回溯 |
| `sources` | array | `{source_id, path, locator, quote, sha256, kind}` —— **无 PDF 时也非空** |
| `uncertainty` / `uncertainties` | array | `{item, reason, manual_check}` |
| `unreadable` | array | `{item, reason, locator}`：读不到的页/文件、被跳过的标记行 |
| `change_log` / `change_records` | array | `{step, change, reason}` |
| `limits` | array | 本次运行的诚实边界（版面缺失、未做 OCR 等） |
| `document` | object | 文档级信息（是否含 PDF、标题、页数、输入清单与 sha256） |
| `output_contract` | object | 逐键回填的契约对象（键来自用例，或本技能默认 10 键） |
| `runtime` | object | `{skill, python, mode, network}` |

## 默认契约键（无 `case.json` 契约时）

`document`、`blocks`、`sections`、`tables`、`formulas`、`reading_order_notes`、`unreadable`、
`sources`、`uncertainty`、`change_records`。

## status 规则（诚实，由产物推导）

- `success`：取得 PDF 文本层，且每页文本量达标（无待 OCR 页），已产出 `answer` 与 ≥1 条 `evidence`。
- `partial`：有文本材料但**无 PDF**；或存在文本量不足/需 OCR 的页；或仅启发式产出。
- `cannot_determine`：整篇无可读文本层（疑似扫描件）；只说明缺什么，不转述。
- `failed`：无 PDF 且除题面外无可读材料；或输入不可读。

## 证据回填与审计

- PDF 路径：`evidence_reconcile.reconcile(result, layout)` 校验每条 `evidence.region` 是否落在布局中；
  `audit_result.audit(result)` 校验必填键与契约回填。审计不过则把 `status` 由 `success` 降为 `partial`。
- 文本路径：`sources`/`evidence` 直接以 `<file>:L<n>` 作为 `region`，逐字引文与 locator 一一对应。

## 回填示例（片段）

用例：`{"output_contract": {"document": "object", "sources": "array"}}`

回填后：

```json
{
  "document": {"pdf_present": false, "title": "…", "page_count": 0},
  "sources": [{"source_id": "S01", "path": "task.md", "locator": "task.md:L3", "quote": "…"}],
  "output_contract": {
    "document": {"pdf_present": false, "title": "…", "page_count": 0},
    "sources": [{"source_id": "S01", "path": "task.md", "locator": "task.md:L3", "quote": "…"}]
  }
}
```

说明：契约键的值就是真实推导结果本身（顶层与嵌套同源），不是类型串回显；`null` 不会被当作结果写出。

## 中间产物（与 result.json 同目录，PDF 路径）

`<stem>.layout.json`、`<stem>.ordered.json`、`<stem>.sections.json`、`<stem>.tables.json`、
`<stem>.formulas.json`、`<stem>.ocr.json` 同时写入 `--work` 与 `--out`。

## 最小调用示例

```bash
python3 pdf_layout_extract.py all --input /input --out /app/output --work /app/work
```
