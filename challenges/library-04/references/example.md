# 完整走查（示例数据，非正式案例结果）

以下示例用最小的自造资料库演示五命令主路径的每一步、每条命令的真实输出形状，以及在哪些位置由 Agent 而不是脚本做判断。示例中的文件与数值都是为演示编造的，**不代表任何官方案例，也不是提交答案**。

## 1. 示例输入

```
demo/input/
├── case.json                       # case_id / task_instruction / output_contract / questions
├── task.md                         # 任务说明（脚本跳过，不进登记表）
└── library/
    ├── paper_v1.md                 # 初稿，报 40 例
    ├── paper_v1_copy.md            # 与初稿字节一致的重复副本
    ├── paper_v2.md                 # 接收版，报 52 例
    ├── _admin_notes.txt            # 管理性版本说明：哪份过时、哪份是副本、哪份不可用
    ├── data_table.csv              # 补充测量值
    └── scan_supp.pdf               # 扫描件，无文本层
```

`case.json` 给 `case_id`、`output_contract`（键名任意，按语义匹配）与 3 个 `questions`：Q1 样本量、Q2 库里有没有抗体货号、Q3 v1 与 v2 是否一致。

## 2. `init`：登记、抽取、家族、问题

```bash
python3 -B scripts/main.py init --input demo/input --output demo/output --work demo/work
```

真实输出形状（节选）：

