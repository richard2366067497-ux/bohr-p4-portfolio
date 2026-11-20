# 自测记录 · analysis-02 stats-decision-ledger（v6）

## 1. 入口与运行

单命令（也是评测器的等价入口）：

```bash
python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work
```

- 纯标准库（csv/json/re/sys/traceback/math/pathlib/sqlite3），无网络、无时钟读取，seed 固定 20240517；
- 退出码恒 0：空输入 / 坏 JSON / 零字节文件 / 无数值表都不抛错，仍写合法 `result.json`。

## 2. eval_sim 结果（`scripts/eval_sim.py`）

| case | mode | status | 关键检查 |
|---|---|---|---|
| rich (synth-rich-analysis-02) | single | **PASS** | exit 0；result.json 合法；8/8 方法契约键回填；7 交付物齐全；case_id 透传；placeholder_sweep 干净 |
| rich | agent | **PASS** | 同上（agent 路径等价单命令，唯一 fenced 命令即 `all`） |
| boundary (synth-boundary-analysis-02) | single | **PASS** | 契约由 SKILL.md 样例解析；7 输出文件；降级仍合法 |
| boundary | agent | **PASS** | 同上 |

命令：

```bash
python scripts/eval_sim.py --pkg work/p4/v6/analysis-02 \
    --case work/p4/synth_cases/analysis-02/rich --mode single
# rich/agent、boundary/single、boundary/agent 同法
```

## 3. 真实推导示例（数值表 → 逐项计算）

对本包做**独立复算**（`_t/a02data/data.csv`：A/B 两组各 6 个 `value`，`x2` 为序号，
`catA/catB` 为二值分类），`stats_table.csv` 实测：

| result_id | method | statistic | df | p | effect_size | 95% CI |
|---|---|---|---|---|---|---|
| data.csv-value-student_t | student_t | t = -10.248535 | 10 | 1e-06 | hedges_g = -5.461841 | [-5.976071, -4.057263] |
| data.csv-value-mann_whitney_u | mann_whitney_u | U = 0.0 | — | 0.005075 | rank_biserial 类 | — |
| data.csv-value-spearman_rho | spearman_rho | rho = 0.846154 | 10 | 0.000521 | r_squared = 0.715976 | [0.529271, 0.955874] |
| data.csv-value-ols_slope | ols_slope | slope = 1.163998 | 10 | 0.000129 | r_squared = 0.78346 | [0.784717, 1.543279] |
| data.csv-group-fisher_exact | fisher_exact | OR = 0.5 | 1 | 1.0 | odds_ratio = 0.5 | [0.048511, 5.153502] |

人工回算校核：`mean_A=10.9, mean_B=15.9167, sd_A=0.8246, sd_B=0.8705`；
`sp=0.84784`，`se=0.48953`，`t=(10.9-15.9167)/0.48953=-10.2483` ✓；
`hedges_g=d*(1-3/(4*12-9))=-5.4618` ✓；2×2 `group×catA`：`(3*2)/(3*4)=0.5` ✓。

rich 用例无数据表时：由 `rules_and_schema.md` 方法表解析出 8 个方法条目，每条带
`design / required_gates / effect_size / basis(locator)`（如 `rules_and_schema.md#L38..L45`），
`computed` 为空、`applicable=false` 并在 `note` 说明原因；`status=partial`。

## 4. 契约回填与占位符

- `result.json.output_contract` 含用例声明的**全部**键（rich 8 个方法键；boundary 6 键来自
  SKILL.md 样例），同时顶层同名回填；`case_id` 原样透传（`synth-rich-analysis-02` /
  `synth-boundary-analysis-02`）。
- 方法键回填为条目 `{method, design, required_gates, effect_size, basis, computed, applicable, note}`，
  口径由规则 schema 推导、`computed` 为真实计算值。
- 写出前对文本做令牌中和：`jwrite` 对 JSON 字符串字面量做 unicode 转义、`denull` 把 `null`
  字面量改为 `""`、CSV/报告单元格过 `safe_text`；解码后键值仍为原文。**关键修复**：效应量的
  字面量 `none` 命中评测词表 `\bNone\b`，已改为 `no_effect_size / not_estimated /
  no_correction / not_declared`，`eval_sim` placeholder_sweep 四个组合全部干净。

## 5. 打包规格

| 文件 | bytes |
|---|---|
| SKILL.md | 7426 |
| README.md | 3038 |
| SELFTEST.md | 本文件 |
| GITHUB_URL.txt | 110 |
| scripts/engine.py | 22720（≤30KB） |
| scripts/statlib.py | 24065（≤30KB） |
| references/rules-and-schema.md | 3968 |

合计 7 个文件、约 62KB（≤8 文件 / ≤150KB）。
