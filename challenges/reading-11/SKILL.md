---
name: litread-bench-ledger
description: 把 /input 里的科研材料现场做成一套"判得动、跑得一致、查得回、改得动"的文献阅读题集与评分台账：Agent 亲自读材料、写题卡与评分锚点，脚本负责材料索引、逐字引文定位、0/1/2 规则评分、评分器自校准探针、分数三指针闭包校验、六轴覆盖矩阵与版本可比性判定，最后把 output_contract 全部字段原样回填进 result.json。适用于文献阅读 benchmark 建设、题集可判性审计、分数可追溯性核查与题集版本对比。
version: 1.0.0
---

# 文献阅读 Benchmark 与评分台账（Agent 主答 + 脚本核验 + 兜底必成）

## 0. 五命令主路径（先看这里，再动手）

```bash
python3 scripts/main.py init       # ① 建索引：解析 case.json / output_contract / task.md，登记材料、workorder 题源、候选输出，先写合法 partial result.json
python3 scripts/main.py show       # ② 打印带 locator 的材料段落与题源，供你逐字引用（--material M01 --start 1 --limit 20）
# ③ 你亲自读材料，写工作稿 /app/work/draft.json（题卡、参考答案、评分锚点、冲突与不确定项）
python3 scripts/main.py check      # ④ 机械校验：字段齐全、quote 逐字命中、locator 一致、workorder 覆盖、契约字段不缺
python3 scripts/main.py build      # ⑤ 由工作稿生成 9 件台账产物（benchmark/）+ finalize result.json（无条件 finalize）
python3 scripts/main.py selfcheck  # ⑥ 复检：三指针闭包率、计数一致性、契约回填、面板与 CSV 对账
```

> **脚本不会代替你阅读理解；必须先阅读材料、写工作稿，再运行 build；禁止只跑 build 就结束。**
> `build` 在没有工作稿时只产出"完整但降级"的最小台账（`mode=fallback_minimal`，`status=partial`），
> 它能保住不空手，但拿不到题目设计、参考答案、冲突识别这几项的分。真正得分的是你在 `draft.json`
> 里写下的判断。

时间分配建议（预算 64 次请求 / 900 秒）：`init` 10 秒 → `show` 分页读 3–6 次 → 写工作稿 → `check` 改 2 轮 → `build` → `selfcheck`。到 700 秒还没写完工作稿，就把已写好的部分交出去直接 `build`。

## 1. 用途与适用条件

**做**：读输入材料 → 按 workorder（若有）或材料本身建题卡 → 给每题写参考答案、0/1/2 评分规则、
逐字证据锚点 → 机械核验 → 出题集快照、锚点审计表、逐题得分 CSV、面板、失败样例库、版本台账 →
回填 `result.json`。

**适用**：
- 材料形态：段落文本、表格文本、Markdown / TXT / CSV / JSON / HTML / TeX / DOCX / XLSX / PDF（有文本层）；
- 任务形态：抽取、数值、方法、定义、表格、冲突识别、覆盖性问答；
- 语言：中英混排（关键项匹配对中文按字滑窗、英文按词，均做大小写与空白归一）；
- 输入是否带 workorder、是否带候选输出、是否带 checker 日志，都能跑（见 §4、§11）。

**不适用 / 明确不做**：
- 纯图片材料（脚本只登记 `no_text` 缺口，不猜内容；需要平台 OCR 工具补读后再 `init`）；
- 替被评测 Agent 答题、凭空补造 gold answer、把合成 checker 日志说成 DSH 分数；
- 复现材料里的代码实验。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入根 | `/input`（含 `case.json`、`task.md`、材料）；可用 `--input` 或 `LITREAD_INPUT` 覆盖 |
| 工作根 | `/app/work`（`index.json`、`draft.json`、`check_report.json`、`draft.resolved.json`）；`--work` / `LITREAD_WORK` |
| 输出根 | `/app/output`（`result.json` + `benchmark/` 八件产物）；`--output` / `LITREAD_OUTPUT` |
| 入口 | `python3 scripts/main.py {init,show,check,build,selfcheck}`；`python3 scripts/main.py --help` 退 0 |
| 依赖 | 仅 Python 3 标准库；不联网；路径由 `Path(__file__)` 推导，**与当前工作目录无关** |
| 退出码 | **恒为 0**：错误写进 `result.json.errors`，不靠非零码表达 |
| 预算 | 64 次请求 / 900 秒 / 单响应 16384 token；`init` 一跑就有合法 `result.json`，随时可中断 |
| 幂等 | 重复 `build` 覆盖同名产物；每次 build 把上一版 `cards.json` 摘要记进 `version_diff.json` |

