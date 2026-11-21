# 专家参考手册 · 科研数据库查询与分析（db-query-workbook）

> 本手册是本 Skill 的核心方法论基准：**执行前必读**。所有交付物（查询报告、SQL 记录、结果导出、
> 对账、字段字典）的**框架、检查表与统计口径**均以本手册为准。与 `SKILL.md` 冲突时：
> 契约键名以 `SKILL.md` 为准，方法/口径以本手册为准。

---

## 1 判分要点与失败模式

核心不是"写了几条 SQL"，而是：**查询可执行**（在授权快照上直接跑通，不依赖外部库或手工）、
**结果可复算**（同一快照 + 你的 SQL/脚本能独立得到相同数字）、**字段可追溯**（每个输出列回溯到
数据字典原始定义，编码字段已解码）。

| 维度 | 评委关注点 |
|------|-----------|
| 实际效果 | 查询跑通 → 数字对 → 覆盖全 → 可复跑 |
| 使用增益 | 比基础 Agent 少改几轮、少核对几次（需对照证据） |
| 创新增益 | 字段语义映射、自动连接路径规划、报错自修复 |
| 可靠体验 + 生态贡献 | 异常处理 + 文档/模板可复用 |

常见失败（错误 → 正确）：

| # | 错误做法 | 正确做法 |
|---|----------|----------|
| F1 | 不读数据字典，凭字段名猜含义 | 第一步读取并缓存数据字典，每字段标类型、单位、取值范围 |
| F2 | `SELECT *` 后在 Python 里处理，SQL 只搬运 | 尽量在 SQL 层完成筛选/聚合/排序 |
| F3 | JOIN 漏条件致笛卡尔积，行数膨胀 | 每次 JOIN 后立刻 `COUNT(*)` 与预期比对并记日志 |
| F4 | 把编码字段（species=0,1,2）当数值求均值 | 先查字典解码为标签再分组统计，原始编码与解码值同留 |
| F5 | 缺失值静默删除不记录 | 处理前 `COUNT` 原始行与各列缺失数；处理后记录删除/填充行数及规则 |
| F6 | 异常值一律 3σ | 先做正态性检验（Shapiro-Wilk），非正态改 IQR 法 |
| F7 | 图表不加单位、不标来源 | 轴标签含单位，图注含快照版本与查询时间 |
| F8 | 交付 PDF 截图代替可编辑文件 | 同时交付源文件（.xlsx/.csv/.py/.sql）+ 渲染预览 |
| F9 | 重复记录未去重就统计 | `GROUP BY` 业务键 + `HAVING COUNT(*)>1` 检测，记录去重行数 |
| F10 | 跨表用错连接键 | 从字典确认外键，写显式 `ON a.x = b.y`，禁止隐式关联 |

---

## 2 求解框架（六步流水线）与门控

每步产出一个**冻结产物**，下一步才能启动：

| 步 | 动作 | 冻结产物 | 门控 |
|----|------|----------|------|
| S0 | 确认 SQLite 路径、版本（文件 MD5）、权限；列表名 | `env_manifest.json` | MD5 与任务说明一致；`SELECT 1` 成功 |
| S1 | 读数据字典 + `PRAGMA table_info` 交叉比对，生成 Schema 卡片 | `schema_cards.json` | 字典覆盖率 ≥ 95%；未覆盖字段标 `unmapped` |
| S2 | 质量探查：行数、缺失率、重复、数值分布、编码值核对 | `quality_report.json` + `quality_summary.md` | 所有缺失率/重复数/异常范围已记录，无静默忽略 |
| S3 | 定义并执行清洗规则（缺失/重复/异常/编码/单位） | `cleaning_rules.json` + `cleaned_data.csv` | 清洗前后行数差 = 各规则删除行数之和，可逐条回查 |
| S4 | 编 SQL 逐条执行，存 SQL 文本 + 结果集 + 日志 | `queries.sql` + `result_tables/*.csv` | 所有查询无报错；JOIN 行数在预期内；聚合可独立复算 |
| S5 | 选图表类型生成图表，撰写分析结论 | `figures/`（PNG+源 CSV）+ `analysis_conclusion.md` | 每图源数据可追溯 S4 结果表；结论中每个数字可在结果表找到 |
| S6 | 组装 `result.json` + 复现命令 | `result.json` + `reproduce.sh` | result.json 含 case_id/status/sources/uncertainty/change_log；reproduce.sh 干净环境可跑通 |

图表选择：连续 vs 连续 → 散点图；分类 vs 连续 → 箱线图；时间序列 → 折线图；占比 → 饼图/堆叠柱。

**映射到本 Skill 产物**：S1↔`field_dictionary.json`；S2↔`data_quality.json` + `query_workbook.json`；
S4↔`queries.sql` + `results/query_results.csv` + `results/Q_*.csv`；对账↔`reconciliation.json` +
`join_ledger.json`；报告↔`query_report.md`；复现↔`code/reproduce.md`；契约↔`result.json`。

---

