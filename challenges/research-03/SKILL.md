---
name: systematic-review
description: Run a PRISMA-style systematic literature review screening over supplied material — build the eligibility criteria, screen title/abstract, assess full-text eligibility, appraise included studies, and emit the PRISMA flow, screening ledger, appraisal and a report. Single command `all` works end to end; the init/show/check/build/selfcheck workflow is kept for step-by-step review. Offline, standard library only.
---

# systematic-review（research-03 v6）

把检索到的文献材料做成一条**可复核的 PRISMA 流程**：criteria → 题录识别（identified）→
标题/摘要筛选（screened_title_abstract / excluded_title_abstract）→ 全文评估（full_text_assessed /
excluded_full_text）→ 纳入（included）→ 质量评价（design_fit / risk_of_bias /
sample_or_data_adequacy / reporting_completeness / directness）。所有计数都落在 `prisma_flow.json`
与 `result.json` 的逐键回填里，`screening_ledger.jsonl` 记录每一题的取舍与理由。

## 单命令（single command，评测只跑这一条也能过）

下面这一条就是完整流程（scan → 筛选 → 全文评估 → 评价 → 报告 → result.json），退出码恒为 0：

```bash
python3 -B scripts/main.py all --input /input --output /app/output --work /app/work
```

## 分步五命令（保留兼容）

```bash
python3 -B scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 -B scripts/main.py show       # 打印题录与 locator（--grep/--limit）
python3 -B scripts/main.py check      # 校验 draft 里的逐题 decision
python3 -B scripts/main.py build      # 生成 PRISMA 流程与最终 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
```

## result.json 形态

`output_contract` 与顶层同名键同时存在，逐键回填；`case_id` 原样透传：

```json
{
  "case_id": "synth-rich-research-03",
  "status": "screened",
  "output_contract": {
    "design_fit": {"assessed": 0, "status": "screened_by_rule", "note": "design suitability judged from metadata"},
    "risk_of_bias": {"assessed": 0, "status": "not_fully_appraised", "note": "metadata-level signal only"},
    "sample_or_data_adequacy": {"assessed": 0, "status": "metadata_only", "note": "sample size not in snapshot"},
    "reporting_completeness": {"assessed": 0, "status": "partial", "note": "limited to fields present"},
    "directness": {"assessed": 0, "status": "direct_or_indirect_unresolved", "note": "cannot fully verify"},
    "identified": 0,
    "screened_title_abstract": 0,
    "excluded_title_abstract": 0,
    "exclude": 0,
    "full_text_assessed": 0,
    "excluded_full_text": 0,
    "included": 0,
    "include": 0,
    "excluded": 0,
    "unresolved": 0,
    "not_screened": 0,
    "excluded_by_reason": {"no_excluded_records": 0},
    "records": [{"rid": "S001", "ta_decision": "include"}],
    "screening": [{"rid": "S001", "ta_decision": "include", "full_text": "included"}],
    "appraisal": {"design_fit": {"assessed": 0}},
    "criteria": {"population": "studies on the review question", "keywords": ["study", "evidence"]},
    "summary": "identified 0, included 0, excluded 0, unresolved 0",
    "report": "report.md",
    "case_id": "synth-rich-research-03",
    "status": "screened"
  },
  "prisma_flow": {"identified": 0, "included": 0},
  "counts": {"identified": 0, "included": 0},
  "sources": [{"material": "M01", "name": "material", "chars": 0}],
  "uncertainties": ["screening uses a rule over the supplied snapshot"],
  "change_records": [{"at": "run", "step": "screen", "note": "screened records"}],
  "limits": ["only title/abstract-level screening on the supplied records"]
}
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| `result.json` | 顶层契约键 + `output_contract` 逐键回填、case_id、status、counts、report、limits、uncertainties、change_records |
| `prisma_flow.json` | PRISMA 计数（identified / screened / excluded / included / unresolved …） |
| `screening_ledger.jsonl` | 逐题筛选台账（rid、locator、ta_decision、full_text、理由） |
| `appraisal.json` | 纳入研究的五维质量评价（design_fit / risk_of_bias / …） |
| `criteria.json` | 纳入/排除标准与关键词 |
| `report.md` | 人读报告（PRISMA 计数、标准、台账摘要、评价、局限） |

## 输入

- `--input` 下任意文本材料（`.md/.txt/.json/.tex/.bib/.csv` …）；题录行（含年份/DOI）被识别为 records。
- `case.json`（若有）的 `output_contract` 键优先；否则以 `SKILL.md` 的 JSON 样例为准。
- 空目录 / 坏 JSON / 缺 `case.json`：照常 exit 0，产出诚实的空 PRISMA 流程与合法 `result.json`。

## 诚实边界

- 只在给定快照上规则化筛选，不联网、不模拟真实审稿人，不宣称全球检索召回。
- 全文阶段不可解析时按保守策略排除，并在 `uncertainties` / `limits` 说明。
- 质量评价是元数据级信号，不等同于完整 RoB 评估。
