# 专家参考手册 — latest-lit-tracking（最新文献追踪）

本手册是本 Skill 的方法论：**九步框架 → 量化口径 → 判重/归一化规则 → 陷阱清单 → 检查表**。
执行前通读，执行中对照，交付前逐项自查。

---

## 1. 问题本质

用户订阅了一个研究问题，希望每次拿到快照时知道：**哪些是新的、哪些是旧文重发/更正/撤稿、
哪些落在窗口外、哪些因为元数据缺失而无法判断**。核心难点不是"找到文献"，而是：

1. **判重**：同一个 DOI 在不同库里出现，标题大小写/标点/排版不同。
2. **增量**：与上一次状态对比，而不是每次都全量报告。
3. **幂等**：同一快照重跑，结果不变、不重复告警。
4. **可辩护**：每条告警都能给出来源、定位和判重依据。

**错误做法**：把"库里出现的条目"直接当成"新的"；用标题字符串原样比较；不保存状态每次全量输出；
把窗口外的老文献混进 new。
**正确做法**：先归一化再判重，先读状态再算增量，先分类再合并告警，最后幂等写回状态。

---

## 2. 九步框架

| 步 | 名称 | 做什么 | 产出 |
|-|-|-|-|
| 1 | parse | 读题面与快照，确定研究问题、订阅源、窗口 | `query`、`sources` |
| 2 | subscription config | 订阅配置：来源列表、窗口 `[start, end)`、判重优先级 | `window` |
| 3 | state | 读 `state.json`：`last_snapshot`、`last_window_end`、`delivery_log` | 上次状态 |
| 4 | retrieve | 扫描快照，切分段落并抽取记录（title/author/year/DOI/arXiv） | 原始记录 + locator |
| 5 | normalize + dedup | 归一化字段，按 DOI > arXiv id > title|author|year 判重合并 | 唯一记录 + 判重依据 |
| 6 | incremental diff | 与 `last_snapshot` 对比，分类 new/update/retraction/correction/old_indexed，窗口外进 out_of_window | 分类结果 |
| 7 | alerts | 合并同类告警、抑制重复投递，压缩告警数 | 告警列表 |
| 8 | state update | 幂等写回 `last_snapshot` / `last_window_end` / `delivery_log` | 新状态 |
| 9 | result.json | 逐键回显 `output_contract`，写全部产物与 change_records | 交付物 |

---

## 3. 量化口径（公式）

- **new 准确率** = 真·新记录 / 报告的 new 记录 ≥ **95%**
- **重复率** = 重复报告数 / 报告总数 ≤ **5%**
- **漏检率** = 漏掉的真实新记录 / 真实新记录 ≤ **10%**
- **窗口覆盖率** = 窗口内被检查的记录 / 窗口内全部记录 = **100%**
- **幂等重跑率** = 同快照重跑结果一致的比例 = **100%**
- **告警压缩率** = 原始候选数 / 最终告警数 ≥ **2**
- **可复现率** = 可回溯到 locator+依据的记录 / 全部记录 = **100%**

窗口定义固定为 **UTC ISO8601、左闭右开 `[start, end)`**，`end` 必须回显进契约。

---

## 4. 判重与归一化规则

**归一化管线**（对标题）：`NFKC → lowercase → 去标点 → 折叠空白`。

**判重键优先级**（自高到低），命中即合并，且**保留合并依据**：

1. `doi:` + DOI（**大小写不敏感**，统一小写）
2. `arxiv:` + arXiv id（形如 `2401.12345`，去掉版本尾 `vN`）
3. `title:` + 归一化标题 + `|` + 第一作者姓（surname）+ `|` + 年份

合并时保留：全部成员 rid、来源列表、locator 列表、命中的判重键。

---

## 5. 增量分类语义

| 分类 | 判定 |
|-|-|
| new | 判重键不在 `last_snapshot`，且在窗口内 |
| update | 文本含 `update` 标记（版本更新） |
| retraction | 文本含 `retract` 标记（撤稿） |
| correction | 文本含 `correction` / `erratum` 标记（更正） |
| old_indexed | 窗口外的旧记录被后补索引 |
| out_of_window | 年份不在 `[start_year, end_year]` 内 |

