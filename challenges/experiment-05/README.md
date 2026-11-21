# experiment-interpretation-dossier — 实验结果解释与异常分析（experiment-05 v10）

把一批实验结果材料整理成**可逐条复核的解释案卷**：五段可检查结论（趋势 / 异常点 / 可能原因 /
复核步骤 / 后续实验建议），每条都回指到 `locator` 与**逐字 quote**；从材料中索引筛查规则
R1–R9、单位字典与阈值常量；在固定夹具上按定义复算均值/样本 SD/中位数/MAD/修正 z/IQR 栅栏/
最小二乘/相对偏差，构成可手算核对的复算台账；任何数值列都按 R1/R2/R5/R8′ 规则筛查并把异常
绑定到具体样品/批次/通道/孔位/时间点。

核心约束：

- 每个数字要么带 `source_id` + `locator` + **逐字 quote** 复制自材料，要么由定义式复算；
  缺失结构写成结构化 "searched-but-absent" 记录，不臆造。
- 阈值/单位冲突**并列保留**，绝不静默择一或换算合并。
- 规则只发现"与自身分布或其它源不一致"，**不判断这是坏事**；归因与排除交给判断者。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；改写后仍未命中的键
  回填派生摘要，绝不留空。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  references/expert_playbook.md
  scripts/main.py   scripts/extract.py   scripts/engine.py   scripts/render.py
  environment/resources.yaml
  examples/case.json   examples/notes.md   examples/readout.csv
  README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

**执行前必读**：`references/expert_playbook.md`（专家参考手册）。先按其 §2 的 S1–S6 六步法与门控
解析材料，再按其 §3 统计口径逐条复算（趋势斜率/R²/拐点/平台期；Z/修正 Z/IQR/Grubbs 阈值；
功效重复数），按其 §3.4 给原因候选标 A/B/C 强度，按其 §4 排雷（AU 量程、pH 对数、°C→K、R²≠因果、
n=3 功效、precision≠accuracy），交付前逐项通过其 §5 的 SC-01…SC-20 自查表并用 §7 排雷。

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 逐文件盘点 → 索引规则/单位/阈值 → 固定夹具复算定义 → 数值列筛查 →
五段结论 → 解释正文、案卷索引、盘点、复算台账、阈值、证据、不确定性、方法说明 8 个产物 →
`result.json`（契约逐键回填 + case_id 透传）→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（trends / dossiers / causes / result_fields）
python3 scripts/main.py check      # 校验每条案卷的 rule_id 存在、judged 案卷必须带 attribution_basis
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、五段结论、规则索引、阈值、单位、盘点、复算、metrics、limits、uncertainties、sources、change_records、`contract_key_sources`、artifacts |
| interpretation.md | 8 节正文：盘点 + 五段结论（趋势/异常/原因/复核/后续）+ 不确定性 + 方法 |
| dossier_index.json | 逐条异常（target/严重度/判断/归因/强度/locator/对应 `dossiers/anomaly-<id>.md`）与逐条 issue |
| inventory.json | 逐文件盘点 + 逐表对象列清单 + 数值序列 + 单位分组 |
| recompute.json | 固定夹具、逐定义复算与期望值、逐序列统计、规则候选、一致性自检 |
| thresholds.json | 逐阈值常量（locator+quote）与并列冲突标记 |
| evidence.json | 每条抽取项 source_id/locator/quote 与逐字命中率 |
| uncertainties.json | 不确定项 + 待人工确认 + 已记录缺口 |
| method_notes.md | 解析/统计/判据/复跑命令 |

## 降级与边界

- 无工作稿：案卷为空、`interpretation.md` 顶部标"筛查事实，未经判断"，`status=partial`。
- 无可读材料：`status=insufficient_evidence`，只给盘点与已检索位置。
- 无规则表/无阈值：分别记为"未声明"，不按案例标签臆造。
- 无 ≥5 个数值的读数列：趋势与异常记为显式证据缺口，已检索位置进 gaps。
- 坏 JSON/二进制/空文件：只影响它自己那条盘点记录。
- 不编造湿实验测量值、不编造因果、不编造重复次数；不联网、不安装工具。

## 维护

版本 2.6.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/extract.py`。
改了脚本必须重跑：空 `/input`、坏 JSON（均 exit 0），并跑一次自测（见 SELFTEST.md）。

## 随包最小样例（examples/，可直接复跑）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；9 件产物；rules=6, thresholds=7, units=6, series=2, candidates=1(R1, M03#L6, high)
# checks 4/4；evidence 19/19 (rate 1.0)；契约 12/12；status=partial（无 draft，如实记 2 条降级）

python3 scripts/main.py build --input examples --output /tmp/out2 --work /tmp/work   # draft 就位后
# exit 0；status=answered；trends=1, dossiers=1(A-001, high), causes=1(B)；契约 12/12
```

样例输入：`examples/case.json`（12 键契约 + 题面）+ `examples/notes.md`（筛检规则 R1–R9 pipe 表、
单位与量纲字典、判据阈值常量）+ `examples/readout.csv`（8 点时间序列，含一个 148.3 mg/L 离谱读数）。
使用增益对照见 `GAIN_EVIDENCE.md`（含确定性 `baseline_sim` 说明，非官方对照）。

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（S1–S6 六步法/统计口径 §3/陷阱与单位 §4/自查表 SC-01…SC-20/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + notes.md + readout.csv）
GAIN_EVIDENCE.md               无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
