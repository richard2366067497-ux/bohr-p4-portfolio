---
name: screening-dedup-conflict-auditor
description: 给定研究问题、纳排标准与标题摘要题录快照，做去重合并、标题摘要筛选、双人独立判断与标准仲裁，保证每步条目数首尾闭合、每条判断带理由码与真实证据片段、每次仲裁留依据，最后输出可独立复核的筛选闭环（result.json + 筛选表 + 去重/冲突/审计产物）。
---

# screening-dedup-conflict-auditor · 筛选去重与冲突仲裁闭环审计

给定材料（研究问题 + 纳排标准 + 检索协议 + 题录快照，可能含双标注意见），把
「纳排标准 → 检索协议 → 去重 → 标题摘要筛选 → 双人判断与冲突仲裁 → 审计与计数闭合 → 结构化输出」
做成**可被第三人独立复跑**的固化产物：筛选表、去重报告、冲突报告、审计日志、计数闭合表。

关键约束：

- **计数闭合**：输入条数 − 合并对数 = 去重后条数，且 去重后条数 = 纳入 + 排除 + 待裁决；
  每步输入/输出条目数用脚本机械校验；
- 每条纳入/排除必须带**预定义理由码**与标题/摘要中的**真实片段**，排除理由不得只写「不相关」；
- 去重保留**合并依据**（`same_doi` / `preprint_of_same_study` / `title_author_year_match`），
  DOI 不同不合并；
- 冲突用**标准仲裁**（记录分歧点、类型、依据），不用多数投票；模拟双标注如实标注，不声称真实人类；
- 标准版本哈希锁定，所有判断记录 `standard_version`；只对给定快照负责，不声称全局召回。

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 求解框架与门控** 推进——读取输入 → 定义纳排标准 → 记录检索协议 → 去重 →
  标题摘要筛选 → 双人判断与冲突仲裁 → 审计与计数闭合 → 结构化输出；前一步冻结产物未完成不进入下一步。
- **口径**：按其 **§3 量化口径** 计算去重合并率、去重后条数、理由码覆盖率、证据片段覆盖率、
  双人一致率与 Cohen's kappa、计数闭合、审计链完整率；数字都要能在中间产物里查到。
- **陷阱**：按其 **§4 领域知识清单与陷阱** 逐条排雷（错误做法 → 正确做法）；不误合并不同研究、
  不把预印本当独立研究、不因摘要为空直接排除、不用多数投票仲裁、不伪造人类审查。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为完整成功。

## 契约（output_contract）

`case.json` 给出 `output_contract` 时以它为准；否则用下列内建键（边界用例同样输出这套键）。
每个键在 `result.json` 顶层与嵌套 `output_contract` 对象里各回填一次，两处完全一致：

```json
{
  "output_contract": {
    "case_id": "string",
    "deliverable": "path",
    "evidence_map": "array",
    "change_log": "array",
    "coverage": "object",
    "status": "string"
  }
}
```

## 单命令（one-shot，评测入口）

- 一条命令走完：扫描材料 → 定义并冻结纳排标准版本 → 记录检索协议 → 去重（含预印本/正式版合并）→
  逐条标题摘要筛选 → 双人独立判断与标准仲裁 → 计数闭合校验 → 落盘。
- **无 `draft.json` 也照常跑完**：仍产出完整契约、全部交付物与 `result.json`，`exit 0`。
- 不访问任何外部数据库；`result.json.limits` 写明「no live database search / snapshot only」，
  并把模拟双标注如实标注为模拟。

## 分步命令（agent 增强路径）

```bash
python3 scripts/main.py init      --input /input --output /app/output --work /app/work
python3 scripts/main.py show      --input /input --output /app/output --work /app/work
python3 scripts/main.py check     --input /input --output /app/output --work /app/work
python3 scripts/main.py build     --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output --work /app/work
python3 scripts/main.py compare   --input /input --output /app/output --work /app/work
```

- `init` 建索引、冻结标准版本、写 `work/draft.skeleton.json` 与 `result.json`。
- `show` 打印任务、来源解析状态与逐条最终判定（含理由码与 locator），便于人工写 `work/draft.json`。
- `check` 机械校验：计数闭合、理由码覆盖率、证据覆盖率、状态枚举；报告写入 `work/check_report.json`，永远 `exit 0`。
- `build` 用 `work/draft.json`（若存在）+ 规则抽取正式成稿；`all` = `build` + 增益报告。
- `compare` 单独产出与朴素基线的结构对照。

## 交付物（每次运行写入 --output）

