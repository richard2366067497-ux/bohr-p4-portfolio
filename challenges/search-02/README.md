# rq-driven-retrieval — 科研问题驱动的检索与筛选（search-02 v6）

把复合科研问题变成**可检索、可复核、可复现**的检索过程：问题拆解 → 查询规划（依赖/优先级/术语扩展）
→ 多轮候选筛选 → 证据台账 → 覆盖度 → 停止判断 → 报告与 `result.json`。核心约束：

- 子问题结构化（对象/机制/方法/比较/时间），每条带 `queries`、`depends_on`、`priority`、`required`。
- 每条候选记录保留 `locator` + 逐字 `quote` + 相关性依据；筛选结论可独立复核。
- 停止判断区分 `saturated / low_marginal_gain / needs_human`，不把“没检索到”写成“全球空白”。
- 契约逐键回填到 `result.json.output_contract` 与顶层同名键，`case_id` 原样透传；空内容给诚实非空结构。

## 安装

仅 Python 3.9+ 标准库，离线，无第三方依赖。放到 `/skills/weekly-skill/`：

```
/skills/weekly-skill/
  SKILL.md
  scripts/main.py
  references/retrieval-contract.md
  GITHUB_URL.txt  README.md  SELFTEST.md
```

## 用法

### 单命令（无草稿也产出完整产物；评测只跑这一条也能过）

```bash
python3 /skills/weekly-skill/scripts/main.py all \
  --input /input --output /app/output --work /app/work
```

### 五命令（Agent 深读，质量更高）

```bash
python3 scripts/main.py init      # 建索引 + partial result.json + draft 骨架
python3 scripts/main.py show      # 打印带 locator 的段落（--grep/--limit/--sources）
# Agent 读材料、写 /app/work/draft.json（子问题 + 筛选决策）
python3 scripts/main.py check     # 校验子问题/决策/rid 合法性
python3 scripts/main.py build     # 组装产物并定稿 result.json
python3 scripts/main.py selfcheck # 复检产物一致性
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|-|-|
| result.json | 主结果：顶层契约键 + `output_contract` 逐键回填、case_id、status、sources、子问题、候选、证据、覆盖度、停止判断、limits、uncertainty、change_records |
| subquestions.json | 结构化子问题（queries / depends_on / priority / required） |
| candidates.jsonl | 逐条候选（rid、locator、relevance、decision、basis、quote） |
| evidence_ledger.json | 证据台账（逐字 quote + locator + verified） |
| coverage.json | 每个子问题的覆盖状态与覆盖率 |
| stop_decision.json | 每个子问题的停止判据 |
| search_log.json | 查询数、轮次、零产出子问题、检索范围声明 |
| report.md | 人类可读报告 |

## 降级与边界（均 exit 0）

- 空输入 / 坏 JSON / 缺 `case.json`：写合法 `result.json`，`status=insufficient_evidence` 或 `input_error`，不补造文献。
- 无可解析文献：候选给带说明的诚实空结构，缺口写入 `degradations`。
- 不做全文精读/翻译/偏倚评估；结论限定在“所给快照内”，不宣称全局召回。

> 以上为本包能力说明；本地评测脚本的复现命令与结果见 `SELFTEST.md`。
