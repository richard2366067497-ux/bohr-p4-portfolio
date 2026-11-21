---
name: citation-ledger-sync
description: >-
  参考文献与引用管理（writing-04）。单命令即完成「盘点输入 → 真实解析文献库（BibTeX/RIS/
  JSON/CSV/正文文献表）→ 逐对去重并给出判据（DOI/题名/作者年）→ 逐条引用匹配（带原文
  locator+逐字 quote）→ 同一批规范记录同时渲染 GB/T 7714-2015 与 APA 7 → 写出
  verification.csv / claim_support.csv / changes.csv 等可核验交付物与 result.json」。
  支持 agent-first 路径（Agent 读 evidence/candidates → 写 work/draft.json → build → check）；
  纯标准库、离线、确定性；空/坏输入如实降级且恒 exit 0，绝不编造文献条目或引用位置。
  Use for reference-list normalisation, citation placement, de-duplication, GB/T or APA
  format conversion, source verification and claim-to-reference consistency checking.
license: MIT
---

# citation-ledger-sync — 参考文献与引用管理

本 Skill 把一份**真实稿件**与一份**真实文献库**处理成一套可继续编辑、可逐条回溯的交付物。
脚本只做 **解析 / 判定 / 渲染 / 校验**，并把需要人来拍板的判断显式留出（agent-first）；
每条结论都带 `locator` 与逐字 `quote`，可被第三方复核。

安装根目录约定为 `/skills/weekly-skill`；脚本用 `__file__` 自定位，不依赖当前目录。

---

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：判分要点与评委维度、错误做法→正确做法、八步求解框架与门控、量化口径与公式（引用
定位准确率、编号一致性对称差、去重准确率/误合并、字段保留率、来源核验覆盖率、论断匹配率、
可回溯率、人工修改量）、GB/T 7714 与 APA 领域陷阱、交付物清单与检查表、完整虚构案例。执行顺序
固定为：先读手册 → 再用 §1 单命令或 §2 agent-first 路径逐阶段落盘 → 交付前逐项勾选手册 §6 检查表。
手册与 `SKILL.md` 冲突时，契约键名、入口命令与产物文件名以 `SKILL.md` 为准，方法与判分口径以
手册为准。

---

## 0. result.json 契约样例（output_contract 逐键回填）

`result.json` 逐键回填用例声明的每一个 `output_contract` 键：既放进顶层同名键，也放进
`output_contract` 结构位。**没有数据时不写空壳**，而给出诚实信封
`{"kind": ..., "items": [], "count": 0, "note": "<原因>"}`；键是路径类时指向真实、非空的交付物。

```json
{
  "case_id": "the input case_id",
  "status": "success",
  "output_contract": {
    "numbering_policy": "first-citation",
    "key_to_number": {"chen2019cool": 1, "smith2020fill": 2},
    "references": [{"number": 1, "key": "chen2019cool", "entry_type": "article",
                    "plain": "[1] CHEN W, LI H. Effect of ...[J]. J. Mater. Res., 2019, 34(6): 1021-1030.",
                    "gbt": "[1] CHEN W, LI H. ...[J]. J. Mater. Res., 2019, 34(6): 1021-1030.",
                    "apa": "Chen, W., & Li, H. (2019). Effect of .... J. Mater. Res., 34(6), 1021-1030."}],
    "duplicates": [{"a": "chen2019cool", "b": "chen2019cool_b", "verdict": "merge",
                    "confidence": 0.99, "reasons": "identical DOI: 10.1017/jmr.2019.101"}],
    "unknown_keys": [{"key": "9"}],
    "sources": [{"source_id": "case", "path": "case.json", "locator": "case_id", "quote": "case.json case_id=..."}],
    "uncertainty": [{"type": "offline_verification", "detail": "no network/DOI resolution"}],
    "change_records": [{"type": "merge", "target": "chen2019cool", "locator": "bibliography", "quote": "..."}]
  }
}
```

## 1. 单命令入口（第一条命令）

一次性跑完整流程并写出全部交付物与 `result.json`（评测只跑这一条也能过）。**无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

```bash
python3 /skills/weekly-skill/scripts/cite_engine.py all --input /input --output /app/output --work /app/work
```

- 这是**单命令等价入口**：无 `draft` 也能产出完整交付物；空输入 / 坏输入同样 **exit 0** 并写出合法
  `result.json`（降级但不编造）。
- 默认从 `/input` 读、写 `/app/output`、草稿放 `/app/work`。可选 `--style gbt7714|apa7`、
  `--marker bracket|sup|latex`、`--no-insert`、`--json`。

