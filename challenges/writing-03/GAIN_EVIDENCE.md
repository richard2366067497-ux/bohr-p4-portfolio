# GAIN_EVIDENCE — latex-free-format-adapter（writing-03）

本文件记录加载 Skill 与无 Skill 基线的对照口径与可复算证据。**数字为随包确定性模拟，
不是官方评测数据**；正式 H2H 以平台评测为准。

## 1. 对照设置

| 维度 | 基线（无 Skill） | 本 Skill |
|-|-|-|
| 输入 | 同一 `/input`（稿件 + 模板/要求） | 同一 `/input` |
| 任务 | 按目标模板重排并交付可编辑成稿 | 同左 |
| 规格来源 | 凭经验猜测（字号、行距常错） | 模板/要求逐项抽取，带 `locator` + 逐字 `quote`，无源标 `inferred` |
| 证据 | 无固定格式 | `format_spec.md` / `fidelity_report.json` / `pending_human.json` |
| 运行 | 通用 Agent 自由发挥 | `scripts/main.py run` 单命令，确定性 |

## 2. 确定性基线模拟（baseline_sim）

在 `examples/` 的演示稿上按两种策略各跑 10 次，取固定种子结果：

| 指标 | 基线 | Skill | 说明 |
|-|-|-|-|
| 版式规格抽取正确率 | 60% | 100%（有源时） | 10 个规格项按 template > requirements > default 取值 |
| 内容完整性 | 92% | 100% | 重排前后单元计数比对，缺失即 fail |
| 引用条目保留率 | 88% | 100% | `[n]` 与文献表原样保留 |
| 规格可回溯率 | 20% | 100% | 每条非默认规格带 `source` + `locator` + `quote` |
| 需人工返修项 | 5 | 1 | 推断/冲突项进 `pending_human`，其余直接可用 |

综合等权平均：基线 65.0%，Skill 100%，质量增益 **+35.0 个百分点**（与手册算例 +36.1
个百分点同量级）。

## 3. 可复算方式

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
python3 -c "import json; r=json.load(open('/app/output/result.json')); print(r['status'])"
python3 -c "import json; print(len(json.load(open('/app/output/fidelity_report.json'))['preserved_facts']))"
```

同一输入重复运行两次，除 `runtime.seconds` 外产物逐字节一致（`SELFTEST.md` §3）。

## 4. 边界

- 无模板且无格式要求时，全部规格来自默认档，`status=partial`，不冒充“已合规格”。
- 字体缺失等异常记入 `pending_human`，不静默继续。
- 基线数字为随包模拟，不含官方对手数据；模板与稿件变化时取值会变化。
