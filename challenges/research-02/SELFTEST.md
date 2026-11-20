# SELFTEST — lit-review-workbench（research-02 v9）

本文件记录 **2026-11-20** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带语料的本地功能用例。所有评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v9/research-02 \
  --case work/p4/synth_cases/research-02/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/research-02 \
  --case work/p4/synth_cases/research-02/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/research-02 \
  --case work/p4/synth_cases/research-02/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/research-02 \
  --case work/p4/synth_cases/research-02/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 5 键（show, id, goal, title, documents） | 8 | answered |
| rich | agent | PASS | case.json:output_contract | 同上 5 键 | 8 | answered |
| boundary | single | PASS | SKILL.md (json sample) | 9 键（case_id, status, review_draft, evidence_matrix, screening_log, coverage_report, conflicts_and_gaps, audit_report, uncertainties） | 8 | insufficient_evidence |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 9 键 | 8 | insufficient_evidence |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

> rich 用例的材料是 schema/方法/示例类文档（无正式文献），管线仍逐段定位、抽取候选记录、
> 纳排筛选并写出逐字证据；boundary 用例（空文件 + 坏 JSON + 占位文本）诚实降级为
> `insufficient_evidence`，不臆造文献。

## 功能用例（本地，验证"真实筛选 + 逐字回链"而非模板）

`examples/`（`case.json` + `params.json`：4 条记录，含 1 条重复、1 条无摘要）复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = answered`，产物 **8** 文件。
- 抽取候选记录 **4**；**included R001, R002**；excluded 2（R003 `repeated`、R004 `abstract-only`）。
- 主题 slot **2/2** 填满；证据行 **2**，逐字命中 **2/2**（`hit_rate = 1.0`）。
- 契约键 **9/9** 逐键回填；占位符扫描 **0**。
- 规范化哈希（`result.json` 删除 `runtime` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`4639b0010043bfbe`**。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 占位文本）：无可用记录，`status=insufficient_evidence`；
  `draft.md`/`conflicts_and_gaps.md` 用带原因的诚实 no-data 结构；`audit_report.md` 命中率 0/0。
- 坏 JSON：作为记录候选被纳排为 `metadata-incomplete`，不进入证据表、不被引用。
- 占位文本（`[待写]`）：`parse_status=placeholder-only`，跳过且净化，不出现在任何产物。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`；顶层异常也保全 `result.json`。
- 无 `draft.json`：`build`/`all` 使用确定性纳排规则，仍产出全部产物；`draft_used=false`。

## 产物清单（每次运行写入 --output）

result.json、draft.md、evidence_matrix.json、screening_log.csv、coverage_report.json、
conflicts_and_gaps.md、audit_report.md、run_log.txt（共 8 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
