# 使用增益证据 — claim-evidence-verifier v3.0.0

本文件说明本 Skill 相对「无 Skill 基线」的结构性改善，并给出可复跑的对照方式。
所有数字均为**本包确定性模拟（`baseline_sim`）产出**，**不是官方跑分**，不得作为相对基础
Agent 的正式分数引用。这里只陈述「有无锚点 / locator / 逐字引文 / 契约回填 / 判定表」这类
**结构可判定**的差异，不对语义质量或真实案例表现打分。

## 1. 对照设置

| 项 | 无 Skill 基线 | 本 Skill |
|---|---|---|
| 输入 | 同一 `--input` 材料目录与同一 `claims-to-verify.json` | 同一输入 |
| 行为 | Agent 直接作答，无固定判定表、无 locator、无逐字引文闸门 | 先锚段（`文件#p序号`）再按判定表 R0..R6 逐子判断作答，引文写盘前逐字回查 |
| 产物 | 一段自由文本 | `result.json` + `evidence_cards.jsonl` + `verification_report.md` |
| 可复核性 | 无法回查答案出自哪一段 | 每条子判断带 `quote + locator + role + rule_id` |

## 2. 对照口径（本案定义）

这些指标只在**同输入、同材料版本、同工具权限**下比较，且由本包自身产物计算，可复跑：

- **支持度判定质量**：每条子判断须落四档之一，且 `supported`/`partially_supported` 必带一条通过
  `quote_unverified` 回查的引文；`contradicted` 必带 `supports:false` 的反证引文。口径见
  `references/verification-rules.md` 判定表。
- **逐字引文命中率** = `counts.verified_quotes / counts.evidence_items`。引文经 NFKC + 空白折叠 +
  CJK 去空白后须为该段原文子串，否则丢弃该证据并记 `degradations[quote_unverified]`。
- **人工回原文条数**：即未被定位到最小充分证据、需要人回到原文的论断数。本包给每个未决子判断
  写 `insufficient_evidence` + `search_scope`（扫了多少块、用了哪些查词）与 `pending_human`，
  把「需要人看的条数」显式列出，而不是藏在一句结论里。
- **契约回填**：`output_contract` 逐键回填真实值，无空值、无类型占位符、无 JSON `null`。

## 3. 样例实跑（确定性，非正式案例）

`examples/` 合成用例 3 条论断（1 支持 / 1 反驳 / 1 证据不足），实跑口径：

```
[run] claims=3 sub_claims=3 units=4 sources=1
[run] supported=1 partial=0 contradicted=1 insufficient=1 | quotes=2/2 | status=partial | self_check=True
```

即：3 条断言全部拿到四档判定（无遗漏），2 条有引文的证据 100% 通过逐字回查，第 3 条因材料无
对应实验记 `insufficient_evidence` 并写入 `uncertainties`，未编造引文。这演示的是**结构闭环**，
不代表真实案例的正确率。

## 4. 复跑方式

```bash
# 本 Skill：单命令（评测方入口）
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work

# 最小样例（应 exit 0）
python3 /skills/weekly-skill/scripts/main.py --input examples --output /tmp/out --work /tmp/work

# 本地评测模拟器（rich/boundary × single/agent 四组）
python scripts/eval_sim.py --pkg work/p4/v10/reading-07 \
  --case work/p4/synth_cases/reading-07/rich --mode single
```

四组组合结果记入 `SELFTEST.md`，均为 PASS。

## 5. 声明

- 本包纯标准库、离线、确定性，不含外部模型与网络依赖，判定路径不读时钟。
- 以上为结构可判定项的确定性对照，**非**官方榜单对照；未取得任何官方跑分，故不列分数。
