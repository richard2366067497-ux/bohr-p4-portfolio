---
name: repro-metric-crosscheck
description: Reproduce a paper's reported metric by actually executing the bundled candidate numerical methods, comparing observed values against the reported ones inside a tolerance band that was locked before any run, and attributing every gap to environment / data / implementation / under-specified paper. Use for paper reproduction, method verification, "our number does not match the paper", parameter restoration, or metric-versus-log reconciliation tasks with case.json, materials and candidate scripts.
version: 1.0.0
---

# 论文复现与方法验证：双方法交叉验算（Agent 主答 + 脚本辅助）

本 Skill 服务于"参数 / 代码 / 指标验算与差异归因"子场景：**真实运行材料包里提供的两份候选数值方法**，
把运行得到的指标与论文声明的指标按**事前锁定的容差**逐项对比，对每处偏差给出归因，
最后给出可复现 / 部分复现 / 不可复现的分级结论，并留下他人可重跑复核的记录。

---

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 1. 五命令主路径（先读这一节）

在 Skill 根目录记为 `$SK` 的前提下，按顺序执行：

```bash
python3 "$SK/scripts/main.py" init       # ① 建索引 + 锁定容差 + 先写合法 partial result.json
python3 "$SK/scripts/main.py" show       # ② 打印带 locator 的原文 / 对象清单，供逐字引用
#   ← 评审 Agent 在这里亲自阅读材料，写工作稿 /app/work/draft.json
python3 "$SK/scripts/main.py" check      # ③ 机械校验：契约字段、quote 命中、覆盖数、容差是否被事后放宽
python3 "$SK/scripts/main.py" build      # ④ 真实运行两份方法 + 对比 + 归因 + 无条件 finalize result.json
python3 "$SK/scripts/main.py" selfcheck  # ⑤ 复检产物：契约齐全、运行可核验、容差未被篡改
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
>
> `init` / `show` / `check` 三个命令是给 Agent 自己的：`init` 告诉你材料结构与容差先验，
> `show` 让你能逐字抄录引文，`check` 告诉你工作稿哪里不达标。跳过这三步直接 `build`，
> 得到的是"脚本自动跑出来的对比表"，缺少你的参数溯源、口径判断、归因解释与结论措辞，
> 只能拿到完整但降级的基础分（`status=partial`，且 `degradations` 会写明缺口）。

`build` 无条件是安全的：工作稿缺失、损坏、不完整、或运行超时，它仍会写出
**合法 `result.json`（契约字段全部回填）+ 最小主产物**，`status=partial`，缺口写进
`degradations` / `pending_human`，退出码恒为 `0`。

包根定位（Harness 安装在 `/skills/weekly-skill`，其他环境用回退查找）：

```bash
SK=/skills/weekly-skill
[ -f "$SK/SKILL.md" ] || SK=$(dirname "$(find / -maxdepth 5 -name SKILL.md 2>/dev/null | head -n1)")
python3 "$SK/scripts/main.py" --help
```

## 2. 用途与适用条件

**适用**：输入含 `case.json`（`case_id` / `output_contract` / `task_instruction`）+ `task.md` + 材料
（论文正文或表格文本、一两份候选实现 `.py`、可选数据与依赖清单），要求给出复现结论与对比数值。

**不适用 / 应当降级**：没有任何可执行候选（只能读论文）→ `insufficient_evidence`；
材料是纯图片或扫描页且无 OCR → 不猜像素，进 `pending_human`；
要求"证明原作者代码在原始数据上完全一致"→ 材料里没有原仓库和原始数据，必须明写
`missing_objects` 并把结论封顶在 `partially_reproduced`。

**硬边界**：只用 Python 3 标准库；不联网；不 `pip install`；不改宿主环境；不伪造运行日志与指标；
论文没报告的数字不补造（写 `null` / `not_reported`）。

## 3. 运行契约

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 材料（相对路径由 case 决定） |
| 工作区 | `/app/work`（`index.json`、`tolerance_plan.json`、`draft.json`、`runs/`、`check_report.json`） |
| 产物 | `/app/output/result.json`（主产物）+ `repro_record.json`、`repro_report.md`、`comparison.csv`、`param_table.csv`、`attribution.csv`、`tolerance.json`、`runs/*.log` |
| 路径覆盖 | 环境变量 `SCIM_INPUT` / `SCIM_OUTPUT` / `SCIM_WORK`，或 `--input/--output/--work`；都缺时回退 `/input`、`/app/output`、`/app/work`，再回退 CWD 下的 `input/` |
| 依赖 | Python ≥ 3.8 标准库；`pdftotext` 可选（缺失时用内置流解码） |
| 退出码 | **恒 0**（包括空输入、坏 JSON、未捕获异常） |
| 预算 | 64 次模型请求 / 900 秒 / 单次 16384 token；脚本软截止 760 秒 |
| 不依赖 CWD | 所有路径由参数或环境变量决定，脚本用 `__file__` 定位自身 |

## 4. 输入发现（按语义识别，不假设键名）

1. 读 `case.json`，编码依次尝试 `utf-8-sig` → `utf-8` → `gb18030` → `latin-1`；损坏时继续，原因写 `errors`。
2. 递归扫描材料目录，跳过 `case.json`；先按**魔数**（`%PDF`、`PK`+`word/`/`xl/`/`ppt/`、PNG/JPEG）再按扩展名判类型，不信标签。
3. 语义字段识别（键名可变）：任务说明（`task_instruction`/`task`/`instruction`/`scope`）、
   候选方法（`candidates`/`implementations`/`methods`/`code_variants`）、
   报告指标（`reported_metrics`/`expected`/`metrics`/`targets`）、
   容差（`tolerance`/`abs_tol`/`rel_tol`）、环境与种子、`output_contract`。
4. 每个材料分配稳定 `id` + `sha1`，正文切成带 locator 的单元，locator 形如
   `paper@pg3.p2`（PDF 第 3 页第 2 段）、`readme@s2.u1`（Markdown 第 2 节第 1 段）、
   `data@r7`（CSV 第 7 行）、`run@j#/metrics/mae`（JSON 指针）。
5. 六个材料类做覆盖登记（脚本自动 + 工作稿补充）：`code`、`data`、`param`、`dependency`、`license`、`eval_script`。
   找不到不静默跳过，写 `missing`；论文写"available upon request / 需申请"的写 `needs_request`。

## 5. 输出契约（result.json）

```json
{
  "case_id": "<原样来自 case.json>",
  "status": "ok | partial | insufficient_evidence | input_error",
  "<output_contract 的每个字段名>": "...",
  "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
  "degradations": [], "changes": [], "runtime": {}
}
```

规则：

- **`output_contract` 的字段名一个不改、一个不漏**，按语义映射填值；无法映射的字段保留 `null`
  并在 `degradations` 记 `contract_field_unmapped:<字段名>`。
- 契约是嵌套对象时逐层保留同名结构；契约是字段清单（`[{"name": ...}]`）时按 `name` 展开为顶层键。
- 缺值用 `null` / `[]`，**不用空字符串假装有值**。
- 信封字段固定存在：`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、
  `degradations`、`changes`、`runtime`。
- 每个案例**第一件事**就是写一份字段齐全的 partial `result.json`，随后增量覆盖。

字段级规则见 `references/output_contract.md`。

## 6. 主流程：七环节闭环

| # | 环节 | 谁做 | 落点 |
|---|---|---|---|
| 1 | 材料定位 | 脚本索引 + Agent 判定缺失/需申请 | `result.sources`、`result.checklist` |
| 2 | 环境快照 | 脚本采集 + Agent 对照论文声明 | `result.environment` |
| 3 | 参数复原 | **Agent 填三类来源**；脚本查冲突 | `result.params`、`param_conflicts` |
| 4 | 代码运行 | 脚本真实执行，逐 run 落日志 | `result.runs` |
| 5 | 结果比较 | 脚本算偏差 + Agent 定口径 | `result.comparison` |
| 6 | 差异归因 | 脚本给判定 + Agent 写解释 | `result.attributions` |
| 7 | 分级结论 | 脚本按封顶规则定档 + Agent 写理由 | `result.verdict` |

**分工原则**：脚本负责确定性重活（解析、定位、执行、算术、校验、渲染）；
Agent 负责需要判断的事（这份材料算不算论文代码、参数该取正文还是代码默认值、
指标口径是百分数还是小数、偏差该归到数据切分还是实现细节、结论怎么写才诚实）。
工作稿就是这些判断的载体；没有工作稿，判断位就是空的。

## 7. 工作稿 `/app/work/draft.json`

`init` 会写同名骨架 `draft_skeleton.json`。最小可用内容：

| 字段 | 要求 |
|---|---|
| `paper` | title / doi / repo / commit / data_version；未知写 `null` |
| `scope` | `synthetic_trial`（本次是否组织方合成试验）、`not_original_repo`（是否有原仓库） |
| `plan` | 步骤列表：goal、command、expected、status |
| `environment` | python、platform、packages、seed、hardware_note |
| `params[]` | `name`、`value`、`class`∈`paper`/`code_inferred`/`self_set`、`evidence{source_id,locator,quote}`、可选 `conflict_note` |
| `paper_values[]` | `metric`（与运行输出同名）、`value`、`unit`、`evidence{...}` |
| `tolerance[]` | 只能等于或严于 `tolerance_plan.json`（含 `__default__`） |
| `claims[]` | `id`、`kind`、`text`、`confidence`∈`direct`/`inferred`/`undetermined`、`evidence[]` |
| `attributions[]` | 你的归因补充：`metric`、`cause`、`evidence`、`confidence`、`disposition` |
| `checklist[]` | 你补充的缺失材料登记（脚本没认出来的项） |
| `candidates[]` | 可选：显式指定要跑哪两份方法（`name` + `path`/`command`） |
| `verdict` | `tier` ∈ `reproduced`/`partially_reproduced`/`not_reproduced`/`insufficient_evidence`、`rationale` |

完整字段字典与填写示范见 `references/draft_schema.md`。

`class` 口径：论文正文/表格明确写出 → `paper`（必须带逐字 quote）；
只能从代码默认值/配置推断 → `code_inferred`（写文件名与行号）；
两边都没有、由你设定 → `self_set`（写理由，并进 `uncertainty`）。

## 8. 证据与定位规范

- 每条关键结论、每个关键数字、每个 `paper` 类参数都要 `quote`（**逐字**）+ `locator`。
- `check` / `build` 会对索引正文做规范化（NFKC、去零宽、空白折叠、大小写）后**逐字查找**；
  找不到即 `evidence_rejected`，该条不进入产物（或降级为 `pending_human`）。
- quote 命中但 locator 段号不同：脚本**回绑**到真实 locator 并记 `locator_rebound`，接受不拒绝，
  但产物里写的是真实 locator，方便他人复核。
- **绝不改写原文凑通过**；也绝不把"我记得论文里是 0.8"写进产物。
- 数字必须能溯源：`comparison` 每行的 `observed` 来自某次 run 的 stdout，行内带
  `run` + `metric_evidence`（解析到该数字的原始输出行）；`reported` 带 `reported_locator` + `reported_quote`。

## 9. 事前容差（本题核心，禁止事后凑）

`init` 在**任何运行之前**写 `/app/work/tolerance_plan.json`：

```json
{"declared_step": "init", "declared_at": "...", "before_any_run": true,
 "plan_sha256": "<entries 的规范序列化哈希>",
 "entries": {
   "mae": {"abs_tol": 0.005, "rel_tol": 0.02, "basis": "case_declared", "source": "case.json#/tolerance/mae"},
   "__default__": {"abs_frac": 0.005, "rel_tol": 0.02, "basis": "prior_default"}
 }}
```

- case 给了容差 → 记为 `case_declared` 并照抄；没给 → 该指标落 `__default__` 先验
  （相对 2%，绝对取报告值的 0.5%，用来吸收论文只报 2~3 位小数带来的舍入）。
- `abs_frac` 在比较时解析为 `abs_frac × |reported|`；`abs_tol` 直接使用。
- **逐指标摊平**：`build` 在启动任何子进程之前，把本次要比较的每个指标写成显式条目
  （继承 `__default__` 或 case 声明），标 `declared_step="build:pre_run"` 并重算 `plan_sha256`。
  于是报告里每个被比较的指标都有一行属于自己的、带时间戳的容差。
- **锁定证明**：`plan_sha256` 是 `entries` 的规范化哈希；每次 run 记录运行时读到的
  `tolerance_plan_sha256` 与 `plan_written_at`。`selfcheck` 校验：① 计划哈希未被改动；
  ② 每个 run 记录的哈希等于计划哈希；③ `plan_written_at ≤ run.started_at`。三条同时成立才叫"事前"。
- 工作稿里的 `tolerance[]` 只能取等或更严；更宽即 `tolerance_widened_after_run`（记 ERROR）。

## 10. 双方法互证与差异归因

材料里通常有**两份**候选数值方法。两份方法互为对照：它们一致与否，直接决定归因方向。

| 判定（脚本确定性） | 触发条件 | 归因候选原因 |
|---|---|---|
| `none` | 所有观测都在容差内 | 无差异 |
| `shared_upstream` | 两份方法彼此接近（极差 ≤ 容差），但都偏离论文值 | 数据版本/切分、预处理口径、关键参数、环境共同上游 |
| `implementation_divergence` | 两份方法彼此差异 > 容差，且至少一份超差 | 实现细节（度量实现、默认超参、随机性） |
| `single_method_only` | 只有一份产出数值 | 无法区分实现与上游 |
| `paper_value_unavailable` | 材料无该指标报告值 | 无法判定一致性 |
| `scale_mismatch` | 观测与报告值相差 ~100 倍（如 76.5 vs 0.765） | 百分数/小数口径不一致 |
| `run_failed` | 某份方法非零退出或超时 | 环境/依赖/实现缺陷 |

脚本给出判定 + 证据引用；Agent 在 `draft.attributions[]` 里补上人类可读的原因、证据与处置建议。
脚本的判定不会被 Agent 覆盖，两者并列写进 `result.attributions`，冲突进 `uncertainty`。

## 11. 结论分级与封顶

| tier | 条件 |
|---|---|
| `reproduced` | 所有可比观测都在事前容差内，且材料类无 `missing` |
| `partially_reproduced` | 部分在容差内；或数值全部在容差内但关键材料（原仓库/原始数据/原始日志）缺失 |
| `not_reproduced` | 所有可比观测都超差 |
| `insufficient_evidence` | 没有任何一份方法跑出可比数值，或没有任何报告值 |

**封顶规则（诚实性优先）**：若 `missing_objects` 含原仓库/原始数据/原始日志，或 `scope.synthetic_trial=true`，
则最高只能给 `partially_reproduced`，并在报告里写明"组织方合成试验不是原作者代码、物理实验或全量数据复现"。

Agent 可以**收紧**结论（写更低的档），不能**放宽**（把 `partial` 写成 `reproduced`）；
放宽时脚本保留自己的判定并记 `verdict_conflict`，`uncertainty` 里说明。

## 12. 异常与降级

| 情况 | 处理 | status |
|---|---|---|
| `case.json` 缺失/坏 JSON | 空 case 继续；原因写 `errors`；契约无字段可回填 | `input_error` |
| 材料目录为空 | 索引为空，跳过运行；仍写合法 result.json | `insufficient_evidence` |
| PDF 无文本层 | `pdf_text:failed` 记 notes，建议渲染/OCR，进 `pending_human` | `partial` |
| 图片/扫描页 | 不读像素，进 `pending_human` | `partial` |
| 找不到候选方法 | 不伪造运行，`pending_human` 要求人工执行 | `insufficient_evidence` |
| 单份方法报错/超时 | 只降级该 run，另一份继续；`runs/*.log` 保留 stderr | `partial` |
| 方法跑通但无指标输出 | `uncertainty` 记录，不猜数值 | `partial` |
| 没有工作稿 | 确定性最小交付（材料/环境/容差/真实运行/对比/自动归因） | `partial` |
| 工作稿部分字段缺失 | 用脚本值补齐，缺的写 `pending_human` | `partial` |
| 容差被放宽 | `check` 记 ERROR；`build` 记 `tolerance_widened_after_run` | `partial` |
| 任何未捕获异常 | 顶层兜底写 partial `result.json` | `partial` |

## 13. 自查（selfcheck）

`selfcheck` 只读产物，不改它们，检查项：

1. `result.json` 存在且是合法 JSON；`output_contract` 的每个字段名都在，信封字段齐全；
2. `case_id` 与输入一致；`status` 在枚举内；无行时必须有 `no_comparison_rows` 说明；
3. `comparison` 每行都有 `tolerance`（abs/rel 之一非空）、`reported_source`、`observed`；
4. 每个 `run` 有 `argv`、`exit_code`、`duration_ms`、`log_path` 且日志文件真实存在；
5. `tolerance_plan.plan_sha256` 可重算一致，且所有 run 记录的哈希等于它；
6. `verdict.tier` 与 `comparison` 统计一致（或 `verdict_conflict` 已登记）；
7. `attributions` 每条都有 `cause` + `evidence`；
8. 输出目录里 `repro_report.md`、`comparison.csv`、`param_table.csv`、`attribution.csv` 非空。

输出 `PASS` / `FAIL: <项>` 清单，并写 `/app/output/selfcheck.json`。退出码仍为 0。

## 14. 最小调用示例（示例，非正式案例结果）

输入：`/input/case.json`（`case_id=demo-001`，`output_contract={"reproduction_record":{}, "comparison_table":[]}`），
材料 `paper.md`、`method_a.py`、`method_b.py`、`data/sample.csv`。

```bash
python3 "$SK/scripts/main.py" init
# → materials 4, units 19; tolerance: __default__ abs_frac=0.005 rel=0.02 (before_any_run=True)
# → coverage: code=2 data=1 param=0 dependency=0 license=missing eval_script=0
python3 "$SK/scripts/main.py" show --id paper --grep "MAE"
# → paper@s3.u2 | Table 2 reports MAE 0.184 and R2 0.87 for the proposed method.
# （Agent 读材料，写 /app/work/draft.json：params 3 条、paper_values 2 条、claims 4 条）
python3 "$SK/scripts/main.py" check
# → CHECK: PASS claims=4 evidence_ok=5 rejected=0 params=3 tol=2 widened=0
python3 "$SK/scripts/main.py" build
# → [band] materialized 2 metric entry(ies) before any run: mae, r2
# → runs 2 (ok 2); rows 4 (in 1 / out 3 / n.a. 0); verdict partially_reproduced
python3 "$SK/scripts/main.py" selfcheck
# → SELFCHECK: PASS (8/8)
```

示意对比（**示例数据，非正式案例结果**）：

| run | metric | observed | paper | rel_dev | 判定 |
|---|---|---|---|---|---|
| method_a | mae | 0.1870 | 0.184 | 1.63% | in_tolerance |
| method_b | mae | 0.2000 | 0.184 | 8.70% | out_of_tolerance |
| method_a | r2 | 0.9958 | 0.87 | 14.46% | out_of_tolerance |
| method_b | r2 | 0.9952 | 0.87 | 14.39% | out_of_tolerance |

本例的归因结果：`mae` → `implementation_divergence`（method_b 把预测四舍五入到一位小数），
`r2` → `shared_upstream`（两份方法一致却都偏离论文），`*` → `parameter_restoration`。

## 15. 文件清单与维护

```
SKILL.md                       本文件：主路径、契约、规则、降级、自查
scripts/main.py                CLI 前端：init | show | check | selfcheck | 参数解析
scripts/build.py               build：报告值合并、容差摊平、执行、对比、归因、定稿、渲染
scripts/engine.py              流水线：索引、报告值、候选发现、执行、比较、归因、结论
scripts/core.py                确定性内核：抽取/定位/逐字校验/容差算术/指标解析/契约回填
references/output_contract.md  result.json 信封与 output_contract 回填规则、状态枚举
references/draft_schema.md     draft.json 字段字典、三类参数口径、常见报错修法
references/method_rules.md     容差锁定协议、互证判定表、封顶规则、复核步骤
```

四个脚本各 ≤30KB（`main.py` ≤25KB），纯标准库，互相 `import` 而无需安装。
辅助开关：`build --timeout N`（单 run 超时，默认 120s）、`build --dry-run`（只装配不执行，
用于校验流水线）、`show --stats/--case`、`python3 -B scripts/core.py --selftest`（内核自检）。

变更时同步三层：脚本行为 → §1/§12；字段 → §5/§7 与两份 references；判定规则 → §9~§11 与 `method_rules.md`。
提交前跑一次 `python3 scripts/main.py build --dry-run`（不执行方法，只校验装配）与 `selfcheck`。