## 3. 输入发现（不要假设键名）

`init` 递归扫描输入根，跳过隐藏文件、`__pycache__`、`.git`、`node_modules`，以及**根目录**的
`case.json` / `task.md` / `result.json`（外壳文件，不是材料）。判型靠扩展名 + 魔数（`%PDF`、`PK`）。

每个材料切成段落，给一个**稳定 locator**：`M<材料号>#p<段号>`，例如 `M01#p12`；PDF 额外记 `page`。
若材料本身带原生 id（JSON 的 `paragraph_id` / `id`，表格的 `table_id`），脚本把它记成 `native_id`，
题卡可以同时引 `locator` 与 `native_id`——这样引用能对上组织方的来源编号。

`case.json` 按语义识别，不按固定 schema 死读：

| 语义 | 认的键名 |
|---|---|
| 案例标识 | `case_id` / `caseId` / `task_id` / `sample_id` / `id` |
| 输出契约 | `output_contract` / `outputContract` / `contract` / `required_outputs` / `result_contract` |
| 任务说明 | `task_instruction` / `instruction` / `prompt` / `task` / `question` |
| 题源 workorder | `organizer_workorder` / `workorder` / `benchmark_workorder` / `items` / `tasks` / `cards` / `questions` |
| 候选输出 | `candidate_output(s)` / `candidate_answer(s)` / `baseline_output` / `model_output` / `submissions` |
| 检查器日志 | `checker_log` / `checker_logs` / `technical_logs` |

同一语义有多个键时按表中顺序取第一个非空值。`output_contract` **原样透传**，不改名、不丢键、不重排。
找不到 `case.json` 时仍继续（材料照常索引），`errors` 记一条，`status=partial`。

## 4. 工作稿 schema（你写的判断，脚本不会替你写）

路径：`/app/work/draft.json`（UTF-8，字段细节与示例见 `references/item-card-schema.md`）。

```json
{
  "set_meta": {"set_id": "读材料后自拟", "version": "v1", "license": "从材料/案例读，读不到写 unknown",
               "scope": "一句话说明这套题考什么"},
  "items": [{
    "item_id": "W01",
    "task_type": "extraction|numeric|method|definition|table|conflict|coverage|other",
    "question": "可判分的题面（≥10 字符，不要含糊的『谈谈』）",
    "source_refs": [{"material": "M01", "locator": "M01#p3", "native_id": "P-07", "quote": "逐字复制的原文片段"}],
    "reference_answer": [{"text": "参考答案要点", "locator": "M01#p3"}],
    "reference_missing": false,
    "scoring_rule": {"mode": "key_terms|numeric|manual_only",
                     "scale": {"2": "答到什么算满分", "1": "部分正确", "0": "错/空/答非所问"},
                     "key_terms": ["1.42", "39 percent"], "must_have": 1},
    "difficulty": "easy|medium|hard",
    "license": "unknown|CC-BY-4.0|...",
    "notes": "出题理由或边界说明（可选）"
  }],
  "conflicts": [{"a": "M01#p4", "b": "M02#p2", "statement": "两处数值不一致，题面要求指出冲突而非裁决"}],
  "uncertainties": ["材料未报告 X，本题按『识别为未报告』给分"],
  "history": [{"set_version": "v0", "scale_version": "1", "run_config_hash": "...", "n_items": 4}]
}
```

工作稿的四条硬规矩：

1. **一题一卡，`source_refs` 至少一条**，`quote` 从 `show` 的输出里**整段复制**，不改词、不翻译、不加省略号；长度 ≥12 字符。
2. **`reference_answer` 只能来自材料**。材料没给答案就 `"reference_missing": true` 并清空
   `reference_answer`，题目改问"材料是否报告了 X"。**严禁自造 gold answer**。
3. **`scoring_rule.key_terms` 用原文用词**（1–5 条短串），它是脚本算 coverage 的唯一依据；写抽象描述
   （如"回答准确"）无法机械判分，`check` 会报错。
4. **冲突写进 `conflicts`**，两处 locator 都留；脚本只核对两处引文都存在，不替你裁决谁对。

