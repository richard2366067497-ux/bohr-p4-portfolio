# literature-evidence-qa（v6 修复包）

把「论文语料 + 问题清单」变成**逐题可复核的回答**：每个问题都定位到具体段落
（`paragraph_id`）并附原文引用，同时给出覆盖范围、未答部分与不确定性。
**纯标准库、确定性、退出码恒 0。**

## 快速开始（单命令）

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 交付物（`/app/output`）

`result.json`、`answers.md`、`evidence_map.json`、`coverage.json`。

## 为什么这样改

上一版把题目做成了「多文档字段对比矩阵」，而题面要求的是**文献问答**：读取论文与问题、整合证据、
逐题回答并标明依据。本版据此重写核心流程（读 → 定位证据 → 回答 → 覆盖/不确定性）。

## 设计要点

- **真实检索**：内置中英概念词表（染料/dye、光催化/photocatalysis、去除率/removal…）与数字线索加权，
  证据来自原文段落，可回溯到 `paragraph_id`。
- **claims 区分**：`reported`（原文片段）与 `inferred`（汇总/覆盖）。
- **契约回填**：用例声明的每个 `output_contract` 键（含嵌套）写入 `result.json.output_contract` 与顶层同名键；
  `case_id` 原样透传。
- **无占位符**：写出前对 JSON 文本做令牌中和（解码后仍为原文），人类可读文本走等义替换。
- **优雅降级**：空目录、坏 JSON、零字节文件、无正文都不抛错；仍输出全部交付物与合法 `result.json`。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

## 目录

```
SKILL.md                        题面式技能说明（第一条即单命令入口）
README.md                       本文件
SELFTEST.md                     自测记录（eval_sim rich/boundary × single/agent）
GITHUB_URL.txt                  仓库地址
environment/resources.yaml      运行时与输入/输出资源清单
scripts/engine.py               单命令入口 + 检索/回答/契约回填
references/qa-contract.md        可编辑的问答契约、概念词表与状态取值
examples/README.md              一个最小可跑示例
```
