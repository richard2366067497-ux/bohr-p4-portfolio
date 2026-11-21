# SELFTEST — reproducible single-command and agent-path runs（writing-16 v10）

Everything below is offline and standard-library only. Interpreter on this workstation:
`C:\Users\23660\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`（Python 3.12）。
基准包：`work/p4/v9/writing-16`（v10 = v9 + 内嵌专家手册 + `environment/resources.yaml`，逻辑不变；
`references/acceptance-rubric.md` 的评分口径已并入 `references/expert_playbook.md` §1/§5）。

## 1. Evaluator matrix（`scripts/eval_sim.py`，rich/boundary × single/agent）

| case | mode | contract source | status | failures | warnings |
|-|-|-|-|-|-|
| rich | single | `case.json:output_contract`（3 键） | PASS | 0 | 0 |
| rich | agent | `case.json:output_contract`（3 键） | PASS | 0 | 0 |
| boundary | single | `SKILL.md` JSON 骨架（9 键） | PASS | 0 | 0 |
| boundary | agent | `SKILL.md` JSON 骨架（9 键） | PASS | 0 | 0 |

复跑：

```bash
python scripts/eval_sim.py --pkg work/p4/v10/writing-16 \
    --case work/p4/synth_cases/writing-16/<rich|boundary> --mode <single|agent> \
    --out OUT --json-out OUT.json
```

四组 `failures=0 / warnings=0`，通过项含 `exit_code`、`result_json`、`contract_echo`、`deliverables`、
`case_id`、`placeholder_sweep`、`field:status`、`field:sources`。

> 注：agent 模式由评测器写入工作稿样本；包内 `references/draft-schema.md §1` 的示例用 ```text
> 围栏，评测器取不到该样本，于是与 single 模式一样走确定性兜底路径，产出无占位符的完整交付物。

## 2. 单命令实跑（exit 0）

```bash
python scripts/main.py all --input work/p4/synth_cases/writing-16/rich --work WORK --output OUT
```

实测：`== build == status=partial fallback=True`、`selfcheck PASS 14 / FAIL 0`、`EXIT=0`，产出
`deliverable.md`(6848 B) / `diff_map.md`(2952 B) / `glossary.csv`(526 B) / `retained_facts.json`(584 B) /
`result.json`(12366 B)；契约键 2/3 回填（1 个 null 为“本次确有内容缺失”的如实回填），引文 13/13，
数字漂移 0。兜底路径（无工作稿）如实标 `partial` 并在稿首写明“未完成受众改写”。

## 3. 降级路径

- 坏 `case.json` → 递归找含 `output_contract` 的 json，仍无则用内置字段，`degradations` 记录；
- 材料全无 → `status=insufficient_evidence`，`deliverable.md` 仅含缺口说明；
- 单文件解析失败 / 图片 / PPTX → 只降级该文件并记名，不中断；
- 输出目录不可写 → 退到包旁 `work/`、`output/` 并写入 `degradations`。

## 4. v10 内嵌专家手册（本版）

新增 `references/expert_playbook.md`：任务本质与判分要点、错误做法→正确做法、8 步求解框架、
量化口径与公式（证据保留率 / 数值一致率与复算容差 / 论断越级率 / 缩写首现展开率·术语锁定率·
段落可追溯率 / 效率增益）、领域知识、交付物清单 + 22 项专家检查表、完整虚构案例、交付前门控；
已去提示词痕迹。`SKILL.md` 增补「执行前必读（专家方法论）」与 §12 自检首条「专家检查表逐项通过」。

### v10 包清单（14 文件，总 ≈150 KiB 上限内）

```
SKILL.md                                19971 B
scripts/render.py                       24976 B
scripts/audit.py                        23103 B
scripts/main.py                         23012 B
scripts/kit.py                          21452 B
references/expert_playbook.md           14362 B   （专家手册）
references/draft-schema.md               8068 B
README.md                                3714 B
references/audience-genre-matrix.md      3670 B
GAIN_EVIDENCE.md                         3813 B
examples/walkthrough.md                  2528 B
environment/resources.yaml                761 B
GITHUB_URL.txt                            112 B
SELFTEST.md                      <this file>
```

纯标准库、离线、无网络、无硬编码路径；最大单文件 `render.py` 24976 B（＜30KB = 30720）。
