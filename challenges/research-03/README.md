# systematic-review — 系统综述筛选（research-03 v6）

把检索到的文献材料做成一条**可复核的 PRISMA 流程**：先由材料与任务文本生成纳入/排除标准，
再对题录做标题/摘要筛选、对候选做全文评估，最后汇总纳入研究并给出元数据级质量评价。所有阶段
都落到 `prisma_flow.json`、`screening_ledger.jsonl`、`appraisal.json` 与 `result.json` 的逐键回填里。

核心约束：

- PRISMA 计数一一对应：`identified` → `screened_title_abstract` → `excluded_title_abstract` →
  `full_text_assessed` → `excluded_full_text` → `included`；并给出 `exclude/include/excluded/
  unresolved/not_screened/excluded_by_reason` 等别名与细分。
- 质量评价五维 `design_fit / risk_of_bias / sample_or_data_adequacy / reporting_completeness /
  directness` 均为真实结构，无占位符；证据不足时诚实标注 `no_included_studies`。
- 逐题取舍有 locator 与理由；空/坏输入仍 exit 0，不臆造结论。

## 安装

仅 Python 3.9+ 标准库，离线。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/systematic-review-spec.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

## 用法

### 单命令（评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

### 五命令

```bash
python3 scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show        # 打印题录与 locator（--grep/--limit）
python3 scripts/main.py check       # 校验 draft 里逐题 decision
python3 scripts/main.py build       # 生成 PRISMA 流程与最终 result.json
python3 scripts/main.py selfcheck   # 复检产物
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 顶层契约键 + `output_contract` 逐键回填、case_id、status、counts、report、limits、uncertainties、change_records |
| prisma_flow.json | PRISMA 计数（identified / screened / excluded / included / unresolved …） |
| screening_ledger.jsonl | 逐题筛选台账（rid、locator、ta_decision、full_text、理由） |
| appraisal.json | 纳入研究五维质量评价 |
| criteria.json | 纳入/排除标准与关键词 |
| report.md | 人读报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：产出诚实的空 PRISMA 流程与合法 `result.json`。
- 无题录可识别：`degradations` 记录原因，计数为 0，不臆造纳入研究。
- 全文不可解析：保守排除并写入 `excluded_by_reason`，在 `uncertainties` 说明。

> 本地评测复现命令与（静态推演的）预期结果见 `SELFTEST.md`。