缺 DOI 或缺年份：**不猜测**，进入 `decision_missing` 并说明缺哪个字段。
年份缺失时窗口成员关系无法判定 → 同样记入 `decision_missing`，不要强行归入 new。

---

## 6. 陷阱清单（错误做法 → 正确做法）

| # | 陷阱 | 错误做法 | 正确做法 |
|-|-|-|-|
| 1 | 标题原样比较 | `if a.title == b.title` | 先 NFKC+小写+去标点+折叠空白再比 |
| 2 | DOI 大小写 | `10.1/AbC != 10.1/abc` | DOI 统一小写后比较 |
| 3 | 全量报告 | 每次都输出全部条目 | 与 `last_snapshot` 求差，只报增量 |
| 4 | 状态被覆盖 | 每次都覆盖 `last_snapshot` 导致重跑全变 new | 幂等写回：已有键保留，`delivery_log` 去重 |
| 5 | 窗口边界 | 用 `<=` 造成重复计入端点 | 固定 `[start, end)` 左闭右开 |
| 6 | 老文献混入 | 把 `old_indexed` 当 new | 先判窗口，窗口外的进 `old_indexed` / `out_of_window` |
| 7 | 缺元数据硬猜 | 给缺失 DOI 编一个 | 保留原值，记入 `decision_missing` |
| 8 | 告警风暴 | 每条记录一条告警 | 合并同类、抑制重复投递，压缩率 ≥ 2 |
| 9 | 无依据 | 只说"是新的" | 给出 locator + 判重键 + 依据 |
| 10 | 联网臆造 | 声称查了远程库 | 只用所给快照，`limits` 写明边界 |

---

## 7. 检查表（交付前逐项通过）

- [ ] 研究问题与订阅源已解析，`sources` 非空
- [ ] 窗口为 UTC ISO8601 `[start, end)`，`end` 已回显进契约
- [ ] 已读 `state.json`；`last_snapshot` / `last_window_end` / `delivery_log` 均存在
- [ ] 记录带 locator（`S0x#rN`），可回溯
- [ ] 归一化与判重按 DOI > arXiv > title|author|year 执行，依据保留
- [ ] 增量分类齐全：new/update/retraction/correction/old_indexed/out_of_window
- [ ] `decision_missing` 给出缺失字段，未猜测补全
- [ ] 告警已合并/抑制，压缩率 ≥ 2
- [ ] 幂等：同快照重跑 `new` 为空，`delivery_log` 不重复
- [ ] `output_contract` 每键回填真实值，无占位符
- [ ] `status` / `sources` / `uncertainties` / `change_records` / `limits` 非空
- [ ] 全部产物写出：result.json、decisions.jsonl、new_records.json、diff_report.json、window.json、report.md

---

## 8. 案例（钙钛矿 / CRISPR 类追踪，示意口径）

一次窗口快照：Crossref 85 条 + EuropePMC 60 条 = **145 原始**。
- 归一化判重后 **115 唯一**（重复率 ≈ 20.7%，多为跨库同 DOI）。
- 版本链合并 **-5** → **110**。
- 分类：撤稿/更正 **3**，`old_indexed` **2**。
- 最终 new **105**，告警 **108**（105 new + 3 retraction/correction）。
- 告警压缩率 = 145 / 108 ≈ **1.34**（若按候选/告警口径则按 §3 公式报告）。
- 同快照重跑：`new = 0`，`delivery_log` 不新增 → 幂等通过 100%。

复算要点：报告数字必须能由快照文件重新推导，任何一条告警都能指到 `S0x#rN` 与判重键。

---

## 9. 交付纪律

- 结论限定在**所给快照**内，不声称全局新颖性或 live coverage。
- 不联网、不查询远程数据库、不臆造 DOI/年份。
- 空输入或无可解析记录：给出带说明的**非空**空结构（`decisions` / `decision_missing` / `out_of_window`），
  原因写入 `degradations`，`status=insufficient_evidence`。
- 任一检查表项未过 → `status=partial`，并在 `limits` / `degradations` 写明原因。
