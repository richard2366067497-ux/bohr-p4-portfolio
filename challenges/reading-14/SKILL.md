---
name: literature-knowledge-graph
version: 1.0.0
description: >-
  Turn a small paper corpus into an evidence-bound literature knowledge graph: ground every
  entity and relation as a node/edge that carries its own source_id#paragraph_id locator and a
  verbatim short quote from the paragraph, merge aliases across papers only on an explicit,
  recorded basis, refuse to fuse a generic term (e.g. "accuracy") that appears with differing
  values or conditions, answer at least three real graph queries, and report what could not be
  grounded instead of guessing. Use when a task asks for 文献知识图谱 / 实体关系抽取 /
  跨文献实体对齐与冲突 with a reproducible path. Pure standard library, offline, deterministic.
---

# literature-knowledge-graph

A knowledge graph is only worth as much as its provenance. Here every node and every edge carries
the locator it came from and the sentence that supports it; a candidate that cannot be matched
verbatim in the material is rejected rather than kept, and two papers that share a name are aligned
by that name alone — never by assuming the same sample, model or condition.

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 八步框架（含门控）** 推进——输入登记 → 正文解析与证据锚定 → 定 Schema 与粒度
  → 保守抽取 → 跨篇对齐与反合并 → 图谱装配与稳定编号 → 执行查询 → 提前保存并验证；前一步未冻结不进入下一步。
- **证据**：按其 **§3 证据结构** 给每条边与节点带 `source_id#paragraph_id` 定位、逐字短引、归属与证据强度。
- **口径**：按其 **§3 量化口径** 计算 `C_node / C_edge / R_valid / P_merge / Q_replay / S_ID`，测量值绑定样品与条件。
- **陷阱**：按其 **§4 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）；同名不代表同样品，共现只生成候选。
- **门控**：交付前逐项通过其 **§7 防扣分自查表（25 项）**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainty` / `conflicts.json`，绝不静默提升为完整成功。

## 0. result.json contract

Every key below is echoed both at the top level of `result.json` and inside its
`output_contract` object; `case_id` is passed through unchanged. When the case supplies its own
`output_contract`, those keys are used instead and each is filled the same way (an artifact-like key
resolves to the written file, any other key gets a real derived value).

```json
{
  "output_contract": {
    "case_id": "the input case id, passed through",
    "status": "answered | partial | insufficient_evidence | input_error",
    "graph": "graph.json",
    "merges": "alignment_report.json",
    "conflicts": "conflicts.json",
    "queries": "query_results.json",
    "sources": "sources.json",
    "uncertainty": "uncertainty.json",
    "change_records": "change_log.json"
  }
}
```

## 1. Draft schema (JSON, optional)

An agent may fill `/app/work/draft.json` with its own candidate nodes, edges and queries; `build`
records that a draft was seen, and the deterministic grounding still runs regardless, so a thin
draft cannot turn an ungrounded claim into a kept node.

```json
{
  "case_id": "",
  "nodes": [],
  "edges": [],
  "queries": [],
  "notes": ""
}
```

## 2. 单命令（等价入口，one-shot，评测入口）

Run this single command; with no draft it still writes every artifact and a complete
`result.json`, and exits 0:

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 3. agent-first 增强路径（可选，质量更高）

List the material with locators, fill the draft above, then check it before `build` grounds it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints each material line with a `M02/p7` locator; `check` reports how many candidate nodes
and edges ground; `compare` writes a base-vs-skill contrast to `/app/work/compare_report.json`.

## 4. Pipeline

1. Index every file under `/input` with its kind, size and parse status (`parsed` / `empty-file` /
   `placeholder-only` / `unparsed-binary`).
2. Read the corpus manifest (`documents`: source_id, doi, title, authors, license), each paragraph
   material (`source_id` + `paragraphs`), the optional candidate graph (`nodes` + `edges`) and the
   query list (`queries`).
3. Ground every candidate node and edge: the paragraph must exist, the quote must be found
   verbatim at `source_id#paragraph_id`, and the surface must appear there — otherwise the
   candidate is rejected with the reason.
4. Align aliases: merge only where the normalised surface and the type agree across sources; refuse
   a merge when one surface carries two types, and refuse to fuse a generic metric term that appears
   with differing values or conditions — that becomes a conflict, reported per source.
5. Run the queries (find_surface / outgoing / incoming / conflicts) and record the subgraph,
   the evidence and the undetermined part of each.
6. Compute coverage (node/edge types, merges, refusals, conflicts, query hit rate, verbatim rate)
   and write every artifact.

The engine lives in `scripts/kglib.py`; `scripts/main.py` is the CLI entry that imports it.

## 5. Artifacts written to `--output`

| file | content |
|-|-|
| `result.json` | every contract key (top level + `output_contract`), case_id, status, counts, conflicts, sources, uncertainties, change_records |
| `graph.json` | nodes, edges and concepts, each with its locator, type and verbatim quote |
| `annotations.jsonl` | one JSON line per node/edge: locator, quote, relation, conditions |
| `query_results.json` | the executed queries with their hits and undetermined part |
| `queries.md` | the same queries in a readable form |
| `alignment_report.json` | the merges (with basis) and the refused merges |
| `conflicts.json` | the conflicts found across sources, with the value/condition that diverged |
| `sources.json` | source provenance from the corpus manifest |
| `uncertainty.json` | what could not be grounded, with the rejection and refusal reasons |
| `change_log.json` | the ordered build steps and their counts |
| `coverage.json` | node/edge types, merges, refusals, conflicts, query hit rate, verbatim rate |
| `self_check.json` | the grounding self-audit (nodes with evidence, rejects, refusals) |
| `run_log.txt` | per-material parse status and the stage counts |

## 6. Degradation rules

- No groundable node or edge → `status=insufficient_evidence`; every artifact carries a structured
  no-data record naming the searched locations; exit 0.
- A supplied candidate whose paragraph, quote or surface cannot be matched verbatim → rejected with
  the reason, listed in `uncertainty.json`, never kept as a node.
- A shared generic term with differing values or conditions → a conflict, reported per source; the
  two papers' samples are never assumed equal.
- Empty / binary / placeholder-only file → recorded with its parse status, never quoted.
- No network, no third-party package, no invented literature or numbers.

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符。
- [ ] `graph.json` 无悬空边、无重复 ID；每条节点/边都带 `source_id#paragraph_id` 定位与逐字短引。
- [ ] 跨篇合并仅在明确依据下执行，拒绝合并与不确定候选都写入 `alignment_report.json`。
- [ ] 至少 3 个查询真实执行，空结果 / 不可判定 / 执行失败三者已区分。
- [ ] 空语料 / 候选无法逐字命中两条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的 25 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainty`，绝不静默提升为完整成功。
