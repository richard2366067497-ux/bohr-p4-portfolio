# 问答契约与检索规则（可编辑）

## 1. 流程

1. **盘点** `/input`：跳过根级 `case.json`/`task.md` 等元文件，其余按类型归类。
2. **读题**：依次从 `case.json`（`questions`/`question_list`）、`*workorder*.json`（`research_question`）、
   `task.md`（形如 `Q1. ...` / `问题1：...` 的行）收集问题；若都没有，则由研究问题合成一条通用问题并在
   `uncertainties` 中声明。
3. **切段**：文本材料按空行切分，若段首有 `[3]` / `3.` / `¶3` 等编号则采用该编号，否则顺序编号；
   `paragraph_id` 形如 `corpus/D1.txt#p3`，指向源码可复核。
4. **检索**：对每个问题做中英概念扩展（见下表）后与段落做词面交集打分，数字线索（浓度/pH/时间/效率等）
   额外加权；取分数最高的至多 3 段作为证据。
5. **作答**：命中 ≥2 段记为 `answered`，1 段记为 `partial`，0 段记为 `insufficient_evidence`。
6. **申报**：每条回答转成 `claims`（原文片段为 `reported`，汇总/覆盖类为 `inferred`），并汇总覆盖范围、
   未答部分与不确定性。

## 2. 中英概念词表（节选）

| 中文概念 | 英文别名 |
|---|---|
| 染料 | dye, methyleneblue, rhodamine, pollutant |
| 光催化 | photocatalysis, photocatalyst, tio2, zno |
| 浓度 | concentration, mg/L, ppm |
| pH | ph, acidity, alkaline |
| 去除率 | removal, efficiency, degradation |
| 时间 | time, min, irradiation |
| 紫外 | uv, ultraviolet, wavelength |

词表定义在 `scripts/engine.py` 的 `LEX` 中，可直接增删。

## 3. 状态取值

`answered` | `partial` | `insufficient_evidence` | `input_error`。

## 4. 输出契约键

`case_id`、`status`、`answers`、`claims`、`coverage`、`uncertainties`、`change_log`；
若用例另外声明了键（例如 `result`），一并回填，不重命名、不丢弃。

## 5. 降级

- 无可读正文：所有问题 `insufficient_evidence`，`coverage.read` 为空。
- 坏 JSON / 空文件：记入 `uncertainties`，不抛错。
- 输入目录不存在：`status=input_error`，仍写出合法 `result.json`。