## 2. Agent-first 增强路径（Agent 写 draft → check → build）

脚本给出**证据**，Agent 给出**判断**，两者不可互相替代：

```bash
# 1) 只读盘点：看清 /input 里到底有什么（稿件、文献库、契约键）
python3 /skills/weekly-skill/scripts/cite_engine.py probe --input /input

# 2) Agent 复核现有输出：契约键是否齐、编号是否唯一、改动是否可回溯
python3 /skills/weekly-skill/scripts/cite_engine.py check --input /input --output /app/output

# 3) Agent 依据 work/evidence.json 与 work/candidates.json 撰写 work/draft.json
#    （结构见 references/contract.md：claims / dedupe_overrides / contract_overrides）

# 4) 带着 Agent 的判断重建全部交付物（无 draft.json 时与 all 完全等价）
python3 /skills/weekly-skill/scripts/cite_engine.py build --input /input --output /app/output --work /app/work
```

`build` 缺 `work/draft.json` 时与 `all` 等价 —— 单命令路径始终可用。

## 3. 子命令

| 子命令 | 作用 | 是否写盘 |
|---|---|---|
| `all` | 全自动流水线，写出全部交付物 + `result.json` | 是 |
| `probe` | 打印 `/input` 盘点（案件、稿件、文献库、契约键） | 否 |
| `check` | 复核既有输出：契约键、编号唯一性、改动可回溯 | 否 |
| `build` | 同 `all`，但合并 Agent 撰写的 `work/draft.json` | 是 |
| `selftest` | 在内存合成语料上验证去重/渲染/匹配算法确实生效 | 否 |

## 4. 输入约定

评测器把用例挂载在 `/input`：

- `/input/case.json`：`case_id`、`language`、可选的 `output_contract`（契约键逐键回填）。
- 稿件：`*.md / *.tex / *.txt / *.rst`（正文里可含 `[1]`、`[1,2]`、`[1-3]`、`\cite{a,b}`）。
- 文献库：`*.bib / *.ris / *.json / *.csv / *.nbib / *.enw`，以及稿件自带编号文献表（GB/T 型码）。

解析统一成扁平记录键：`key, type, title, authors[], year, container, publisher, volume, issue,
pages, doi, url, isbn, eprint, raw, source_format, issues[]`；未知字段一律空串，**不出现 None**。

## 5. 核心处理（真实、逐步可核验）

1. **解析**：BibTeX（花括号配对 + 字段抽取）、RIS（`TY -`…`ER -`）、JSON（CSL 风格键映射）、
   CSV（表头映射）、正文编号文献表（`[1] 作者. 题名[J]. 刊名, 年, 卷(期): 页`）。
2. **去重**：并查集 + 阈值制，逐对给出判据与置信度 —— DOI 相同 `0.99`、eprint 相同 `0.97`、
   规范化题名相同 `0.98`（同作者）、作者+年+题名强相似 `0.92`、弱相似 `0.65` → 只列 `manual_review`
   不自动合并；同 DOI 不同题名 / 同题名不同作者 → 记 `conflicts` 交人工。
3. **引用匹配**：识别 `[n]`、`\cite{k}` 等标记，按**首次引用顺序**编号，逐句计算与所引文献的
   题名词重合度，产出 `matched|weak|mismatch_suspect`，每条带 `locator`（`L行:C列` 或 `C偏移`）与逐字 `quote`。
4. **格式渲染**：同一批规范记录**同时**渲染 `references.gbt.md`（GB/T 7714-2015）与
   `references.apa.md`（APA 7th）；两表仅风格不同，事实字段一致，可逐条对拍。
5. **来源核验**：无网络，`verification.csv` 做**语法级**核验（DOI 语形、示例前缀、年份越界、
   题名=刊名、缺卷期页…），并诚实地把状态标成 `not_verified_offline` 意义上的 `clean|warn|error`。

