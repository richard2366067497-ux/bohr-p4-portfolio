# GAIN_EVIDENCE — reading-14 / literature-knowledge-graph（使用增益证据）

本文件给出「不加载本 Skill 的基线 Agent」与「加载本 Skill」在同一小型文献语料上的对照证据，并映射到
官方 rubric 五维。所有「加载本 Skill」数字来自本包 `examples/` 的**真实运行**（见 `SELFTEST.md`），可逐字复现。

> **诚实声明**：本文「基线 Agent（无 Skill）」一栏为**基线模拟，非官方对照**，由随包文档描述的
> 确定性朴素策略（§1.2）在同一输入上生成，仅用于说明**缺口类别**，不代表官方评测中的真实对手；
> 本包**未伪造任何官方 A/B 数据**。对照的公平性在于：两组使用**同一**输入（`examples/params.json` +
> `examples/case.json`）、**同一**任务（把两篇材料读成可核验的知识图谱并回答查询）与**同一**评估口径（§3）。

---

## 1 基线 Agent（无 Skill）

### 1.1 典型输出与缺口

输入 `examples/`（两篇合成段落 + 候选图 + 3 查询）下，未加载本 Skill 的基线 Agent 典型缺口：

1. **散文而非图谱** —— 输出「两篇都用到 AsterNet，准确率分别是 0.88 与 0.72」这类总结，无节点/边。
2. **无 locator** —— 实体与关系不标 `source_id#paragraph_id`，不可复核。
3. **无逐字校验** —— 候选若含原文没有的名字（如示例中的 `CIFAR`），基线常直接采信。
4. **同名即合并** —— 两篇的 `Accuracy` 被并成一个结论，忽略 0.88 与 0.72 的条件差异。
5. **无查询产物** —— 不产出可执行的查询结果，也没有 `no_match` 与 undetermined 的区分。
6. **无契约回填** —— 不产出 `result.json`，契约键覆盖 0/7。

### 1.2 基线模拟（确定性，非官方对照）

```python
# baseline_sim（示意）：把两篇段落拼成一段通读文字，不建节点/边、不定位、不查询
import json, pathlib
p = json.loads(pathlib.Path("examples/params.json").read_text(encoding="utf-8"))
paras = [x["text"] for m in p["materials"] for x in m["paragraphs"]]
pathlib.Path("baseline_out").mkdir(exist_ok=True)
pathlib.Path("baseline_out/summary.md").write_text("文献综述：\n" + "\n".join(paras) + "\n", encoding="utf-8")
# 无 graph.json / annotations.jsonl / query_results.json / alignment_report.json / conflicts.json / result.json，
# 无 locator、无逐字校验、无别名合并依据、无冲突分离、无查询
```

模拟结果：产物 **1** 件、节点 **0**、边 **0**、locator 证据 **0**、合并依据 **0**、冲突 **0**、
查询 **0**、契约键 **0/7**、无自检。

---

## 2 加载本 Skill（真实运行）

命令（§4）在 `examples/` 上的实测（`status=answered`，exit 0）：

| 可核验指标 | 基线模拟 | 加载本 Skill（实测） |
|---|---|---|
| 输出文件数 | 1（拼接文字） | **14** |
| 节点（全部带逐字引文） | 0 | **6** |
| 边（全部带 locator） | 0 | **3** |
| 别名合并（有 basis） | 0 | **1**（`AsterNet` 跨两篇） |
| 拒绝合并 | 0 | **1**（`Accuracy` 条件不同） |
| 冲突（按来源并列） | 0（被并成一个结论） | **1**（0.88 vs 0.72） |
| 被拒绝的未 grounding 候选 | 0（照单全收） | **1**（`CIFAR` 无逐字证据） |
| 查询 | 0 | **3**（2 answered；1 conflicts） |
| 逐字节点率 | 不适用 | **1.0000** |
| 契约键覆盖 | 0/7 | **7/7**（顶层 + `result.output_contract`） |
| 占位符扫描 | — | **0** |
| `result.json` 规范化哈希 | — | `sha256=a4a62af269eb2f8a` |

关键产物：`graph.json`（节点/边/概念，各带 locator、type、引文）/ `annotations.jsonl`（逐行带 locator 与
引文）/ `query_results.json` + `queries.md`（3 条查询与 undetermined）/ `alignment_report.json`（合并 basis 与
拒绝理由）/ `conflicts.json`（泛化术语取值分歧）/ `sources.json`（DOI/作者/许可）/ `uncertainty.json` /
`change_log.json` / `coverage.json` / `self_check.json` / `run_log.txt`。

---

## 3 差异对照表 → rubric 五维

| 对照项 | 无 Skill（基线模拟，非官方对照） | 加载本 Skill（实测） | 主要增益维度 |
|---|---|---|---|
| 任务完成度 | 1 件拼接文字，无图谱 | 14 件成套产物（图谱/标注/查询/对齐/冲突/来源/覆盖） | **实际效果** |
| 结果正确性 | 同名即合并，忽略条件差异 | 仅 surface+type 一致才合并；泛化术语冲突按来源并列 | **实际效果** |
| 结果完整性 | 无查询、无未决说明 | 覆盖 8 类实体/12 类关系的口径；缺失以 `missing_entity_types`/undetermined 交代 | **实际效果** |
| 结果可核验性 | 无 locator、无引文 | 每节点/边带 `source_id#paragraph_id` + 逐字引文，逐字率 1.0 | **实际效果** |
| 使用增益 | 无对照、无法复核 | `compare_report.json` 给「基线文字 vs 结构化图谱」的可核验差；同输入同口径（§1） | **使用增益** |
| 创新增益 | 直接通读段落 | 逐字 grounding + 拒绝合并 + 泛化术语冲突分离 + 真实查询（README §9，含价值边界） | **创新增益** |
| 可靠体验 | 无降级、无自检 | 空/坏/占位 → `insufficient_evidence`；未命中候选记原因；四组 eval_sim PASS | **可靠体验** |
| 生态贡献 | 无文档、无模板 | README/SELFTEST + 契约骨架 + 图谱模板 + 字段口径，可换成新语料复跑 | **生态贡献** |

**为什么这些差异对应 rubric**：实际效果＝「真的把几篇材料读成可核验、可继续查询的图谱」；使用增益＝
「同一语料、同一口径下，结构化与可核验性优于基线，且给出可复算差」；创新增益＝「逐字 grounding、拒绝合并、
冲突分离的方法本身带来实质改进并给出边界」；可靠体验＝「异常输入下仍产出可用的诚实结论」；
生态贡献＝「说明、模板、示例可被他人直接复用」。

---

## 4 复现命令

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 14 个文件；result.json.status=answered；
#       节点 6；边 3；合并 1；拒绝合并 1；冲突 1；被拒候选 1；查询 3（2 answered）；逐字率 1.0
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime`（本包不写该键）后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`a4a62af269eb2f8a`。
