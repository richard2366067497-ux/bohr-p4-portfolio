# intro-relatedwork-writer — 引言与相关工作写作（writing-07 v9）

把一份稿件与评审意见整理成**可逐条复核的四段式修订稿**（研究背景 / 相关工作 / 研究空白 /
贡献）：每个数字与引用标记都**逐字**从材料复制并带 `locator` 与逐字引文，引用**落在具体
论断上**，研究空白由 **≥2 条前提**推出，每条评审意见映射到实际改动。

核心约束：

- 每个数字/引用要么带 `locator` + **逐字 quote** 复制自材料，要么由这些句子按写在产物旁的
  规则重算；缺失输入写成结构化诚实记录，不臆造。
- 契约逐键回填到 `output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构
  与可读原因，不写占位符。
- 空输入 / 坏 JSON / 缺 `case.json` 仍写合法 `result.json`，**exit 0**。

## 安装

仅 Python 3.9+ 标准库，离线，无需第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md   README.md   SELFTEST.md   GAIN_EVIDENCE.md   GITHUB_URL.txt
  environment/resources.yaml
  references/expert_playbook.md   （执行前必读的专家方法论）
  examples/            （case.json + draft.json 示例）
  templates/           （manuscript_template.md）
  scripts/main.py   scripts/core.py   scripts/render.py
```

执行前先读 `references/expert_playbook.md`，按其八步框架推进，交付前逐项通过其 §6 检查表。

## 用法

### 单命令（无 draft 也产出全部产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描输入 → 逐行登记事实（locator + 逐字 quote + 数字 + 引用标记）→ 绑定引用到论断 →
推导四段 → 校验逐字命中率与 preserved_facts → 10 个 JSON/MD 产物 → `result.json`
（契约逐键回填 + case_id 透传 + `contract_check`）→ 占位符净化 → `selfcheck`。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文句
python3 scripts/main.py check      # 校验四段可推导、空白是否 ≥2 前提、逐字命中率
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显（即随包可靠性自测）
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、sections、citations、preserved_facts、evidence_stats、metrics、contract_check、limits、uncertainties、pending_human、sources、change_records、artifacts |
| manuscript.md | 四段式修订稿，引用落在句内 |
| sources_used.md | 每条 S# 来源 + locator + 逐字引文 |
| claim_map.md | `F#:locator` 论断—来源映射 |
| gap_ledger.md | 每个空白及其 ≥2 条前提 |
| contribution_alignment.md | 每条贡献与结果定位的对齐 |
| change_log.md | 评审意见 → 实际改动 |
| baseline_comparison.md | base-vs-skill 对照口径与效率指标 |
| evidence.json | 每条事实 + locator + quote + 逐字命中标记 |
| verification.json | 四段计数、引用绑定数、空白前提数、preserved_facts |

## 降级与边界

- 无可读正文句：四段报 absent 并列出已检索位置；`status=insufficient_evidence`。
- 空白前提不足 2 条：空白标为 provisional；`status=partial`。
- 无引用标记：相关工作仅绑定到来源句，不虚构外部文献。
- 二进制/坏 JSON：记入 `errors` 并跳过，不猜内容。
- 不联网、不安装工具、不臆造材料外事实。

## 维护

版本 9.1.0；契约键名冻结，抽取规则集中在 `SKILL.md` 与 `scripts/core.py`。
改脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次
`main.py selfcheck`（见 SELFTEST.md）。
