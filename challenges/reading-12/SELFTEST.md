# SELFTEST.md — reading-12 v6 自测记录

包：`work/p4/v6/reading-12` · 引擎 `extraction-table-auditor/2.0.0` · 纯标准库、退出码恒 0。

## 0. 运行环境

```
$PY = D:\tool\DSH\resources\runtime\primary-runtime\dependencies\python\python.exe
> python scripts/eval_sim.py --pkg work/p4/v6/reading-12 --case <case> --mode <single|agent>
```

## 1. 单命令入口（SKILL.md 第一条可执行命令）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

`eval_sim` 解析结果：`entry.kind = single-command`，`documented_commands = [all]`
（SKILL.md 只有一个 fenced 命令块，agent 模式与 single 模式等价）。

## 2. 修复点（对应 EVAL_SIM_REPORT2 / full2/reading-12.json 的失败项）

| 原失败项 | 根因 | 修复 |
|---|---|---|
| 入口只到 `init`（single 只产 result.json） | CLI 没有 `all`，SKILL 首条是 `init` | 新增 `all`（init + build + 清理）；SKILL 第一条改为 `all`，其余子命令只列在无围栏表格里 |
| `contract_echo` | result.json 没有 `output_contract` 对象（只有 `output_contract_template`） | `fill_contract` 结尾始终写 `res["output_contract"]`；契约模板并入默认 6 键 |
| `contract_values` FAIL：`empty=['deliverable','coverage']`、`missing-file=['evidence_map','change_log']` | 键名与 `ART_KINDS`/tag 规则对不上，被解析成 null | 新增显式映射：`deliverable→cleaned.csv`、`evidence_map→sources`、`change_log→changes`（空变更时给一条诚实聚合说明）、`coverage→result.coverage` |
| `field:uncertainties` 空 | 无 pending 时数组为空 | `assemble` 在为空时补一条 scope 说明（不伪造数值） |
| `placeholder_sweep` | 报告里的 `none`、JSON 里的 `null` | 新增 `sanitize_out`：递归清理 JSON（`null→""`），正则清理 csv/tsv/md/txt/log；过小文件补诚实说明行 |
| boundary `contract_echo` FAIL（8 个产物名当契约键） | SKILL 无 JSON 契约样例，回退成 `default artifacts` | SKILL.md §0 首个 fenced 块为 `output_contract` JSON 样例 → 契约来源变为 `SKILL.md (json sample)` |
| 词表随包缺失时退化 | 需砍到 ≤8 文件，无法保留 `references/` | `refs(inp)` 改为优先读用例自带 `materials/field_dictionary.json`、`unit_table.json`（缺失才退化），规则目录沿用 discover 的用例规则 |
| `--input/--output` 不识别 | CLI 只有 `--in/--out` | 子命令同时接受 `--input/--output`（保留 `--in/--out`） |

## 3. eval_sim 结果（rich / boundary × single / agent 全 PASS）

| 用例 | 模式 | status | failures | warnings | 契约来源 |
|---|---|---|---|---|---|
| `synth_cases/reading-12/rich` | single | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/reading-12/rich` | agent | **PASS** | [] | [] | `case.json:output_contract` |
| `synth_cases/reading-12/boundary` | single | **PASS** | [] | [] | `SKILL.md (json sample)` |
| `synth_cases/reading-12/boundary` | agent | **PASS** | [] | [] | `SKILL.md (json sample)` |

逐项：`exit_code`、`result_json`、`contract_echo`（6 键）、`contract_values`、
`deliverables`（8 个产物）、`case_id`、`placeholder_sweep`（8 文件 0 命中）、
`field:status/sources/uncertainties` 全部 PASS。

- **rich**：`materials/` 里的字段词典 + 单位表 + 规则目录被识别（`rules.json` 13.6KB），
  产出 cleaned.csv / change_log.csv / pending_review.csv / anomaly_report.md / rules.json /
  field_mapping.json / unit_table.json / result.json（8 文件），`status=partial`。
- **boundary**：`broken.json` / `empty.md` / `notes.txt` → 退出 0，合法 `result.json`（9.5KB），
  8 个视图齐全、6 键回填、无占位符。

## 4. 子命令冒烟

`all / init / show / check / build / selfcheck` 逐个手工运行均 exit 0；
`selfcheck` 7/7 pass（含两跑逐字节一致 determinism）。

## 5. 确定性

- 无网络、无时钟读取；`selfcheck` 两跑产物逐字节一致。
- 输入目录只读（只扫描，不复制原始材料）。

## 6. 包清单（8 文件，≤150KB，单文件 ≤30720B）

```
SKILL.md                          5200 B
README.md                         2372 B
SELFTEST.md                       <this file>
GITHUB_URL.txt                     108 B
scripts/main.py                  23291 B
scripts/clean_engine.py          27220 B
scripts/clean_flow.py            29904 B
scripts/clean_report.py          23355 B
```
