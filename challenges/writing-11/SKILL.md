---
name: manuscript-revision-desk
description: 学位论文与长文档写作的"改稿工作台"：在 organizer 工单边界内，只对带段落锚点的原稿追加可逐条回源的编辑注记（实验条件、解释边界、澄清），原句、数字、表格、公式、引用一律逐字保留；对每条注记做 propose/accept、版本比对、回滚与重放验证、非法操作拒绝且状态不变，并给出可导出的修订稿、证据地图、保留事实清单、变更日志与 result.json。单命令 all 在无草稿时也产出完整契约与全部关键交付物；五命令 init/show/check/build/selfcheck 支持 Agent 先读后写。适用于论文章节修订、审稿意见逐条处理、实验条件补全、论证边界标注、可回溯改稿与导出预览；不适用于整章重写、代写研究内容、伪造数据或跳过原文核验的改写。
version: 2.0.0
---

# 学位论文 / 长文档改稿工作台：源文保真的编辑注记（annotation-first）

本包把"改稿"拆成两件事：**原稿不动**（逐字保留）、**注记可回源**（每条注记都能定位到原句）。
脚本负责解析、定位、渲染、版本控制与契约回填；Agent 负责判断"这一段该补什么注记"。

## 执行前必读（专家方法论）

**动手前必须先读 `references/expert_playbook.md`，并严格按其检查表产出。** 该手册是本 Skill 的
方法论基准：任务本质与判分要点、错误做法→正确做法、求解框架（G0–G6）、量化口径与公式（结构/
对齐/术语/数字/引用各覆盖率）、领域知识、交付物清单与专家检查表、完整虚构案例、交付前门控。
执行顺序固定为：先读手册 → 再按手册求解框架逐块落盘冻结产物 → 交付前逐项勾选手册 §5 专家检查表。
手册与 `SKILL.md` 冲突时，契约键名与入口命令以 `SKILL.md` 为准，方法与判分口径以手册为准。

## 0. result.json 契约样例（output_contract 逐键回填，顶层 + 嵌套）

`result.json` 把**用例声明的每一个 `output_contract` 键**原样写进 `output_contract` 对象，
并在顶层写入同名键；标量写真实值，路径键指向真实非空产物，数组写真实结构。
用例未给契约（`output_contract: null`）时使用下列默认 7 键：

```json
{
  "case_id": "case-unknown",
  "status": "partial",
  "output_contract": {
    "case_id": "case-unknown",
    "status": "partial",
    "deliverable": "revised_manuscript.md",
    "preserved_facts": [{"fact_id": "PF-001", "fact": "28.5 MPa", "quote": "the mean tensile strength rose from 28.5 to 41.2 MPa", "locator": "chapters/ch01.md:L12", "status": "preserved"}],
    "evidence_map": "evidence_map.json",
    "change_log": "change_log.json",
    "uncertainties": ["规则化注记需作者确认后定稿；原文与引用未改动"]
  }
}
```

- 每个值都是**真实推导结果**或真实产物路径，绝不写 `"string"`/`"array"`/`"value"` 这类类型串。
- 空内容不写 `null`/`[]`，而写带 `locator`/`quote`/`status` 的诚实非空结构，并在 `degradations` 说明。
- `case_id` 从 `case.json`（`case_id`/`caseId`/`id`）**原样透传**，不得改写。

### 0.1 工作稿样例（Agent 写 `/app/work/draft.json` 时照此结构）

```json
{
  "case_id": "case-unknown",
  "segments": [
    {"target_id": "C01-P002", "quote": "quote one verbatim sentence from that paragraph",
     "kind": "condition", "annotation": "your source-grounded annotation, at least one sentence",
     "status": "accepted", "confidence": "high"}
  ]
}
```

`kind` 取 `condition`（实验条件/复现边界）、`limitation`（解释边界/关联非因果）、`clarification`（术语与范围澄清）。
`quote` 必须是该段落的**逐字子串**；校验失败就缩短 quote 或改段，**不得改原文**。草稿不可用时自动回退到
规则化注记并在 `degradations` 记录，`build` 仍然 finalize 全部产物。

## 1. 单命令入口（single-command entry，一条命令跑完全流程；评测入口，无 draft 时执行）

```bash
python3 /skills/weekly-skill/scripts/main.py all --input /input --output /app/output --work /app/work
```

这一条命令完成：发现 case/workorder/章节 → 解析段落锚点 → 生成源文注记（Agent 草稿存在则优先合并）
→ 生成修订稿（原文逐字 + 注记块）→ 抽取并核对保留事实 → 证据地图 → propose/accept、版本比对、
回滚/重放验证、非法操作拒绝（状态哈希不变）→ 写全部交付物与 `result.json`（契约逐键回填 + `case_id` 透传）
→ 占位符净化。**无 draft、空输入、坏 JSON 都 exit 0，并保留合法结果与限制说明。** **无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。**

## 2. Agent-first 增强路径（agent 写 draft → check → build）

```bash
python3 /skills/weekly-skill/scripts/main.py init       # 建索引 + 合法 partial result.json + draft 模板
python3 /skills/weekly-skill/scripts/main.py show       # 打印带 locator 的锚点段落，供逐字引用
#  >>> 你（评审 Agent）阅读段落，写 /app/work/draft.json <<<
python3 /skills/weekly-skill/scripts/main.py check      # 机械校验：目标存在、quote 为逐字子串、注记非空
python3 /skills/weekly-skill/scripts/main.py build      # 合并草稿并 finalize 全部交付物
python3 /skills/weekly-skill/scripts/main.py selfcheck  # 复核契约键、产物非空、注记可回源
```

