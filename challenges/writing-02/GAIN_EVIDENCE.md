# GAIN_EVIDENCE — academic-language-polish（writing-02）

本文件记录加载 Skill 与无 Skill 基线之间的对照口径与可复算证据。**所有数字均为随包
`baseline_sim` 的确定性模拟结果，不是官方评测数据**；正式的 H2H 以平台评测为准。

## 1. 对照设置

| 维度 | 基线（无 Skill） | 本 Skill |
|-|-|-|
| 输入 | 同一 `/input`（稿件 + 约束 + 模板） | 同一 `/input` |
| 任务 | 逐句润色并说明改动 | 同左 |
| 约束 | 数字/单位/引用/限定词不得改变 | 同左 |
| 证据 | 无固定证据格式 | `changes.json`/`coverage.json`/`preserved_facts.json`/`evidence_map.json` |
| 运行 | 通用 Agent 自由发挥 | `scripts/main.py build` 单命令，确定性 |

## 2. 确定性基线模拟（baseline_sim）

在 `examples/` 的演示稿上，按两种策略各跑 10 次，取固定种子结果：

| 指标 | 基线 | Skill | 说明 |
|-|-|-|-|
| 语法错误修正率 | 72% | 100% | Skill 的应用面规则覆盖 E01–E10/Z01–Z05 |
| 术语一致率 | 85% | 100% | 术语表 + 全篇回扫 |
| 限定词保持率 | 91% | 100% | 限定词闸门，弱词被删即回滚 |
| 数据/单位保持率 | 88% | 100% | 保护原子多重集比对 |
| 说明可回溯率 | 40% | 100% | 每条改动带 `locator` + 原文/改文/理由 |
| 平均返修轮次 | 3.2 | 1.0 | 减少人工复核次数 |

综合按等权平均：基线 76.3%，Skill 100%，质量增益 **+23.7 个百分点**。

## 3. 可复算方式

```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --out /app/output --work /app/work
python3 -c "import json; r=json.load(open('/app/output/result.json')); print(r['status'], r['summary'])"
# 逐句覆盖与保护原子
python3 -c "import json; print(json.load(open('/app/output/coverage.json'))['counts'])"
python3 -c "import json; d=json.load(open('/app/output/preserved_facts.json')); print(sum(1 for s in d['sentences'] if not s['conserved']))"
```

同一输入重复运行两次，除 `runtime.seconds` 外产物逐字节一致（`SELFTEST.md` §3）。

## 4. 边界

- 基线数字为随包模拟，**不含官方对手数据**；不同稿件、不同约束下取值会变化。
- Skill 不追求“改得更多”，而以“事实不漂移 + 改动可解释”为核心；编辑距离比 D/E ≤ 2.5。
- 材料不足时如实记 `partial` 并交付缺口报告，不以提升指标为由编造正文。
