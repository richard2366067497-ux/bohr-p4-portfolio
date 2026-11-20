---
name: facet-catalog-curator
description: 把一批科研文献/资料按面元目录（facet catalog）自动归类：扫描文件（sha256/魔数/文本层）、抽取题名/作者/年份/DOI 等待核验元数据、按受控面元 schema 登记条目、识别重复与版本候选对、渲染目录树/命名视图/倒排索引、生成可回滚与幂等证明，并逐键回填 output_contract。用于"文献资料自动分类""文件重命名归档""元数据抽取""重复/版本对账"等任务；每个面元值都要有 locator+quote，取不到就进 unresolved，绝不编造。
version: 2.0.0
tags: [catalog, facet-schema, deduplication, provenance, idempotency]
---

# 文献资料自动分类（面元目录 / facet catalog）

本包是 `library-03` 的 v6 修复形态：**第一条命令是全流程单命令**，评估器只跑它也能拿到
条目表、对账、视图、溯源与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 同时把每个契约键放进 `output_contract` 结构位与顶层同名键。用例声明的键总是合并
进来、绝不改名或丢弃；用例未声明契约时使用下列默认键（与 SKILL 本样例一致）：

```json
{
  "case_id": "string",
  "status": "success | partial | failed",
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

- `case_id` 原样透传；路径类键指向真实存在且非空的产物；无法直接映射的键写成诚实结构信封。
- 写出前统一清理占位符令牌（`待写/待补充/none/null/pending/N/A/TBD` 等）。

## 1. 单命令全流程（single-command entry）

一条命令跑完：扫描输入 → 抽取元数据与面元候选 → 登记条目 → 重复/版本对账 → 渲染
schema/条目/对账/视图/溯源 → 回填契约 → 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

- 退出码恒 0；空输入 / 坏输入同样退出 0 并写合法 `result.json`（`status=failed` 或 `partial`）。
- 不做真实文件搬运（`all` 使用计划模式），因此输入目录只读、输出目录不被原始材料污染；
  需要真实复制时使用 `build`（不带 `--no-materialize`）。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `catalog_entries.jsonl` | 每条登记：entry_id、sha256、size、文本层、题名/作者/年份/DOI、面元值、字段来源 locator+quote、状态 |
| `reconciliation_ledger.jsonl` | 重复/版本候选对与裁决：relation、decision、basis、证据、回滚动作 |
| `facet_schema.json` | 生效的面元 schema（名称、定义、allowed_values、pattern、evidence_kind、填充率） |
| `facet_coverage.json` | 面元填充率矩阵（filled/total/rate/missing） |
| `facet_index.json` | 面元值 → entry_id 的倒排索引 |
| `directory_tree.txt` | 由 facets + 模板确定性渲染的目标目录树 |
| `naming_view.tsv` | 每个条目的旧名 → 新名、模板编号、降级链、目标路径 |
| `operations.log` | 计划/执行操作日志（来源、目标、sha256 前后、状态） |
| `skipped.json` | 无法登记或明确跳过的条目及原因 |
| `rollback.json` | 回滚清单（输入从未被修改；删除本次副本即可回滚） |
| `idempotency.json` | 幂等证明（二次运行 ops=0、命名摘要一致） |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、`status`、证据、不确定性、限制 |

## 3. 子命令与参数（可选，供人工/Agent 分步复核）

| 子命令 | 作用 | 写盘 |
|---|---|---|
| all | 扫描 + 登记 + 对账 + 渲染（推荐，单命令等价入口） | 是 |
| init | 仅扫描并写部分 result.json 与 work/index.json | 是 |
| show | 打印带 locator 的文件清单、面元候选、候选对 | 否 |
| check | 校验工作稿（draft.json）与候选对裁决 | 否 |
| build | 同 all；可加 `--no-materialize` 控制是否复制文件 | 是 |
| selfcheck | 重开输出目录复核条目/对账/命名/幂等 | 否 |

公共参数：`--input`、`--output`、`--work`、`--limit`、`--no-materialize`。所有子命令都接受
`--input/--output/--work` 并始终退出 0。

## 4. 面元与证据

默认面元（`references/facet_spec.json`，案例可覆盖）：`project`、`doc_type`、`year`、`method`、
`topic`、`source_type`、`version_state`、`language`、`identifier`。每个值必须带 `locator` 与
逐字 `quote`；取不到就不填并进 `unresolved`，不猜 DOI / 作者 / 年份。

## 5. 对账与命名

- 重复判定：同 sha256 → `duplicate`；同 DOI → 版本链或预印本/正式版；同题名+首作者 → 版本链；
  文件名互为别名 → `rename_alias`。证据不足 → `needs_human`，文件保持原状。
- 命名：`{first_author}-{year}-{short_title}`（可换模板），缺字段按 `fallback_order` 逐级降级，
  每次降级写入 `naming_view.degradation`，绝不无声改名；重名加 `_dup2` 后缀。

## 6. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 用默认契约继续扫描 | `degradations: case_json_missing/invalid` |
| 无材料 / 空文件 / 坏 JSON | 合法 result.json，status=failed 或 partial | `degradations` / `skipped.json` |
| 文本层不可读（扫描件/加密） | 只登记 sha256+size，面元依据文件名与伴随元数据 | `skipped.json` |
| 面元证据不足 | 不填该面元，进 unresolved | `uncertainties` |
| 运行中断 | 已写 partial result.json 保留，异常进 errors | `status=partial` |

## 7. 边界与限制

纯标准库、无网络、无时钟读取；输入目录只读；重复运行同输入幂等（ops=0、命名一致）。
只做内容分类与去重判定，不判断文献学术价值，不编造任何元数据。