```
== registry (6 documents) ==
D1 | _admin_notes.txt  | text  |  374 B | sha 91ac02b6 | F1 v1 | readable   | 5 paras
D3 | paper_v1.md       | text  |  463 B | sha 7dbefb4e | F3 v2 | readable   | 4 paras
D4 | paper_v1_copy.md  | text  |  463 B | sha 7dbefb4e | F3 v1 | readable   | 4 paras
D5 | paper_v2.md       | text  |  555 B | sha 9d2834ee | F3 v3 | readable   | 4 paras
D6 | scan_supp.pdf     | pdf   |   69 B | sha cfa3181c | F4 v1 | UNREADABLE | 0 paras | no_text_layer
== families ==
F3 | members=D3,D4,D5 | canonical=D5 | D3~D4:sha256_identical; D3~D5:text_similarity_0.96
== administrative version notes (top 4) ==
D1 `t1#para2` mentions=D3,D5 :: 1. paper_v1.md 是会议初稿，数值已过时，请以 paper_v2.md 为准。
D1 `t1#para3` mentions=D3,D4 :: 2. paper_v1_copy.md 是 paper_v1.md 的重复副本（可删除）。
== questions (3) ==
Q1 | 最终分析样本量是多少例？
```

判断分工：脚本给出 D4 与 D3 哈希相同、D5 与二者相似度 0.96、文件名分别带 v1/v2、管理说明点名谁作废；"因此 D5 是权威版、D4 是可删副本"这句结论仍由 Agent 写进工作稿。

## 3. `show`：逐字读，拿现成引文

```bash
python3 -B scripts/main.py show --doc D5 --work demo/work
python3 -B scripts/main.py show --query "sample size participants" --emit --work demo/work
```

```
[D5 t1#para2] ## Methods Male C57BL/6J mice (8 weeks) ... A total of 52 participants were
analysed in the primary cohort after two animals were excluded for incomplete records. ...
-- D5 (paper_v2.md) family=F3 v=3 readable=True: 4 paragraphs, showed 1..2
```

`--emit` 输出可直接粘贴的 exhibit 对象（编号/doc/版本/locator/引文已填），Agent 只改 `kind` 与 `polarity`；引文是原文子串，逐字校验必然通过。

## 4. 写工作稿（Agent 的核心工作）

```bash
python3 -B scripts/main.py show --template --work demo/work
cp demo/work/draft.template.json demo/work/draft.json
```

填入的判断（节选）：

```json
{"qid":"Q1","answer_draft":"最终分析的样本量为 52 例 [E1]。该数值来自接收版 v2 的 Methods，同段说明有 2 只动物因记录不完整被排除 [E1]。初稿 v1 报告 40 例 [E2]，该版已被管理说明标注为数值过时 [E3]。",
 "issues":[
  {"issue_id":"Q1-I1","issue_text":"最终分析的样本量为 52 例","verdict":"supported",
   "positive_exhibits":["E1"],"counter_exhibits":[],"missing_evidence":"",
   "reasoning":"D5（v2）Methods 明确写 52 participants were analysed"},
  {"issue_id":"Q1-I2","issue_text":"52 例这一数值属于接收版 v2，而非初稿 v1",
   "verdict":"contradicted_with_reason","positive_exhibits":["E1","E3"],"counter_exhibits":["E2"],
   "reasoning":"v1 报 40、v2 报 52；管理说明指明 v1 过时、以 v2 为准，故取 v2"}]}
```

问"库里有没有抗体货号"那一问判 `insufficient`：

```json
{"issue_id":"Q2-I1","issue_text":"知识库中存在报告抗体货号的可读证据","verdict":"insufficient",
 "positive_exhibits":["E7","E6"],"counter_exhibits":[],
 "missing_evidence":"缺少报告抗体品牌/货号的 Methods 文本；D6 为扫描件无文本层，需 OCR 后才能确认",
 "reasoning":"全库检索 western/antibody/货号 无命中；可读段落只覆盖动物与给药"}
```

## 5. `check`：机械校验会真的拦住错误

首次运行示例工作稿时，脚本报出三处 `locator_mismatch`（引文抄对、段号抄错，正是本题最常见的失分形态）：

```
FIX [locator_mismatch] E1 :: claimed locator 't1#para3' does not contain the quote;
                            quote really occurs at t1#para2
```

按提示把 `t1#para3` 改成 `t1#para2` 后：

```
ok=True docs=6 questions=3 issues=4 exhibits=7 quote_pass=1.0 locator_pass=1.0
verdicts={"supported": 2, "contradicted_with_reason": 1, "insufficient": 1} errors=0 warnings=0
```

另做一次故意造假的对照：把引文的 52 改成 58，答案里写"58 例"：

```
FIX [quote_not_found] E1 :: quote not found verbatim in D5: 'A total of 58 participants were analysed.'
FIX [number_unanchored] Q1 :: number '58' in answer has no cited quote containing it
FIX [number_unanchored] Q3 :: number '52' in answer has no cited quote containing it
```

第三行说明：引文一旦未通过核验，便不再能为数值作担保，依赖它的数字也会被标出。

## 6. `build` 与 `selfcheck`

```bash
python3 -B scripts/main.py build --input demo/input --output demo/output --work demo/work
python3 -B scripts/main.py selfcheck --output demo/output --work demo/work
```

```
status=partial docs=6 families=4 duplicates=1 questions=3 issues=4 exhibits=7
verdicts={"supported": 2, "contradicted_with_reason": 1, "insufficient": 1} check_ok=True
unfilled contract: none
```

`status=partial` 是诚实的：三问中有一问证据不足。若三问均可答且无降级，则为 `ok`。

```
PASS result_json_parses / contract_keys_present(none) / exhibit_quotes_reverify(7, bad=none)
PASS exhibit_locators_reverify(mismatch=none) / dockets_rendered(3)
selfcheck: PASS
```

## 7. 兜底演示（不写工作稿）

```bash
rm -rf demo/work/draft.json
python3 -B scripts/main.py build --input demo/input --output demo/output --work demo/work
```

```
status=partial docs=6 families=4 duplicates=1 questions=3 issues=3 exhibits=0
verdicts={"insufficient": 3} check_ok=True
unfilled contract: none
```

此时产物仍然完整：文件登记、哈希、权限、版本家族、重复组、整理动作都是真实计算结果；每题给 `insufficient` 卷宗并写明检索范围；`report.md` 第 2 节列出候选段落供复核，但**不**把它们当证据。`degradations` 记录 `no_draft: ...`。这条路径保证"没写工作稿"也不会变成空目录 0 分，但答案质量取决于你是否真的读了材料。
