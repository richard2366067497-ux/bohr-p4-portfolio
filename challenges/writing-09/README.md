# writing-09-results-discussion — 结果与讨论章节写作

数据表、图表与统计输出已经在手时，把材料写成可投稿的 **Results / Discussion / Limitations / Sources**：
读数按原单位逐字保留并可回溯来源，结果段只陈述观察，讨论段把每条解释对照到本研究数据或可定位文献，
因果边界与局限写到方法层面。纯 Python 标准库、完全离线。

## 1 安装与运行

| 项 | 约定 |
|---|---|
| 安装位置 | `/skills/weekly-skill`（Harness 挂载点） |
| 依赖 | Python 3.8+ 标准库；不联网；不写输入目录 |
| 退出码 | **恒为 0**（含全部降级）；仅 argparse 用法错误返回 2 |
| 目录参数 | `--input /input`、`--output /app/output`、`--work /app/work`（均有默认值） |

单命令（等价入口，评测只跑这一条也能过）：

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

可叠加 `--case /input/case.json`、`--lang zh|en`；不依赖任何草稿或前置步骤。

离线自测（19 项，不联网）：

```bash
python3 /skills/weekly-skill/scripts/main.py --selftest
```

## 2 材料与解析

| 支持 | 说明 |
|---|---|
| `.md .txt .tex .bib .html .csv .tsv .json` | 直接读取；JSON 扁平化为可检索文本 |
| `.docx .xlsx .pptx` | 从 OOXML 解出正文/共享字符串/幻灯片文本 |
| **PDF** | 用标准库解出**文本层**（FlateDecode 流 + 字面串）；无文本层的扫描件记入 `degradations` |
| **PNG / JPEG** | 读文件头记录尺寸（PNG IHDR / JPEG SOFn），内容转 `human_review` 人工读数 |
| 坏文件 | 坏 JSON / 空文件 / 不支持的二进制记入 `degradations`，不阻断 |

## 3 产物（写入 `--output`）

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 主产物：Results、Discussion、Limitations、Sources 四节 |
| `preview.svg` | 成稿的离线预览（文本渲染，CJK 可用浏览器直接打开） |
| `results_map.json` | 每个读数 token → 值/单位/来源/上下文 |
| `evidence_map.json` | 讨论论断 → 数据或文献定位 + 相似度 |
| `preserved_facts.json` | 保留的数值、单位与来源 |
| `change_log.json` | 本次写作动作与边界处理记录 |
| `metrics.json` | 与包内声明阈值的基线对照（单位保留率、证据定位率、因果措辞、契约字段） |
| `result.json` | 结构化结果 + `output_contract` 逐键回填 + 契约顶/嵌套一致 |

## 4 示例（示意，非官方固定案例结果）

```text
/input/case.json              {"case_id": "…", "language": "en", "output_contract": {...}}
/input/materials/paper.md     方法与结果原文（含数值、单位）
/input/materials/refs.md      讨论对照用的文献片段
```

`python3 scripts/main.py --input /input --output /app/output --work /app/work` → 退出码 0；
rich 样例实测 `status=success`、读数 12、生成 8 个产物、`metrics.json.pass=true`；无读数时
`status=partial`，仍写出全套产物与 `limits`。

## 5 限制

- 不判断结论在科学上是否成立；只保证观察与解释分节、数值与单位未改、因果措辞被拦截。
- 离线无 OCR：位图图表与扫描 PDF 只能清点并转人工读数；PNG 光栅化需外部字体渲染器，故预览用 SVG。
- 显著性只在材料给出时报告；数值分级是启发式，最终以人工复核为准。

维护与复算见 `SELFTEST.md`，增益证据见 `GAIN_EVIDENCE.md`，评分口径见 `references/rubric.md`。
