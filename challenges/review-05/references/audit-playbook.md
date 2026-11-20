# 审查剧本：严重度锚点、整改优先级、报告结构、复核清单

配合 `SKILL.md`（流程）与 `references/matrix-schema.md`（字段）使用。本文件解决三个问题：**这条问题该判多重**、**整改先改哪个**、**交付前怎么自查**。

## 1. 严重度锚点（四档，必须能说清相邻档差别）

| 档位 | 定义 | 判据（任一成立） | 例子 |
|---|---|---|---|
| `critical` | 可致拒稿、撤稿、伦理事故或数据不可用 | 影响结论成立/受试者权益/数据合法性；期刊或机构会启动调查 | 未声明的人体数据；声称有伦理批件但全文无批件信息；图像与已完成发表图一致却未声明复用；编造引用支撑核心结论 |
| `major` | 发表/提交前必改，否则被退回或整改 | 违反强制项；影响可核查性但不推翻结论 | COI/基金/数据可用性声明缺失；正文引用悬空；引文张冠李戴支撑次要论点；真实 PII 未脱敏 |
| `minor` | 规范瑕疵，编辑/审稿人可能提出 | 格式、完整性、一致性 | 文献元数据缺 DOI；编号跳号；声明区块用词不规范；图注未写来源 |
| `suggestion` | 改进建议，不是缺陷 | 提高透明度/可复现性 | 建议公开分析脚本；建议补注册号；建议在图注写样本量 |

写法模板：`"<可核对事实> → <后果/影响> → 因此为 <档位>"`。例：`"COI 声明缺失，而稿中含企业资助的动物实验 → 读者无法判断结论独立性，期刊多列为强制项 → 发表前必改 → major"`。

**相邻档判别**：critical 与 major 的分界是"结论是否可能不成立/受试者权益是否受影响"；major 与 minor 的分界是"是否会被退回"。说不清就往低一档判，并写清理由——评审更反感夸大，而不是漏一档。

## 2. 整改优先级（报告第 4 节）

| 优先级 | 内容 | 处理人 |
|---|---|---|
| P0 | 全部 `critical`：先停投，核实事实与原始材料 | 作者 + 通讯作者 + 机构 |
| P1 | 全部 `major`：投稿/提交前必须完成 | 作者 |
| P2 | 全部 `minor`：与格式整改一起做 | 作者/编辑助理 |
| P3 | `suggestion`：可选改进 | 作者 |

每条整改写"改哪里 + 改什么 + 谁确认"，例：`"在 §Declarations 新增 COI 小节，逐作者写明无财务冲突；通讯作者确认"`。不要写"建议完善声明"。

## 3. 报告结构（`compliance_report.md`，脚本生成，不需手写）

```
0. 输入与范围        材料清单 + 抽取器 + 文本质量 + 覆盖/不覆盖声明
1. 合规矩阵          按 domain 分组的 33 行表（row / 要求 / 判定 / 严重度 / 位置 / 依据类型）
2. 违规清单          每条 finding：矩阵行、位置、逐字证据、期望/实际、为什么算问题、整改
3. 待人工核实        unverifiable 行 + 需要核对的具体对象（DOI、指南版本、许可范围）
4. 整改建议          P0–P3
5. 覆盖、缺口与诚实性 行数/判定数/引文命中率/降级/不确定性/待人工
6. 复跑与版本        命令、规则版本、确定性排序说明
```

**为什么不是"按方向罗列问题"**：矩阵是事实源，报告只是视图。评审抽查任意一条结论时，能沿 `matrix_row_id → evidence_locator → quote` 三步回到原文，这比文章写得多漂亮更重要。

## 4. 交付前复核清单（12 项）

| # | 检查 | 通过判据 | 失败处置 |
|---|---|---|---|
| 1 | 契约完整 | `build` 打印 `unfilled contract: none` | 补 `pending_human` 说明，不编造内容 |
| 2 | 矩阵完整 | 33 行，7 个 domain 全覆盖，`DEC-01..09` 齐 | 补行（`not_applicable` 也要有） |
| 3 | 证据门控 | 每条 violation 有 `quote`+`evidence_locator` | 补齐或降级 `unverifiable` |
| 4 | 引文逐字 | `quote_pass_rate = 1.0` | 回 `show` 重新复制 |
| 5 | 定位一致 | 无 `locator_quote_mismatch` | 用 `show --grep` 找真段落 |
| 6 | 不编造 | 无 `invented_identifier` / `guideline_basis_unavailable` | 删编号，改 `unverifiable` |
| 7 | 待复核可执行 | 每条 `unverifiable` 有具体核对对象 | 写"核什么、在哪核" |
| 8 | 不适用有据 | 每条 `not_applicable` 有 `searched_scope` | 补检索范围与关键词 |
| 9 | PII 台账干净 | 无 `pii_not_redacted`，报告已遮罩 | 换成 `[REDACTED-*]` |
| 10 | findings 可反查 | `selfcheck` 的 `findings_traceable` PASS | 修 `matrix_row_id` |
| 11 | 确定性 | 两次 `build` 的 `run_manifest.counts` 一致 | 检查是否有随机排序/时间戳混入 |
| 12 | 诚实降级 | 扫描件/缺页/缺指南都记入 `degradations` | 补记，不写成结论 |

命令：`check` 看错误码与 `counts`；`build` 看 `status` 与 `unfilled contract`；`selfcheck` 看逐项 PASS/FAIL。

## 5. 状态语义（`result.json.status`）

| status | 何时 | 下游含义 |
|---|---|---|
| `ok` | 有判定、无 check 错误、无降级 | 可直接用于投稿前自检 |
| `partial` | 有判定但有降级/缺格/未判定行 | 结论可用，缺口清单必须一并看 |
| `insufficient_evidence` | 材料可读但一行都没判定 | 只能当检查表用，不能当审查结论 |
| `input_error` | `/input` 缺失、无材料、case.json 坏 | 需修复输入后重跑 |

## 6. 典型材料形态与策略

| 材料 | 策略 |
|---|---|
| 完整论文（摘要+方法+结果+文献表） | 全量 33 行；CITE 系列用 `init` 信号确定性判定，声明区块逐项找 |
| 只有正文无文献表 | CITE-01/02/03 判 `unverifiable`（`no_reference_list`），其余照常 |
| 学位论文章节 | 声明区块常缺 COI/数据可用性 → 注意区分"学校规范未要求"（`unverifiable`）与"确实缺"（`violation`） |
| 结题/中期报告 | 基金号一致性（INT-04）与成果标注是高价值检查点 |
| 附作者指南 | VEN 四行可判定；务必在 `doc_meta.venue_name` 记下期刊名与指南版本 |
| 纯扫描 PDF | 全量判 `unverifiable` + 降级说明（需 OCR），不要凭图像内容猜文字 |
| 多材料（稿件 + 指南 + 数据说明） | `doc_id` 区分：稿件 D1、指南 D2，跨文档判 `internal_consistency` 时给两侧 locator |

## 7. 维护

- 新增要求：`rules.py` 的 `CAT`/`DECL` 增行 → 同步 `references/requirement-catalog.md` → 升 `VERSION`。
- 新增误报抑制规则：写进 `requirement-catalog.md` §4 与 `SKILL.md` §12。
- 调整严重度锚点：本文件 §1 + `SKILL.md` §5.3 同步改。
- 报告版式：只改 `rules.py::render_report`，不要手改生成的报告（下次 `build` 会覆盖）。
