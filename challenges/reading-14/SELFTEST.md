# SELFTEST — reading-14 / literature-knowledge-graph（稳定性与边界证据）

本文件的每个数字都来自随包 `scripts/main.py` 在本机 Python 3.12（仅标准库）上的**真实运行**，
可用下列命令逐字复现。四组「输入形态 × 运行模式」全部 PASS（`scripts/eval_sim.py`）：

```bash
python scripts/eval_sim.py --pkg work/p4/v9/reading-14 --case work/p4/synth_cases/reading-14/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-14 --case work/p4/synth_cases/reading-14/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/reading-14 --case work/p4/synth_cases/reading-14/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-14 --case work/p4/synth_cases/reading-14/boundary --mode agent
```

## 1. eval_sim 结果

| 输入 | 模式 | 结果 | 契约来源 | 契约键 | 输出文件 |
|---|---|---|---|---|---|
| rich（两篇合成段落 + 候选图 + 3 查询） | single | **PASS**（0 FAIL / 0 WARN） | `case.json:output_contract` | graph, merges, conflicts, queries, sources, uncertainty, change_records | 14 |
| rich | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 14 |
| boundary（坏 JSON + 空文件 + 占位文件） | single | **PASS**（0 FAIL / 0 WARN） | `SKILL.md` json sample | case_id, status, graph, merges, conflicts, queries, sources, uncertainty, change_records | 14 |
| boundary | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 14 |

审计项全部 PASS：`exit_code` / `result_json` / `contract_echo` / `contract_values` / `deliverables` /
`case_id` / `placeholder_sweep` / `field:status|sources|uncertainties|change_records|limits`。

## 2. rich 运行实测

| 可核验指标 | 实测值 |
|---|---|
| `status` | `answered` |
| 节点 | **6**（method 3、dataset 1、metric 2，全部带逐字引文） |
| 边 | **3**（`evaluated_on` 1、`reports` 2，全部带 locator + 引文） |
| 概念 | **5** |
| 别名合并 | **1**（`WideNet` 跨两篇合并，记录 basis） |
| 拒绝合并 | **1**（泛化术语 `Accuracy` 取值不同 → 不合并） |
| 冲突 | **1**（`Accuracy`：0.91 vs 0.80，条件不同） |
| 被拒绝候选 | **1**（`ImageNet` 在声明 locator 处无逐字证据 → 拒绝） |
| 查询 | **3**（`find_surface` / `outgoing` / `conflicts`；2 条非冲突查询 answered） |
| 逐字节点率 | **1.0000** |
| 输出文件 | **14**（含 `evidence/sources_snapshot.json`） |
| `result.json` 规范化哈希 | `sha256=a4a62af269eb2f8a`（示例输入，见 §4） |

## 3. boundary 运行实测（诚实降级）

| 材料 | `parse_status` | 处理 |
|---|---|---|
| `broken.json`（非法 JSON，29 B） | `parsed` 但无法解析 | 不进图；记运行日志 |
| `empty.md`（0 B） | `empty-file` | 只记状态，从不引用 |
| `notes.txt`（`[待写]`） | `placeholder-only` | 只记状态，从不引用 |

结果：`status=insufficient_evidence`；`graph.json` 的节点/边为空；`annotations.jsonl` 写一条
`kind=no-data` 记录；`uncertainty.json` 说明「未能在给定材料中 grounding 任何节点」并列出检索位置；
`query_results.json` 的查询如实写 `no_match` 与 undetermined 说明；**exit 0**，无占位符。

## 4. 复现命令（示例）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 14 个文件；result.json.status=answered；
#       节点 6；边 3；合并 1；拒绝合并 1；冲突 1；被拒候选 1；查询 3（2 answered）；逐字率 1.0
```

规范化哈希复算：读 `/tmp/out/result.json`，删除 `runtime`（本包不写该键）后
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))` 取 `sha256` 前 16 位应为
`a4a62af269eb2f8a`。

## 5. 确定性

同一输入连续运行两次，`result.json` 规范化哈希一致；不含时钟、随机数或网络调用，仅标准库。
