# 规则与方法 schema（可编辑）· analysis-02 stats-decision-ledger

本文件是包内**可编辑**的规则来源；`scripts/statlib.py:parse_rules_md` 会从 `materials/` 下的
Markdown 表解析方法注册表、门禁顺序、禁止词与降级矩阵，`scripts/engine.py` 据此选择检验并
在真实数值上计算。评测输入自带的规则材料优先级相同（同名键合并）。

## 1. 方法表（methods | design | 必要门禁 | 效应量）

引擎按下方表头识别：含 `method` / `设计` / `门禁` / `效应量` 列即为方法表。单元格可用
`` `a` / `b` `` 写多个方法别名（斜杠分隔，反引号可选）。

| method | design | 必要门禁 | 效应量 |
|---|---|---|---|
| student_t / welch_t | two_independent_groups | 样本量, 正态性, 方差齐性 | hedges_g / cohen_d |
| mann_whitney_u | two_independent_groups | 样本量, 独立性 | rank_biserial |
| kruskal_wallis | multi_group | 样本量, 独立性, 多重比较家族 | epsilon_squared |
| wilcoxon_signed_rank | paired | 样本量, 差值分布 | rank_biserial |
| spearman_rho | correlation | 样本量, 单调性 | r_squared |
| ols_slope | regression | 样本量, 线性, 残差 | r_squared |
| fisher_exact | contingency | 2x2 计数, 边际固定 | odds_ratio |
| descriptive | descriptive | 样本量 | no_effect_size |

## 2. 门禁顺序（evaluation sequence）

1. 样本量（每组 n）→ 2. 正态性 → 3. 方差齐性 → 4. 独立性 → 5. 多重比较家族。
本离线实现以 `not-run` 显式标注未运行的门禁（不编造 p 值），样本量按真实分组计数给出。

## 3. 效应量公式（与主包一致）

- `hedges_g = d * (1 - 3 / (4*(n1+n2) - 9))`，其中 `d = (m1 - m2) / sp`。
- `rank_biserial`：秩方法的两组效应量。
- `epsilon_squared`：Kruskal-Wallis 的效应量。
- `r_squared`：相关/回归的确定系数。
- `odds_ratio`：2x2 列联表的优势比。
- 95% 区间：解析近似（`analytic_large_sample`）或 Fisher-z；`percentile_bootstrap` 在本离线
  实现中标注 `not-run`。

## 4. 解读规则（禁止词）

报告与结果**不得**出现：`证明 / 证实 / proves / proven / proved / confirmed causal /
no difference exists`。只报效应量与区间，不做因果或"无差异"断言。引擎在写出前用词表扫描，
命中不计入结果（`result.json.lint.banned_hits`）。

## 5. 产出 schema

- `results_ledger.json`：`{schema, case_id, seed, families, rows[]}`，每行
  `{result_id, decision_id, estimate_type, statistic_name, statistic, df, p, n, effect_size, ci_95, status}`。
- `decision_log.json`：`{decision_id, question_id, design, chosen_method, variables, table,
  gate_results, multiple_comparison_family, correction, status, notes}`。
- `effect_ci.json`：`{result_id, effect, ci_95}` 列表。

## 6. locator 约定

- 文本行：`<file>#L<n>`；方法表：`<file>#L<起>..L<止>`；列：`<file>#col:<name>`；
  case 键：`case.json#<key>`；规则键：`<file>#<table>`。

## 7. 降级矩阵（kind | 触发 | 影响）

| kind | 触发 | 影响 |
|---|---|---|
| draft_missing | 找不到 case.json / draft.json | 用默认契约，status 不降 |
| no_analyzable_data | 无 ≥2 有效值的数值列 | status=partial，方法条目仅口径 |
| bootstrap_not_run | 无本地随机重采样 | 区间改解析法，显式标注 |
| banned_phrase | 报告命中禁止词 | 移除该表述，仅留效应量与区间 |

## 8. draft.json schema（agent-first，可写 `/app/work/draft.json`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| registry | array | 否 | Agent 覆盖/补充的方法表行（同 §1 字段） |
| design_overrides | object | 否 | 列名 → 设计（two_independent_groups / paired / …） |
| decisions | array | 否 | 直接给出的决策条目（同 §5） |

`result.json.method_registry[].source` 标注 `draft` 或 `synthesized`，便于评审区分。
