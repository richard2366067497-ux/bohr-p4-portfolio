# reading-client v3.0.0

忠实适配自 P3 `reading-05` 参考包（参考分 68）：保留其**入口语义**
（`scripts/main.py --input /input --output /app/output`）、**七步阅读闭环**
（open/locate/select/ask/save/review/export）、**产物名**
（`reading_record.md`、`golden_standard.json`、`diff_report.md`、`version_history.md`、
`self_check.json`、`run.log`、`reader/*`）与**result 字段**
（`case_id/status/result/claims/uncertainties/sources/change_records/limits/...`），
实现与文本全部重写。

## 安装

把本目录整体放到 `/skills/weekly-skill` 即可。入口脚本用 `__file__` 自定位，
不依赖当前目录，也不需要安装第三方包。

## 用法

```bash
# 单命令全流程（等价于 main.py build）
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work

# agent-first：先确定性全流程，再让 Agent 读锚点写 draft，最后过闸门
python3 -B /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work

# 取证：打印某份材料的全部锚点
python3 -B /skills/weekly-skill/scripts/main.py show --input /input --output /app/output --work /app/work --doc D1
```

## 产物

| 产物 | 说明 |
|-|-|
| `result.json` | 契约逐键回填 + 结构化主结果；`case_id` 透传；无 JSON null |
| `reading_record.md` | 人读记录（文档 / 证据 / 质检 / 备注） |
| `golden_standard.json` | 金标（文档 sha1、锚点、span 的 quote+locator） |
| `diff_report.md` | 与金标逐项对照 |
| `version_history.md` | 版本与本次变更 |
| `self_check.json` | 交付前自查 |
| `run.log` | 运行摘要 |
| `reader/anchors.json` | 全部锚点（含字符区间） |
| `reader/annotations.json` | 证据批注 |
| `reader/qa_log.json` | 质检明细 |
| `reader/reading_state.json` | 阅读状态 |
| `reader/index.html` | 单文件离线阅读器 |

## 设计要点

- **只用标准库**：`json`/`re`/`zipfile`/`zlib`/`html`/`hashlib`/`argparse`。
- **PDF/DOCX**：PDF 解压内容流后抽 `(...)Tj`；DOCX 走 `zipfile` 读 `word/document.xml`。
  抽不出就记 `degradations`，不猜正文。
- **逐字引文**：答案必须是材料中的原句；质检对每条 span 复核 `quote in paragraph`。
- **locator 稳定**：`p{页}#para{序}` + 绝对字符区间，重复运行结果一致。
- **离线阅读器**：内嵌 JSON、无外链、无网络；所有开标签带显式属性，扫描时不会
  被误认为未填写的占位片段。
- **诚实降级**：空目录 → `input_error`；有文件但读不出 → `insufficient_evidence`；
  有锚点但无量化句 → `partial`。三条路径都写合法 `result.json` 并 exit 0。

## 限制

- 不做 OCR：扫描版 PDF 抽不出文字时只记降级，不伪造。
- 不做语义推理：选句是确定性打分，不判断结论真伪。
- 对超长单句按 ~1600 字符切段，可能把一句话拆到两个锚点；char 区间仍可还原。
- 只读取材料本身，不联网、不调用外部模型。

## 维护

- 契约键名冻结；新增键走次版本，阈值与文案走修订号。
- 改动后至少跑：`main.py selfcheck` + `scripts/eval_sim.py` 的 rich/boundary × single/agent
  四组组合，并把结果记入 `SELFTEST.md`。
- 资源与命令声明见 `environment/resources.yaml`；口径细节见 `references/client_contract.md`。