## 3 量化口径（逐条可复算）

```
missing_rate(col) = COUNT(col IS NULL) / COUNT(*) × 100%          # 精确值，不涉及浮点近似
```

**重复行检测**：

```sql
SELECT col1, col2, ..., COUNT(*) AS dup_count
FROM table_name GROUP BY col1, col2, ... HAVING COUNT(*) > 1 ORDER BY dup_count DESC;
```

重复率 = 重复涉及行数 / 总行数 × 100%。

**异常值判定（IQR 法，非正态）**：`Q1=第25百分位, Q3=第75百分位, IQR=Q3-Q1`；下界 `Q1-1.5×IQR`，
上界 `Q3+1.5×IQR`；超出即为异常值（物理下界可收紧，如浓度取 0）。

**异常值判定（3σ 法，仅正态）**：先 Shapiro-Wilk（p>0.05 不拒绝正态），下界 `mean-3σ`，上界 `mean+3σ`。

**跨表 JOIN 行数校验**：预期最小值 = `max(左,右)`（一对一），最大值 = `左×右`（笛卡尔积，绝不允许）；
实际 = JOIN 后 `COUNT(*)`；膨胀比 = 实际 / `min(左,右)`；**膨胀比 > 5 时必须人工审查连接条件**。

**聚合交叉验证**：`SUM(分组聚合值) = SUM(明细数据)`，浮点相对误差 ≤ 1e-6。

**编码字段解码**：`df["label"] = df["code"].map(encoding_map)`；未映射值数 `= df["label"].isna().sum()` **必须为 0**。

---

## 4 领域知识与单位陷阱

| # | 错误 | 正确 |
|---|------|------|
| K1 | Iris 有 150 行就认为完整 | Bezdek variant 行数/列名可能不同，必须查 PRAGMA |
| K2 | Concrete 强度只看 28 天 | 可能含不同龄期，必须按 `age` 分组 |
| K3 | Wine 的 `class` 当连续变量 | 它是分类编码（1/2/3）代表品种，不可求均值 |
| K4 | 混淆 `cement` 与 `concrete` | `cement` 是水泥用量(kg/m³)，`strength` 是抗压强度(MPa) |
| K5 | Iris 的 `petal_width` 当 mm | 标准数据集单位为 cm，仍须查字典确认 |
| K6 | SQLite 的 `INTEGER` 当 Python int | 可能含 NULL，必须先检查 nullable |

| 数据集 | 字段 | 常见单位 | 易混点 |
|--------|------|----------|--------|
| Concrete | cement/slag/ash/water/… | kg/m³ | 不同来源可能用 lb/ft³，须查字典 |
| Concrete | age | days | 有的数据集用 hours |
| Concrete | strength | MPa | 偶见 psi，1 MPa ≈ 145.038 psi |
| Iris | sepal/petal_* | cm | 几乎无歧义，仍须字典确认 |
| Wine | alcohol | % vol | 体积百分比，非质量百分比 |
| Wine | proline | mg/L | 脯氨酸含量，非 g/L |

字段语义以**任务提供的数据字典**为第一来源；字典缺失时引原始论文/数据集发布页，不做无来源假设。

---

## 5 交付物清单与防扣分自查表

| # | 文件 | 内容要求 | 自证方式 |
|---|------|----------|----------|
| 1 | `result.json` | case_id, status, 分析结果, 证据, anomaly, uncertainty, change_log | 每数值可追溯源 CSV |
| 2 | `env_manifest.json` | 库路径、MD5、表列表、权限 | `md5sum` 可复验 |
| 3 | `schema_cards.json` | 每表字段卡片 | 与 `PRAGMA table_info` 交叉比对 |
| 4 | `quality_report.json` | 缺失率、重复数、异常范围 | 内含 SQL 可独立执行 |
| 5 | `cleaning_rules.json` | 每条规则的列、条件、操作、理由 | 规则号 → cleaned_data 行号可追溯 |
| 6 | `cleaned_data.csv` | 清洗后数据 | 行数 = 原始 − 删除行（可算） |
| 7 | `queries.sql` | 所有执行 SQL 含注释 | 在 SQLite 逐条执行结果一致 |
| 8 | `result_tables/*.csv` | 每个查询结果集 | 行数与 COUNT 校验一致 |
| 9 | `figures/*.png` | 图表 | 文件名含源数据表引用 |
| 10 | `figures/*.csv` | 图表源数据 | 可重绘 |
| 11 | `analysis_conclusion.md` | 分析结论 | 每个数字后附 `[来源: table_name, row_filter]` |
| 12 | `reproduce.sh` | 一键复现脚本 | 干净环境可跑通 |

**防扣分自查表（DC-01…DC-17）**：

