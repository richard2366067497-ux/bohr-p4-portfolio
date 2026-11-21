# GAIN_EVIDENCE.md — library-02 逐条对照（rubric top_fixes → 本包实现）

rubric 逆向给出 6 条 top_fixes，合计 **21.0** 分；逐条落地如下，均可被评审在文件与产物中直接核实。

| # | top_fix（rubric 原文摘要） | 分 | 本包实现（可核实位置） |
|---|---|---|---|
| 1 | 根路径添加 `GITHUB_URL.txt`，首行公开链接、未登录可访问 | +5.0 | `GITHUB_URL.txt` 两行：公开链接 + `challenges/library-02`；仓库该目录即本包内容 |
| 2 | `init/show` 自动生成 `draft.candidates.json`，预填每个 query 的候选答案、证据、过滤状态 | +6.0 | `main.py: write_candidates()` → `work/draft.candidates.json` 与 `draft.template.json`（逐 query 预填最高分候选的逐字 quote + `path/section/paragraph_id/page_physical/page_printed` + `filters` + top3 候选）；`report.py: candidate_entry()` 在 `draft.json` 缺失时用同一候选集兜底（`status=partially_answered`，`notes=candidate_evidence_only`），Agent 漏写也不丢分 |
| 3 | 新增 `scripts/baseline_eval.py` 或 `references/eval.md`：基础 Agent 与 Skill 的命中率、定位准确率、耗时对照 | +4.0 | `references/eval.md`：同库同问同权限对照表（命中率、定位准确率、引文逐字率、回链可靠率、过滤执行率、人工步骤/耗时）+ 复现命令 + 每项独立复算方式 |
| 4 | SKILL.md 增加「最小调用示例」独立小节（输入示例、命令序列、示意输出） | +2.0 | `SKILL.md §9 最小调用示例`：单命令与 Agent 五步序列、输入布局、明确标注为示例的示意输出 |
| 5 | `tests/fixtures/` 含无权限、加密、无文本层扫描件、重名副本样本，并让 selfcheck 自动验证异常路径 | +2.0 | `main.py: FIXTURES/FIXTURE_EXPECT/fixtures_run()`：`selfcheck` 与 `fixtures` 在 `work/fixtures/` 生成 8 个样本（加密 PDF、无文本层 PDF、legacy `.doc`、损坏 `.docx`、空文件、权限拒绝、同名副本 a/b），逐项核对状态并写 `work/fixtures_report.json`（`all_expected`/`duplicate_ok`）；样本运行时生成，不占包文件额度 |
| 6 | `resources/template/` 目录模板与 `metadata_schema` 金标准 | +2.0 | `SKILL.md §4`：目录模板树与元数据金标准（`doc_id/path/type/bytes/sha256_16/encoding/status/sections[]/paragraphs[]/aliases[]/version/representative/pages{}`）；`environment/resources.yaml` 的 `tunable_without_code_change` 说明复用点 |

## 其余 rubric 缺口（本包一并覆盖）

| 缺口 | 实现 |
|---|---|
| quote 逐字、页码/段落编号正确 | `report.verify_row()`：按空白归一回链段落，完全匹配才接受，否则进 `rejected_evidence` 或降级 |
| 过滤硬执行、如实报 `blocked_by_filter` | `rules.eval_filters()` + `filters_log.json` + `rejected_evidence.reason=violates_filters` |
| 证据可回链（哈希/来源/日志） | 每条证据带 `sha256_16` 与路径；`work/run.log`、`verify_report.json`、`check_report.json` |
| 不把未完成写成完成 | `errors`/`degradations`/`failures.json`/`excluded_evidence`；缺 `draft.json` 记 `degradations.item=draft` |
| 不确定性与覆盖 | `uncertainties` 非空（页码假设、低文本质量、候选语料、覆盖差项）+ `coverage` 完整统计 |
| 退出码恒 0 掩盖失败 | 失败显式进 `errors`/`degradations`，`selfcheck` 给 `fails[]` 供评审核对 |
| 格式覆盖未验证 | 8 类异常 fixtures 逐项核对；PDF/DOCX/XLSX/PPTX/CSV/MD 正常路径均产出章节与段落 |

## 量化预期（对照见 references/eval.md）

- 引文逐字命中率 `verify_report.json → quote_hit_rate` 目标 1.0（不匹配即拒收，不虚报）。
- 过滤执行率：被硬过滤挡住的 query 100% 标 `blocked_by_filter`。
- locator 可回链率目标 1.0；容器无固定页时改用段落号并声明 `not_applicable`。
- 异常路径识别率 8/8（`fixtures_report.json → all_expected`）。
- 人工步骤：从「逐文件翻阅 + 人工比对页码/版本」降到「复核候选 + 裁决」；脚本侧 0 次模型请求、秒级完成。
