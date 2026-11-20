# SELFTEST — search-11 / patent-search-dossier（稳定性与边界证据）

本文件的每个数字都来自随包 `scripts/main.py` 在本机 Python 3.12（仅标准库）上的**真实运行**，
可用下列命令逐字复现。四组「输入形态 × 运行模式」全部 PASS（`scripts/eval_sim.py`）：

```bash
python scripts/eval_sim.py --pkg work/p4/v9/search-11 --case work/p4/synth_cases/search-11/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/search-11 --case work/p4/synth_cases/search-11/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/search-11 --case work/p4/synth_cases/search-11/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/search-11 --case work/p4/synth_cases/search-11/boundary --mode agent
```

## 1. eval_sim 结果

| 输入 | 模式 | 结果 | 契约来源 | 契约键 | 输出文件 |
|---|---|---|---|---|---|
| rich（字段字典 + 评分清单两份 md 材料） | single | **PASS**（0 FAIL / 0 WARN） | `case.json:output_contract` | case_id, deliverable, evidence_map, change_log, coverage, status | 19 |
| rich | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 19 |
| boundary（坏 JSON + 空文件 + 占位文件） | single | **PASS**（0 FAIL / 0 WARN） | `SKILL.md` json sample | 同上（6 键） | 20 |
| boundary | agent | **PASS**（0 FAIL / 0 WARN） | 同上 | 同上 | 20 |

审计项全部 PASS：`exit_code` / `result_json` / `contract_echo` / `contract_values` / `deliverables` /
`case_id` / `placeholder_sweep` / `field:status|sources|uncertainties|change_records|limits`。

## 2. rich 运行实测

| 可核验指标 | 实测值 |
|---|---|
| `status` | `partial`（方法走通，但材料未提供可定位的真实专利记录） |
| 规范化号码 | **12**（US10123456B2 / US20170123456A1 / US15234567 / US62132456 / WO2018123456A1 / WO2018123456 / WO2018012345 / EP3456789A1 / CN110123456A / US10123456 / JP2019123456A / US20180123456A1） |
| locator 数（号码 → 出处） | **29** |
| 状态 provenance 行 | **12**（全部 `unknown`，source_kind `not-declared`，`needs_official_verification=true`） |
| 许可分级行 | **4**（全部 `yellow`，许可未声明） |
| 边界条目 | **7** |
| 证据映射条目 | **17**（5 条规则引文 + 12 条号码样本） |
| 族边 | **0**（无观察到链接，不声称穷尽） |
| 渲染图 | `family_graph.png`（zlib+struct 手写 PNG） |
| 契约键覆盖 | **6/6**（顶层 + `result.output_contract`） |
| 占位符扫描 | **0**（19 个输出文件） |

号码规范化与材料 §2 的表逐行一致，例如 `US 10,123,456 B2 → US10123456B2 (us_grant)`、
`US 2017/0123456 A1 → US20170123456A1 (us_publication)`、`PCT/US2018/012345 → WO2018012345 (pct_application)`、
`10,123,456 → US10123456 (us_grant, parse_status=ambiguous, inferred_country:US)`。

## 3. boundary 运行实测（诚实降级）

| 材料 | `parse_status` | 处理 |
|---|---|---|
| `materials/broken.json`（非法 JSON，29 B） | `corrupt-json` | 不进号码表；写进 `run_log.txt` 与 `evidence/M03.json` 的 no-data 记录 |
| `materials/empty.md`（0 B） | `empty-file` | 只记状态，从不引用 |
| `materials/notes.txt`（占位文本） | `no-data-only` | 只记状态，从不引用 |
| `case.json` / `task.md` | `parsed`（脚手架） | 索引但不作为可检索来源 |

结果：`status=insufficient_evidence`；`number_registry.json` 的 entries 写一条 no-data 记录并列出检索位置
（`M01=case.json [parsed]; M02=task.md [parsed]; ...`）；`status_provenance.csv` 写一条 `patent_id=no-record`
的 no-data 行并列出检索位置；`family_graph.json` 节点/边为空并写 `no_data`；`evidence_map.json` 写一条
`kind=no-data` 记录；`dossiers.md` 写「未找到可定位号码」并列出检索位置；**exit 0**，无占位符。

## 4. 复现命令

```bash
python3 scripts/main.py all --input examples_in --output /tmp/out --work /tmp/work
# 期望：exit 0；/tmp/out 下 19 个文件；result.json.status=partial；
#       号码 12；locator 29；状态行 12；许可行 4；边界 7；证据 17；契约 6/6；占位符 0
```

## 5. 确定性

同一输入连续运行两次，`result.json` 规范化哈希一致；不含时钟、随机数或网络调用，仅标准库。
`self_check.json` 的 `evidence_all_located` 与 `figure_written` 恒为 true（或如实为 false 并记原因）。
