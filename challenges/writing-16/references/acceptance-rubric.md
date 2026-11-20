# 验收口径：评分五维 → 可执行检查项 → 交付证据

题面 100 分分五维。本文件把每一维翻译成"在包里能被执行、能被第三方复算"的动作，避免文字自述代替运行证据。

---

## 1. 实际效果（40 分）

| 评分点 | 分值 | 本包的落实 | 复算方式 |
|---|---|---|---|
| 任务完成度 | 15 | 必须交出**成稿正文**（`sections[].text`），不是提纲/建议/片段；体裁骨架由 `genre.conventions` 声明 | `check` 的 `sections`、`body_words`、`too_short`；`deliverable.md` 第二节 |
| 结果正确性 | 15 | 数字/单位/样本/统计口径/图表编号与源文逐字比对；quote 逐字回溯 | `check` 的 `numeric_drift`、`figure_mismatch`、`*_quote_miss`；`fidelity_summary` |
| 结果完整性 | 5 | `retained` 覆盖 P0；候选保留项的未解释缺口被点名 | `retained_coverage`、`unexplained_gap`、`silent_drop` |
| 结果可核验 | 5 | 每条结论/数据有 locator + 逐字 quote + 落点；每处删改有理由 | `evidence_map`（trace）、`change_log`、`diff_map.md` |

**验收底线**：`selfcheck` 全 PASS；`check` 无 `[错误]`；`quote_hit_rate = 1.0`；`numeric_drift = 0`。

---

## 2. 使用增益（25 分）

质量增益靠"更少的事实漂移、受众错配、术语不一致"，不靠自评。

| 评分点 | 本包的落实 | 可核验证据 |
|---|---|---|
| 质量增益 15 | 改写前先锁定 P0 台账与读者画像；架构上把"判断"留给 Agent、"比对"交给脚本 | `check` 前后差异（同一 `draft.json` 修完再跑，漂移/命中率变化可见）；`fidelity_summary` 的 7 个指标 |
| 效率增益 5 | 五命令主路径替代人工通读比对：`init` 自动切段编号、`show` 定点读段、`check` 一次列出全部机械问题 | `runtime.elapsed_s`、`runtime.counts`；`check.json` 的错误条数（人工核对项 = 错误条数） |
| 增益可验证 5 | 所有指标由 `source + result.json` 复算，`fidelity_summary.recompute` 给出复算入口；允许第三方换 draft 重跑对照 | `python3 scripts/main.py check` / `selfcheck` 可重跑且结果稳定（幂等） |

**公平对照的做法**（不伪造分数）：同一 `/input`，先用"不写 draft 直接 `build`"得到兜底基线，再写 draft 走完整路径；比较两组 `fidelity_summary` 即可看出增益来源。平台白板由组织方提供，参赛包不自造对照分。

---

## 3. 创新增益（15 分）

题面点名要"受众画像 → 取舍策略 → 边界标注 → 多文体映射"的链条。四个环节在本包中都有可见落点：

| 环节 | 落点 | 产物 |
|---|---|---|
| 受众画像 | `audience` 六字段 + 矩阵表 | `deliverable.md` 第一节；`result.json.transformation_spec.audience` |
| 取舍策略 | P0/P1/P2 三级 + `retained`/`dropped` | `retained_facts.json`、`diff_map.md` 第 3 节 |
| 边界标注 | 三级强度 + `open_questions`/`uncertainty` + `strength_upgrade`/`hedge_lost` 校验 | `result.json.uncertainty`、`.pending_human` |
| 多文体映射 | 体裁骨架表 + 同一事实多版本共用同一 `retained` | 换 `genre` 重跑即得第二个版本 |

**相对基础 Agent 的边界**：本包不生成"更好看的句子"，而是保证"改完还能逐条核对"——事实漂移为 0、每条结论可回溯到 `Mx:Py`、删改有理由。超出这条边界（如无源材料的创作、市场预测）明确拒绝。

---

## 4. 可靠体验（10 分）

| 评分点 | 本包的落实 |
|---|---|
| 调用与易用性 3 | 五个子命令语义单一；`--input/--output/--work` 可放子命令前或后；默认路径即官方契约路径；`show` 支持 `--ids/--grep/--mat/--cands` |
| 运行稳定性 4 | 退出码恒 0；`init` 先写合法 partial；重复运行幂等覆盖；`build` 无 draft 也产出完整最小交付；解析降级逐个文件隔离 |
| 异常处理 3 | 坏 `case.json`（递归找 `output_contract`）、空输入（`insufficient_evidence`）、坏 `draft.json`（兜底）、图片/PPTX（不 OCR 不臆造）、目录不可写（自动换路径）——全部写进 `degradations`/`errors` |

**异常处置的四条纪律**：材料缺失 → 说明缺什么；无法判断 → 标 `uncertainty` 或 `open_questions`；输入冲突 → 两值并列、请作者定夺；运行失败 → 仍出 partial 且说明失败位置。

---

## 5. 生态贡献（10 分）

| 评分点 | 本包的落实 |
|---|---|
| 文档完整性 3 | `SKILL.md` 含用途/适用条件/调用方式/输入输出契约/方法/边界/失败处理/自查/版本维护 |
| 资源可复用 4 | `draft-schema.md` 字段字典与校验代码表、`audience-genre-matrix.md` 受众矩阵与六种体裁骨架、本文件的验收口径——三者可被别的写作类 Skill 直接复用 |
| 分享价值 3 | 五命令主路径可模板化；`init/show/check/build/selfcheck` 的分工（脚本做机械活、Agent 做判断）可直接迁移到其他"产物 + 来源"型任务 |

---

## 6. 交付验收清单（`selfcheck` 覆盖机械项）

- [ ] `SKILL.md` 在包根，frontmatter 含 `name` / `description` / `version`。
- [ ] `python3 scripts/main.py --help` 退出码 0；四个模块可单独 `--help`。
- [ ] 走完五命令：`init` → `show` → 写 `draft.json` → `check` → `build`（→ `selfcheck`）。
- [ ] `result.json`：契约键全在且同名、`case_id` 原样、`status` 与实际一致、`degradations`/`errors` 诚实。
- [ ] `deliverable.md` 八节齐全，正文是成稿；附表 `retained_facts.json` / `diff_map.md` / `glossary.csv` 非空。
- [ ] 删掉 `draft.json` 重跑 `build`：仍 exit 0，`status=partial`，稿首标注"兜底稿"。
- [ ] 空 `/input` 重跑：`status=insufficient_evidence`，不编造内容。
- [ ] 示例与示意输出均标注"示例，非正式案例结果"；包内无预制答案、无 `__pycache__`。

---

## 7. 已知边界（写在明处，不掩盖）

1. **PDF 版式风险**：无 `pdftotext` 时用内置流解析，双栏/表格可能错序，脚本标 `builtin-pdf-lowconf`，须人工核对后再引用。
2. **数字校验是"存在性"而非"语义"**：能保证成稿里的数字在源文出现过，不能保证它被放在了正确的论证位置——后者由 Agent 的 `retained`/`trace` 与人工通读负责。
3. **改写质量不可全自动判定**：`check` 能挡住事实漂移、术语漂移、强度升级、提纲冒充，但"读得懂"只能由人以目标读者身份通读确认；因此 `selfcheck` 结尾固定提示回读。
