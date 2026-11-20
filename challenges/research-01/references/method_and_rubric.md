# 方法与评分映射（research-01）

## 1. 方法总览

本 Skill 把「深度研究」拆成五个可检查的中间态，每一步都有产物、有校验、可回退：

```
/input（case.json + task.md + 材料）
   │  init：发现输入、解析材料、逐句建 locator 索引、写合法 partial result.json
   ▼
index（材料清单 + 块/句定位 + 记录表 + output_contract 键表）
   │  show：打印带 locator 的逐字原文（Agent 阅读）
   ▼
draft.json（Agent 的判断：子问题、检索日志、发现卡、备忘录、未决）
   │  check：契约/逐字命中/定位/覆盖/引用/越级 —— 只判机械一致
   ▼
notebook 五章 + appendix/evidence-register.jsonl + result.json（build 无条件 finalize）
   │  selfcheck：重读产物、重算引文、二次渲染比对
   ▼
可复核交付（每条结论 → 卡片 → 证据 → 原文定位）
```

**分工原则**：脚本做确定性重活（解析、定位、去重、校验、渲染、契约回填、兜底）；判断留给 Agent（相关性、结论提炼、冲突处置、方案取舍、表述强度）。这条分工是本题「使用增益」与「可靠体验」两个维度的主要落点。

## 2. 定位与证据规则

1. 分段：空行与 Markdown 标题分块（`B1…`），块内按句末标点/换行断句（`S1…`），记录绝对字符偏移。
2. `locator = <相对路径>#B<块>.S<句> chars:<start>-<end>`；`case.json` 内联材料用 `case.json:sources[i]#…`。
3. 匹配三级：精确 → 忽略空白与引号差异 → 前缀探测（只给可疑位置，判 FIX）。
4. 命中但 locator 不符：按命中位置**回改**，记 `changes[kind=locator_repaired]`；这提高回链正确率，但不改变「引文必须逐字」的要求。
5. 不补造：材料没写的书目信息、数值、年份一律留空或写「材料未提供」。

## 3. 三维判据（本题「做对没做对」的三件事）

| 判据 | 落点 | 可核验方式 |
|---|---|---|
| 问题拆成哪些可独立检索的子问题 | `01-brief.md` 拆解表（对象/机制/方法/时间/比较/证据要求/依赖/层次） | 每个子问题可单独指派检索动作；`depends_on` 给出先后 |
| 每条结论能否回链到具体文献段落 | `finding-cards.jsonl` 的 `support[].quote + locator` | 脚本 `quote ∈ material` 命中；`appendix/evidence-register.jsonl` 逐条登记 |
| 整条路径能否被他人复跑 | `02-search-log.jsonl` | 按 `step_id` 重放 `action+target+params`，比对 `hits/status`；失败步保留 |

## 4. 评分维度 → 实现映射

| 维度（分值） | 评分点 | 本包落点 | 可核验证据 |
|---|---|---|---|
| 实际效果 40 | 完成度 15 | 五章 + 证据登记 + result.json 全字段；`contract_audit` 逐键 | `notebook/00-README.md` 计数表 |
| | 正确性 15 | 逐字命中校验、冲突卡 `contested`、越级表述拦截 | `quality.quotes_verified/quotes_failed`、`conflicts[]` |
| | 完整性 5 | 六类要点：拆解(1.3)、检索覆盖(1.5/2)、回链(3)、冲突(4 回链表 + 5)、综合(4)、空白(5 四型) | 章节齐全性检查（selfcheck） |
| | 可核验 5 | locator + 逐字 quote + 检索日志 + 复跑说明 | `evidence-register.jsonl`、`changes[]` |
| 使用增益 25 | 质量增益 15 | 拆解结构化、卡自足、冲突不隐藏、memo 经卡引用 | 相对「一次检索+综述式回答」的差异体现在字段而非篇幅 |
| | 效率增益 5 | 依赖排序 + 停止条件 + 材料内覆盖估计，减少重复查 | `01-brief.md` 1.4/1.5、`coverage.materials_read` |
| | 增益可验证 5 | 全部指标来自脚本重算（命中率、覆盖数、修复数），不写自评分 | `coverage{}`、`quality{}`、`selfcheck.json` |
| 创新 15 | 新增能力 5 | 发现卡为单位 + 反证内嵌 + memo 只引卡 | 第 3/4 章结构 |
| | 方法改进 5 | quote 命中→自动定位回改（R211）；冲突隐藏检测（C213）；越级强度闸门（C221/C222） | `check` 输出与 `changes[]` |
| | 创新证据 5 | 重复运行一致性（deterministic_render）+ 修复计数 | `selfcheck.json` |
| 可靠 10 | 调用易用 3 | 五命令、无参默认路径、`--help` | SKILL 第 2/3 节 |
| | 稳定 4 | 每命令重建索引、幂等渲染、异常不崩 | 冒烟用例 T1–T6 |
| | 异常处理 3 | 空输入/坏 JSON/缺工作稿/无文本层 PDF/权限不足，各有降级码 | SKILL 第 10 节 |
| 生态 10 | 文档 3 | SKILL + schema/错误码 + 本文件 | `references/` |
| | 复用 4 | 卡片 schema、拆解模板、检索日志格式、错误码表可迁移 | `references/draft_schema.md` |
| | 分享 3 | 方法总览与局限写清，可直接作为他人案例的运行手册 | 本文件第 1/5 节 |

## 5. 边界与已知限制

1. 只在 `/input` 材料内综合，不检索外部数据库；`coverage` 是材料内覆盖率，不是领域覆盖率，结论不外推到材料之外。
2. `pdf` 解析优先 `pdftotext`，缺失时退回内置 Flate 流解析，再退回 `read_method=none`；复杂版式/双栏/扫描件可能丢字，需回看 `show` 输出。
3. 冲突检测是启发式：脚本只提示「同子问题下方向相反的候选句」，是否构成冲突由 Agent 判定；提示未处置会记 `conflict_hint_unadjudicated`。
4. 兜底推导（无工作稿）产出的卡都是 `provisional/low` 且标 `auto_extracted`，只作线索，不能当作合格结果。
5. 不判断单篇论文的方法学质量（那是学术审查课题），只转录材料自述的设计与局限。

## 6. 复跑与对账

```bash
python3 scripts/main.py init     --input /input --work /app/work --output /app/output
python3 scripts/main.py show     --input /input --work /app/work --output /app/output
#   → 写 /app/work/draft.json
python3 scripts/main.py check    --input /input --work /app/work --output /app/output
python3 scripts/main.py build    --input /input --work /app/work --output /app/output
python3 scripts/main.py selfcheck --input /input --work /app/work --output /app/output
```

对账口径：`result.findings` 条数 = `finding-cards.jsonl` 行数；`result.evidence_summary.total` = `evidence-register.jsonl` 行数；`quality.quotes_verified + quotes_failed` = 证据条数；`coverage.sub_questions_covered` = 有卡覆盖的子问题数。任一不等 → `selfcheck` 判 FAIL。

## 7. 维护

| 变更 | 必做 |
|---|---|
| 新增/修改判据 | 先改 `references/draft_schema.md` 错误码表 → 改 `scripts/check.py` → 跑冒烟 T1–T6 |
| 改章节结构 | 改 `scripts/render.py` → 同步 SKILL 第 7 节与 `notebook/00-README.md` 导航 |
| 改输入发现 | 改 `scripts/parse.py` 的 `build_index` → 同步 SKILL 第 4 节与降级码 |
| 版本 | 三个文件同步 `version`，并在 `result.runtime.skill` 更新 |
