---
name: literature-evidence-qa
description: 读取论文语料与问题清单，逐题定位可复核证据（段落编号 + 原文引用）并给出回答、覆盖范围与不确定性；纯标准库、确定性、退出码恒 0。
---

# literature-evidence-qa · 文献智能问答

围绕「读论文 → 定位证据 → 逐题回答」组织：对每个问题都给出可回溯到具体段落的回答，
保留未答部分与覆盖范围，绝不使用材料之外的知识。

## 输出契约（result.json.output_contract）

```json
{
  "output_contract": {
    "case_id": "string",
    "status": "string",
    "answers": [],
    "claims": [],
    "coverage": {},
    "uncertainties": [],
    "change_log": []
  }
}
```

用例声明的每个键（含嵌套）都会写入 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传；
用例另声明的键（例如 `result`）一并回填，不重命名、不丢弃。

## 单命令入口

一条命令完成全流程（也是评测器的等价入口）：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

## 输入

- `/input/case.json`：`case_id`、`paper_id`、`material_version`，可选 `questions` / `question_list`。
- `/input/task.md`：题目与（可选的）问题清单。
- `/input/comparison-workorder.json`（或任一 `*workorder*.json`）：`research_question`、`documents`。
- 语料：`corpus/*.txt`、`*.md` 等文本材料，按空行切分为段落。

## 输出（`/app/output`）

`result.json`、`answers.md`、`evidence_map.json`、`coverage.json`。

问题清单缺失时，由 `research_question` 合成一个通用问题并在 `uncertainties` 中声明。

## 规则

- **证据优先**：每条回答附 `paragraph_id` 与原文 `quote`；`claims[].kind` 区分 `reported` / `inferred`。
- **不改写材料**：引用为原文片段，超出材料的推断一律记为 `inferred` 或列入不确定性。
- **跨语言检索**：内置中英概念词表（染料/dye、光催化/photocatalysis、去除率/removal…）与数字线索加权。
- **优雅降级**：无正文、坏 JSON、空文件都不抛错，仍写出全部交付物与合法 `result.json`（`status=insufficient_evidence`/`input_error`）。
- **可复跑**：无网络、无时钟读取，同输入重复运行字节稳定。

可编辑的规则与词表见 `references/qa-contract.md`。
