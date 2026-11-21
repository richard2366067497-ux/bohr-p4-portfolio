# traceable-literature-retrieval (search-01)

把「研究问题 + 给定材料快照」变成**可追溯的文献候选集**：规划查询、逐条定位、按 DOI/标题去重、
按相关性打分与排序、分开记录入选与排除、如实说明遗漏与不确定，并回填 `case.json` 声明的
全部 `output_contract` 字段。纯标准库、离线、确定性。

## 安装

把本目录安装到 `/skills/weekly-skill`（评测环境会自行安装）。无需第三方依赖，Python ≥ 3.9。

## 快速开始

```bash
# 单命令（评测入口，等价于 all）
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work

# 本地复跑打包示例（应得 status=answered）
python3 -B scripts/main.py --input examples --output /tmp/out --work /tmp/work
```

agent-first 可选路径：`init → show → check → build → selfcheck → compare`（见 `SKILL.md` §3）。

## 输入

- `/input/case.json`：`case_id`、`language`、`materials_root`、`output_contract`（键会被逐字回填）。
- `/input/task.md`：当 `case.json` 未给研究问题时，从首行有效文本取用。
- `/input/materials/**`：结构化材料（`json/jsonl/csv/tsv`）提供候选记录；`md/txt` 只索引为可引行。
  空文件 / 坏 JSON / 二进制会被登记为对应 `parse_status`，绝不引用。

## 输出（`/app/output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + 结构化结果、状态、来源、不确定性与变更记录 |
| `candidates.jsonl` | 入选候选（object_id / locator / DOI / 相关性分值 / rank） |
| `queries.jsonl` | 查询计划（query_id / query / intent / source） |
| `screening.json` | 被排除候选与遗漏项，逐条带依据 |
| `coverage.json` | 覆盖计数与范围说明 |
| `report.md` | 人读报告：问题 / 查询计划 / 候选表 / 排除表 / 覆盖 / 遗漏与不确定 |
| `selfcheck.json` | 交付前自查 |
| `run_log.txt` | 运行摘要 |
| `gain_report.json` / `gain_report.md` | 确定性结构对照（非官方分数） |

## 状态与降级

`answered`（有入选候选）/ `insufficient_evidence`（材料存在但无候选）/ `input_error`（无材料）。
`case.json` 缺失或坏 JSON、`output_contract` 缺失或为 null、空文件、坏 JSON、无候选——
这些路径都写出合法 `result.json` 并 `exit 0`；仅 argparse 用法错误返回 2。

## 限制

- 只在给定快照内检索，**不声称**远程数据库的全量覆盖、最新性或不遗漏。
- 相关性来自研究问题的关键词重叠（可用 `case.json.research_question` 指定），
  不是语义模型打分；它给出**可复算的相对顺序**，不冒充官方指标。
- 不提供全文解析、单篇精读、写作润色或同行评议替代。

## 人工接管点

- 需要更强相关性判定时：改 `case.json.research_question`，或扩展 `references/retrieval-guide.md` 的概念组。
- 需要实时检索时：把响应落到材料文件并在 `queries.jsonl` 的 `source` 标 `live_request`，
  不要与 `local_snapshot_replay` 混写。

## 维护

版本 1.0.0：契约键名冻结；新增规则 → 次版本；阈值与文案 → 修订号。
每次改动后跑 `main.py selfcheck` 与 `scripts/eval_sim.py` 四组组合，结果记入 `SELFTEST.md`。
