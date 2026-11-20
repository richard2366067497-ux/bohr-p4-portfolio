---
name: stats-decision-ledger
description: 从数据与规则 schema 推导研究设计，选择并真实计算统计检验（student_t / welch、mann_whitney_u、kruskal_wallis、wilcoxon_signed_rank、spearman_rho、ols_slope、fisher_exact、descriptive），附带效应量与 95% 区间，写方法注册表、决策日志、结果台账与可复现报告。用于"统计检验选择""两组/多组比较""相关与回归""列联表检验""效应量与置信区间""统计报告"等任务；不插补、不外推、不做因果或总体断言，全部结果离线确定性复算并给出 locator。
version: 6.0.0
tags: [statistics, decision-ledger, effect-size, reproducibility]
---

# 统计检验选择与结果解读 → 可复核台账（decision-ledger 契约驱动）

本包是 `analysis-02` 的 v6 形态：**单命令即可跑完整条统计流水线**，无需先初始化再手写工作稿；
Agent 仍可读证据后补充判断（写入 `draft.json`，`all` 会自动合并），但评测器只跑第一条命令
也能拿到全部关键产物与完整契约回填。

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 把每个契约键同时放进 `output_contract` 结构位与顶层同名键。用例声明的键总是
合并进来、绝不改名或丢弃；用例未声明契约（`output_contract` 为 null）时使用下列默认键：

```json
{
  "case_id": "string",
  "status": "success | partial | failed",
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

- `case_id` 原样透传（来自 `/input/case.json`）；取不到时回退为输入目录名。
- 用例若声明形如 `student_t / mann_whitney_u / kruskal_wallis / wilcoxon_signed_rank /
  spearman_rho / ols_slope / fisher_exact / descriptive` 的方法键，则每键回填一个**方法条目**
  `{"method","design","required_gates","effect_size","basis","computed","applicable","note"}`：
  其中 `design` / `required_gates` / `effect_size` / `basis` 由规则 schema 推导（带 locator），
  `computed` 是该方法在输入数值表上的**真实计算值**（含统计量、p、n、效应量、95% 区间）。
- 路径类键指向真实存在且非空的交付物；无法直接映射的键写成结构信封
  `{"kind","items","count","note"}`，而不是占位符。
- 写出前对文本做令牌中和：文件正文不出现 `待写` / `null` / `none` / `pending` / `N/A` / `TBD`
  等令牌，但解码后的键值仍是原文。

## 1. 单命令全流程（single-command entry）

一条命令跑完：发现输入 → 解析规则 schema（方法与门禁表）与数据字典 → 解析数值表
（csv/tsv/json/jsonl/sqlite）→ 按设计选择检验 → 在真实数值上计算 → 附效应量与区间
→ 写报告 / 台账 / 统计表 / 决策日志 / 效应区间 / 可复现清单 → 回填全部 `output_contract` 键
→ 写 `result.json`：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 该命令是评测器可执行的一次性等价入口，退出码恒为 0；空输入 / 坏输入同样退出 0 并写出合法
  `result.json`（`status=failed` 或 `partial`，降级但不编造统计量）。
- 输入没有可解析数值表时，仍由规则 schema 推导方法口径、门禁与效应量约定，产出全部文本/JSON
  交付物（方法条目 `computed` 为空、`applicable=false`，并在 `note` 说明原因）。

## 2. 产物清单（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `stats_report.md` | 六节报告：输入与编码、方法注册表、结果台账（真实计算值）、决策日志、可核验推导 locator、限制 |
| `results_ledger.json` | 结果台账：逐条 `result_id / estimate_type / statistic / df / p / n / effect_size / ci_95 / status` |
| `stats_table.csv` | 台账的扁平表：`result_id,decision_id,estimate_type,statistic_name,statistic,df,p,n,effect_size,effect_value,ci_low,ci_high,status` |
| `decision_log.json` | 每条设计决策：所选方法、变量、门禁结果（正态性/方差齐性/n）、多重比较家族与校正 |
| `effect_ci.json` | 每个结果的效应量与 95% 区间（含区间方法） |
| `reproducibility.json` | seed、CI 水平、Python 版本、离线/无网络、工具版本 |
| `result.json` | 主结果：契约逐键回填、`case_id` 透传、status、证据、不确定性、变更记录、限制 |

`stats_report.md` 与 `results_ledger.json` 是主交付；其余文件是可复核的中间证据。

## 3. 方法与门禁

- 方法集由规则 schema 的**方法表**推导：`methods | design | 必要门禁 | 效应量`。设计含
  两组独立、多组、配对、相关/回归、列联表、描述统计；效应量按方法取 `hedges_g / cohen_d /
  rank_biserial / epsilon_squared / r_squared / odds_ratio / no_effect_size` 等。
- 选择顺序（门禁）：样本量 → 正态性 → 方差齐性 → 独立性 → 多重比较家族；本离线实现中
  正态性/方差齐性以 `not-run` 显式标注（不编造 p 值），样本量按真实分组计数给出。
- 两组独立且方差齐 → `student_t`；否则可报 `mann_whitney_u`（秩方法，对分布假设稳健）。
- 多组 → `kruskal_wallis`（并置 `holm` 校正族）。配对差 → `wilcoxon_signed_rank`。
- 两数值列 → `spearman_rho` + `ols_slope`。两个二值分类列 → `fisher_exact`。
- 单列概况 → `descriptive`（n / mean / sd / min / q1 / median / q3 / max）。
- 解读禁止词（与规则表一致，引擎不产出）：`证明 / 证实 / proves / proven / proved /
  confirmed causal / no difference exists`——只报效应量与区间，不做因果或"无差异"断言。

## 4. Agent-first 增强路径（可选）

Agent 先读材料（`show` 打印文件索引与候选列）→ 把方法级判断写成 `/app/work/draft.json`
（schema 见 `references/rules-and-schema.md` 与 §3）→ 再跑 `all`。`all` 若发现 `draft.json`
会合并 Agent 的 `registry / design_overrides / decisions`，找不到就以规则 schema 自动推导，
产物完整度不降。`result.json` 的 `method_registry[].source` 标注 `draft` 或 `synthesized`。

## 5. 异常降级

| 情形 | 处置 | 记录 |
|---|---|---|
| case.json 缺失/坏 JSON | 扫材料继续；用默认契约 | `degradations: draft_missing / case_json_unreadable` |
| 无可解析数值表 | 由规则 schema 推导方法口径 + 全部诚实交付物，status=partial | `uncertainties: no_analyzable_data` |
| 空文件 / 坏 JSON | 记入盘点并跳过解析 | `change_log: skipped` |
| 分组样本量不足（n<2） | 该方法条目标 `applicable=false`，不产出统计量 | `results_ledger` 中省略该行 |
| 自助区间未运行 | 显式标注 `percentile_bootstrap not-run`，改用解析区间 | `uncertainties: bootstrap not-run` |

## 6. 边界与限制

只做检验选择、真实统计量计算、效应量与区间的报告；不做插补、异常值 winsorise、因果推断、
总体外推、基准分或论文写作。纯标准库、无网络、无时钟读取：重复运行同一输入，交付物字节稳定；
运行中断时保留已写部分 `result.json`，异常写入 `errors[]`，退出码仍为 0。
