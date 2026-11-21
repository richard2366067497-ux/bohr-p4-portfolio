# plan-feasibility-review — 实验方案可行性复核（experiment-02 v6）

把一批实验材料整理成**可逐条复核的可行性审查**：从材料中抽出资源四态（已具备 / 可外协 /
需采购 / 不可用）、价格与货期行、机时窗口、有限参数域与显式约束、伦理与安全审批项，
再对每个候选方案版本逐项判定七大类别（设备、材料、时间、样本、伦理与安全、参数范围、
风险与异常），把每步时长与每项成本按行算出单次时长与单次成本，比较版本并给出待确认清单。

核心约束：

- 每个数字要么带 `source_id` + `locator` + **逐字 quote** 复制自材料，要么由这些数字按写在
  产物旁边的公式重算；缺失输入写成结构化 "searched-but-absent" 记录，不臆造。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构与
  可读原因，不写占位符。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py   scripts/extract.py   scripts/engine.py   scripts/render.py
  references/expert_playbook.md
  environment/resources.yaml   examples/   GAIN_EVIDENCE.md
  README.md  SELFTEST.md  GITHUB_URL.txt
```

> **执行前必读**：`references/expert_playbook.md` 是本 Skill 的专家参考手册（七类审查框架、
> 时间/样本量量化口径、设备匹配判据、风险分级、伦理周期表、定位符格式、18 项专家检查表、完整案例）。
> 产出交付物时按其框架与口径执行，交付前逐项通过其 §6 检查表（S01–S18）。

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 抽资源/价格/机时/参数域/约束/审批 → 逐版本七大项判定 → 行级时长与成本 →
版本排序与胜出 → 待确认清单与降级 → 时间线报告、检查台账、估算、风险、确认、证据、版本对比
7 个 JSON/MD 产物 → `result.json`（契约逐键回填 + case_id 透传）→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（chosen_version 与 recommended 参数值）
python3 scripts/main.py check      # 校验 draft 的建议值是否落在已抽取的域与约束内
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、资源、参数域、约束、版本可行性、算术自检、待确认、limits、uncertainties、sources、change_records、artifacts |
| feasibility_review.md | 七大项 × 逐版本表、行级时长与成本、带 locator+quote 的域与约束、风险、待确认、算术台账、降级 |
| checks.json | 逐版本 × 逐类别状态台账、排序与胜出、参数域证据、规则索引、命中率 |
| estimate.json | 时长与成本公式、逐版本估算（步骤行/成本行）、预算与自检 |
| risks.json | 逐版本风险项、所有显式约束（带证据）、不可用资源 |
| confirmations.json | 批准前必须关闭的确认项、审批项、预算状态 |
| evidence.json | 每条抽取项的 source_id/locator/quote 与逐字命中率 |
| version_diff.md | 逐版本对比表（设置、不可行项数、单次成本、占预算、可行性、locator）与胜出 |

## 降级与边界

- 材料中无候选方案也无资源契约：给规则索引与已检索位置，`status=insufficient_evidence`。
- 无有限参数域：域内与步长对齐检查报 absent 并列出已检索位置。
- 无预算：总成本保留公式，超预算百分比留空，不猜预算。
- 无样本量 / 无审批：分别报"未声明"，绝不默认满足。
- 单一材料行支撑某资源可用性时，标注单点风险与无重复缓冲。
- 不联网、不安装工具、不臆造缺失数据。

## 维护

版本 2.6.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/extract.py`。
改了脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次自测（见 SELFTEST.md）。
