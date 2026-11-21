# SELFTEST — reproducible single-command and agent-path runs（writing-15 v10）

Everything below is offline and standard-library only. Run from the package root. The interpreter is
`python3` on the platform; on this workstation it was
`C:\Users\23660\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` (3.12).

基准包：`work/p4/v9/writing-15`（v10 = v9 + 内嵌专家手册，逻辑不变）。v10 复跑结果见 §7。

## 1. Example run (walks the whole pipeline)

```bash
python3 scripts/main.py all --input examples --output /tmp/w15-out --work /tmp/w15-work
```

Measured result on 2026-11-21:

- exit code 0; `status=ok`
- 1 material parsed (`manuscript.md`, 1493 chars), 11 located blocks
- ledger rows: term 2, symbol 1, definition 2, numbering 3, citation 3, claim 3, unit 6 (20 total)
- findings 4: term expansion clash (high), missing caption list (low), citation `[5]` without an
  entry (high), opposite-polarity claim pair (high)
- 3 annotation blocks applied; `preserved_facts.json` total 11, not-preserved 0
- selfcheck: files ok, contract echo ok, placeholder sweep ok

Inspect `result.json` and the `output_contract` object; every contract key is non-empty and is
repeated inside `output_contract`.

## 2. Evaluator matrix (`scripts/eval_sim.py`)

The local evaluator installs the package as `/skills/weekly-skill`, copies the synthetic case into
`/input`, and runs either the single documented command or the agent subcommands. All four
combinations were run:

| case | mode | contract source | status | failures | warnings |
|-|-|-|-|-|-|
| rich | single | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| rich | agent | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| boundary | single | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |
| boundary | agent | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |

Reproduce with, for each pair of `case in {rich, boundary}` and `mode in {single, agent}`:

```bash
python scripts/eval_sim.py --pkg work/p4/v10/writing-15 \
  --case work/p4/synth_cases/writing-15/rich --mode single \
  --out /tmp/es-out --json-out /tmp/es.json
```

## 3. Boundary degradation (honest, not hidden)

The boundary case supplies an empty file, an invalid JSON file and a placeholder-only text. The run
still exits 0 and writes:

- `status=partial` (or `insufficient_evidence` when nothing is readable),
- `sources` with a per-file `status` (`empty-file`, `invalid-json`, `placeholder-only`),
- `uncertainties` naming each skipped file and the reason,
- a complete non-empty contract echo whose `term` … `unit` fields state "zero entry found",
- `revised_manuscript.md` with an explicit no-editable-chapter note rather than invented text.

## 4. Agent enhancement path

```bash
python3 scripts/main.py init   --input /input --output /app/output --work /app/work
python3 scripts/main.py show   --input /input --work /app/work --find FDM
python3 scripts/main.py check  --input /input --work /app/work
python3 scripts/main.py build  --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output
```

`init` writes `work/source_index.json` and `work/draft_template.json`. A draft annotation is accepted
only when its locator resolves and its quote is verbatim inside that block; rejected items land in
`work/check_report.json` and never modify the source. `build` is the deterministic path, so the
single-command and agent paths produce the same artifacts for the same input.

## 5. Failure-mode spot checks

```bash
# missing input: still a valid result.json, exit 0
python3 scripts/main.py all --input /tmp/does-not-exist --output /tmp/o --work /tmp/w

# no draft: deterministic ledgers and annotations are still produced
rm -f /tmp/w/draft.json && python3 scripts/main.py build --input examples --output /tmp/o --work /tmp/w

# tampered draft annotation (quote not verbatim): rejected, source unchanged
python3 scripts/main.py check --input examples --work /tmp/w
```

The full matrix (chapter types, oversized files, binary formats, NUL bytes, invalid JSON, Unicode
normalisation) is in `references/rules-and-failure-modes.md`.

## 6. Invariants checked by `selfcheck`

- `result.json` plus all nine named artifacts exist;
- `output_contract` is a non-empty object;
- no placeholder token survives in any artifact;
- the annotated manuscript keeps every source line; removing the `EA-` quote blocks restores the
  original text (`versions/rollback_check.json`).

## 7. v10 内嵌专家手册（本版）

新增 `references/expert_playbook.md`（12416 B）：把专家手册整理为可执行方法论——任务本质与判分
要点、错误做法→正确做法、6 步求解框架、量化口径与公式（事实-来源匹配率 / 术语一致性 / 引用
缺失率 / 编号连续性 / 修改可追溯率 / 未确认项占比）、领域知识与单位陷阱、交付物清单 + 专家
检查表、完整虚构案例、交付前门控；已去除提示词痕迹。`SKILL.md` 增补「执行前必读（专家方法论）」
与 §9 自检首条「`references/expert_playbook.md` §5.2 专家检查表逐项通过」。

复跑（本机、离线、纯标准库）：

```
python scripts/eval_sim.py --pkg work/p4/v10/writing-15 \
    --case work/p4/synth_cases/writing-15/<rich|boundary> --mode <single|agent>
```

| case | mode | contract source | status | failures | warnings |
|-|-|-|-|-|-|
| rich | single | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| rich | agent | `case.json:output_contract` (10 keys) | PASS | 0 | 0 |
| boundary | single | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |
| boundary | agent | `SKILL.md` JSON sample (10 keys) | PASS | 0 | 0 |

四组 `failures=0 / warnings=0`。单命令实跑

```bash
python scripts/main.py all --input work/p4/synth_cases/writing-15/rich --output OUT --work WORK
```

输出 `build: status=ok artifacts=13`、`selfcheck: files=ok echo=ok placeholders=ok status=ok`，
exit 0；rich 输入 56 blocks、7 类账本、5 findings、2 annotation，`preserved_facts` 未保留 0。

### v10 包清单

```
SKILL.md                                10654 B
scripts/main.py                         19787 B
scripts/ledger_engine.py                26668 B
references/expert_playbook.md           12416 B   （专家手册）
references/rules-and-failure-modes.md    7348 B
templates/glossary-citation-checklist.md 1916 B
environment/resources.yaml               2860 B
README.md                                5842 B
GAIN_EVIDENCE.md                         3667 B
GITHUB_URL.txt                            112 B
examples/case.json                        449 B
examples/manuscript.md                   1494 B
SELFTEST.md                      <this file>
```

**13 个文件**，总 **97577 B**（≤150KB），最大单文件 `ledger_engine.py` 26668 B（＜30KB），纯标准库。
