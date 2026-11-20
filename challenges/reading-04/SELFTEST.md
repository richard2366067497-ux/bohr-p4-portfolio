# 自测记录 · literature-evidence-qa v7

## 1. 运行环境

- Python 3.12（纯标准库：argparse / json / re / hashlib / pathlib）。
- 入口：`python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work`。
- 无网络、不读时钟；同一输入重复运行输出字节稳定。

## 2. 验收矩阵（`scripts/eval_sim.py`）

| 案例 | 模式 | 结果 | 失败 | 警告 | 契约来源 |
|---|---|---|---|---|---|
| rich | single | PASS | 0 | 0 | case.json:output_contract |
| rich | agent | PASS | 0 | 0 | case.json:output_contract |
| boundary | single | PASS | 0 | 0 | SKILL.md (json sample) |
| boundary | agent | PASS | 0 | 0 | SKILL.md (json sample) |

rich 交付物字节数：`result.json` 21378、`answers.md` 853、`coverage.json` 817、`evidence_map.json` 708。
退出码均为 0；`placeholder_sweep` 在全部输出文件上通过。

## 3. 真实问答证据（rich 案例实际输出）

问题：`染料初始浓度与 pH 如何影响光催化去除率？`（来自 comparison-workorder 的 research_question）

- 读入 2 个文档 / 6 个段落（同一材料的重复副本按内容 sha256 只读一次）。
- 3 条证据回填 `paragraph_id` 与逐字引用：

| paragraph_id | 引用（逐字，节选） |
|---|---|
| corpus/D1.txt#p2 | After 120 min at pH 3, the removal efficiency reached 95%. |
| corpus/D2.txt#p2 | The removal efficiency was 88% after 60 min at pH 7. |
| corpus/D1.txt#p3 | Increasing the solution pH to 9 lowered the removal efficiency to 61%. |

回答即由上述可定位段落构成，未引入材料之外的知识；`conditions` 逐条声明证据来源。

## 4. 边界行为（boundary 案例）

材料为坏 JSON、零字节文件与含占位符的笔记：不抛错，`status=partial`，
`uncertainties` 如实说明缺材料；`answers` 为空数组但仍写出全部交付物，退出码 0。

## 5. 已知限制

- 检索为词表 + 词频加权，不做语义向量；跨语言只覆盖内置概念表。
- 单文档段落数过多时仅取前 3 条证据，`coverage.json` 给出未覆盖段落数。
- 不对材料做任何改写或补全，原文引用超过 320 字符时截断并在引用末尾标注。
