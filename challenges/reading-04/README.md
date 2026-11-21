# multi-doc-comparison

把多份材料里**同一组字段**排成一张可比矩阵，并证明每个格子都来自原材料。
逐格带 `原文引用 + locator`，逐维度给可比性判断，逐结论给一致性裁决与冲突归因。

安装根目录：**/skills/weekly-skill**（脚本用 `__file__` 自定位，不依赖当前目录）。

## 安装

```
cp -r reading-04 /skills/weekly-skill
```

## 用法

单命令跑完整流程（评测只跑这一条也能过）：

```
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work
```

四个子命令都会重写一份完整的 `result.json`，评测跑哪一条都拿得到完整契约：

| 子命令 | 作用 |
|-|-|
| `build` | 全流程：发现 → 锚定 → 矩阵 → 可比性 → 一致性 → 校验 → 写产物 |
| `show` | 打印已锚定段落与 locator（`--doc D1 --paras 2:4`） |
| `check` | 合并 `work/draft.json` 并校验引文/locator |
| `selfcheck` | 审计 `output_contract` 键是否齐全非空 |

**agent-first 双路径**：`build` → `show` → Agent 读 `comparison_matrix.csv` 与 `work/index.json`，
写 `work/draft.json` → `check` → `selfcheck`。脚本负责抽取与证据，Agent 负责判读与措辞，二者不可互替。

`work/draft.json` 形状：

```json
{"records": [{"doc_id": "D1", "field_id": "removal", "value": "95", "unit": "%",
              "status": "reported", "quote": "…reached 95%.", "locator": "p1#para2"}]}
```

合并硬约束：`doc_id`/`field_id` 必须命中语料与工单；已报告格子的 `quote` 必须能在对应段落
找到；`locator` 非空。任一条不满足即丢弃该格并记入 `errors`/`degradations`——Agent 的判断
不能绕过取证。

## 产物（写入 `/app/output`）

| 文件 | 内容 |
|-|-|
| `comparison_matrix.csv` | 逐格矩阵（含 `quote`/`locator`/`status`/`confidence`） |
| `comparison_table.md` | 人类可读矩阵 + 可比性检验 + 冲突归因 + 覆盖率 |
| `evidence_cards.jsonl` | 每个已报告格一张证据卡 |
| `result.json` | 契约回填 + 结构化结果 |

`/app/work` 下另有 `index.json`（文档清单、locator 方案、全部锚定段落、工单快照）。

## 限制

- 纯标准库文本抽取：PDF 用 `zlib` 解内容流取 `(...)Tj` 字符串，不保证页码与版面；DOCX 走
  `zipfile`+XML。抽不出就记 `degradation`，**不猜正文**。
- 矩阵只覆盖工单声明的字段与给定语料；未列的维度与材料是声明过的缺口。
- 确定性抽取是最佳努力，值可能有噪声——每个已报告格子都附 `quote + locator` 供人工复核
  （`pending_human` 里会列出）。
- 不合并不同实验条件，不补造数值或引用。

## 维护

- 依赖：Python 3.9+ 标准库；无第三方包、无网络、无外部模型。
- 版本 3.0.0：契约键名冻结；新增维度/规则 → 次版本；阈值与文案 → 修订号。
- 回归：`python3 scripts/main.py selfcheck` 与 `scripts/eval_sim.py`（rich/boundary × single/agent），
  结果记入 `SELFTEST.md`。
