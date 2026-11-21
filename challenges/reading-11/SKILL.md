---
name: table-cleaning-benchmark
version: 1.0.0
description: Clean a batch of real literature extraction records into one standardised table. Normalise material aliases, indicator spellings, values and units with a traced rule chain, hold every unresolvable unit or unreported value for a human instead of converting it, detect duplicates, and return every result to its source row. Standard library only, offline, deterministic.
license: MIT
---

# table-cleaning-benchmark

Turn a batch of literature extraction records into one standardised, source-traceable table.

The task has four questions and this skill answers each with an artifact, not an opinion:

| question | what it means | where it is answered |
|---|---|---|
| 规得齐 | one indicator collapses to one field name and one value set, not one spelling per paper | 节点规范化 with a traced rule chain |
| 换得准 | a conversion keeps the original value, shows the formula and precision, and never breaks a prefix or a range | 单位不换算原则：换不动就交给人 |
| 合得对 | merging duplicate records and synonyms uses a defensible judgement key; different materials are never merged | duplicate detection on the judgement key |
| 追得回 | every changed value walks back along a rule id to the input row and the original source | change_log.json + evidence/ |

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 六步框架（含门控）** 推进——识别任务 → 建原始层与证据层 → 字段映射与类型规范化
  → 实体/单位转换 → 校验/去重/冲突消解 → 导出与复核；前一步未冻结不进入下一步。
