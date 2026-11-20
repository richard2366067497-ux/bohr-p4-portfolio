# GAIN_EVIDENCE — writing-09-results-discussion（使用增益证据）

只记**可复算的机械证据**：下表每个数字都能用第 4 节命令重跑出来，或从产物里直接读出。

## 1 对照协议（同材料 / 同约束 / 同验收口径）

| 项 | 基础 Agent（基线） | 本 Skill v9 |
|-|-|-|
| 输入 | 同一 `/input`（数据表、统计输出、文献片段） | 同左 |
| 指令 / 输出契约 | 同一 task_instruction、同一 `output_contract` | 同左 |
| 验收四项 | 读数与单位是否逐字保留；观察与解释是否分节；因果措辞是否被拦截；每条论断是否有来源 locator | 同左，且由 `metrics.json` + `--selftest` 自动给出判定 |
| 判定路径 | 人工逐条核对成稿 | 脚本判定 + `human_review` 人工确认项 |

基线由平台自带，本包不代跑；本包保证的是**同一守卫下，机械不变量可被第三方复算**。

## 2 本包实际运行记录

```bash
python3 scripts/main.py --input <case>/rich     --output /tmp/rich --work /tmp/wr
python3 scripts/main.py --input <case>/boundary --output /tmp/bnd  --work /tmp/wb
python3 scripts/main.py --selftest
```

| 组合 | 退出码 | status | 读数 | 产物 | 契约 | 备注 |
|-|-|-|-|-|-|-|
| rich | 0 | `success` | 12 | 8 件 | 5/5 键 | `metrics.json.pass=true`；数值与单位逐字保留 |
| boundary | 0 | `partial` | 0 | 8 件 | 5/5 键 | 无读数时只写缺口，坏文件入 `degradations` |
| selftest | 0 | — | — | — | — | `SELFTEST PASS (19 checks)` |

四个 eval_sim 组合（rich/boundary × single/agent）全 `PASS`，`failures=[]`、`warnings=[]`。

## 3 增益口径（把"减少返工"拆成可数条目）

| 指标 | 基线（通用改写） | 本 Skill | 证据位置 |
|-|-|-|-|
| 数值/单位被改坏 | 无自动拦截，人工逐条核对 | 单位保留率阈值 0.90，未达标即 `metrics.json.pass=false` | `metrics.json.baseline_checks[0]` |
| 论断可核验性 | 常只给改后文本 | 每条文献论断带 `source_id` + `locator` | `evidence_map.json` |
| 观察/解释混写 | 常见"结果段里解释原因" | 分节渲染 + `no_causal_wording` 自测项 | `manuscript.md`、`--selftest` |
| 因果措辞 | 无拦截 | `causal_phrases_in_deliverable == 0` | `metrics.json.baseline_checks[2]` |
| 材料解析 | 遇 PDF/位图即放弃 | PDF 文本层；位图记尺寸转人工；坏件降级 | `degradations`、`figure_inventory` |
| 预览 | 无 | `preview.svg`（离线、CJK 可读） | `outputs.preview.svg` 字节数 |
| 契约回填 | 常缺失或改名 | 顶层 + `output_contract` 逐键，`case_id` 透传 | `result.json` |
| 单命令可用性 | 无 | 1 条命令跑完，无材料也产出全套，退出码 0 | `SELFTEST.md §1` |

## 4 复现命令

```bash
python3 scripts/main.py --input work/p4/synth_cases/writing-09/rich     --output /tmp/rich --work /tmp/wr
python3 scripts/main.py --input work/p4/synth_cases/writing-09/boundary --output /tmp/bnd  --work /tmp/wb
python3 scripts/main.py --selftest
python scripts/eval_sim.py --pkg work/p4/v9/writing-09 --case work/p4/synth_cases/writing-09/rich     --mode single
python scripts/eval_sim.py --pkg work/p4/v9/writing-09 --case work/p4/synth_cases/writing-09/boundary --mode agent
```

## 5 效率与边界

- 基线路径：读材料 → 手抄读数 → 写结果段 → 写讨论段 → 人工回查单位/因果/来源，至少 4 轮往返。
- 单命令路径：1 条命令完成抽取、定稿、附表、预览、契约回填与指标对照。
- 本证据只覆盖机械不变量（读数/单位/分节/因果措辞/契约/占位符/解析降级），不声称文笔优于基线；
  合成案例不等于官方固定案例；守卫是词表+正则，能证明"没改坏"，不能证明"写得最好"。
