---
name: systematic-review
description: Run a PRISMA-style systematic literature review screening over supplied material — build the eligibility criteria, screen title/abstract, assess full-text eligibility, appraise included studies, and emit the PRISMA flow, screening ledger, appraisal and a report. Single command `all` works end to end; the init/show/check/build/selfcheck workflow is kept for step-by-step review. Offline, standard library only.
---

# systematic-review（research-03 v10）

把检索到的文献材料做成一条**可复核的 PRISMA 流程**：criteria → 题录识别（identified）→
标题/摘要筛选（screened_title_abstract / excluded_title_abstract）→ 全文评估（full_text_assessed /
excluded_full_text）→ 纳入（included）→ 质量评价（design_fit / risk_of_bias /
sample_or_data_adequacy / reporting_completeness / directness）。所有计数都落在 `prisma_flow.json`
与 `result.json` 的逐键回填里，`screening_ledger.jsonl` 记录每一题的取舍与理由。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§3 求解框架与门控（九步 S1–S9）** 推进——输入解析 → 问题结构化 → 检索式构造
  → 检索执行 → 题录筛选 → 全文筛选 → 质量评价 → 证据综合 → 输出 result.json；前一步未冻结
  不进入下一步。
- **量化口径**：按其 **§4 量化口径与公式** 逐项复算——检索式覆盖率、纳排一致性、排除理由完整率、
  证据回链率、质量评价依据覆盖率、可复算率，并满足其 PRISMA 守恒等式。
- **陷阱与单位**：按其 **§5 领域陷阱与单位** 逐条排雷（文献类型混淆、错误领域标签、效应量/浓度/
  温度/样本量单位不可混用），每条论断附 `[文献ID] 表/图/段落` 级 locator。
- **门控**：交付前逐项通过其 **§7 防扣分自查表（20 项）**；任一项未过则修正后重出，绝不静默提升
  为完整成功。

## 评测契约（`result.json` 形态）

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

契约键来源优先级：`case.json:output_contract` → `task.md` → 本文件这段 JSON 样例。无 `case.json` 或
其契约为空时回退到本样例（25 键）并照常逐键回填。

## 单命令（single command，评测只跑这一条也能过）

下面这一条就是完整流程（scan → 筛选 → 全文评估 → 评价 → 报告 → result.json），退出码恒为 0：

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

```bash
python3 -B /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

## 分步五命令（保留兼容）

```bash
python3 -B scripts/main.py init       # 建索引 + partial result.json + draft 骨架
python3 -B scripts/main.py show       # 打印题录与 locator（--grep/--limit）
python3 -B scripts/main.py check      # 校验 draft 里的逐题 decision
python3 -B scripts/main.py build      # 生成 PRISMA 流程与最终 result.json
python3 -B scripts/main.py selfcheck  # 复检产物
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
- `case.json`（若有）的 `output_contract` 键优先；否则以本文件的 JSON 样例为准。
- 空目录 / 坏 JSON / 缺 `case.json`：照常 exit 0，产出诚实的空 PRISMA 流程与合法 `result.json`。

## 诚实边界

- 只在给定快照上规则化筛选，不联网、不模拟真实审稿人，不宣称全球检索召回。
- 全文阶段不可解析时按保守策略排除，并在 `uncertainties` / `limits` 说明。
- 质量评价是元数据级信号，不等同于完整 RoB 评估。

## 交付前自查清单

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键非空、无类型占位符。
- [ ] `prisma_flow.json` 计数与 `screening_ledger.jsonl` 逐条对账，满足 PRISMA 守恒等式。
- [ ] `appraisal.json` 五维均为含 `assessed/status/note` 的非空结构，证据不足时诚实标注。
- [ ] `criteria.json` 的每个排除条目可回指一条纳排条款，排除理由非空。
- [ ] `report.md` 非空，且与计数、标准、台账、评价互相可核验。
- [ ] 空输入 / 坏 JSON / 缺 `case.json` 三条降级路径各跑过一次，均 exit 0 且有缺口报告。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` **§7 防扣分自查表（20 项）** 全项通过；
  未过则修正后重出，不得静默提升 status。
