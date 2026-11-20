# academic-writing-benchmark-builder — 写作题金标准与双评一致性（writing-13）

把一批科研材料变成**可判分的学术写作 benchmark 包**：题面（每题六字段）、抽取式参考答案、
0/1/2 档可观察锚点、双评分员分数与 Cohen's kappa、正控/负控校准、逐题评测报告、复现记录，
一次落盘到 `/app/output`，并把 `output_contract` 逐键回填进 `result.json`。

## 安装

纯 Python 3.9+ 标准库，无网络、无第三方包。把目录放到 `/skills/weekly-skill`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py        # 入口：init / check / build / run
  scripts/verify.py      # 确定性内核：发现、事实抽取、出题、锚点、双评、kappa、契约
  scripts/render.py      # 渲染层：题面 / 锚点 / 报告 / 复现 / 金标准 / 对照 / 版本
  environment/resources.yaml
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

单命令全流程（评测只跑这一条也能通过）：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

默认 `--input /input`、`--output /app/output`、`--work /app/work`。退出码恒为 0；
`run` 内部等价于 `init → check → build`，任一步写入的 `result.json` 都会被最终版本覆盖。

### agent-first 路径

脚本负责机械判定，Agent 负责写什么：

```bash
python3 /skills/weekly-skill/scripts/main.py init  --input /input --output /app/output --work /app/work
# Agent 读 /app/output/tasks.jsonl 与 reference_answers/，把作答写入 /app/work/answers.json
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

`answers.json`：`{"answers": [{"task_id": "T01", "text": "..."}]}`；缺省或坏 JSON 时
`build` 回退到抽取式参考答案（`answer_source=auto_extract`），不报错。

## 最小可运行示例

`/input` 只需一个材料文件（`case.json` 可选）：

```
/input/case.json                  {"case_id": "demo-1", "language": "en"}
/input/materials/material.md      两段正文：方法段含 0.35 g、750 °C、1.2 bar、12000 h^-1；
                                  结果段含 99.1 %、550–750 °C；另附一条 DOI。
```

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出（本包自测时真实得到）：

```
== run | status=ok | tasks=3 | kappa=1.0 | self_check=pass
```

产物：`deliverable.md`、`tasks.jsonl`、`reference_answers/T01.md…`、`anchors.md`、`scores.csv`、
`scores_detail.csv`、`evaluation_report.md`、`reproducibility.md`、`golden_standard.json`、
`diff_report.md`、`version_history.md`、`run.log`、`self_check.json`、`result.json`。
空输入或坏 JSON 时 `status=insufficient_evidence`，`result.json` 仍合法、exit 0。

## 判分口径

- 每题 4 个必需要点，逐字取自材料，带 `材料 + ¶定位`；要点没写进材料的题不会生成。
- 每题 5 条锚点：`contains_all`、`number_preserved`、`no_new_numbers`、`word_limit`、`section_order`，
  覆盖 0/1/2 档（0 拒绝，1 可接受但需注明，2 直接接受）。
- rater_a = 严格归一化包含；rater_b = 词袋覆盖；两者独立计分，delta>1 只登记锚点复查项，不改分数。
- 正控（抽取式参考答案）必须通过，负控（删数字并截断 16 词）必须被拒绝，否则 `status=partial`。

## 限制

- 不联网、不调用外部模型；改写类答案只能按字符串/词袋口径判定，人工认可的等价改写可能被低估
  （逐题证据会列出命中项，便于人工复核）。
- 扫描件、图片中的数值不读取、不推断；PDF 仅做文本层抽取（优先 `pdftotext`，否则内置 flate 解码）。
- 材料只有标记行（如空模板）时不造题，状态 `insufficient_evidence` 并在 `degradations` 写明缺口。

## 维护与版本策略

- 版本 2.0.0：契约键名冻结，主版本才改；新增锚点/检查 → 次版本；文案与阈值 → 修订号。
- 改动后跑 `verify.py` 侧的空/坏输入探针与 `scripts/eval_sim.py`（rich/boundary × single/agent），
  记录在 `SELFTEST.md`。
- 规则句集中在 `SKILL.md`（`golden_standard.json` 的 `source` 逐条指回行号），实现集中在内核脚本。
