---
name: citation-trace
description: 引文追踪。从种子文献出发，利用所给快照中的文献记录与引用标记构建引用网络，追踪前向/后向路径，标注元数据缺口与越界引用，输出逐键回填 output_contract 的 result.json 与可复核台账。提供单命令 all 入口，同时保留 init/show/check/build/selfcheck 五命令工作流；纯标准库、离线、空/坏输入也 exit 0。
---

# citation-trace（search-04 v6）

把一批文献材料整理成**可回链的引用网络**，从种子文献出发追踪路径，指出元数据缺口与快照外引用。
核心约束：每条边保留 `locator`；缺字段如实记录不猜；不宣称全局引文索引。

## 单命令（single command，无草稿也产出完整产物；评测只跑这一条也能过）

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` = 扫描材料 → 识别文献记录与引用标记 → 建节点/边 → 从种子追踪路径 → 缺口 → 报告与
`result.json`（契约逐键回填 + case_id 透传）→ 占位符净化 → exit 0。

## 五命令工作流（等价入口）

```bash
python3 -B scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B scripts/main.py show        # 打印带 locator 的段落 / 文献记录（--grep/--limit）
python3 -B scripts/main.py check       # 校验 draft 边的 source/target
python3 -B scripts/main.py build       # 组装网络/路径/缺口并定稿 result.json
python3 -B scripts/main.py selfcheck   # 复检产物
```

## result.json 约定（片段示例，键名冻结）

```json
{
  "case_id": "synth-case",
  "status": "traced",
  "output_contract": {
    "show": {"command": "show", "purpose": "list paragraphs and records"},
    "build": {"command": "build", "purpose": "assemble network and result"},
    "citations": 3,
    "edges": [{"source": "M01#p2", "target": "R001", "kind": "cites"}],
    "seed": "M01#r1",
    "paths": [{"from": "M01#r1", "path": ["M01#r1", "R001"], "depth": 1}],
    "gaps": [{"rid": "R002", "missing_fields": ["doi"]}],
    "network": {"nodes": [{"rid": "R001"}], "edges": []},
    "summary": "nodes 1, edges 1, traced paths 1",
    "report": "report.md"
  }
}
```

契约键逐键写入 `result.json.output_contract`，并在顶层放同名键；`case_id` 原样透传；`status` 非空；
`sources/uncertainties/change_records/limits` 非空；路径键指向真实非空文件。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、seed、网络、路径、缺口、limits、uncertainty、change_records |
| `citation_network.json` | 节点（文献）与边（cites/lists） |
| `edges.jsonl` | 逐条边（source、target、kind、locator、marker） |
| `traced_paths.json` | 从种子出发的路径与深度 |
| `gaps.json` | 元数据缺口与越界引用 |
| `report.md` | 人类可读报告 |

## 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`。
- 无引用边：`edges/paths` 给带 `status`/`note` 的诚实非空结构，`degradations` 记录原因。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不查询外部引文库、不臆造元数据；结论限定在所给快照内。
