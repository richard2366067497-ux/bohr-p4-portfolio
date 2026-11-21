# SELFTEST — systematic-review（research-03 v10）

本文件记录 **2026-11-21** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带题录快照的本地功能用例。四组评测均为
**PASS，0 WARN，0 FAIL**。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v10/research-03 \
  --case work/p4/synth_cases/research-03/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 |
|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 17 | 6 |
| rich | agent | PASS | case.json:output_contract | 17 | 6 |
| boundary | single | PASS | SKILL.md (json sample) | 25 | 6 |
| boundary | agent | PASS | SKILL.md (json sample) | 25 | 6 |

逐项检查（四组均 PASS，failures / warnings 均为空）：`exit_code`、`result_json`、`contract_echo`、
`deliverables`、`case_id`、`placeholder_sweep`、
`field:{status,sources,uncertainties,change_records,limits}`。

- rich：契约 17 键（五维 + 12 个计数键），全部逐键回填为非空值；产物 6 件齐全且 >40 字节。
- boundary（`output_contract=null`）：契约回退到 `SKILL.md` 的 JSON 样例（25 键），照常逐键回填。
- agent 模式 `init → check → build → selfcheck` 全部 exit 0。

## 本地功能用例（`examples/`）

`examples/`（`case.json` 固定 criteria 关键词 + `materials/records.md` 的 6 条题录）可直接复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：exit 0，`status=screened`，产物 **6** 文件；
`identified=6`、`screened_title_abstract=6`、`excluded_title_abstract=2`、`full_text_assessed=4`、
`excluded_full_text=1`、`included=3`、`excluded=3`、`unresolved=1`、`not_screened=0`；
`excluded_by_reason` 2 类；台账 **6** 行（每行带 `M01#rN` locator）；`appraisal.json` 五维非空；
契约键 **25/25**；占位符 0；规范化摘要 `sha256=1c9e3ad7123467ce`
（对 `result.json` 去掉 `runtime`/`change_records`/`outputs` 后 `sort_keys` 序列化，两次运行一致）。

## 边界行为核对

- boundary（空文件 + 坏 JSON + 10 字节文本）：`identified=0`，`status=insufficient_evidence`，
  `degradations` 记录原因，契约逐键照常回填，exit 0。
- 无 `draft.json`：`build`/`all` 用规则化筛选，仍产出全部 6 个产物。
- 坏 JSON / 缺 `case.json`：忽略并以材料自建，exit 0。
- 全文不可解析：保守排除写入 `excluded_by_reason`，`uncertainties` 说明。

## 产物清单（每次运行写入 `--output`）

`result.json`、`prisma_flow.json`、`screening_ledger.jsonl`、`appraisal.json`、`criteria.json`、
`report.md`（共 6 个）。

## v10 交付状态（专家手册嵌入）

- **新增 `references/expert_playbook.md`**（专家参考手册：九步框架 / 量化口径与公式 / 领域陷阱与单位 /
  防扣分自查表 20 项 / 完整虚构案例）；`SKILL.md` 增加「随包方法论（执行前必读）」段，指向手册的
  §3/§4/§5/§7，并在末尾「交付前自查清单」加入「专家检查表逐项通过（§7）」。
- **契约样例上移到首个代码块**，使 `eval_sim` 的契约解析在无 `case.json` 契约（boundary）时能读到
  `SKILL.md` 的 25 键 JSON 样例；rich 仍以 `case.json:output_contract` 为准。
- **单命令入口未受影响**：`python3 -B scripts/main.py all` exit 0，产出全部 6 件产物 + 契约逐键回填。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
