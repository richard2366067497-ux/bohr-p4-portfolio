---
name: search-coverage-gap-auditor
description: 冻结已知相关参考集，逐条比对检索快照，算出可复算的查全率与漏检率，把每条漏检归因到具体查询式/字段/时间窗/来源，做补检并量化边际收益，最后输出可独立复核的覆盖审计闭环（result.json + 七类中间产物）。
---

# search-coverage-gap-auditor · 检索覆盖与漏检闭环审计

给定材料（研究问题 + 综述/指南/专家清单 + 检索结果与查询日志），把「构建参考集 → 算覆盖率 →
列漏检 → 做补检 → 闭环复核」做成**可被第三人独立复跑**的固化产物：冻结参考集、命中矩阵、
漏检归因表、补检计划与边际收益、复算审计轨迹。

关键约束：

- 覆盖率**分母是冻结的参考集有效条目**，不是检索结果；分子是逐条比对后的命中数；
- 每条漏检必须指认到具体 `query_id` / 字段 / 时间窗 / 来源，并附 locator 与逐字引用；
- 撤稿 / 重复 / 无全文 / 标识冲突的记录单独标注，理由写进台账，不静默计入；
- 补检针对漏检类别设计，新增命中真实来自补检且不与初始命中重复；边际收益为 0 则停止。

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 随包方法论（执行前必读）

在执行任何命令、产出任何交付物之前，**先完整阅读 `references/expert_playbook.md`（专家参考手册）**，
并按其组织全部产出：

- **流程**：按其 **§2 求解框架与门控** 推进——解析输入 → 构建参考集 → 初始检索 →
  命中判定 → 覆盖率与遗漏率 → 漏检分类 → 补充检索 → 闭环复核与输出；前一步冻结产物未完成不进入下一步。
- **口径**：按其 **§3 量化口径** 计算覆盖率、遗漏率、补检边际收益、漏检归因准确率与命中判定一致性；
  分母写清评价范围，分子分母都要能在中间产物里查到。
- **陷阱**：按其 **§4 领域陷阱** 逐条排雷（错误做法 → 正确做法）；不混淆标识符、不把撤稿当有效、
  不把数据库未收录当不相关、不把近似匹配当精确匹配。
- **门控**：交付前逐项通过其 **§7 防扣分自查表**；任一项未过则 `status=partial`
  并把未决项写入 `uncertainties`，绝不静默提升为完整成功。

## 契约（output_contract）

`case.json` 给出 `output_contract` 时以它为准；否则用下列内建键（边界用例同样输出这套键）。
每个键在 `result.json` 顶层与嵌套 `output_contract` 对象里各回填一次，两处完全一致：

```json
{
  "output_contract": {
    "case": "string",
    "parse": "string",
    "read": "string",
    "discover": "string",
    "queries": "string",
    "gap": "string",
    "draft": "string",
    "quote": "string",
    "paths": "string",
    "products": "string",
    "init": "string",
    "show": "string",
    "check": "string",
    "build": "string",
    "selfcheck": "string"
  }
}
```

## 单命令（one-shot，评测入口）

- 一条命令走完：扫描材料 → 冻结参考集（核对标识符、去重、标注不可用）→ 逐条命中判定
  （标识符精确 / 标题+作者+年份近似 / 边界待裁决）→ 覆盖率与遗漏率 → 漏检分类与归因 →
  补检计划与边际收益 → 落盘。
- **无 `draft.json` 也照常跑完**：仍产出完整契约、全部交付物与 `result.json`，`exit 0`。
- 不访问任何外部数据库；`result.json.limits` 写明「no live remote search / scope limited to the supplied snapshot」。

## 分步命令（agent 增强路径）

```bash
python3 scripts/main.py init  --input /input --output /app/output --work /app/work
python3 scripts/main.py show  --input /input --output /app/output --work /app/work
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --output /app/output --work /app/work
python3 scripts/main.py compare --input /input --output /app/output --work /app/work
```

- `init` 建索引、冻结参考集、写 `work/draft.skeleton.json` 与 `result.json`。
- `show` 打印任务、来源解析状态与参考集的逐条命中状态（含 locator），便于人工写 `work/draft.json`。
- `check` 机械校验：分母来自参考集、`命中 + 遗漏 = 分母`、覆盖率可复算、状态枚举合法；报告写入 `work/check_report.json`，永远 `exit 0`。
- `build` 用 `work/draft.json`（若存在）+ 规则抽取正式成稿；`all` = `build` + 增益报告。
- `compare` 单独产出与朴素基线的结构对照。

## 交付物（每次运行写入 --output）

