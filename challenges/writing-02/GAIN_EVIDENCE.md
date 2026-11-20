# 使用增益证据（claim-preserving-polish v9）

只记**可复算的机械证据**；数字都能用下面的命令重跑出来，语义质量仍由平台对照决定。

## 1. 对照协议（同源文 / 同约束 / 同验收口径）

| 项 | 基础 Agent（基线） | 本 Skill v9 |
|-|-|-|
| 输入 / 指令 / 输出契约 | 同一 `/input`、同一条 task_instruction、同一 `output_contract` | 同左 |
| 验收三项 | 数字·单位·引用·图表指向是否逐字保留；限定强度是否漂移；每处改动是否带类型+理由 | 同左，且由 `verification.json` 自动给出判定 |
| 判定路径 | 人工逐条核对成稿 | 脚本判定 + `human_review.md` 人工确认项 |

基线由平台自带，本包不代跑；本包保证的是**同一守卫下机械不变量可被第三方复算**。

## 2. 本包实际运行记录（eval_sim 本地复现）

    python scripts/eval_sim.py --pkg work/p4/v9/writing-02 --case work/p4/synth_cases/writing-02/rich     --mode single
    python scripts/eval_sim.py --pkg work/p4/v9/writing-02 --case work/p4/synth_cases/writing-02/rich     --mode agent
    python scripts/eval_sim.py --pkg work/p4/v9/writing-02 --case work/p4/synth_cases/writing-02/boundary --mode single
    python scripts/eval_sim.py --pkg work/p4/v9/writing-02 --case work/p4/synth_cases/writing-02/boundary --mode agent

| 组合 | 退出码 | result.json | 契约 | 原子守恒 | 覆盖 |
|-|-|-|-|-|-|
| rich / single | 0 | 合法，逐键回填 | 7/7 | 数字 43 → 43，`conserved=true` | 18/18 段 |
| rich / agent | 0 | 合法，逐键回填 | 7/7 | 数字 43 → 43，`conserved=true` | 18/18 段 |
| boundary / single | 0 | 合法，逐键回填 | 10/10 | 数字 40 → 40，`conserved=true` | 18/18 段 |
| boundary / agent | 0 | 合法，逐键回填 | 10/10 | 数字 40 → 40，`conserved=true` | 18/18 段 |

四个组合全部 PASS、无 warning。两个合成案例的材料以中文格式要求与任务说明为主，auto-draft 的机械规则
没有命中语义改写点，因此 `changed=0`——这正是守卫的预期：**没有高置信度改动就不硬改**。英文摘要类输入会命中
`In this paper, we → We`、`in order to → to`、`utilize → use`、`,x → , x`、`et al → et al.`，
每处都在 `changes.csv` 里带 `type` 与 `reason`。

## 3. 增益口径：把"减少返工"拆成可数条目

| 指标 | 基线（通用改写） | 本 Skill | 证据位置 |
|-|-|-|-|
| 数字/单位/引用被改坏 | 无自动拦截，需人工逐条核对 | 0（违规段落整段回退） | `verification.json` → `global_conservation` |
| 限定强度漂移 | 无自动拦截 | 0（除已声明 `hedge_override` 一律回退） | `verification.json` → `paragraph_checks[*].hedge_before/after` |
| 每处改动的可核对信息 | 通常只给整段改后文本 | 5 要素（locator/before/after/type/reason） | `changes.csv`、`edit_log.md` |
| 人工确认项 | 散落正文 | 汇总成清单并给选项 | `human_review.md`、`pending_human` |
| 契约字段完整性 | 常缺失或改名 | 逐键回填 + `_contract_report` 标记 | `result.json` |

## 4. 效率与边界

- 基线路径：读原文 → 逐段改写 → 人工回查数字/引用/强度 → 补写修改说明，至少 4 轮往返。
- 单命令路径：1 条 `all` 完成 `init→auto-draft→check→build→selfcheck`，机械核对由脚本完成，人工只看确认项。
- Agent 路径：`init → show → 写 draft.json → check → build → selfcheck`，写 draft 前即可看到每段原子清单与限定强度等级。
- 本证据只覆盖机械不变量（原子、强度、否定、契约、占位符），不声称语义质量优于基线；合成案例不等于官方固定案例；
  守卫是词表+正则，能证明"没改坏"，不能证明"改得最好"，因此转人工确认清单。
