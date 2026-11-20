# 最小调用示例（示例，非正式案例结果）

以下全部是**构造的示意输入与示意输出**，用于说明接口与完整流程，不代表任何正式案例的结论或分数。

## 1. 示例输入目录

```
demo/input/
├── case.json
├── task.md
├── records.jsonl
└── sources/
    ├── S01.md            # 试验类材料，报告指标下降
    ├── S02_cohort.md     # 队列，报告无差异（与方法 S01 结论相反）
    └── S03_abstract.md   # 仅摘要，结局与问题无关
```

`case.json`（节选）：

```json
{
  "case_id": "DEMO-1",
  "research_question": "<本案例的研究问题>",
  "output_contract": {
    "review_draft": "带引用的综述草稿",
    "screening_log": "逐条纳排记录",
    "evidence_table": "证据表",
    "gap_report": "缺口与空白",
    "coverage": "覆盖统计"
  }
}
```

## 2. 五条命令

```bash
python3 scripts/main.py init       # 建索引；写出合法 partial result.json 与 draft.json 脚手架
python3 scripts/main.py show       # 材料清单（带 source_id / 是否仅摘要 / 句数）
python3 scripts/main.py show --source S01        # 该文献的块-句与 locator（逐字复制用）
python3 scripts/main.py show --grep "primary outcome" --max 20   # 全材料检索候选引文
#   —— 到这里 Agent 亲自读材料，把结论写进 /app/work/draft.json（schema 见 workbook_schema.md）——
python3 scripts/main.py check      # 机械校验：标准先行 / 引文逐字 / 槽位覆盖 / 冲突 / 契约
python3 scripts/main.py build      # 生成 draft.md、outline、slots、gap_report、coverage、result.json
python3 scripts/main.py selfcheck  # 独立复检（引文重新回材料核验、回链、契约）
```

## 3. `show --source S01` 的示意输出

```
S01 | sources/S01.md | kind=source method=text abstract_only=False chars=691 sentences=7
meta: title=<材料自述标题> year=20XX doi:10.0000/demo.001
## sources/S01.md#B1S1@0-72
      # <材料标题行>
  sources/S01.md#B5S1@455-588
      Results
<该文献结果段的原句，含数字与区间，逐字复制>
```

`quote` 直接复制最后那行原句（含标点、单位、数字），`locator` 直接复制 `sources/S01.md#B5S1@455-588`。
**不要改写、不要翻译、不要把两句缝合**——脚本做逐字比对，改一个字就会报 `Q103`/`Q104`。

## 4. 工作稿片段（示意）

```json
{
  "case_id": "DEMO-1",
  "criteria": [
    {"criterion_id": "IC1", "type": "include", "statement": "<对象条件>", "judge_rule": "<出现什么词/报告什么结局才算命中>", "priority": 1, "stage": "title_abstract"},
    {"criterion_id": "EC1", "type": "exclude", "statement": "<排除条件>", "judge_rule": "<可机械判定的表述>", "priority": 2, "stage": "title_abstract"}
  ],
  "screening": [
    {"record_id": "R01", "source_id": "S01", "stage": "title_abstract", "decision": "include", "criterion_ids": ["IC1"], "reason": "<命中哪条条款>", "locator": "sources/S01.md#B5S1@455-588"},
    {"record_id": "R03", "source_id": "S03", "stage": "title_abstract", "decision": "exclude", "criterion_ids": ["EC1"], "reason": "仅摘要且结局无关", "locator": "sources/S03.md#B3S1@0-1"}
  ],
  "outline": [
    {"sec_id": "SEC1", "heading": "<支持类证据的章节>", "purpose": "<该节回答研究问题的哪一面>", "slots": [
      {"slot_id": "SL1", "claim_prompt": "<要做出的论断>", "required_evidence": "<需要什么证据>"}]},
    {"sec_id": "SEC2", "heading": "<相反证据的章节>", "purpose": "<为什么必须并列>", "slots": [
      {"slot_id": "SL2", "claim_prompt": "<相反论断>", "required_evidence": "<需要的证据>"}]}
  ],
  "slots": [
    {"slot_id": "SL1", "state": "filled", "claim": "<由 S01 原句支持的论断>", "strength": "moderate",
     "evidence_refs": [{"source_id": "S01", "locator": "sources/S01.md#B5S1@455-588",
       "quote": "<show 输出中的逐字原句>"}]},
    {"slot_id": "SL2", "state": "filled", "claim": "<由 S02 原句支持的相反论断>", "strength": "moderate",
     "polarity": "counter", "conflicts_with": ["SL1"],
     "evidence_refs": [{"source_id": "S02", "locator": "sources/S02.md#B5S1@0-1",
       "quote": "<show 输出中的逐字原句>"}]}
  ]
}
```

## 5. `check` 的示意输出

```
check: 0 FIX / 1 WARN -> 就绪，可 build
      当前工作稿：条款 2，筛选行 2，章节 2，槽位 2
  [WARN] X102 SL2<->SL1: 冲突关系单向 -> build 自动补对称
```

若把 `SL1` 的引文改成意译或翻译，`check` 会给出：

```
check: 1 FIX / 0 WARN -> 未就绪，先修 FIX
  [FIX] Q104 SL1: 引文在 S01 中找不到 -> 回原文重取或改判 gap
```

## 6. `build` 与产物（示意数字，非正式案例结果）

```
build: status=ok 章节=2 槽位=2 已填=2 缺口=0 覆盖率=100% 引文=2
       修补：引文纠正 0，丢弃 0，强度下调 1，槽位转缺口 0，冲突对称 1
       产物：/app/output/draft.md（约 900 字）与 result.json（契约 5/5）
```

`draft.md` 片段（示意）：

```markdown
## <支持类证据的章节>

现有研究提示，<论断>[S01]。 [SL1]

## <相反证据的章节>

与此相反，现有研究提示，<相反论断>[S02]。 [SL2]
```

注意：第二段因为 `polarity=counter` 另起段落，两个相反结论并列出现，而不是被平均成一句话。

## 7. 缺工作稿时的兜底输出（示意）

```
build: status=partial 章节=2 槽位=2 已填=0 缺口=2 覆盖率=0% 引文=0
       产物：/app/output/draft.md（约 1200 字）与 result.json（契约 5/5）
```

此时 `draft.md` 只含：研究问题、文献清单表（材料转录、非论断）、证据缺口清单、边界说明、参考文献。
`result.json` 的契约字段全部存在，`degradations` 写明 `work_draft_missing`，`status=partial`。**不会出现空目录或退出码非 0。**

## 8. 套用到新案例的最小改动

1. 把新材料放进 `input/`（PDF/MD/TXT/DOCX/JSONL/CSV 都可），保持 `case.json` 的 `output_contract` 原样。
2. 跑 `init`：题录、重复标记、仅摘要标记、语言都由脚本给出，无需改代码。
3. 只有一处需要判断：**这一批文献该怎么分节**（写进 `outline_basis`）。其余都是填字段。
4. 契约字段名不同也不需要改代码：`rules.py` 的 `FIELDS` 按语义关键词匹配；确实对不上的键会保留为 `null` 并记 `unmapped_field`。
