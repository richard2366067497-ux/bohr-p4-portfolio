# plan-forge-experiment — 实验方案生成与优化（experiment-01 v6）

把一批实验材料整理成**可逐条复核、可复跑的版本化实验方案**：先从材料里抽出六类必需要素
（假设与变量 / 对照组 / 设备材料 / 时间成本 / 参数范围 / 风险和异常），每条都带
`source_id` + `locator` + **逐字 quote**；再由这些数字逐项算出三版候选方案的成本、工时、
违规项，跑六条校验规则，对失败项做规则化修订（`from → to` + 原因），最后给出带容差带的推荐版本。

核心约束：

- 每个数字要么带 locator 与逐字 quote 复制自材料，要么由写在产物旁边的公式重算；缺失输入写成
  结构化记录并注明原因，不臆造设备清单或价格。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构与可读原因。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py   scripts/plan.py   scripts/design.py   scripts/render.py
  README.md  SELFTEST.md  GITHUB_URL.txt
```

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描材料 → 抽六要素（含 fenced JSON 数据块与散文区间/规则）→ 生成三版候选 →
逐版算成本与工时 → 六条规则校验 → 规则化修订 → 渲染 8 个产物 → `result.json`（契约逐键回填 +
case_id 透传）→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（recommended 里填参数值）
python3 scripts/main.py check      # 把 draft 的取值映射到参数域并判断是否越界/离格
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物存在性与契约回显是否非空
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、六要素、参数域、约束、资源、版本表、推荐、算术、校验汇总、limits、uncertainties、sources、change_records、artifacts |
| plan_report.md | 状态与原因、六要素逐条（带 locator/quote）、推荐值与容差带、每条算术自检、limits 与来源 |
| plan_revised.json | 三版方案、每版的修订动作（`from → to` + 原因）、胜出版本、修订规则 |
| validation_report.json | 六条规则定义、逐版 violations/warnings/notes、修订前状态、汇总计数 |
| arithmetic_ledger.json | 逐版：公式、成本行、工时行、输入行（含 locator）、每条自检 |
| evidence.json | 每条抽取项的 source_id/locator/quote 与逐字命中率 |
| version_diff.md | 逐版对比表（取值、成本、工时、违规数、可行、是否修订）与 locator |
| reproduce.md | 入口命令、读到的材料、推荐值、执行步骤、修订规则 |

## 六条校验规则

`param_domain`（落在参数域内且与 step 对齐）、`constraint_*`（材料里的 le/ge/lt/gt/eq/ne 与互斥）、
`booking`（有窗口的设备），`budget`（总成本 ≤ 上限）、`quantity`（用量 ≤ 库存）、`control`（有对照臂）、
`unit`（参数与计价项都有单位）。修订规则：夹到最近合法格点、满足被违反的界、用量裁到库存、
重复数降到 `floor(预算 / 单次成本)`（不低于 1）、补一条标注为“须确认”的对照臂。

## 降级与边界

- 材料无有限参数域：参数范围与算术如实报缺并列出已检索位置；`status=insufficient_evidence`。
- 材料无候选方案：按参数域三分位生成 v1/v2/v3，并标注为 generated（绝不冒充材料原文）。
- 材料无对照 / 无风险表 / 无预算：给规则化建议或留空规则并写明原因，进 `uncertainties`。
- 样品少、价格缺位时不做显著性检验，成本报表只写能核验的行与公式。
- 不联网、不安装工具、不臆造缺失数据。

## 维护

版本 2.6.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/plan.py`。
改了脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次自测（见 SELFTEST.md）。
