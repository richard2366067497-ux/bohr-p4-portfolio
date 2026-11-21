# structured-reading — README

把一个 PDF 或多份文本材料读成**按阅读顺序排好的页面对象**，再派生出标题、作者、摘要、章节、
表格网格、公式、题注、参考文献、脚注；每一项都带 `locator` 与逐字引文，可核回原文件。

- 纯标准库、离线运行，无网络、无模型调用。
- 单命令入口一次产出全部交付物；材料读不出来时同样产出完整契约并退出 0。
- 与 `case.json` 的 `output_contract` 对齐：顶层与嵌套 `output_contract` 各回填一份。

## 安装

把本目录整个装到运行时的 skill 目录（评测环境为 `/skills/weekly-skill`），入口脚本
`scripts/main.py` 只用标准库：

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

本地试跑（含样例材料）：

```bash
python3 scripts/main.py all \
  --input examples --output /tmp/sr-out --work /tmp/sr-work
python3 scripts/main.py selfcheck --output /tmp/sr-out
```

`examples/` 里有 `case.json` 与两页两栏样例 `sample.pdf`（表格、公式、题注、参考文献、页眉页脚
齐全），可以直接看到版式重建的结果。

## 命令

| 命令 | 作用 |
|-|-|
| `all`（默认） | 完整流水线 + 自检，评测入口 |
| `build` | 完整流水线（不跑自检） |
| `init` | 写索引与模板，并自动生成带 locator 的草稿候选 |
| `show` | 按 `--find` / `--mat` 打印对象与候选 |
| `check` | 校验草稿 locator，接受/拒绝写入 `work/check_report.json` |
| `selfcheck` | 复核交付物齐全、契约非空、无占位符 |
| `compare` | 同输入同契约下基线与本 skill 的质量/效率对照报告 |

所有命令退出码都是 0：失败走 `status=input_error` 并写出 `result.json`，不抛异常。

## 文件

```
SKILL.md                        技能说明与评测契约（含单命令入口）
README.md                       本文件
SELFTEST.md                     实测数字、双路径、边界降级、测试矩阵
GAIN_EVIDENCE.md                基线与本 skill 的对照证据
GITHUB_URL.txt                  仓库地址
environment/resources.yaml      资源入口声明
templates/reading-notes-template.md  人读笔记模板（对齐交付物字段）
examples/case.json              样例契约
examples/sample.pdf             两页两栏样例材料
scripts/main.py                 CLI：契约、索引、编排、自检、对照
scripts/pdf_engine.py           纯标准库 PDF 文本层 + 版式与阅读顺序
scripts/report_engine.py        结构抽取、覆盖矩阵、证据、草稿候选
```

## 产出

`/app/output`：`result.json` 及 `parsed.md`、`structure.json`、`evidence.json`、`coverage.json`、
`page_map.json`、`layout_objects.jsonl`、`unreadable.json`、`self_check.json`。
`/app/work`：`source_index.json`、`draft_template.json`、`draft_candidates.json`、
`check_report.json`、`compare_report.json`、`analysis_state.json`。

## 维护顺序

1. 改规则先改 `scripts/pdf_engine.py`（版式/阅读顺序）或 `scripts/report_engine.py`（结构）。
2. 跑 `init` → `show` 看对象；跑 `check` 看草稿通过率。
3. 跑 `all`，确认 `status`、`coverage.missing`、`evidence.count`。
4. 跑 `compare`，更新 GAIN_EVIDENCE.md 里的数字。
5. 跑 SELFTEST.md 里的四条 eval 组合，全 PASS 再交付。

## 已知边界

- 无文本层的扫描件不可读，会被明确列出，不做 OCR。
- 纯文本材料没有版面几何，分栏与表格无法恢复，会写进 `uncertainty`。
- 自由排版（没有栏沟）按自上而下排序。
- 表格由连续行对象重建，合并单元格会被拆开；公式按"含数学符号且有运算符"的行识别。
- 不判断哪一栏/哪个结论在科学上正确，只把读到的位置和原文交给评审。