| 文件 | 内容 |
|-|-|
| `result.json` | 顶层 + 嵌套 `output_contract` 契约回填、`coverage`、`gap_summary`、`supplement`、`change_records`、`uncertainties`、`limits` |
| `scope_card.md` | 范围卡：case、研究问题、参考集指纹、分母策略、四个可审计数字 |
| `hit_ledger.csv` | 逐条命中台账（ref_id × 命中状态 × 匹配规则 × 置信度 × locator × 逐字引文） |
| `gap_matrix.csv` | 漏检矩阵（ref_id × 主因类别 × 可修性 × 处置 × 证据 locator） |
| `gap_atlas.json` | 漏检图谱（按类别聚合 + 残余遗漏清单） |
| `supplement_plan.md` | 补检计划、补检前后覆盖率对比与停止规则 |
| `coverage_report.md` | 主报告：覆盖率与遗漏率、归因、补检、不确定性与限制 |
| `audit_trail.json` | 复算轨迹（分子/分母 ref_id 清单、公式、指纹、确定性哈希） |
| `self_check.json` | 机械自检结论（D 项） |
| `gain_report.md` / `gain_report.json` | 与朴素基线的结构对照（诚实声明：基线为确定性模拟） |

## 判定口径

- 命中规则（先冻结再比对）：L1 标识符精确 `id_doi` / `id_pmid`；L2 标题相似度 ≥ 0.92 且作者或年份相符
  `bib_title_author_year`；L3 标题相似度 0.80–0.92 记为 `bib_borderline`，标 `needs_review` 交人工裁决。
- 分母策略：`dedup_exclude_unavailable`（默认，去重并剔除撤稿/缺元数据）、`dedup_only`、`all`，可用 `--policy` 切换。
- 漏检类别：`query_term_missing` / `field_too_narrow` / `time_window_cut` / `source_not_indexed` /
  `ref_record_anomaly` / `ranking_depth`；每类附判定证据。
- 状态：参考集非空且覆盖 ≥ 0.5 且无遗漏 → `ok`；有遗漏或材料不足 → `partial`；无参考集且无视图 → `insufficient_evidence`；空输入 → `input_error`。

## 异常与降级（可靠体验）

| 情形 | 处置 |
|-|-|
| 材料无参考集文件 | 如实 `insufficient_evidence`，不伪造命中卡；`degradations` 写明原因 |
| 记录缺标识符/年份 | 参考集内标 `meta_incomplete` 并移出分母，理由入台账 |
| 撤稿 / 无法获取全文 / 重复记录 | 标注不可用并单列，不纳入分母 |
| 标题近似匹配 | 冻结阈值；边界区间标 `needs_review`，不静默判命中 |
| 补检无新增 | 记录 `no_gain`，边际收益为 0 则停止并说明 |
| 坏 JSON / 空文件 | 登记 `degradations`，仍写合法 `result.json`，`exit 0` |
| 时间窗/来源冲突 | 以材料声明为准并写入 `uncertainties` |

## 交付前自查（逐项通过）

- [ ] `result.json` 可解析，`case_id` 与输入一致，`output_contract` 逐键回填、无空壳值。
- [ ] 覆盖率分母来自冻结参考集有效条目，分子来自命中台账，数字可复算。
- [ ] 每条漏检指认到具体查询式/字段/来源，附 locator 与逐字引用。
- [ ] 补检针对漏检类别设计，新增命中真实且不重复计初始命中。
- [ ] 撤稿/重复/无全文/标识冲突已标注并说明理由。
- [ ] 空输入 / 坏 JSON / 无参考集三条路径各跑过一次，均 `exit 0` 且有缺口说明。
- [ ] 两次运行结果一致，时间戳不参与判等。
- [ ] **专家检查表逐项通过**：`references/expert_playbook.md` §7 的 20 项防扣分自查表逐项勾选通过；
  任一项未过则 `status=partial` 并把未决项写入 `uncertainties`，绝不静默提升为完整成功。

## top_fix → 实现

| top_fix | 实现 |
|-|-|
| 分母必须是冻结参考集 | `freeze_refset` 冻结 + `audit_trail.json` 记录分母 ref_id 清单 |
| 逐条命中状态矩阵 | `build` 输出 `hit_ledger.csv`；`show` 亦可打印 |
| 漏检归因到具体查询/字段/来源 | `attribute_miss` 六类归因 + `gap_matrix.csv` / `gap_atlas.json` |
| 补检边际收益 | `supplement_plan.md` 前后对比 + `no_gain` 停止规则 |
| 复算命令 | `audit_trail.json` 的公式与分子分母清单；`compare` 产出增益对照 |
| GITHUB_URL 校验 | `GITHUB_URL.txt` 指向 `challenges/search-07`，与作品目录一致 |