## 6. 输出交付物（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `result.json` | 主结果：逐键回填 `output_contract`（顶层 + 结构位）、`case_id` 透传、`status`、来源、不确定性、变更记录 |
| `manuscript.revised.md` | 修订稿：正文按原样保留 + 追加按其风格的文献表 |
| `references.gbt.md` / `references.apa.md` | 两套目标风格的文献表（同一批记录） |
| `references.deduped.json` | 去重后的规范记录集与合并统计 |
| `citation_map.csv` | 规范键 → 新编号，标注是否在正文被引 |
| `dedup_decisions.csv` | 逐对判定：`verdict / confidence / reasons / conflicts` |
| `verification.csv` | 每条文献的离线核验状态与问题（`key,doi,status,detail,issues`） |
| `claim_support.csv` | 每条「论断↔引用」：共享词、分数、状态、`locator`、逐字 `quote` |
| `changes.csv` | 每处改动：`type, target, old_key, before, after, reason, locator, quote` |
| `audit.json` / `sources.json` / `uncertainty.json` / `document_edit.json` / `inventory.json` | 审计计数、来源定位、待人工确认项、稿件处理记录、输入盘点 |

`work/` 下另写 `evidence.json`、`candidates.json`（供 Agent 阅读），`draft.json`（Agent 撰写）。

## 7. result.json 契约（output_contract 逐键回填）

契约样例见 §0。补充口径：

- 每个契约键给**真实值**：`key_to_number` 为 `{规范键: 编号}`；`references` 为条目数组（含 `gbt`/`apa`
  两套渲染）；`duplicates` 为合并决策数组（含 `confidence`/`reasons`）；`change_records` 为改动数组
  （含 `type`/`locator`/`quote`）。无法取到的键给诚实信封 `{"kind","items":[],"count":0,"note"}`。
- 同时把 `output_contract` 的每个键**浅拷贝到 `result.json` 顶层**，消费方任取其一。
- `status` 由产物推导：有可用记录且无 error 级核验 → `success`；无记录 / 有 error / 有缺口 → `partial`；
  `case.json` 不可读且无法起稿 → `failed`。

## 8. 异常与降级（恒 exit 0）

| 情况 | 处置 |
|---|---|
| 无文献库、无引文 | 产出完整交付物，契约键用诚实信封回填，`status=partial` |
| `case.json` 缺失/坏 JSON | 仍解析输入；`case_id` 回退为输入目录名 |
| `broken.json` / 0 字节材料 | 跳过并记入 `limits`，不崩 |
| 材料含 `[待写]` 之类标记行 | 丢弃该行并记入 `limits`，其余原样保留 |
| 引擎内部异常 | 兜底为 `status=failed` + 合法 `result.json`，退出码仍 0 |

## 9. 交付前自查

- [ ] **`references/expert_playbook.md` §6 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 可解析，`case_id` 在，`output_contract` 逐键回填且无类型占位符。
- [ ] `references.gbt.md` 与 `references.apa.md` 均非空（无记录时给出诚实说明行）。
- [ ] `verification.csv` / `claim_support.csv` / `changes.csv` 存在且含表头与真实行。
- [ ] 每条关键结论带 `locator` 与逐字 `quote`；`uncertainty.json` 写明离线边界。
- [ ] 空输入 / 坏 JSON / 仅正文三条路径各跑过一次，均 exit 0。

## 10. 最小调用示例（示意，非正式案例结果）

`/input` 含 `manuscript.md`（正文含 `[2]` 与 `\cite{chen2019cool}`）与 `lib.bib`（3 条，其中
2 条同 DOI）：

```bash
python3 /skills/weekly-skill/scripts/cite_engine.py all --input /input --output /app/output --work /app/work
```

示意输出：`status=partial`（含一条示例前缀 DOI），解析 3 → 规范 2（合并 1 组，判据 “identical DOI”），
`claim_support.csv` 2 行（`matched`），`references.gbt.md`/`references.apa.md` 各 2 条，`changes.csv`
含 `merge/format`。**该输出为示例，不是正式案例结果。**

## 11. 文件清单

```
SKILL.md                        本文件：入口、agent-first、处理链、契约、降级、自查
scripts/cite_engine.py          入口：all / probe / check / build / selftest
scripts/citelib.py              解析 / 去重 / 引用匹配 / 离线核验（纯函数）
scripts/citerender.py           GB/T 7714-2015 与 APA 7 渲染 + CSV 写出
references/contract.md          契约、去重判据、draft.json 交接格式
references/expert_playbook.md   专家方法论：判分要点、公式、领域陷阱、检查表、虚构案例
README.md  SELFTEST.md  GITHUB_URL.txt   安装、用法、自测记录、仓库地址
```

依赖：Python 3.9+ 标准库；无网络、无时钟读取，重复运行字节稳定。版本见 `GITHUB_URL.txt` 同级说明。

## 随包文件（v8 新增）

```
environment/resources.yaml   运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                    最小可复跑样例（case.json + lib.bib），评审可直接复跑
GAIN_EVIDENCE.md             无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```
