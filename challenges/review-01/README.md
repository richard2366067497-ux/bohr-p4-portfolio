# source-bound-manuscript-audit

把一篇科学稿件（或一组研究材料）审成一组**可定位、可核对、可交办**的条目：每条带原文逐字引用、段落级
locator、问题性质、严重度与理由、判定依据，以及落到句子上的修改建议；对没有查的部分显式登记。
**不写评语、不改稿、不做查重或排版。**

## 快速开始

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work   # 带 locator 读材料
#   评审 Agent 读材料 → 写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check  --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py build  --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output
```

**执行前必读** `references/expert_playbook.md`（专家方法论），交付前逐项过其 §7 防扣分自查表。
每条命令 **exit code 恒为 0**；无工作稿时 `init`/`build` 仍产出完整降级交付（全部 `pending_review`）。

## 文件清单

```
SKILL.md                                用途、五命令主路径、契约、方法、降级、自查
README.md                               本文件：安装、快速开始、文件清单、维护
SELFTEST.md                             实测数字、双路径、边界降级、测试矩阵
GAIN_EVIDENCE.md                        同输入同契约下的基线对照（compare 复现）
GITHUB_URL.txt                          仓库目录链接（两行）
scripts/main.py                         五命令入口：init / show / check / build / selfcheck
scripts/audit_core.py                   解析与定位：编码/PDF/DOCX、切段、locator、quote 校验、草稿规范化
scripts/audit_leads.py                  规则扫描：结构/一致性/引用/方法统计/论证/规范候选
scripts/render.py                       契约回填、兜底条目、报告与证据卡渲染、run_manifest
references/checklist-and-severity.md    检查项与规则号、严重度锚点、误报抑制表、判定流程
references/io-and-draft-schema.md       输入发现、字段字典、工作稿 schema、最小示例、异常处置
references/expert_playbook.md           专家方法论：六面判分、求解框架、证据口径、误报抑制、自查表、虚构案例
environment/resources.yaml              资源入口声明
examples/case.json                      最小示例输入
```

## 依赖与配置

- 仅 Python ≥3.8 标准库；`pdftotext` 可选（缺失时自动换 pypdf / PyPDF2 / pdfminer / 原始流）。离线，不联网。
- 目录解析顺序：`--input/--output/--work` → 环境变量 `AUDIT_INPUT/AUDIT_OUTPUT/AUDIT_WORK` → `/input`、`/app/output`、`/app/work`
  → 包内 `input/`、`output/`、`work/`。脚本用 `Path(__file__).resolve()` 定位自身，不依赖 CWD。

## 产物

`/app/output/` 下：`result.json`（信封 + 契约逐键回填）、`audit_report.md`（主产物）、`evidence.jsonl`、`candidates.json`、
`run_manifest.json`。同一输入重复运行 `result.json` 逐字节一致（仅 `run_manifest.json` 耗时不同）。

## 来源与限制

只审材料内可核对的内容；外部文献主张、期刊最新要求无法离线核实 → 记 `pending_review`。图表只读题注与正文引用，
不做像素级读数。不复算统计、不重跑实验、不做查重。完整限制见 `SKILL.md` §9 与 `references/expert_playbook.md`。

## 维护

改阈值/规则号/字段须同步 `references/` 与 `SKILL.md`；新增材料格式只改 `audit_core.read_document`；新增规则放
`audit_leads.scan_*` 且必须给出「需 Agent 回答的问题」，不得直接产出 confirmed 结论。改脚本后须重跑 `--help`、
空 `/input`、坏 JSON 三条路径，均应 exit 0。
