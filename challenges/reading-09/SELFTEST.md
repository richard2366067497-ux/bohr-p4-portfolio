# SELFTEST — paper-notes-structurer（reading-09 v9）

本文件记录 **2026-11-20** 在仓库根目录用 `scripts/eval_sim.py` 对 rich / boundary 两个合成用例
× single / agent 两种模式做的本地评测结果，以及一个自带语料的本地功能用例。所有评测均为
**PASS，0 WARN，0 FAIL**（每组 11/11 项检查 PASS）。

## 复现命令

```bash
python scripts/eval_sim.py --pkg work/p4/v9/reading-09 \
  --case work/p4/synth_cases/reading-09/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-09 \
  --case work/p4/synth_cases/reading-09/rich     --mode agent
python scripts/eval_sim.py --pkg work/p4/v9/reading-09 \
  --case work/p4/synth_cases/reading-09/boundary --mode single
python scripts/eval_sim.py --pkg work/p4/v9/reading-09 \
  --case work/p4/synth_cases/reading-09/boundary --mode agent
```

## 实测结果

| 用例 | 模式 | 状态 | 契约来源 | 契约键 | 产物数 | result.status |
|-|-|-|-|-|-|-|
| rich | single | PASS | case.json:output_contract | 5 键（case_id, status, result, claims, uncertainties） | 7 | partial |
| rich | agent | PASS | case.json:output_contract | 同上 5 键 | 7 | partial |
| boundary | single | PASS | SKILL.md (json sample) | 9 键（case_id, status, result, notes, note_units, paper_card, coverage, claims, uncertainties） | 7 | insufficient_evidence |
| boundary | agent | PASS | SKILL.md (json sample) | 同上 9 键 | 7 | insufficient_evidence |

逐项检查（每组均 PASS）：`exit_code`、`result_json`、`contract_echo`、`contract_values`、
`deliverables`、`case_id`、`placeholder_sweep`、`field:{status,sources,uncertainties,change_records,limits}`。

> rich 用例的材料是一篇 3 小节的短论文（`# Reproduction demo paper` / `## 3.2 Training setup` /
> `## 4.1 Main results`）+ 两个打印 metrics JSON 的候选实现：管线切出 3 个章节、命中 2/6 卡片字段
> （其余诚实 `not-reported`，故 `status=partial`）、2 条带锚点笔记逐字命中 2/2，并把 4 个候选指标
> 与论文报告值（0.765 / 0.741）比对——`candidate_a top1=0.766 delta=0.001` 判「复现」，
> `macro_f1=0.700 delta=0.041` 判「未复现」。boundary 用例（空文件 + 坏 JSON + 占位文本）无可用正文，
> 诚实降级为 `insufficient_evidence`，产物全部带结构化 no-data 记录。

## 功能用例（本地，验证"真实切章 + 逐字回链 + 候选比对"而非模板）

`examples/`（`case.json` + `params.json`：一篇 6 段小论文 + 2 个候选）复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

最近一次运行（本机、离线、纯标准库）：

- exit 0，`result.json.status = answered`，产物 **7** 文件。
- 章节骨架 6 个 `S0..S5`（`1. Research question` … `6. Limitations and future work`）。
- 六字段卡片 **6/6** 命中（`card_ratio = 1.0`）；锚点笔记 **6** 条，逐字命中 **6/6**（`hit_rate = 1.0`）。
- 候选比对 **4** 行：`candidate_a` 两项均 `reproduces=True`（delta 0.0）；
  `candidate_b` `top1=0.879 vs 0.882 delta=0.003 True`、`macro_f1=0.860 vs 0.871 delta=0.011 False`。
- 契约键 **9/9** 逐键回填；占位符扫描 **0**。
- 规范化哈希（`result.json` 删除 `runtime` 后 `json.dumps(sort_keys=True, ensure_ascii=False,
  separators=(",",":"))` 的 `sha256` 前 16 位）：**`9371df96db61df23`**。

## 边界行为核对

- `boundary`（空文件 + 坏 JSON + 占位文本）：无可用正文，`status=insufficient_evidence`；
  `notes.md`/`coverage.json`/`claims.json`/`note_units.jsonl` 用带原因的诚实 no-data 结构，
  `note_units.jsonl` 写一条 `C000 field=no-paper` 的记录而非空文件。
- 坏 JSON（`broken.json`）：`parse_status=parsed` 但解析失败 → 不作为论文、不作为候选，不被引用。
- 占位文本（`notes.txt` = `[待写]`）：`parse_status=placeholder-only`，跳过且净化，不出现在任何产物。
- 指令文件（`task.md`）：被显式排除在论文来源之外，不会被误当正文。
- 空 `/input`、坏 JSON、缺 `case.json`：均 exit 0 并写合法 `result.json`；顶层异常也保全 `result.json`。
- 无 `draft.json`：`build`/`all` 使用确定性抽取规则，仍产出全部产物；`draft_used=false`。

## 产物清单（每次运行写入 --output）

result.json、notes.md、note_units.jsonl、paper_card.json、coverage.json、claims.json、run_log.txt（共 7 个）。

> 以上为本地模拟评测（`scripts/eval_sim.py`）结果，不代表平台正式分数；正式案例以平台 `/input` 为准。
