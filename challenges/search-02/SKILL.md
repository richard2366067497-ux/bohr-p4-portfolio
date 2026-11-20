---
name: rq-driven-retrieval
description: 科研问题驱动检索。把复杂科研问题拆成结构化子问题、规划查询、对候选记录做可复核的筛选/排序并给出停止判断，输出逐键回填 output_contract 的 result.json 与完整证据台账。提供单命令 all 入口，同时保留 init/show/check/build/selfcheck 五命令工作流；纯标准库、离线、空/坏输入也 exit 0。
---

# rq-driven-retrieval（search-02 v6）

围绕“科研问题驱动检索”把一个复合科研问题变成**可检索、可复核、可复现**的检索过程：
问题拆解 → 查询规划（含依赖/优先级/术语扩展）→ 多轮候选筛选 → 证据台账 →
覆盖度 → 停止判断 → 报告 + `result.json`。

## 单命令（single command，无草稿也产出完整产物；评测只跑这一条也能过）

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

`all` = 扫描材料 → 结构化子问题 → 规划查询 → 规则化筛选候选并写证据台账 → 覆盖度与停止判断
→ 生成 `report.md` 等产物 → `result.json`（契约逐键回填 + case_id 透传）→ 占位符净化 → exit 0。
无需 `draft.json`；空输入、坏 JSON、缺 `case.json` 同样 exit 0 并写合法 `result.json`。

## 五命令工作流（等价入口，Agent 深读时质量更高）

```bash
python3 -B scripts/main.py init       # 扫描输入、写 partial result.json 与 draft 骨架
python3 -B scripts/main.py show        # 打印带 locator 的段落/候选记录（--grep/--limit/--sources）
python3 -B scripts/main.py check       # 校验 draft 子问题/筛选决策/rid 合法性
python3 -B scripts/main.py build       # 组装产物并定稿 result.json
python3 -B scripts/main.py selfcheck   # 复检产物一致性与非空
```

五条命令与 `all` 共用同一引擎；`all` ≈ `init` + 自动候选 + `build` + `selfcheck`。
全局参数 `--input / --output / --work` 可放在子命令前或后（也可用环境变量 `SKILL_INPUT` 等）。

## result.json 约定（片段示例，键名冻结）

```json
{
  "case_id": "synth-case",
  "status": "partial",
  "output_contract": {
    "contract_overrides": {"note": "agent overrides if any"},
    "id": "SQ1",
    "type": "mechanism",
    "other": "additional structured notes for this key",
    "text": "the sub-question text",
    "queries": ["planned query"],
    "depends_on": ["SQ0"],
    "priority": 1,
    "required": true,
    "rid": "R001",
    "subquestion_ids": ["SQ1"],
    "decision": "include",
    "relevance": 0.5,
    "quote": "verbatim supporting span",
    "locator": "M01#p1",
    "reason": "why this decision was made",
    "subquestions": [{"id": "SQ1", "text": "sub-question"}],
    "candidates": [{"rid": "R001", "decision": "include"}],
    "evidence": [{"rid": "R001", "verified": true}],
    "coverage": {"required_total": 1, "covered": 1},
    "search_log": {"n_queries": 1, "rounds": 1},
    "stop_decision": [{"stop": "saturated"}],
    "report": "report.md"
  }
}
```

契约键**逐键**写入 `result.json.output_contract`，同时在 `result.json` 顶层放同名键；
`case_id` 原样透传；`status` 取 `answered / partial / insufficient_evidence / input_error` 之一并给
非空 `sources`、`uncertainty`、`change_records`、`limits`。值不做任何占位，路径键指向真实非空文件。

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、子问题、候选、证据、覆盖度、停止判断、limits、uncertainty、change_records |
| `subquestions.json` | 结构化子问题（含 queries / depends_on / priority / required） |
| `candidates.jsonl` | 逐条候选记录（rid、locator、relevance、decision、basis、quote） |
| `evidence_ledger.json` | 证据台账（逐字 quote + locator + verified 标记） |
| `coverage.json` | 每个子问题的证据覆盖状态与覆盖率 |
| `stop_decision.json` | 每个子问题的停止判据（saturated / low_marginal_gain / needs_human） |
| `search_log.json` | 查询数量、轮次、零产出子问题、检索范围声明 |
| `report.md` | 人类可读报告（子问题、筛选摘要、覆盖与停止、证据与限制） |

## 输入

- `--input`（默认 `/input`）：`case.json`（可含 `case_id`、`output_contract`、`research_question`）与任意
  UTF-8 文本材料（`.md/.txt/.json/.tex/.csv/...`）。`task.md` 用于推断研究问题。
- 无 `case.json` 时按材料文本推断问题；无材料时给诚实的空候选与 `insufficient_evidence`。

## 异常与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`，不编造文献。
- 无可解析文献记录：`candidates` 给带说明的诚实空结构，`degradations` 记录原因。
- 任何阶段异常：捕获后保留 partial `result.json`（含 `errors`、`traceback_tail`）并 exit 0。
- 不联网、不安装工具、不臆造元数据；检索结论限定在“所给快照内”，不宣称全局召回。

## 自查

`python3 -B scripts/main.py selfcheck` 或在评测器中跑 `all`，见 `SELFTEST.md` 的复现命令与结果。