工作稿格式见 §0.1（`/app/work/draft.json` 是唯一人工写入口）。

## 3. 输入约定

| 输入 | 说明 |
|---|---|
| `/input/case.json` | `case_id`、`task_instruction`、可选 `output_contract`、`deliverable`、`preserved_facts`、`change_log` |
| `/input/task.md` | 题面（工单边界、需要补的注记类型） |
| 工单 JSON | `organizer-edit-workorder.json` 等，含 `target_ids[]`、`operation_requirements`、`project_mode`、`authority` |
| 章节材料 | `/input/chapters/*.md`、`*.markdown`、`*.txt`（排除 task.md/README），段落以 `<!-- C01-P002 -->` 形式带锚点 |
| 其他材料 | 实验记录、返修意见、原件快照等，仅作证据，不直接改写 |

段落锚点正则：`<!-- <ID> -->`，`ID` 形如 `C01-P002`（章节-段号）。无锚点的段落不进入改稿，只作为证据登记。

## 4. 输出交付物（写入 `/app/output`）

| 文件 | 内容 |
|---|---|
| `result.json` | 主结果：契约逐键回填（顶层 + `output_contract`）、`case_id` 透传、`status`、注记、证据、变更、限制 |
| `revised_manuscript.md` | 修订稿：原文章节逐字复制，仅在目标段落后插入可回源的编辑注记块 |
| `evidence_map.json` | 每条注记 ↔ target_id / locator / 逐字 quote / 校验状态 |
| `preserved_facts.json` | 关键数字、单位、标准号、样本量等事实清单 + 锚点段落保留核对 |
| `change_log.json` | 逐条 propose / accept / reject 记录 |
| `version_compare.md` | 原/修哈希、回滚与重放验证、非法操作拒绝记录 |
| `operation_log.json` | 导入、注记、非法操作、回滚、重放的状态序列 |
| `task_receipt.json` | 工单回执：case、workorder、targets、materials、authority |
| `export_preview.md` | 导出预览：注记卡片 + 限制说明 |
| `original_snapshot.json` | 原稿每章字符数与哈希，供回滚核对 |
| `manifest.json` | 产物清单、契约键、依赖（仅标准库） |
| `verify_report.json` | `selfcheck` 生成的机械检查报告 |

## 5. 改稿规则（每条都可机械复核）

1. **原句不改**：修订稿中的正文行逐字等于原文；注记只以独立块追加（`<!-- EDITORIAL-ANNOTATION ... -->` 包裹）。
2. **注记必须回源**：`source_quote` 是该锚点段落的逐字子串，`locator` 写 `文件:L起行`；无法回源就不写。
3. **实验条件注记**：段落报告测量但未给离散度（SD/CI）或预处理状态时，写明"结果只对所列试样与参数成立"。
4. **解释边界注记**：只给端点数字的趋势必须标注"关联，非已测因果"；未测孔洞/孔隙时不得把机制写成测量结论。
5. **范围澄清注记**：把术语与结论限定在该段所述材料、条件、端点，不扩到其他群体或工况。
6. **工单边界**：整章重写、改动数据、删减引用一律 **reject** 并写理由；target 列表外的段落不改。
7. **版本控制**：修订前后各记哈希；回滚 = 移除注记块，必须恢复原文哈希；重放 = 重新插入全部注记，必须逐条存在。
8. **非法操作**：至少演示一次"空替换"被拒绝，返回错误码，且 `state_sha_before == state_sha_after`。

## 6. 状态与降级

- `status`：`ok`（目标段全部有已接受注记且回源命中）/ `partial`（有降级或草案待确认）/ `insufficient_evidence`（无带锚点正文）。
- 无 case.json：用默认 7 键并记录降级；无工单：取前两个锚点段落并在 `degradations` 说明。
- 章节为空/无锚点：仍写 `revised_manuscript.md`（说明无可用锚点正文）、证据地图、变更日志与合法 `result.json`。
- 任何异常：捕获到 `result.json.errors`，保留已有产物，**恒 exit 0**。

## 7. 可靠性

- 纯 Python3 标准库、离线、无网络；路径由 `Path(__file__).resolve()` 定位，不依赖当前目录。
- 可用 `--input/--output/--work` 或 `SKILL_INPUT/SKILL_OUTPUT/SKILL_WORK` 覆盖；默认回退到 skill 同级目录。
- 所有输出文本在收口时净化占位符；确定性重活全部由脚本完成，可重复运行。

## 8. 自检清单

- [ ] **`references/expert_playbook.md` §5 专家检查表逐项通过**（未通过项先修复再交付）。
- [ ] `result.json` 的 `output_contract` 与顶层同名键齐全，无类型串、无空壳。
- [ ] `case_id` 与输入一致；`status` 合理。
- [ ] `revised_manuscript.md` 非空，原句逐字保留，注记块可定位。
- [ ] 每条注记有 `source_quote` + `locator`，quote 为原文子串。
- [ ] `change_log.json` 含 propose/accept/reject；`version_compare.md` 含回滚与重放验证。
- [ ] 非法操作被拒绝且状态哈希不变。
- [ ] 全部产物无 `待写`/`TBD`/`null`/`pending` 等占位符。
