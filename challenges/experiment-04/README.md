# plan-choice-sensitivity — 方案比较多准则选择与敏感性（experiment-04 v10）

把一批实验材料整理成**可逐条复核的方案比较与选择**：从材料中抽出准则字典（id/单位/方向/权重）、
状态映射（0–4）、证据等级（A–D）、成本与周期公式、有限参数域，读入候选工作簿，做
**min–max 归一 + 加权打分 + 硬约束门禁 + 支配关系判定**，逐行复算成本/周期台账表达式，
并对每个假设区间扫描**翻转门槛**（17 点等距 + 22 轮二分），最后给出可比对的选择与舍弃理由。

核心约束：

- 每个数字要么带 `source_id` + `locator` + **逐字 quote** 复制自材料，要么由受限表达式求值器
  按其 `expr` 重算；缺失输入写成结构化 "searched-but-absent" 记录，不臆造。
- 表达式求值使用 AST 白名单（禁止任意代码），仅允许四则运算与括号。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；未按名称识别的契约字段
  仍回填复算摘要，绝不留空。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  references/expert_playbook.md
  scripts/main.py   scripts/extract.py   scripts/engine.py   scripts/render.py
  environment/resources.yaml
  examples/case.json   examples/params.json   examples/notes.md
  README.md  SELFTEST.md  GAIN_EVIDENCE.md  GITHUB_URL.txt
```

**执行前必读**：`references/expert_playbook.md`（专家参考手册）。先按其 §2.1 定义统一比较矩阵的
7 类字段，再按其 §3 口径复算成本/时间/风险，按其 §3.4 评分与敏感性，交付前逐项通过其 §5 的 15 项
自查表并用 §7 专家注意点排雷。

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 抽准则/状态/等级/公式 → 读候选工作簿 → 值转数 → 候选集合内 min–max →
加权 0–100 → 硬约束门禁 → 支配关系 → 台账逐行复算 → 假设区间翻转扫描 → 排序 →
决策备忘录、准则矩阵、翻转报告、成本台账、证据、对比表 6 个 JSON/MD 产物 →
`result.json`（契约逐键回填 + case_id 透传）→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 模板（候选与准则已预填）
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（candidates / cost_time / assumptions / selected）
python3 scripts/main.py check      # 校验权重合计、schema、台账表达式、矩阵可算性
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、准则、候选、排序、台账、敏感性、metrics、limits、uncertainties、sources、change_records、artifacts |
| decision_memo.md | 决策问题、硬门禁、准则字典与权重校验、逐条权重引用、矩阵、归一区间、支配关系、排序、台账逐行、翻转扫描、风险、待确认、降级 |
| criteria_matrix.json | 准则字典（带证据）、权重合计与判定、逐准则归一化、逐候选得分与覆盖、支配关系、排序、状态映射、证据等级、可行性四状态、约束、metrics |
| flip_report.json | 逐假设 17 点选择轨迹、二分门槛、稳健假设、声明的翻转点（用于复算比对） |
| cost_ledger.json | 币种、runs、逐条成本项（expr 与复算值）、逐条时长项、逐候选合计、算术自检 |
| evidence.json | 每条抽取项的 source_id/locator/quote 与逐字命中率 |
| version_diff.md | 逐候选对比表（得分、覆盖、状态、命中/缺值准则、来源）与胜出 |

## 降级与边界

- 无候选工作簿：矩阵只保留准则索引与权重校验，`status=partial`，并列出已检索位置。
- 无准则字典且无候选：`status=insufficient_evidence`，不编造准则。
- 无硬约束：门禁记"未声明"，绝不默认通过。
- 无假设区间：翻转扫描记"不可算"。
- 缺值按 0 分计入得分并暴露在覆盖率里；未声明状态不给中间分。
- 不联网、不安装工具、不臆造缺失数据。

## 维护

版本 2.6.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/extract.py`。
改了脚本必须重跑：空 `/input`、坏 JSON（均 exit 0），并跑一次自测（见 SELFTEST.md）。

## 随包最小样例（examples/，可直接复跑）

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
# exit 0；7 件产物；status=answered；winner=plan_A；
# criteria=6（weight_sum=1.0）, candidates=3, cells 18/18；
# 得分 A 84.4197 / C 55.0 / B 24.2857(infeasible)；台账 15/15；翻转阈值 2.890302；A2 stable
```

样例输入：`examples/case.json`（契约 + 指令）+ `examples/params.json`（3 个路线候选 × 6 准则取值、
2 条硬约束、成本/工期台账、2 条敏感性假设、风险与 selected）+ `examples/notes.md`（准则字典 pipe 表：
id/name/unit/direction/weight/why）。使用增益对照见 `GAIN_EVIDENCE.md`（含确定性 `baseline_sim`
说明，非官方对照）。

## 随包文件（v10 新增）

```
references/expert_playbook.md  专家参考手册（Step 0–5/统一矩阵 7 类字段/成本时间风险口径/敏感性/15 项自查表/完整案例）
environment/resources.yaml     运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                      最小可复跑样例（case.json + params.json + notes.md）
GAIN_EVIDENCE.md               使用增益证据（无 Skill 基线对照 + 真实运行数字）
```
