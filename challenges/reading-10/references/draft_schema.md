# `/app/work/draft.json` 工作稿规范（Agent 的判断落点）

`init` 会在同一目录生成 `draft_skeleton.json`（骨架，**不是答案**）。
`check` 用它做结构门禁，`build` 是唯一消费者。字段缺失不会崩，但会降级并记缺口。

为什么要写工作稿：脚本能跑代码、算偏差、查引文，但不能替你决定
"这段材料算不算论文原始代码""alpha 该取正文还是代码默认值""76.5 与 0.765 哪个才是同一口径""偏差该归到数据切分还是实现细节"。
这些判断只在工作稿里，不写就是空的。

## 1. 顶层

```json
{
  "case_id": "demo-001",
  "paper":  {"title": "...", "doi": null, "repo": "https://...", "commit": "a1b2c3d",
             "data_version": "data/v2.csv (sha1 9f2c...)"},
  "scope":  {"synthetic_trial": true, "not_original_repo": true},
  "plan":   [{"step": 1, "goal": "locate materials", "command": "main.py init",
              "expected": "7 materials", "status": "done"}],
  "environment": {"python": "3.12.4", "platform": "Linux-...", "packages": {"numpy": "1.26.4"},
                  "seed": 7, "hardware_note": "8 vCPU, no GPU", "env": {"OMP_NUM_THREADS": "1"}},
  "params": [], "paper_values": [], "tolerance": [], "claims": [], "attributions": [],
  "checklist": [], "candidates": [],
  "verdict": {"tier": "partially_reproduced", "rationale": "..."}
}
```

`scope.synthetic_trial=true` 表示本次是组织方合成试验而非原作者代码；它会触发结论封顶
（见 `method_rules.md` §5），所以**如实填写**，不要为了拿高分写 `false`。

## 2. `params[]` —— 参数复原（三类来源）

```json
{"name": "alpha", "value": 0.1, "class": "paper", "source": "§3 Method",
 "conflict_note": "code default is 1.0; paper says 0.1, paper wins",
 "evidence": {"source_id": "paper", "locator": "paper@s2.u2", "quote": "ridge penalty alpha of 0.1"}}
```

| `class` | 判定标准 | 额外要求 |
|---|---|---|
| `paper` | 正文/表/附录**逐字**写出 | 必须有 `quote`，且 `check` 能在索引里逐字命中 |
| `code_inferred` | 只能从代码默认值/配置/常量推断 | `source` 写文件名 + 行号或代码片段；进 `uncertainty` |
| `self_set` | 两处都没有，由 Agent 设定 | 写清理由与敏感度；进归因 `parameter_restoration` |

冲突处理（正文 vs 代码默认值不一致）：

- 以论文为准，`value` 取论文值，`class=paper`；
- 代码值写进 `conflict_note`，两个值都进 `uncertainty`；
- **不要**静默采用仓库默认值 —— 这正是"跑得对"的失分点。

## 3. `paper_values[]` —— 比较基准

```json
{"metric": "mae", "value": 0.184, "unit": "absolute error, held-out split",
 "evidence": {"source_id": "paper", "locator": "paper@s3.u2", "quote": "Table 2 reports MAE 0.184"}}
```

- `metric` 尽量与候选程序**实际输出的键名**一致；不一致时脚本按别名表匹配
  （`mae`/`mean absolute error`、`r2`/`r2_score`/`r squared`、`acc`/`accuracy`/`top-1 accuracy` …），
  仍匹配不上就多出一行 `no_reported_value`。
- 口径统一：`76.5%` 与 `0.765` 不要混写。脚本会在观测值上做 1:100 的自动换算并记
  `scale_adjusted`，但**报告值必须按原文写**；口径冲突写进 `uncertainty`，不要改数字。
- 论文只给一位小数就照写一位，不要补零凑精度。

## 4. `tolerance[]` —— 只能更严

```json
{"metric": "mae", "abs_tol": 0.00092, "rel_tol": 0.02, "basis": "论文三位小数，取半个末位"}
```

`init` 已写 `tolerance_plan.json`（含 `__default__` 通配先验）；`build` 在任何子进程启动前
把每个指标摊平成显式条目并重算 `plan_sha256`。工作稿里只能取**相等或更严**的值，
更宽即 `tolerance_widened_after_run`（`check` 报 ERROR，`build` 记 degradation）。

## 5. `claims[]` —— 带证据的结论

```json
{"id": "c1", "kind": "paper_result", "text": "Table 2 reports MAE 0.184 on the held-out split",
 "confidence": "direct",
 "evidence": [{"source_id": "paper", "locator": "paper@s3.u2", "quote": "Table 2 reports MAE 0.184"}]}
```

