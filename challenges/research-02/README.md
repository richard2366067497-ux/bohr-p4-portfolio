# lit-review-workbench — 源定位文献综述工作台（research-02 v9）

把一批科研材料整理成**可逐条回链的文献综述**：先写清纳排标准，再筛选记录
（重复 / 仅摘要 / 低相关 / 元数据不全），从语料中长出主题，建立带 `locator` + **逐字 quote**
的证据矩阵，给出覆盖度与研究空白，并对每条论断做 selfcheck 回链核验。所有数字与引文都
来自材料，缺失输入写成结构化 no-data，不臆造文献。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md   README.md   SELFTEST.md   GITHUB_URL.txt   GAIN_EVIDENCE.md
  scripts/main.py
  environment/resources.yaml
  examples/case.json   examples/params.json
  templates/evidence_matrix.csv   templates/screening_log.csv   templates/outline.json
```

## 用法

### 单命令（无 draft 也产出全部产物 + result.json，exit 0）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

`all` = 扫描材料 → 段落定位 → 抽取候选记录 → 纳排筛选 → 主题归纳 → 证据索引 →
覆盖度 & 冲突/空白 → 草稿 → selfcheck 回链 → `result.json`（契约逐键回填 + case_id 透传）
→ 占位符净化。

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show       # 打印带 locator 的原文段（--grep/--mat）
# Agent 读材料、写 /app/work/draft.json（sections/claims 填主题与逐字引文）
python3 scripts/main.py check      # 校验 draft 是否锚定到纳排后的记录
python3 scripts/main.py build      # 生成全部产物与最终 result.json
python3 scripts/main.py selfcheck  # 复检产物一致性与契约回显
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 契约键（顶层 + `output_contract`）、status、themes、coverage、evidence_stats、sources、uncertainties、change_records、artifacts |
| draft.md | 带引用的综述草稿，每条证据一行 `[record, source, locator, strength]` |
| evidence_matrix.json | record_id/source_id/locator/逐字 quote/claim/strength + 命中统计 |
| screening_log.csv | record_id, source_id, locator, decision, flag, reason |
| coverage_report.json | 每 slot 的 filled/gap、filled_ratio、quote_hit_rate |
| conflicts_and_gaps.md | 每主题状态、反证并列说明、具体证据缺口 |
| audit_report.md | selfcheck 回链：逐条 claim 在其 locator 的逐字命中 |
| run_log.txt | 逐材料 parse_status 与各阶段计数 |

## 降级与边界

- 无材料 / 无记录 / 仅摘要 / 空文件 / 坏 JSON / 占位文本：写出结构化 no-data，`status` 取
  `insufficient_evidence` 或 `partial`，并列出已检索位置；**exit 0**。
- 没有记录通过纳排：`screening_log` 逐条解释排除理由，草稿明确说明未写引用综述。
- 引文与其 locator 不逐字一致时，`audit_report` 标 `verbatim=False`，不冒充已回链。
- 不联网、不装第三方库、不臆造文献。

## 维护

版本 1.0.0；契约键名冻结，抽取与纳排规则集中在 `scripts/main.py` 与 `SKILL.md`。
改了脚本必须重跑：`--help`、空 `/input`、坏 JSON（三者均 exit 0），并跑一次自测（见 SELFTEST.md）。
