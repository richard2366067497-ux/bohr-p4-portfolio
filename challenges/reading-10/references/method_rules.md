# 验算规则：容差锁定、指标对齐、归因判定、结论分级、复核

本文件是判定规则的唯一权威说明。`SKILL.md` §9~§11 是摘要；脚本实现见
`scripts/engine.py`（`tolerance_plan` / `compare` / `attribute` / `verdict_for`）与
`scripts/build.py`（`lock_band`）。

## 1. 为什么先锁容差

"对得上"的判定必须与运行结果无关，否则任何偏差都能靠事后放宽容差抹平。
本 Skill 的做法是把容差写成**带哈希的时间点文件**，让"事前"这件事可被第三方验证。

## 2. 容差锁定协议（三段时间戳 + 一个哈希）

| 时刻 | 动作 | 留痕 |
|---|---|---|
| T1 `init` | 为 case 已声明的每个指标写条目；其余落 `__default__` 通配先验 | `tolerance_plan.json`: `declared_at=T1`, `declared_step="init"`, `before_any_run=true`, `plan_sha256=sha256(entries)` |
| T2 `build` 开头 | 把本次要比较的每个指标摊平成显式条目（继承通配先验或 case 声明） | 条目加 `declared_step="build:pre_run"`；`materialized_at=T2`；重算并覆盖 `plan_sha256`；**此时尚未启动任何子进程** |
| T3 每个 run | 记录当时读到的 `tolerance_plan_sha256` 与 `plan_written_at` | `runs[].tolerance_plan_sha256`、`runs[].started_at` |
| T4 `selfcheck` | 复算 `sha256(entries)` 并逐 run 比对 | 不一致即 FAIL |

判定"事前"成立需要三条同时为真：① 计划哈希自洽；② 每个 run 记录的哈希等于计划哈希；
③ `plan_written_at ≤ run.started_at`。任一条不成立，就说明容差可能被改过，`selfcheck` 报 FAIL。

## 3. 容差取值

| 情形 | 取值 | 依据 |
|---|---|---|
| case 明确给出 `abs_tol`/`rel_tol`（或 `abs`/`rel`、`atol`/`rtol`、百分数） | 照抄，`basis="case_declared"` | 组织方口径优先 |
| 只给了全局容差、没绑定指标 | 写进 `__default__`，`basis="case_declared_default"` | 全指标同一口径 |
| 没给 | `rel_tol=0.02` + `abs_frac=0.005`（比较时解析为 `0.005×|reported|`） | 常规训练的 run-to-run 波动量级约 1~2%；0.5% 吸收论文只报 2~3 位小数的舍入 |

比较公式（同 `scripts/core.py:compare_values`）：

```
abs_dev = |observed − reported|
rel_dev = abs_dev / |reported|            (reported ≠ 0)
in_band = (abs_dev ≤ abs_tol) or (rel_dev ≤ rel_tol)
```

**OR 语义**：任一条满足即在带内。容差为空（该指标没有报告值）→ `within_tolerance=null`，
判定 `no_reported_value`，**绝不能写成"一致"**。

自定义容差只能**更严**：工作稿里 `abs_tol/rel_tol` 大于计划值即 `tolerance_widened_after_run`。

## 4. 指标对齐（同一指标不同写法 / 不同口径）

1. **名称对齐**：`nk()` 去掉非字母数字后比较；同名直接匹配；否则按别名组
   （acc / f1 / auc / precision / recall / mae / mse / rmse / mape / r2 / corr / logloss / loss / time）
   匹配；再否则做长度受限的子串匹配。命中强度写进匹配分（3 精确 / 2 同组 / 1 子串）。
2. **口径对齐**：`observed/reported` 落在 [60,140] 或 [1/140,1/60] 时判为百分数 ↔ 小数不一致，
   把观测值乘 0.01 或 100，行内记 `scale_adjusted={factor, applied_to, note}`。
   报告值**永不改写**，换算只发生在观测值上，并且必须在报告里可见。
3. **单位/切分对齐**：论文报的是 test split、候选算的是全量 → 属于 `data` 归因，
   在 `uncertainty` 明写，不要静默当一致。

## 5. 双方法互证与差异归因

两份候选方法互为对照。设同一指标下各方法的观测值集合为 `O`，容差带为 `band`：