`kind` ∈ `paper_result` / `method` / `param` / `environment` / `attribution`。
`confidence` ∈ `direct`（原文直读）/ `inferred`（由材料推断）/ `undetermined`（判断不了）。
`quote` 会被规范化（NFKC、去零宽、空白折叠、大小写）后在索引正文里**逐字查找**：

- 命中 → `verified`，若 `locator` 段号不同则回绑真实 locator（`locator_rebound`）；
- 不命中 → `evidence_rejected`，该条不进 `evidence[]`。

宁可不写，也不要改写原文凑命中。

## 6. `attributions[]` —— 你的归因补充

```json
{"metric": "mae", "cause": "implementation_divergence", "confidence": "inferred",
 "evidence": "method_b.py 第 4 行把预测四舍五入到一位小数；见 runs/method_b.log",
 "disposition": "同时报告两份方法，把差异归到预测舍入，不放宽容差"}
```

脚本会先给确定性判定，你补的条目**并列保留**，`(metric, cause)` 与脚本相同的会去重。
冲突（你说 `none`、数据说超差）不会被静默丢弃，会进 `uncertainty`。

## 7. `checklist[]` —— 脚本没认出来的材料

```json
{"id": "original_repo", "kind": "code", "status": "needs_request",
 "note": "论文的原始仓库未随材料提供，只有两份合成候选方法"}
```

`kind` ∈ `code/data/param/dependency/license/eval_script`，`status` ∈
`available/missing/needs_request`。`needs_request` 指"论文声明存在但需要申请/未随包提供"，
它与 `missing` 都会进 `gaps`，也都参与结论封顶。

## 8. `candidates[]` —— 显式指定跑哪两份

```json
[{"name": "method_a", "path": "method_a.py"}, {"name": "method_b", "command": "python3 -u impl/b.py"}]
```

不写时脚本按文件名/目录名启发式挑（`cand/method/impl/variant/baseline` 优先），最多 3 个。
`path` 相对输入根目录；`command` 原样执行（`shlex` 切分，cwd 在只读副本里）。

## 9. 常见 `check` 报错与修法

| 报错 | 原因 | 修法 |
|---|---|---|
| `draft_missing` | 没写工作稿 | 复制 `draft_skeleton.json` 为 `draft.json` 后填 |
| `draft_section_empty:params/claims/verdict` | 关键段为空 | 至少一条参数、一条 claim、一个合法 tier |
| `claim_without_evidence` | claim 没证据 | 补 `evidence[]` 或改 `confidence=undetermined` 并说明 |
| `evidence_rejected:*:quote_not_found` | 引文与原文不符 | 用 `show --grep` 取原文原句再抄 |
| `evidence_rejected:*:missing_quote` | 只写了 locator | 必须给逐字 `quote` |
| `paper_param_without_verified_quote` | `class=paper` 但引文没命中 | 补可命中的引文，或降级为 `code_inferred`/`self_set` |
| `paper_value_quote_rejected` | 报告值没有可信来源 | 补引文；补不上就把该指标留给自动抽取并在 `uncertainty` 说明 |
| `param_class_invalid` | 类名拼错 | 只用 `paper`/`code_inferred`/`self_set` |
| `tolerance_widened_after_run` | 事后放宽 | 只能收紧；需要更宽请在 `uncertainty` 说明理由但不要改表 |
| `locator_rebound`（WARN） | 段号与索引不同但引文命中 | 可接受，建议改用提示里的 locator |
| `contract_mapped 3/7`（WARN） | 契约字段语义未识别 | 在 `output_contract.md` §3 找对应载荷，或接受 `null` + degradation |

## 10. 最小可交付工作稿（时间紧时照抄）

```json
{"case_id": "<抄 case.json>",
 "paper": {"title": null, "doi": null, "repo": null, "commit": null},
 "plan": [{"step": 1, "goal": "run both methods", "status": "done"}],
 "environment": {"python": "<实测>", "platform": "<实测>", "packages": {}, "seed": null},
 "params": [{"name": "lr", "value": 0.1, "class": "paper", "source": "§3",
             "evidence": {"source_id": "<paper id>", "locator": "<loc>", "quote": "<逐字>"}}],
 "paper_values": [{"metric": "mae", "value": 0.184, "unit": null,
                   "evidence": {"source_id": "<paper id>", "locator": "<loc>", "quote": "<逐字>"}}],
 "claims": [{"id": "c1", "kind": "paper_result", "text": "MAE 0.184 reported",
             "confidence": "direct",
             "evidence": [{"source_id": "<paper id>", "locator": "<loc>", "quote": "<逐字>"}]}],
 "verdict": {"tier": "partially_reproduced", "rationale": "原仓库与评估脚本缺失，只有合成候选"}}
```

只要这 7 个键有内容，`build` 就能产出完整记录；其余字段是加分项（归因细节、冲突登记、清单补充）。
