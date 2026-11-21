# claim-evidence-verifier v3.0.0

把一份待核验的科研论断清单落到原文的逐字证据上，逐条给出四档支持度判定
（`supported` / `partially_supported` / `contradicted` / `insufficient_evidence`），
并把「论断 → 原子子判断 → 逐字引文 → 原文定位 → 判定 → 理由」整条链写成可复核的
`result.json`、证据卡片与人读报告。待核验论断默认是问题，不是既定事实。

## 安装

把本目录整体放到 `/skills/weekly-skill` 即可。入口脚本用 `__file__` 自定位，不依赖当前目录，
也不需要安装第三方包（仅 Python 3.9+ 标准库）。

## 用法

**单命令（评测方只需这一条，等价 `main.py run`）**

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

无参数运行也会走同一条全流程：发现输入 → 读契约 → 切块建索引 → 确定性推导 → 写 work 稿 →
渲染产物 → 写最终 `result.json`。纯标准库、不联网、判定路径不读时钟。

**agent-first 双路径（可选增强）**

```bash
# 1) 确定性全流程，先拿到候选与草稿模板
python3 /skills/weekly-skill/scripts/main.py run   --input /input --output /app/output --work /app/work
# 2) 查看候选段落，便于人工/Agent 判读
python3 /skills/weekly-skill/scripts/main.py show  --input /input --output /app/output --work /app/work
# 3) Agent 读 /app/work/draft.template.json，写 /app/work/draft.json
# 4) 合并草稿：逐条硬校验（判定词在闭集、unit_id 真实存在、quote 逐字命中），失败即退回规则判定
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
# 5) 再跑一次 run/build 产出最终结果
python3 /skills/weekly-skill/scripts/main.py run   --input /input --output /app/output --work /app/work
```

**最小可跑样例（应 exit 0，得到 1 支持 / 1 反驳 / 1 证据不足）**

```bash
python3 /skills/weekly-skill/scripts/main.py --input examples --output /tmp/out --work /tmp/work
```

## 产物（写入 `--output`）

| 文件 | 内容 |
|---|---|
| `result.json` | 契约键逐键回填（不改名、不漏键），含 `case_id`/`status`/`claims`/`evidence`/`sources`/`uncertainties`/`counts`/`self_check` 等 |
| `evidence_cards.jsonl` | 每子判断一行：claim_id/sub_id/text/verdict/rule/evidence[{quote,locator,role}]/rationale |
| `verification_report.md` | 人可读报告：逐条判定、引文、冲突、不确定性与限制 |

`--work` 下另有 `index.json`（输入索引）与 `draft.template.json`（可选的 Agent 草稿模板）。

`status` 取三值：`answered`（论断都有确定判定且无缺口）、`partial`（有弃权项或降级）、
`input_error`（无清单或材料完全不可读）。任意未捕获异常也会先写出合法 partial `result.json` 再退出。

## 限制

- 核验是词面 + 数值 + 方向的可复核匹配，不是同行评审，也不是语义蕴含模型。改写、同义替换、
  跨段推理、图表读数会让它偏保守或偏宽；判 `supported` 仍建议人工扫一眼 quote。
- 无文本层 PDF、只有题录的材料如实记为缺口（`insufficient_evidence` + `pending_human`），不猜内容。
- 不做 OCR、不联网、不调用外部模型；判定路径不含随机数或时钟，同一输入复跑结果一致。
- 越界请求（代写综述、整篇翻译、跑统计、跨文献元分析）应拒绝并说明范围。

## 维护

- 改判定规则必须同步 `references/verification-rules.md`（判定表 / 打分公式 / 字段字典 / draft schema）。
- 新增材料格式只改 `scripts/engine.py` 的 `load_source`，输出 schema 不变。
- 改动后至少跑：`main.py run --input examples`（exit 0）+ `scripts/eval_sim.py` 的
  rich/boundary × single/agent 四组组合，并把结果记入 `SELFTEST.md`。
- 方法论见 `references/expert_playbook.md`（执行前必读）；资源与命令声明见
  `environment/resources.yaml`；增益对照口径见 `GAIN_EVIDENCE.md`。
- 版本 3.0.0：契约键名冻结；新增规则走次版本，阈值与文案走修订号；纯标准库、离线、无外部模型。
