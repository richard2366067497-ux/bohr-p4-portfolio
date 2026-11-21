# writing-05-evidence — 文献证据驱动写作（v10）

把「要写的内容」与「能支撑它的材料」分开处理：输出的每一条实质论断都能被指认——依据在哪一段
（`locator`）、依据有多强（高/中/低/不足）、哪里还不确定。运行完全**离线、纯 Python 标准库、确定性**。

## 安装

无需第三方依赖（Python 3.9+ 标准库）。把本目录放到 `/skills/weekly-skill` 即可：

```
/skills/weekly-skill/
  SKILL.md
  scripts/{main.py,kit.py}
  references/expert_playbook.md  # 专家参考手册：判分要点、六步法、量化口径、专家检查表（执行前必读）
  references/method.md      # 方法 + 产物字段约定 + 默认契约
  examples/                 # 可复跑样例
  environment/resources.yaml
  README.md  SELFTEST.md  GITHUB_URL.txt  GAIN_EVIDENCE.md
```

## 单命令入口（评测一次跑完）

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

无草稿也能产出**全部交付物 + result.json**；空输入 / 坏输入同样 **exit 0**（降级但不编造）。
退出码恒为 0（仅 argparse 用法错误返回 2）。

## Agent 增强路径（可选，质量更高）

Agent 先在 `work/draft.json` 写明对确定性结果的**证据覆盖**，再重跑；不写则与单命令完全等价：

```bash
# 1) 先跑一次，阅读 /app/output/evidence_table.json 与 claims.json
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
# 2) Agent 依据材料改写 work/draft.json（示意）：
#    {"evidence_overrides": {"C001": {"source_id": "D02", "strength": "中"}}}
# 3) 带着判断重建（--draft 或自动读取 $WORK/draft.json / $INPUT/draft.json）
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work --draft /app/work/draft.json
```

被采纳的覆盖会记入 `result.json` 的 `change_records` / `change_log` 与 `uncertainties`，可逐条回溯。

## 产物（写入 `--output`）

`evidence_driven_draft.md`、`claims.json`、`evidence_table.json`、`evidence_strength.md`、
`reference_check.md`、`uncertainty_notes.md`、`human_review.json`、`verification.json`、`result.json`。

## 契约回填

`result.json` 顶层与 `output_contract` 同时逐键回填用例的 `output_contract`：`case_id` 透传输入；
`deliverable` 指向真实主稿文件；`preserved_facts` / `evidence_map` / `change_log` 为真实取值。
`status` 取 `success` / `partial` / `failed`，无占位符。

## 限制

- 离线运行，**不联网核验文献真实性**；PDF 正文需外部解析器（仅登记文件名与缺口）。
- 数字与单位按材料原样保留，不做换算。
- 强度为启发式评分（研究设计 + 样本量 + 独立来源 + 冲突惩罚），非统计学显著性检验。

## 维护与版本

- 版本 1.2.0（v10）：随包 `references/expert_playbook.md` 专家参考手册（判分要点、六步法、量化口径、专家检查表），SKILL 规定执行前必读并按检查表产出。
- 版本 1.1.0（v9）：新增 Agent `evidence_overrides` 路径与随包生态（examples / resources / 增益证据）。
- 改动主流程后请跑 `scripts/eval_sim.py`（rich/boundary × single/agent）与样例复跑，见 `SELFTEST.md`。