- **口径**：按其 **§3 换算与精度口径** 用十进制换算、保留公式/规则编号/精度，重复判定默认 `abs_tol=rel_tol=0`。
- **判重**：按其 **§4 重复键** 同时核对来源、实验身份、物质、指标、条件签名与限定符，缺失条件不是通配符。
- **自检**：按其 **§5 自检指标** 逐项核验变更审计覆盖率、来源追溯覆盖率、单位复算通过率与行数守恒。
- **陷阱**：按其 **§6 领域陷阱清单** 逐条排雷（错误做法 → 正确做法）。
- **门控**：交付前逐项通过其 **§9 防扣分自查表（20 项）**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties` / `pending_review`，绝不静默提升为完整成功。

## 0. result.json contract

The entry command writes `/app/output/result.json`. It echoes every field of the caller's
`output_contract` verbatim, both at the top level and inside `output_contract`:

```json
{
  "case_id": "synth-rich-reading-11",
  "status": "partial",
  "deliverable": "cleaned_table.csv",
  "cleaned_table": "cleaned_table.csv",
  "change_log": "change_log.json",
  "pending_review": "pending_review.json",
  "counts": {"input_rows": 12, "cleaned_rows": 10, "held_rows": 2, "duplicate_groups": 2, "unknown_units": 1, "changes": 26},
  "rules_applied": ["R_ALIAS", "R_IND", "R_VAL", "R010", "R_VAL_HOLD"],
  "unknown_units": ["a.u."],
  "duplicates": [{"key": "titanium dioxide | band gap | 3.2 | eV", "row_ids": ["R001", "R002"], "count": 2}],
  "evidence_map": [{"label": "row:R001", "locator": "M01#rec1", "match": "verbatim"}],
  "self_check": "self_check.json",
  "sources": [{"id": "M01", "name": "extraction-records.json", "parse_status": "parsed"}],
  "uncertainties": ["2 row(s) are held for human review"],
  "change_records": [{"step": 1, "action": "scan material"}],
  "limits": ["an arbitrary or unresolvable unit is held for a human, never converted (rule R010)"],
  "gaps": [{"item": "resolvable unit for every held row"}],
  "output_contract": {
    "cleaned_table": "cleaned_table.csv",
    "change_log": "change_log.json",
    "pending_review": "pending_review.json",
    "counts": {"input_rows": 12, "cleaned_rows": 10, "held_rows": 2},
    "rules_applied": ["R_ALIAS", "R_IND", "R_VAL", "R010", "R_VAL_HOLD"],
    "unknown_units": ["a.u."],
    "duplicates": [{"key": "titanium dioxide | band gap | 3.2 | eV", "row_ids": ["R001", "R002"], "count": 2}]
  }
}
```

`status` is one of `partial` (records cleaned), `insufficient_evidence` (no record row found) or
`input_error` (the run could not read the input at all).

## 1. agent draft

An agent may pre-write `/app/work/draft.json` before the build step. Every field is optional; the
build step fills what is missing and records what it used:

```json
{
  "case_id": "synth-rich-reading-11",
  "notes": "free-text triage note from the agent",
  "indicator_overrides": {"bank gap": "band gap"},
  "hold_policy": "hold every unresolvable unit and unreported value for a human"
}
```

## 2. 单命令（等价入口，评测入口，one-shot）

This is the single-command equivalent and the evaluation entry point. With **no** draft present it
still produces the complete contract, every deliverable and `result.json`, and exits 0:

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

Optional arguments: `--input` (default `/input`), `--output` (default `/app/output`),
`--work` (default `/app/work`). The command is deterministic, offline and standard-library only.

## 3. agent 增强路径 (multi-step)

An agent that wants to triage first runs these in order; `init` writes a draft, `build` reads it:

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`show` prints the parsed material without writing anything. Every subcommand exits 0.

## 4. pipeline

1. **scan** every file under the input, class each one `parsed` / `empty-file` / `no-data-only` /
   `corrupt-json` / `unparsed-binary`, and record its byte size and content hash.
2. **collect** record rows from any parsed JSON carrying a `records` list, rows from any CSV, and the
   declared case-number rules from any parsed JSON carrying a `rules` list.
3. **normalise** material aliases, indicator spellings, numeric values and unit tokens with a traced
   rule chain (`R_ALIAS`, `R_IND`, `R_VAL`, `R_UNIT`, plus the declared rules).
4. **hold** every row whose value is an unreported marker or whose unit is arbitrary/unresolvable.
   A held row is never converted and never guessed — it goes to `pending_review.json` for a human.
5. **detect duplicates** on the judgement key `material | indicator | value | unit`; held rows are
   excluded so an unknown is never merged.
6. **write** the cleaned table, the change log, the pending-review list, the counts, the duplicate
   and unknown-unit lists, the report, the self check, the run log, the gain report and the evidence
   snapshots.

## 5. artifacts under /app/output

- `result.json` — the contract echo plus sources, uncertainty, change records and limits.
- `cleaned_table.csv` — one row per record with `row_id … status … note` (the deliverable).
- `change_log.json` — every changed field with `from`, `to` and the `rule_id` that caused it.
- `pending_review.json` — every held row with its reason; the human decision list.
- `counts.json`, `rules_applied.json`, `duplicates.json`, `unknown_units.json` — the four listings.
- `normalization_report.md` — counts, rules, the cleaned table, held rows and duplicates.
- `self_check.json`, `run_log.txt` — the self check and the deterministic run trace.
- `gain_report.json` / `gain_report.md` — baseline vs skill, honestly labelled.
- `evidence/M##.json` — one snapshot per material file with its parse status and quoted lines.

## 6. degradation

- No record row anywhere → `status: insufficient_evidence`; every artifact is still written, the
  cleaned table carries one explicit no-data row and records the searched locations.
- A corrupt or empty material file → recorded as `corrupt-json` / `empty-file` / `no-data-only` and
  never used; the search locations are named in `pending_review.json` and the report.
- A row with an arbitrary unit or an unreported value → held, listed, and never converted.
- A material file is never invented, and no value outside the supplied records is written.

## 7. 交付前自查

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符。
- [ ] `cleaned_table.csv` / `change_log.json` / `pending_review.json` / `counts.json` 均非空且可互相核对。
- [ ] 每个变更都有 `rule_id` 与来源行定位，未知单位保持原值且进入待确认。
- [ ] 空表 / 缺列 / 乱码 / 冲突四条路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] 两次运行主表、变更表和待确认表规范化后哈希一致。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §9 的 20 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为完整成功。
