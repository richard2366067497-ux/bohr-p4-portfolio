# 可复用检索式模板（query templates）

配套 `patent-search-dossier` v1.0.0。每个模板给出一条可直接改写用于检索平台的检索式形态，并写清
**专利文献与技术文献分开检索、分开排序**的口径。模板中的 `NUMBER`、`TEXT`、`APPLICANT`、`CLASS`、`DOI`
都是待替换的占位词，替换后即为一次真实检索式；模板本身不是任何一次运行的结果。

## 1. 号码式（number lane）

| 目的 | 模板 | 口径说明 |
|-|-|-|
| 按公开/授权号定位 | `NUMBER OR family:NUMBER` | 先定位号，再按族扩展；号码必须先规范化 |
| 按申请号反查公开 | `apno:NUMBER` | 申请号与公开号是不同文书类型，不可互相冒充 |
| 按优先权号扩展 | `prn:NUMBER` | 同优先权只可**推定**简单族，不推断权利要求等同 |
| 前后向引证 | `cited_by:NUMBER` / `cites:NUMBER` | 方向必须分开写，不能混成一个「相关」 |

号码进入检索式之前一律先走规则链：
`strip_separators → cc:*（国别前缀）→ kind:*（尾部 kind code）→ 位数判型 → inferred_country:*`。
例：`US 2017/0123456 A1 → US20170123456A1`；`PCT/US2018/012345 → WO2018012345`；
`10,123,456 → US10123456`（无国别，靠位数推断，`parse_status=ambiguous`，不得冒充确定号码）。

## 2. 主题式（topic lane，专利）

| 目的 | 模板 | 口径说明 |
|-|-|-|
| 关键词 + 分类号组合 | `("TEXT1" OR "TEXT2") AND IPC:CLASS` | 同义词写清；分类号与关键词可组合 |
| 仅分类号 | `IPC:CLASS` | 分类号检索不依赖语言，适合跨语言 |
| 申请人监控 | `pa:"APPLICANT" AND ipc:CLASS` | 竞品/机构监控；申请人名称变体需列举 |
| 号码 + 主题收窄 | `family:NUMBER AND "TEXT1"` | 先用号码定族，再用主题在族内收窄 |

## 3. 技术文献式（topic lane，非专利）

| 目的 | 模板 | 口径说明 |
|-|-|-|
| 已知 DOI | `doi:DOI` | 精确命中，优先于关键词 |
| 主题词 | `"TEXT1" AND "TEXT2"` | 与专利分库检索、分开排序 |
| 作者/机构 | `au:"AUTHOR" AND "TEXT1"` | 仅作线索，需回到原文核对 |

**纪律**：专利与文献**分开检索、分开排序，不混排成一张榜单**。一次检索只回答一个问题；
号码命中不等于技术主题命中，技术主题命中也不等于同一族。

## 4. 检索面的五问（每次检索都要能被这五问答上）

1. 这件专利保护什么？（权利要求原文 + 出处定位）
2. 它与同族其他成员什么关系？（观察到的族边 + 口径 simple / extended + `not_exhaustive`）
3. 现在是否有效？（状态值 + `as_of` + 来源分级 + `needs_official_verification`）
4. 同一技术主题还有谁在做？（主题检索式 + 排序依据）
5. 这些信息自己是否有权访问与展示？（许可分级 green / yellow / red + 降级方案）

## 5. 排序/筛选依据（可复核）

- 号码通道优先：有确定号码的文档先入候选，按号码定位排序。
- 主题通道：按关键词/分类号命中与 `why_relevant` 排序，写清排序键。
- 每条入选结果保留 `source_id` + `locator` + 逐字 `quote`；未命中的检索面写入 `boundaries` 的
  `coverage_gap`，不补造结果。

## 6. 遗漏说明（omission）

- 材料未提供的号码/文献 → 写 `gaps`（缺什么、为什么、何时补），不臆造。
- 无法解析的号码 → 保留原串，标 `parse_status=unparsed`，进 `boundaries.metadata_missing`。
- 未获得完整同族表 → 族结论限于 observed 范围，并记 `not_exhaustive`。
