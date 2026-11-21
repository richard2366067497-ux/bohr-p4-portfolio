# README — search-08 · 筛选去重与冲突仲裁闭环审计

## 这是什么

给定「研究问题 + 纳排标准 + 检索协议 + 标题摘要题录快照（可含双标注意见）」，把一次文献筛选
做成**可独立复核**的固化产物：去重合并、标题摘要筛选、双人独立判断与标准仲裁、计数闭合与审计日志。

执行前先读 `references/expert_playbook.md`，产出后按其 §7 检查表逐项自检。

核心约束：

- **计数闭合**：输入 − 合并 = 去重后 = 纳入 + 排除 + 待裁决，每步条目数机械校验；
- 每条判断带**预定义理由码**与标题/摘要**真实片段 + locator**，排除理由不得只写「不相关」；
- 去重保留合并依据（`same_doi` / `preprint_of_same_study` / `title_author_year_match`），DOI 不同不合并；
- 冲突用**标准仲裁**并记录依据，不用多数投票；模拟双标注如实标注，不声称真实人类；
- 标准版本哈希锁定，只对给定快照负责，不声称全局召回。

## 快速开始

```bash
python3 scripts/main.py all --input /input --output /app/output --work /app/work
```

`/app/output` 会得到 `result.json` + 十一类中间产物。没有 `draft.json` 也能跑完，`exit 0`。

自带 fixture 复跑：

```bash
python3 scripts/main.py all --input examples --output /tmp/out --work /tmp/work
```

## 三种用法

1. **单命令**（推荐，评测入口）：`all`。
2. **人机协作**：`init` → 看 `show` 输出并可选写 `work/draft.json` → `check` → `build`。
3. **例行复检 / 对照**：`selfcheck` 重新核对产物与契约回填；`compare` 产出与朴素基线的结构对照。

## 判定口径

- 去重：DOI 精确 → `title_norm + first_author + year`；含预印本标记归 `preprint_of_same_study`，其余 `title_author_year_match`。
- 筛选顺序：`EX-LANG` → `EX-DES` → `EX-DATE` → `EX-POP` → `P-ABS` → `IN-INT` → 待全文兜底。
- 理由码：`config/reason_codes.json` 为回退；材料自带码表优先，来源写入 `criteria.json.code_source`。
- 指标：去重合并率、理由码覆盖率、证据片段覆盖率、双人一致率、Cohen's kappa、计数闭合、审计链完整率。
- 状态：闭合且无待裁决且有题录 → `ok`；有待裁决 / 未闭合 → `partial`；无题录 → `insufficient_evidence`；空输入 → `input_error`。

## 目录

```
scripts/main.py               命令入口（all/init/show/check/build/selfcheck/compare）+ 产物渲染
scripts/core.py               材料解析、去重、筛选、仲裁、计数闭合与契约值
references/expert_playbook.md 专家方法论：框架/口径/陷阱/检查表（执行前必读）
config/reason_codes.json      默认理由码字典（材料自带字典优先）
SKILL.md                      契约、单命令、分步命令、异常处置、自查、top_fix 映射
SELFTEST.md                   本地评测记录（4 组 eval_sim 全 PASS）
GAIN_EVIDENCE.md              与朴素基线的对照（诚实声明：基线为确定性模拟）
environment/resources.yaml    运行时契约
examples/                     自包含 smoke fixture（case.json + materials/records.json）
```

## 依赖与边界

纯标准库、离线、无第三方包、确定性（时间戳不参与判等）。空 `/input`、坏 JSON、材料无题录时
仍写合法 `result.json`（`status=input_error` / `insufficient_evidence`）并 `exit 0`。