| 文件 | 内容 |
|-|-|
| `result.json` | 顶层 + 嵌套 `output_contract` 契约回填、`coverage`、`counts`（计数闭合）、`uncertainties`、`limits` |
| `screening_table.csv` | 筛选表：record_id × decision × reason_code × locator × excerpt × reviewer × standard_version |
| `dedup_report.json` | 去重报告：输入/输出条数、合并对与依据（`same_doi` / `preprint_of_same_study` / `title_author_year_match`） |
| `conflict_report.json` | 冲突报告：分歧点、类型、双方标签、仲裁结论与依据（非多数投票） |
| `audit_log.jsonl` | 审计日志：每步输入输出条目数、操作人、标准版本、判定依据 |
| `criteria.json` | 纳排标准（标准版本哈希、理由码字典、码表来源、时间窗） |
| `search_protocol.json` | 检索协议：数据库、字段、时间范围、语种、记录数、标准版本 |
| `count_closure.md` | 计数闭合表与指标表（恒等式机械校验） |
| `self_check.json` | 机械自检结论（含计数闭合、覆盖率、标准版本） |
| `gain_report.md` / `gain_report.json` | 与朴素基线的结构对照（诚实声明：基线为确定性模拟） |
| `run_log.txt` | 本次运行的简短摘要 |

## 判定口径

- 去重：先按 DOI 精确合并（`same_doi`）；否则按 `title_norm + first_author + year` 合并，
  含预印本标记的归 `preprint_of_same_study`，其余归 `title_author_year_match`；DOI 不同不合并。
- 筛选顺序：语言限制（`EX-LANG`）→ 设计不合格（`EX-DES`）→ 时间窗（`EX-DATE`）→
  非人类/非临床人群（`EX-POP`）→ 摘要为空（`P-ABS`）→ 干预/暴露信号（`IN-INT`）→ 兜底待全文。
- 理由码：随包 `config/reason_codes.json` 为默认回退；材料自带码表优先，来源写入 `criteria.json.code_source`。
- 冲突仲裁：评审 A 与评审 B 不一致时，由标准逐条判定（记录分歧类型、双方标签、依据与方法
  `standard_based_arbitration_not_majority_vote`），不采用多数投票。
- 指标：去重合并率、理由码覆盖率、证据片段覆盖率、双人一致率、Cohen's kappa、计数闭合、审计链完整率。
- 状态：计数闭合且无待裁决且有题录 → `ok`；有待裁决 / 未闭合 → `partial`；无题录 → `insufficient_evidence`；空输入 → `input_error`。

## 异常与降级（可靠体验）

| 情形 | 处置 |
|-|-|
| 材料无题录文件 | 如实 `insufficient_evidence`，不伪造筛选表内容；`degradations` 写明原因 |
| DOI 缺失 | 用 `title_norm + first_author + year` 生成去重键，不丢弃记录 |
| 摘要为空 | 标题相关则标记待全文（`P-ABS`），标题不相关才排除并记录 |
| 预印本 / 多来源副本 | 合并并记 `preprint_of_same_study` / `same_doi`，保留合并依据 |
| 评审分歧 | 标准仲裁并记录依据，不用多数投票 |
| 标准版本冲突 | 以材料声明为准，记录 `standard_version` 并写入 `uncertainties` |
| 坏 JSON / 空文件 / 乱码 | 登记 `degradations`，仍写合法 `result.json`，`exit 0` |

## 交付前自查（逐项通过）

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键回填、无空壳值。
- [ ] 计数闭合：输入 − 合并 = 去重后 = 纳入 + 排除 + 待裁决，恒等式成立。
- [ ] 每条纳入/排除带预定义理由码与标题/摘要真实片段 + locator。
- [ ] 去重保留合并依据；DOI 不同不合并；预印本与正式版已合并。
- [ ] 冲突有仲裁结论与依据，未用多数投票；模拟双标注已标注为模拟。
- [ ] 标准版本哈希锁定，所有判断记录 `standard_version`。
- [ ] 空输入 / 坏 JSON / 无题录三条路径各跑过一次，均 `exit 0` 且有缺口说明。
- [ ] 两次运行结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的 23 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为完整成功。

## top_fix → 实现

| top_fix | 实现 |
|-|-|
| 计数必须闭合 | `build_payload` 计算 `closure.closed`；`count_closure.md` 与 `check` 机械校验 |
| 理由码 + 证据片段 | `screen_one` 产出理由码与 locator/片段；`screening_table.csv` 逐行记录 |
| 去重依据可复核 | `dedup` 保留每对 kept/merged 与 `basis`；`dedup_report.json` |
| 冲突不用多数投票 | `adjudicate` 标准仲裁 + `conflict_report.json`（含 method 与 basis） |
| 审计链完整 | `audit_log.jsonl` 记录每步条目数、操作人、标准版本 |
| 标准版本管理 | `criteria-<sha12>` 锁定；每行判断带 `standard_version` |
| GITHUB_URL 校验 | `GITHUB_URL.txt` 指向 `challenges/search-08`，与作品目录一致 |