若案例自带 workorder（`init` 会列出 `W01..W0n`），题卡 `item_id` 优先沿用 workorder 编号；
workorder 项没做要写进 `set_meta.uncovered` 并说明原因，否则 `check` 报 `workorder_uncovered`。

## 5. 输出契约（result.json）

`/app/output/result.json` = **信封字段** + **output_contract 全字段回填**。

信封：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`stage`、`skill{name,version}`、
`sources[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、
`runtime{}`、`outputs{}`、`benchmark{}`、`anchors{}`、`scoring{}`、`coverage_matrix{}`、
`calibration{}`、`version_record{}`、`technical_synthetic{present,not_a_dsh_score}`。

契约回填规则（`references/contracts.md` 是字段字典）：

1. `output_contract` 里**每一个键都在顶层出现**，键名逐字不变；
2. 有对应真实结果就填真值（做语义映射：`scores/items/cards→benchmark`、`anchors/evidence→anchors`、
   `panel/summary/aggregate→scoring`、`failures/rejected→failures`、`version/comparison→version_record`、
   `status→status`、`sources/materials→sources`、`uncertainty/uncertainties→uncertainty`）；
3. 映射不上就写 `null` / `[]` / 同形空结构，**不留空键、不漏键**；
4. 另给 `contract_fields_present`（原序键名）与 `contract_fill`（`{字段: {filled: bool, from: 来源}}`）便于审计。

## 6. 评分口径（0/1/2，任何人可复算）

规则评分（`mode=key_terms`）：

- `coverage = |key_terms 命中数| / |key_terms|`，匹配方式＝大小写折叠 + 空白归一后子串包含；
- **2**：`coverage ≥ 0.75` 且该题至少 1 条 verified 锚点；
- **1**：`0.25 ≤ coverage < 0.75`（要点只对一半），或 `coverage ≥ 0.75` 但无 verified 锚点（答对无据）；
- **0**：`coverage < 0.25`、空答、或答非所问。

非正常态单独成状态，不混进 0/1/2：`missing_reference`（题卡无参考答案，不评）、
`no_anchor`（无逐字锚点，不可判）、`format_error`（输出不可解析/空文件/超长截断）。

**自校准探针（本包增量）**：build 对每道可评题自动生成三条探针答案——
`gold`（参考答案原文拼接，应得 2）、`partial`（只给首个关键项，应得 1）、`empty`（空串，应得 0）——
用同一套规则打分，比对 `期望 vs 实际`。`calibration.agreement` 即"自动得分与人工口径一致率"，
不一致的题进失败样例库并写 `uncertainty`。这让"自动得分是否与人判得上"有可核验证据，而不是自述。

**这不是被评测 Agent 的官方分数，也不是 DSH 分数**：本包不运行官方 Harness，产物是题集与台账。
`benchmark/run_config.json` 固定记录评分口径、匹配方式、预算与权限，任何人按同一配置重跑应得同一 CSV。

## 7. 可核验性：locator + 逐字证据 + 三指针闭包

两段闭包，`check` 与 `selfcheck` 分别机械核验：

**(a) 证据闭包**：`quote → locator → 材料原文`。
`verify` 做 exact → casefold → 去空白 三级匹配，命中位置反推真实段号，与题卡声明 locator 比对；
不一致报 `locator_mismatch`（用真实段号，不静默通过）。

**(b) 分数三指针闭包**：`scores.csv` 每行必须同时给
`raw_output_ref`（被评文本，指向 `benchmark/raw_outputs.json#/...` 或 `probes.json#/...`）、
`config_ref`（`benchmark/run_config.json#/run_config_hash`）、
`scoring_record_ref`（`benchmark/scoring_records.json#/records/<i>`）。
指针语法：`相对路径#/a/b/0`（JSON Pointer）、`#row=N`（CSV）、`#L3-L9`（文本行）。
`selfcheck` 逐行解析，输出**闭包率** `closure_rate`；解析失败的标记 `untraceable` 并进失败样例库。

## 8. 六轴覆盖矩阵（完整性不靠自述）

`build` 从产物本身算 6 个轴的状态（`ok|partial|missing`），写进 `result.coverage_matrix` 与面板：

