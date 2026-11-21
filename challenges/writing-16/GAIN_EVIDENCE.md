# 使用增益证据（source-faithful-retargeting v10）

只记**可复算的机械证据**，不写主观自评；下表数字都能用第 2 节命令重跑出来。

## 1. 对照协议（同源文 / 同约束 / 同验收口径）

| 项 | 基础 Agent（基线） | 本 Skill |
|-|-|-|
| 输入 / 指令 / 契约 | 同一 `/input`、同一 task_instruction、同一 `output_contract` | 同左 |
| 验收三项 | 数字·单位·样本·条件·图表引用是否逐字保留；论断强度是否被悄悄加减；每条事实是否有 locator | 同左，且由 `fidelity_summary` + `selfcheck` 自动判定 |
| 判定路径 | 人工逐条核对成稿 | 脚本判定 + `pending_human` 人工确认项 |

基线由平台自带，本包不代跑；本包保证的是**同一守卫下机械不变量可被第三方复算**。

## 2. 本包实际运行记录（eval_sim 本地复现）

    python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/rich     --mode single
    python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/rich     --mode agent
    python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/boundary --mode single
    python scripts/eval_sim.py --pkg work/p4/v10/writing-16 --case work/p4/synth_cases/writing-16/boundary --mode agent

| 组合 | 退出码 | result.json | 契约 | 产物 | 备注 |
|-|-|-|-|-|-|
| rich / single | 0 | 合法，顶层+嵌套逐键回填 | 3/3（`dropped`/`retained`/`errors`） | 5 件齐全 | 无 placeholder |
| rich / agent | 0 | 合法 | 3/3 | 5 件齐全 | 空工作稿→兜底稿，仍产出全产物 |
| boundary / single | 0 | 合法 | 9/9（SKILL.md 骨架键） | 5 件齐全 | 坏 JSON / 二进制材料按降级处理 |
| boundary / agent | 0 | 合法 | 9/9 | 5 件齐全 | `degradations` 记 broken.json / notes.txt |

四组合 `status=PASS`、`failures=[]`、`warnings=[]`。合成案例以中文格式要求与任务说明为主，auto/
兜底路径不硬改成稿，因此 `changed=0`——这正是守卫的预期：**没有工作稿就不假装完成受众改写**，
但契约、产物与降级记录必须完整。

## 3. 增益口径：把“减少返工”拆成可数条目

| 指标 | 基线（通用改写） | 本 Skill | 证据位置 |
|-|-|-|-|
| 数字/单位/引文被改坏 | 无自动拦截，需人工逐条核对 | 0（`check` 报 `numeric_drift`，`build` 记漂移数） | `result.json.fidelity_summary.numeric_drift` |
| 引文可核验性 | 通常只给改后文本 | 逐字命中率 `quote_hit/quote_total` | `fidelity_summary` |
| 必保留项落点 | 不追踪 | `retained_in_body/retained_total` | `retained_facts.json` |
| 每处改动的可核对信息 | 常缺 | 5 要素（locator/原文/改文/动作/理由） | `diff_map.md`、`change_log` |
| 契约字段完整性 | 常缺失或改名 | 顶层+嵌套逐键回填，`errors` 用 `{count,items,note}` 给真实计数 | `result.json`、`contract_fill` |
| 单命令可用性 | 无 | `all`：无工作稿也产出全部交付物，退出码 0 | `SKILL.md §0.1` |

## 4. 效率与边界

- 基线路径：读材料 → 逐段改写 → 人工回查数字/引文/强度 → 补写对照说明，至少 4 轮往返。
- 单命令路径：1 条 `all`（init→build→selfcheck）完成索引、定稿、附表与契约回填。
- Agent 路径：`init → show → 写 draft.json → check → build → selfcheck`，写 draft 前即可见候选必保留项。
- 本证据只覆盖机械不变量（数字/单位/引文/保留覆盖/强度/契约/占位符），不声称文笔优于基线；
  合成案例不等于官方固定案例；守卫是词表+正则，能证明“没改坏”，不能证明“改得最好”，故转人工确认清单。