| `cause` | 判定条件 | 含义 | 下一步 |
|---|---|---|---|
| `none` | 全部在带内 | 无差异 | 记录最大相对偏差即可 |
| `scale_mismatch` | 存在 `scale_adjusted` 且仍在带外 | 百分数/小数口径不一致 | 在报告里明写口径换算 |
| `shared_upstream` | `max(O)−min(O) ≤ |reported|×rel_tol`，但都超差 | 共同上游：数据版本/切分、预处理、被复原的参数、环境 | 优先查数据与参数，不要先怀疑代码 |
| `implementation_divergence` | 方法间极差 > 带，且至少一方超差 | 实现细节：度量实现、默认超参、随机性 | 逐行 diff 两份代码，指出具体行 |
| `single_method_only` | 只有一份产出数值 | 无法区分实现与上游 | 写进 `pending_human`，不硬下结论 |
| `paper_value_unavailable` | 材料无该指标报告值 | 无法判定一致性 | 列进缺口，不猜论文数字 |
| `run_failed` | 某份非零退出/超时 | 该 run 不能支撑任何"一致"结论 | 保留 stderr，单独降级 |
| `parameter_restoration` | 存在 `code_inferred`/`self_set` 参数 | 参数复原不确定性 | 列出参数名，说明取值依据 |
| `material_missing` | 六类对象有 `missing`/`needs_request` | 材料不齐 | 进 `gaps`，参与结论封顶 |

判定由脚本给出（可复算）；解释由 Agent 给（可读）。两者并列保留，不互相覆盖。

## 6. 结论分级与封顶

| `tier` | 条件 |
|---|---|
| `reproduced` | 所有可比观测在带内，且六类对象全部 `available`，且非合成试验 |
| `partially_reproduced` | 部分在带内；或数值全在带内但存在材料缺口/合成试验（被封顶） |
| `not_reproduced` | 所有可比观测都在带外 |
| `insufficient_evidence` | 没有任何方法产出可比数值，或没有任何报告值 |

封顶规则：脚本算出的 `reproduced` 遇到
`coverage` 有 `missing`/`needs_request`，或 `scope.synthetic_trial=true`，
降为 `partially_reproduced` 并写 `caps`。

Agent 干预规则（**只许收紧**）：

- Agent 写的 tier 比脚本更严（档位更低）→ 采纳 Agent，`rationale` 追加 "tightened by agent"；
- Agent 写的 tier 比脚本更松 → 不采纳，保留脚本判定，记 `verdict_conflict`，
  写进 `degradations` 与 `uncertainty`。

档位顺序（松 → 严）：`insufficient_evidence` > `not_reproduced` > `partially_reproduced` > `reproduced`。

## 7. 他人复核路径（把这段写进报告就够）

```bash
# 1. 材料一致
python3 -c "import json;d=json.load(open('/app/output/result.json'));print([(m['rel'],m['sha1']) for m in d['sources']])"
# 2. 容差未被篡改
python3 -c "import json,hashlib;d=json.load(open('/app/output/result.json'));e=d['tolerance_plan']['entries'];print(hashlib.sha256(json.dumps(e,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())"   # == plan_sha256
# 3. 重跑同一命令
for f in /app/output/runs/*.log; do head -3 "$f"; done      # argv + cwd + plan hash + exit + duration
# 4. 复算指标
python3 /app/work/runs/<run>/sandbox/<method>.py             # 同一文件、同 cwd、同 SEED
# 5. 复算偏差
python3 -c "print(abs(0.187-0.184), abs(0.187-0.184)/0.184)" # 与 comparison.csv 的 abs_dev/rel_dev 对账
```

## 8. 降级矩阵（脚本已实现，此处为约定）

| 触发 | `status` | 留痕 |
|---|---|---|
| case.json 缺失/坏 | `input_error` | `errors` + `degradations`（契约字段全 null） |
| 材料目录为空 | `insufficient_evidence` | `degradations: no_material_found` |
| 无候选方法 | `insufficient_evidence` | `degradations: no_candidate_found`，`pending_human` |
| 某方法非零退出 | `partial` | `degradations: run_error:<run>:<msg>`，该 run 有 `error` 与 `log_path` |
| 方法无指标输出 | `partial` | `uncertainty` + `degradations: no_comparison_rows` |
| 无工作稿 | `partial` | `degradations: no_draft:deterministic_minimal_delivery` |
| 报告值靠自动抽取 | `partial` | `degradations: reported_values_auto_extracted:N` |
| 环境只用宿主快照 | `partial` | `degradations: environment_from_host_only` |
| 容差被放宽 | `partial` | `tolerance_widened_after_run` |
| 结论冲突 | `partial` | `verdict_conflict:<detail>` |
| 未捕获异常 | `partial` | `errors: [traceback]`，`degradations: unhandled_exception` |
| 时间不足 | `partial` | `run_skipped_deadline:<name>` |

## 9. 预算内的取舍

64 次模型请求 / 900 秒 / 单次 16384 token。脚本软截止 760 秒：
剩余 < 50 秒时不再启动新 run（记 `run_skipped_deadline`），已完成的 run 照常入表。
默认单 run 超时 120 秒，可用 `build --timeout` 收紧。
时间紧时的最小正确路径是：`init` → 写 7 个键的工作稿 → `build`（脚本会自动抽取报告值并跑两份方法）。