| 轴 | 判定依据 |
|---|---|
| 任务定义 | `cards.items[].question` 非空且 `task_type` 合法 |
| 数据与答案管理 | 每题有 `source_refs`；有 `reference_answer` 或 `reference_missing=true`；`set_meta.version/license` 有值 |
| 评分维度 | 每题 `scoring_rule.scale` 三档齐全且 `mode` 可机械执行 |
| 原始输出留存 | `raw_outputs.json` + `probes.json` 非空，且被评分行引用 |
| 误差分析 | `failures.md` 有条目（被拒题/0 分/校准不一致/定位不符） |
| 版本迭代 | `version_diff.json` 有当前版本记录与可比性判定 |

四轴以上 `ok` 且无 `missing` → `status` 可为 `ok`；否则 `partial`（`degradations` 写缺哪轴）。

## 9. 版本记录与可比性

`version_diff.json` 记三类版本：`set_version`（题卡集合）、`scale_version`（评分档位口径）、
`run_config_hash`（运行配置）。`build` 每次把上一版 `cards.json` 的摘要（题数、题号集合哈希、版本号）
记入 `history`。可比性规则（机械判定，写入 `comparable` / `incomparable`，各带 reason）：

- 三条全同 → `comparable`（分数可直接对比）；
- `set_version` 同、`scale_version` 变 → `incomparable`（口径变了，需按新口径重算历史题）；
- 题号集合哈希不同 → `incomparable`（题集变了，只对交集题可比，`partial_overlap` 列出交集）。

没有任何历史时写 `history: []` 并注明"本次为基线 v1，无历史分数可混算"，**不编造历史分数**。

## 10. 失败样例库与"改得动"

`failures.md` 每条：`failure_id`、`item_id`、`type`（`missing_reference|no_anchor|locator_mismatch|
format_error|low_coverage|calibration_disagreement|unattributed_raw_output`）、原因、`raw_output_ref`、
`next_action`。同一 `type` 再给一条**下一版专项题建议**（如 `S01 ← locator_mismatch ×3`），
这就是从"一次失败"到"下一版题集专项题"的可执行路径。

## 11. 异常与降级（一律 exit 0）

| 情况 | 行为 | 结果字段 |
|---|---|---|
| 无 `case.json` / 坏 JSON | 继续索引材料、照常出题 | `errors[]`、`status=partial` |
| 无 `output_contract` | 只写信封字段，`contract_fields_present=[]` | `degradations[]` |
| 无材料 / 材料无文本 | 产物仍生成（空题集），入参错误 | `status=input_error`（`insufficient_evidence` 用于有材料无段落） |
| draft 缺失 / 坏 JSON | **确定性兜底**：从真实段落生成最小题卡（摘录/数值，≤6 题），产物不空 | `mode=fallback_minimal`、`status=partial` |
| draft 部分题不可核验 | 其余正常出包，被拒题入 `rejected` 与失败库 | `mode=agent_authored_with_fallback` |
| 题卡缺参考答案 | 标 `missing_reference`，不评分、不补造 | `scores.csv.status=missing_reference` |
| 候选输出无法归属到题 | 只登记原文，不评分 | `failures[].type=unattributed_raw_output` |
| 材料解析降级（低文本质量/图片） | 记降级，提示 quote 需平台解析器复核 | `degradations[]`、`uncertainty[]` |
| 含 checker/合成日志 | 只登记，`kind=technical_synthetic`、`not_dsh_score=true` | `technical_synthetic{}` |
| 未捕获异常 | 打印栈、写 partial `result.json`、退 0 | `errors[].traceback` |

## 12. 边界与限制（写给你也写给复核人）

- 证据核验是**字符级**：同义改写、翻译、跨段拼接都算"未命中"，此时应改引文或降级到 `pending_human`，**不要改原文凑通过**。
- 只做文本层：扫描件、图表像素里的数字不由本包负责（`degradations` 会点名哪个材料）。
- 规则评分只认 `key_terms` 的字面命中，对"表述正确但用词不同"偏严；这类题应 `mode=manual_only`，
  `scores.csv` 给 `manual_review` 状态，交人工。
- 不产出官方 Harness 分数，不做跨 Agent 的统计显著性判断；对照实验由平台固定。

## 13. 交付前自查清单