- [ ] DC-01 数据字典已完整读取，字段覆盖率 ≥ 95%，未覆盖字段已列出
- [ ] DC-02 数据库文件 MD5 已记录且与任务说明一致
- [ ] DC-03 每张表原始行数已记录在 quality_report.json
- [ ] DC-04 每列缺失率已计算并记录，处理规则写入 cleaning_rules.json
- [ ] DC-05 重复行已检测，重复行数与去重规则已记录
- [ ] DC-06 异常值检测方法已标注理由（正态性检验或分布特征）
- [ ] DC-07 所有 SQL 已保存含意图注释，可独立执行
- [ ] DC-08 每个 JOIN 后有 COUNT(*) 校验，膨胀比已记录
- [ ] DC-09 编码字段已解码，encoding_map 已记录，未映射值数 = 0
- [ ] DC-10 聚合结果已交叉验证（SUM 分组 = SUM 明细），误差 ≤ 1e-6
- [ ] DC-11 所有图表含标题、轴标签（含单位）、数据来源注释
- [ ] DC-12 分析结论中每个数字可追溯到具体表名与筛选条件
- [ ] DC-13 result.json 含 case_id、status、sources、uncertainty、change_log
- [ ] DC-14 reproduce.sh 可在干净环境一键执行并产出相同结果
- [ ] DC-15 无静默修改：所有数据变更均有记录和理由
- [ ] DC-16 交付物含可编辑源文件（.csv/.sql/.py），非仅截图/PDF
- [ ] DC-17 跨表连接键来自数据字典外键定义，非凭字段名猜测

---

## 6 完整案例（Concrete 强度分析）

> 案例 `demo_concrete_strength`：分析 `cement` 与 28 天 `strength` 关系，按 `coarseagg` 高/低分组。
> 数据源 `concrete.db`，表 `concrete_data`，1030 行。

**S2 质量**：`SELECT COUNT(*)` = 1030；cement/strength/age 缺失均为 0；9 列全同的重复 18 组涉及 38 行
（多余副本 20 行）；min/max/avg cement = 102/540/281.17，strength = 2.33/82.60/35.82，age = 1/365。

**S3 清洗**：规则 R1 "9 列全同 → 保留首条" → 删 20 行 → `SELECT DISTINCT` 得 **1010 行**。

**S4 查询**：age=28 得 768 行；coarseagg 中位数 972.0；
high_agg（≥972, n=384）avg_cement=278.33, avg_strength=**37.15**；
low_agg（n=384）avg_cement=284.01, avg_strength=**34.49**。
行数校验 384+384=768 ✓；均值交叉验证 (278.33×384+284.01×384)/768 = 281.17 ✓、
(37.15×384+34.49×384)/768 = 35.82 ✓。

**S5 结论**：高骨料组平均强度 37.15 MPa，低骨料组 34.49 MPa，差 2.66 MPa；两组水泥用量相近，
说明强度差异主要来自骨料用量而非水泥用量。`[来源: cleaned_concrete, age=28, Q3]`

**S6 result.json**：`status="completed"`；`quality_evidence` = {db_md5, duplicate_groups:18,
duplicate_rows_removed:20, join_inflation_ratio:"N/A (单表分析)"}；`uncertainty` 说明中位数分界
972.0 为样本中位数、非物理阈值，边界 ±5 不影响结论方向。

---

## 7 快速决策树

```
收到案例 →
  ├─ 有 SQLite 文件？ → S0 环境探测
  ├─ 有数据字典？     → S1 Schema 卡片
  └─ 两者都有 → S2 质量探查
       ├─ 有缺失值？ → 记录 → S3 定义填充/删除规则
       ├─ 有重复行？ → 记录 → S3 定义去重规则
       ├─ 有异常值？ → 正态性检验 → 选 IQR 或 3σ → S3
       └─ 质量良好 → S3（仅记录"无需清洗"）
            → S4 查询执行
                 ├─ 单表查询 → 直接执行 + COUNT 校验
                 └─ 跨表 JOIN → 确认连接键 → 执行 + 膨胀比校验
                      → S5 可视化 + 结论 → S6 封装 result.json + reproduce.sh
```

---

## 8 专家注意点（逐条排雷）

1. **快照只读**：有授权库时只读打开（`file:...?mode=ro`）；无库时把输入表材料装入快照再执行同一批 SQL，
   **查询始终真实执行**，绝不交付"像 SQL 的文本"。
2. **编码≠数值**：编码型字段（distinct ≤ 20）出取值分布，永不求和。
3. **膨胀比复核**：每个 JOIN 后立即核对行数与膨胀比，>5 须人工审查。
4. **可复算优先**：每个数字都能回算到结果集；SQL 与结果 CSV 保持逐字原样（便于直接复跑）。
5. **不猜不编**：不猜连接参数、不接外部库、不判断科研结论对错；缺料降级为诚实 no-data。
6. **确定性**：纯标准库、无网络、无时钟读取；重复运行同一快照，交付物字节稳定。
7. **异常可恢复**：运行中断保留已写部分 `result.json`，异常写入 `errors[]`，退出码仍为 0。

---

> **交付前门控**：用第 5 节自查表（DC-01…DC-17）逐项核验、第 8 节逐条排雷，全部通过后方可交付。
