# evidence-first-pdf-reader — 证据优先的论文阅读（reading-01 v6）

把输入（PDF 或纯文本材料）解析成**可回溯到页/区域/行**的结构化阅读结果：一条命令产出
`result.json` 与全部结构化产物；每条结论附原文 `quote` 与 `locator`；读不到的内容如实进入
`unreadable` 与 `limits`，不臆造、不转述图像页。

## 安装

无需第三方依赖（Python 3.9+ 标准库）。放到 `/skills/weekly-skill` 即可：

```
/skills/weekly-skill/
  SKILL.md
  pdf_layout_extract.py
  section_structure.py
  evidence_reconcile.py
  audit_result.py
  references/result_contract.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

解析文本层 PDF 时会探测 `pdftotext`（Poppler）与 `pymupdf`；两者都没有时回退到内置的
stdlib PDF 流解析器，仍可读出 `Tj/TJ` 文本层。

## 用法

单命令全流程（评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/pdf_layout_extract.py all \
  --input /input --out /app/output --work /app/work
```

等价的旧别名：`... --input /input --out /app/output --work /app/work --full`。

- 无 PDF：自动切到**文本逐行锚点**路径，产出 `blocks/sections/tables/formulas/sources`，
  并写明 `limits`（版面/图/扫描页不可读）。
- 无材料、只有题面：`status=failed`，仍写合法 `result.json` 与全部产物。
- 空文件 / 坏 JSON：记入 `unreadable`，不中断，**exit 0**。

其他入口：

```bash
python3 pdf_layout_extract.py all --input /input --out /app/output --work /app/work   # 全流程
python3 section_structure.py /app/work/paper.layout.json /app/work/sections.json      # 单阶段调试
python3 pdf_layout_extract.py /input/paper.pdf --output /app/work/paper.layout.json   # 只出布局 JSON
```

退出码恒为 0（含全部降级）；仅 argparse 用法错误返回 2。

## 产物（写入 `--out`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：契约逐键回填（顶层 + `output_contract`）、`case_id`、`status`、evidence、sources、uncertainty、change_records、limits |
| `document.json` | 文档级信息（是否含 PDF、标题、页数、输入 sha256） |
| `blocks.json` | 逐行区块 + locator（`<file>:L<n>` 或 `p01-l003`） |
| `sections.json` | 章节/标题层级 |
| `tables.json` | 表格（PDF 候选 / markdown 逐字表） |
| `formulas.json` | 公式线索（candidate，需人工核对） |
| `reading_order.md` | 阅读顺序说明 |
| `sources.json` | 逐字引文 + locator + sha256 |
| `unreadable.json` | 读不到的页/文件/被跳过的标记行及原因 |
| `uncertainty.json` | 需人工确认的点 |
| `change_records.json` | 本次运行步骤与原因 |

## 限制

- 不联网、不安装工具；不做 OCR：图像页只列出，绝不转述。
- 表格是候选、公式是线索，均须对照页面核对；文本表的单元格逐字复制。
- 无 PDF 时不断言任何版面/页序；`limits` 逐条写明缺口。

## 维护

版本 2.0.0；契约键名冻结，规则判据集中在 `SKILL.md` 与 `references/result_contract.md`。
自测见 `SELFTEST.md`。