- [ ] `python3 scripts/main.py --help` 退出 0
- [ ] `init` 后 `/app/output/result.json` 已存在且是合法 JSON，契约字段全部在顶层
- [ ] `check` 的 `RESULT: PASS`（或明确接受剩余 error 并写进 `uncertainty`）
- [ ] `cards.json.items` 非空；workorder 项全覆盖或有 `uncovered` 原因
- [ ] 每条 `anchors.json[].verified` 为 true，或该题在 `rejected`
- [ ] `scores.csv` 每行三指针齐全，`selfcheck` 的 `closure_rate=1.0`
- [ ] `calibration.agreement=1.0`，否则失败库里能看到不一致的题
- [ ] `panel.md` 的数字与 `scores.csv` 复算一致（`selfcheck` 会对账）
- [ ] 无 `__pycache__`、`.pyc`、临时文件；包内无预制答案

## 14. 最小调用示例（示例，非正式案例结果）

```bash
$ python3 scripts/main.py init
case: /input/case.json | case_id=demo-0001 | contract fields (5): case_id, status, result, claims, uncertainties
materials: 2 (paragraphs=37) | workorder items: 4 (W01..W04) | candidates: 0
partial result.json written: /app/output/result.json

$ python3 scripts/main.py show --material M01 --start 1 --limit 3
[M01#p1] (412 chars)
... specific growth rate fell from 1.42 d-1 at 25 psu to 0.87 d-1 at 45 psu, a 39 percent decline ...
[M01#p2] (287 chars)
...

# ← 此处由 Agent 读材料并写 /app/work/draft.json（题卡/答案/锚点）

$ python3 scripts/main.py check
items=4 accepted=4 rejected=0 errors=0 warnings=1
RESULT: PASS

$ python3 scripts/main.py build
mode=agent_authored items=4 anchors=7 verified=7 scores=12 closure=? status=ok
wrote cards.json anchors.json raw_outputs.json scoring_records.json scores.csv run_config.json panel.md failures.md version_diff.json

$ python3 scripts/main.py selfcheck
closure_rate=1.00 (12/12) | calibration_agreement=1.00 | panel_vs_csv=OK | SELFCHECK: PASS
```

示意题卡（**示例，不是任何真实案例的答案**）：

```json
{"item_id": "W01", "task_type": "numeric",
 "question": "盐度从 25 升到 45 psu 时，比生长速率从多少降到多少？降幅多少？",
 "source_refs": [{"material": "M01", "locator": "M01#p1",
                  "quote": "fell from 1.42 d-1 at 25 psu to 0.87 d-1 at 45 psu, a 39 percent decline"}],
 "reference_answer": [{"text": "1.42 d-1 → 0.87 d-1，降幅 39 percent", "locator": "M01#p1"}],
 "scoring_rule": {"mode": "key_terms",
                  "scale": {"2": "两个速率与降幅都对", "1": "只对速率或只对降幅", "0": "未命中任何关键项"},
                  "key_terms": ["1.42", "0.87", "39 percent"], "must_have": 1},
 "difficulty": "easy", "license": "unknown"}
```

## 15. 文件清单、版本与复用

```
SKILL.md                          本文件：主路径、契约、规则、异常、自查（唯一流程入口）
scripts/main.py                   CLI：init / show / check / build / selfcheck（编排层，19KB）
scripts/litio.py                  库：材料扫描、locator、引文核验、契约回填、case/workorder 发现
scripts/core.py                   库：题卡归一与校验、0/1/2 评分、探针、三指针闭包、六轴矩阵
scripts/ledger.py                 库：八件台账产物、面板/失败库/版本渲染、selfcheck 复检
references/item-card-schema.md    工作稿 schema + check 判定表 + 0/1/2 口径 + 探针 + 失败归因
references/contracts.md           result.json 字段字典、契约回填规则、三指针语法、运行契约
SMOKE.md                          本包构建时的冒烟记录（打包时删除）
```

换新案例：替换 `/input` → `init` → `show` → 写 `draft.json` → `check` → `build` → `selfcheck`。
命令与产物结构不变，旧产物被覆盖（要留档先 `cp -r /app/output /app/output.v1`，
再 `build` 时 `version_diff.json` 会把新版本记进 `history`）。

别人怎么复用：整个目录拷走即可跑（无安装步骤）。`cards.json` 当题集快照，
`anchors.json` 当引文抽查表，`scores.csv` 当评分台账，`panel.md` 直接进汇报，
`version_diff.json` 回答"哪些历史分数还能比"。

版本：1.0.0（五命令主路径 + 兜底必成 + 契约全回填 + 三指针闭包 + 探针自校准 + 六轴覆盖矩阵）。
