---
name: writing-05-evidence
description: Literature-evidence driven academic writing. Turns a draft (or a topic) plus source materials into a located claim list, a graded evidence table, an editable evidence-driven draft, and a reviewable result.json. Use when an academic text must be produced or revised so that every substantive sentence can be traced to a located source snippet of a known strength.
version: 1.1.0
---

# 文献证据驱动写作 / Literature-evidence driven writing

本 Skill 把"要写的内容"与"能支撑它的材料"分开处理。它不追求多写，而是让写出的每一条实质论断都能被指认：依据在哪一段、依据有多强、哪里还不确定。运行完全离线，只用 Python 标准库。

## 单命令入口（single command，一次跑完）

下面这一条命令就是完整流程：读取材料 → 切分论断 → 匹配来源 → 判定强度 → 生成成稿与证据产物 → 写出 result.json。**不需要任何草稿或前置步骤**，缺材料时也会退出码 0 并写出合法的降级结果。

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

等价的绝对路径写法（由平台安装到搜索路径时）：

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
```

可选参数：`--case /input/case.json`、`--draft FILE`、`--lang zh|en`（默认按材料语言自动判断）、`--version`。

### Agent 增强路径（可选，质量更高）

脚本给出**证据**，Agent 给出**判断**，两者不可互相替代：

1. 先跑一次单命令，阅读 `/app/output/evidence_table.json`、`claims.json` 与 `evidence_strength.md`；
2. Agent 依据材料撰写 `/app/work/draft.json`（结构：`{"evidence_overrides": {"C001": {"source_id": "D02", "locator": "...", "strength": "中"}}}`）；脚本自动读取 `$WORK/draft.json` 或 `$INPUT/draft.json`，也可用 `--draft FILE` 指定；
3. 重跑单命令。被采纳的覆盖写入 `result.json` 的 `change_records` / `change_log` 与 `uncertainties`，逐条可回溯。

**无 draft 时单命令与带 draft 路径等价**（覆盖为空即为确定性结果）。


### 最小调用示例（示意，非正式案例结果）

输入目录示意（`/input`）：

```text
/input/case.json            # { "case_id": "...", "language": "zh", "output_contract": {...} }
/input/materials/draft.md   # 待写/待改的稿件
/input/materials/refs.txt   # 可引用的来源材料
```

调用：`python3 scripts/main.py --input /input --output /app/output --work /app/work`

示意输出（`/app/output`）：`evidence_driven_draft.md`、`claims.json`、`evidence_table.json`、`evidence_strength.md`、`reference_check.md`、`uncertainty_notes.md`、`human_review.json`、`verification.json`、`diff_report.md`、`result.json`。以上为接口示意，正式结果由平台用固定案例生成。

## 产物清单

| 文件 | 内容 |
|---|---|
| `evidence_driven_draft.md` | 主成稿：每条论断带 [n] 引用标记与限定语，附证据边界 |
| `claims.json` | 论断清单：claim_id、正文、类型、定位 |
| `evidence_table.json` | 证据表：claim_id / source_id / locator / quote / strength / support_scope / conflicts / rationale / verified |
| `evidence_strength.md` | 逐条强度与理由 |
| `reference_check.md` | 著录完整度核验（离线，只做一致性） |
| `uncertainty_notes.md` | 不确定性说明与限定语口径 |
| `human_review.json` | 需要人工确认的项 |
| `verification.json` | 自检指标（引用可解析、引文命中、`verified_quote_rate`、`claim_coverage`） |
| `diff_report.md` | 期望 vs 实际：契约回填表、覆盖指标、剩余缺口 |
| `result.json` | 结构化结果，含 output_contract 回填 |

## result.json 字段

`result.json` 顶层字段固定包含：`case_id`、`status`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`outputs`、`sources`、`uncertainties`、`change_records`、`limits`、`human_review`、`degradations`、`errors`、`runtime`，并有一个 `output_contract` 对象**逐键回填**输入 `output_contract` 的全部键。

示意取值：`case_id` 透传输入；`deliverable` 指向本次真实产出的主稿文件；`preserved_facts` 为材料中保留的数字与单位；`evidence_map` 为每条论断到来源定位与强度的映射；`change_log` 为本次改动动作。`output_contract` 内与顶层同名的键取相同值。

`status` 取 `success` / `partial` / `failed`。输入契约里给的键会被原样保留在 `output_contract` 中；只给描述、只给空值或指向文件的键，会被回填成真实可核的值或真实存在的文件。`case_id` 始终透传输入值。

## 论断切分与来源匹配口径

1. **论断单元**：有草稿时按句切分草稿；无草稿时按与任务说明的相似度从材料里取若干实质句。
2. **来源匹配**：对每条论断，在**非本文件**的材料单元里做词元余弦相似度匹配（含数字加权），取最高 3 条；低于阈值的记"未匹配"。
3. **定位**：每段来源标注 `路径 [Bn.Sm] chars:a-b`，便于独立回查。
4. **强度**：由研究设计、样本量、独立来源数、冲突惩罚四因子合成，分 `高/中/低/不足`。
5. **过度推断**：出现因果词（causes / leads to / 导致）但强度不足时，改写为相关性表述，并记入 `change_log`。

## 异常处理

- 输入目录不存在或无可读材料：退出码 0，`status=failed`，仍写出带 `limits` 的合法 `result.json`。
- 文件不可解析（坏 JSON / 空文件 / 二进制）：记录到 `degradations`，不阻断流程。
- 输出目录不可写：回退到当前目录下的 `output/`。

## 适用条件与限制

- 适用：需要"论断—来源—强度"三段可核的学术写作、改稿、引用与不确定性表达。
- 限制：离线运行，**不联网核验文献真实性**；PDF 正文需要外部解析器，仅登记文件名与缺口；数字与单位按材料原样保留，不做换算。

更细的方法、产物字段约定与默认契约见 `references/method.md`。

## 方法与创新点（边界说明）

基础 Agent 在"写学术文本"时不做区分地生成连贯段落，本 Skill 相对它新增了四件事，且都能被运行产物核验：

1. **句子级论断切分**：把成稿拆成 `claims.json` 里带 `claim_id` 的论断单元（有草稿按句；无草稿按与任务说明的相似度取实质句），使"哪一句需要证据"成为显式对象，而非隐含在段落里。
2. **定位式来源匹配**：每条论断与非本文件的材料单元做词元余弦相似度匹配（数字命中加权），命中结果写成 `路径 [Bn.Sm] chars:a-b` 的 `locator` 与逐字 `quote`，可独立回查。
3. **四因子证据强度分级**：`设计 × 1.05 + 样本量 + 独立来源加分 − 冲突惩罚` → `高/中/低/不足`，冲突证据**保留不合并**；强度不足而使用因果措辞的句子被降级为相关性表述并记入 `change_log`。
4. **可量化的自证**：`result.json.metrics` 与 `diff_report.md` 给出 `verified_quote_rate`、`claim_coverage`、`pending_human_count`、`overclaim_flags`，把"增益"变成可复算的数字。

**边界（诚实声明）**：离线，**不联网核验文献真实性**，不识别撤稿/二手转引；PDF/扫描件正文需外部解析器，此处只登记文件名与缺口（写入 `degradations`）；不做单位换算；强度是启发式分级，不是统计学显著性检验。最小失败类型：材料为空或全部不可解析时，`claims=0` → `status=failed`，仍写出合法 `result.json`（见 `examples/` 与 `SELFTEST.md`）。

公开作品链接见 `GITHUB_URL.txt`（仓库公开，可直接访问）。

## 随包文件（v9 新增）

```
environment/resources.yaml   运行环境、入口命令、输入/输出路径、预算与依赖声明（离线、纯标准库）
examples/                     最小可复跑样例（case.json + materials/{manuscript.md,refs.md}），评审可直接复跑
GAIN_EVIDENCE.md             无 Skill 基线对照与使用增益证据（含确定性 baseline_sim 说明，非官方对照）
```

依赖：Python 3.9+ 标准库；无网络、无时钟读取，重复运行字节稳定。版本与自测见 `README.md` / `SELFTEST.md`。

