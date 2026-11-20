# paper-notes-structurer — reading-09 (v9)

把一篇真实论文变成**结构化、可复用、可回链**的阅读笔记：重建论文**自己的**章节骨架（而不是套用
Introduction/Methods 模板），为六字段卡片（研究问题 / 数据 / 方法条件 / 主要发现 / 结论 / 局限）逐字段
给出 value + anchor + 逐字引文，把每条关键笔记写成机器可读的 note unit（带 `S3 ¶2/L17` 定位符），
**逐条核验引文是否真的出现在原文**，并把候选复现实验的数字与论文报告值做比对。纯标准库、离线、确定性。

## 1. 一条命令（评测入口）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

即使没有 draft，也会写出**全部**产物与完整 `result.json`，并 exit 0。

## 2. agent-first 增强路径（可选）

```bash
python3 /skills/weekly-skill/scripts/main.py init      --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py show      --input /input --work /app/work
#   Agent：用 show 打印的 M02/p9 定位符读原文，按需填 /app/work/draft.json（照抄 init 生成的骨架）
python3 /skills/weekly-skill/scripts/main.py check     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build     --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py compare   --input /input --output /app/output --work /app/work
```

`compare` 会把「基线 vs 加载 Skill」的对照写到 `/app/work/compare_report.json`。

## 3. 产物

写入 `--output`：`result.json`、`notes.md`、`note_units.jsonl`、`paper_card.json`、`coverage.json`、
`claims.json`、`run_log.txt`（7 个）。`result.json` 的 `output_contract` 键**同时**出现在顶层与
`output_contract` 对象内，`case_id` 原样透传。

## 4. 契约键

默认键（当 `case.json` 未给 `output_contract` 时）：

`case_id, status, result, notes, note_units, paper_card, coverage, claims, uncertainties`

若 `/input/case.json` 自带 `output_contract`，则**以它为准**逐键回填：指向产物的键解析为真实文件路径，
其余键给出真实的派生值（如 `claims` 给出带锚点的笔记行）。

`status ∈ {answered, partial, insufficient_evidence, input_error}`。

## 5. 输入约定

- 论文来源：JSON 材料的 `paper` / `text` / `abstract` 字段，否则取最大的散文文件；
  `task.md` / `case.json` 等指令与元数据文件会被跳过，绝不当成论文。
- 章节切分：论文自己的 `#` 标题与编号小节（`1.`、`3.2`、`4.1` …）→ `S0..Sn`；每段得到锚点 `S1 ¶2/L5`。
- 六字段卡片：按标题关键词映射到 `research_question / data / method_conditions / main_findings /
  conclusion / limitations`；没有对应章节的字段写 `not-reported`，**不猜**。
- 候选复现：JSON 的 `{"candidates": [{"name": ..., "metrics": {...}}]}` 列表，或一个赋值 `metrics` 字典的
  `.py` 脚本（重复的候选会被去重）。
- 不可用文件：二进制 / 空文件 / 占位文本只记录 `parse_status`，永不引用。

## 6. 目录

```
SKILL.md                           # 名称、契约、单命令、agent 路径、draft schema、管线、降级规则
scripts/main.py                    # 单文件 CLI：all / init / show / check / build / selfcheck / compare
environment/resources.yaml         # 资源入口声明：入口命令、路径、输入约定、契约、运行时
examples/case.json                 # 自带示例用例（6 段论文 + 2 个候选）
examples/params.json
templates/paper_card_template.json # 可复用模板：六字段卡片
templates/notes_template.md
templates/note_units_schema.json
README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

## 7. 降级与诚实性

- 读不到论文正文 → `status=insufficient_evidence`；每个产物都带结构化的 no-data 记录并说明检索位置；exit 0。
- 引文与原文不匹配 → 记 `verbatim=false`，不会被当成有据可依。
- 无候选实现 → 不做复现比对，并在 `uncertainties` 里说明。
- 无网络、无第三方依赖、不编造数字。

## 8. 运行要求

Python ≥ 3.9，仅标准库；不需要网络、不需要时钟、结果确定性可复现。详见 `environment/resources.yaml`。
