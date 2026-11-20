# 方法说明 — 清洗、统计与图件口径

本文件是 `sci-analysis-dag` 的口径备忘；引擎实现与之一一对应。

## 1. 导入

- 递归扫描 `/input`，跳过 `.git` / `__pycache__` / `node_modules` 与根级元数据
  （`case.json`、`challenge.json`、`task.md`、`config.json`、`resources.yaml`）。
- 识别：`.csv/.tsv`（表）、`.json`（若含对象数组则当表）、SQLite（按魔数 `SQLite format 3` 或
  `.db/.sqlite/.sqlite3` 后缀识别，只读打开，`mode=ro`）、其余文本/二进制仅入盘点。
- 编码一律按 `utf-8-sig` 读取，天然吃掉 BOM。

## 2. 清洗（行数守恒）

对每张表依次执行，并把每一步写进 `checkpoint_ledger.jsonl`：

1. **去重**：完全相同的整行只保留第一条，记 `removed=n_dupes`。
2. **必填丢弃**：若 `decisions.missing.required` 指定了列，该列为空的行整行丢弃，记 `removed=n_dropped`。
3. **填补**：数值列用中位数，分类/文本列用众数；记 `impute`（列、方法、值、条数）。
4. **离群标记**：数值列按 IQR 1.5 规则标记（不删除），记 `flag_outliers`。

守恒等式：`rows_out + n_dupes + n_dropped == rows_in`。该等式在 ledger 的 `row_conservation`
检查里逐表核验。

## 3. 统计

- **列画像**：当某列的数值可解析比例 ≥ 60% 且数量 ≥ 3 时判为 `num`，否则当 `cat`（distinct ≤ 30）
  或 `text`。单位从列名末尾括号里抽取，如 `温度（℃）` → `℃`。
- **描述统计**：n、缺失、distinct、mean、sd（分母 n−1）、min、max、median、q1、q3、IQR 离群界。
- **Welch t**：两组均值比较，自由度按 Welch–Satterthwaite；附 Cohen's d（合并 SD）。
- **单因素 ANOVA**：k 组，F=MSB/MSW，df=(k−1, n−k)，效应量 η²=SSB/(SSB+SSW)。
- **Pearson r**：n ≥ 3 且方差非零；显著性由 t=r√((n−2)/(1−r²)) 换算。
- **简单 OLS**：n ≥ 4；返回 slope/intercept/se_slope/t/p/R²。
- **p 值**：由正则化不完全 Beta 函数（连分式 `betacf` + `betai`）计算 t 上尾与 F 上尾，
  与 `scipy.stats` 同量级但零依赖。

> 不做 Shapiro-Wilk；正态性用偏度与样本量做近似说明。多样本比较时用 Holm 校正叙述。

## 4. 图件（真实 SVG）

- 图型由数据形状决定，并在 `figure_records[].why` 中写明选择理由：
  - 有可用分组（2–8 类、且至少一组 n ≥ 3）→ 组均值柱图 + SD 误差线（`figure_01`）。
  - 否则有数值列 → 直方图（`figure_01`）。
  - 完全无表 → 输入盘点柱图（`figure_01`）。
- 有两个数值列时追加散点 + OLS 拟合线（`figure_02`）。
- 每个 SVG 标签都带属性（`xmlns`、`width`、`fill` 等），文本经 XML 转义并套用占位符清理。

## 5. 溯源

`verification.json` 把报告里的每个数字登记为 `(key, value, step)`；报告第五节列出 registry 键。
`coverage` 汇总文件数、表数、数值列数、图件数与检验数。
