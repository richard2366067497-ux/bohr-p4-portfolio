# SELFTEST.md — library-03 v6 自测记录

包：`work/p4/v6/library-03` · 引擎 `facet-catalog-curator/2.0.0` · 纯标准库、退出码恒 0。

## 0. 运行环境

```
$PY = D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe
> python scripts/eval_sim.py --pkg work/p4/v6/library-03 --case <case> --mode <single|agent>
```

## 1. 单命令入口（SKILL.md 第一条可执行命令）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

`eval_sim` 解析结果：`entry.kind = single-command`，`documented_commands = [all]`
（agent 模式与 single 模式等价，只跑这一条）。

## 2. 修复点（对应 EVAL_SIM_REPORT2 的失败项）

| 原失败项 | 根因 | 修复 |
|---|---|---|
| 入口只到 `init`（build !） | CLI 没有 `all`，SKILL 首条是 `init` | 新增 `all` 子命令（init+build 一条命令），SKILL 第一条改为 `all` |
| `contract_echo` | 只写 `contract_fields` 顶层，没有 `result.json.output_contract` 对象 | finalize 始终写 `output_contract`，并把用例键与默认 6 键合并 |
| `contract_values` | `deliverable`/`evidence_map` 解析为 null，`coverage` 未绑定 | 新增键映射：`deliverable→entries/catalog_entries.jsonl`、`evidence_map→evidence_index`、`coverage→facets/facet_coverage.json`、`change_log→provenance/operations.log` |
| `field:uncertainties` 空 | 自动路径无人工不确定项 | finalize 在为空时补一条 scope 说明（不伪造结论） |
| `placeholder_sweep` | 条目/视图里的 JSON `null`、`naming_view` 的 `none`、文本中的 `none` | 新增 `sanitize_out`：递归清理 JSON 与 jsonl，正则清理 tsv/txt/md/log |
| `deliverables` 近空 | `facet_index.json` 等可能为空、`operations.log` 仅表头 | 小 JSON 自动补 `note` 诚实说明；空 jsonl 补注释行；`all` 用计划模式避免复制原始材料 |
| boundary `result_json` | 坏 JSON / 0B / `[待写]` | 扫描逐文件 try/except，异常记入 skipped/degradations，退出 0 |

`all` 使用 `--no-materialize`（计划模式），避免把输入原文复制进输出目录而引入占位符。

## 3. eval_sim 结果（rich / boundary × single / agent 全 PASS）

| 用例 | 模式 | status | failures | warnings | 契约来源 |
|---|---|---|---|---|---|
| `synth_cases/library-03/rich` | single | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/library-03/rich` | agent | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/library-03/boundary` | single | **PASS** | [] | [] | `SKILL.md (json sample)` |
| `synth_cases/library-03/boundary` | agent | **PASS** | [] | [] | `SKILL.md (json sample)` |

逐项：`exit_code`、`result_json`、`contract_echo`（6 键）、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:status/sources/uncertainties/change_records/limits`
全部 PASS。

- **rich**：输入为 `catalog_guide.md` + `facet_spec.json` → 登记 2 条，渲染 schema/coverage/
  index/tree/naming/operations/rollback/idempotency，`status=partial`（面元证据不足处进 uncertainties）。
- **boundary**：`broken.json` / `empty.md` / `notes.txt`（`[待写]`）→ 退出 0，合法 `result.json`，
  6 键回填、全部视图齐全、无占位符。

## 4. 确定性

- 无网络、无时钟读取；同输入重复运行 ops=0、命名摘要一致（`idempotency.json`）。
- 输入目录只读；`all` 不复制原始材料。

## 5. 包清单（8 文件，≤150KB，单文件 ≤30720B）

```
SKILL.md                          6019 B
README.md                         2339 B
SELFTEST.md                       <this file>
GITHUB_URL.txt                     108 B
scripts/main.py                  30239 B
scripts/catalog_core.py          29804 B
scripts/build_core.py            29638 B
references/facet_spec.json       14491 B
```
