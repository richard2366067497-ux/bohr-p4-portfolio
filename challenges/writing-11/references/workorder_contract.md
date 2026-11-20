# 工单契约与注记判定细则（manuscript-revision-desk）

本文件是 `SKILL.md` 的细则补充，供人工复核与二次开发使用。

## 1. 工单字段

| 字段 | 必填 | 含义 | 本包处理 |
|---|---|---|---|
| `target_ids` | 建议 | 允许编辑的段落锚点，如 `["C01-P002","C01-P057"]` | 只处理这些段落；缺失时取前两个锚点段并记降级 |
| `operation_requirements` | 可选 | 要求支持的操作（回执、propose/accept/reject、版本比对、回滚/重放、非法操作异常、可编辑稿件、原始/修订记录、证据地图、导出预览） | 全部映射为交付物与 `result.json` 字段 |
| `project_mode` | 可选 | 项目形态 | 写入 `task_receipt.json` |
| `authority` | 可选 | 工单签发方 | 写入 `task_receipt.json` |

任何**改写正文内容**（润色、合并、删段、改数据）的请求都属于越界，输出 `reject` 记录；
本包只允许"追加注记块"这一种编辑。

## 2. 三类注记的判定

### 2.1 condition（实验条件 / 复现边界）

触发：段落含标准号（ASTM/ISO/GB/T）、样本量、`mean/average`、工艺参数（喷嘴、层高、填充率、温度等），
但缺少离散度（SD/CI/±/error bar）或预处理状态（conditioning/humidity/stored at）。

写法要求：
- 逐字引用含条件的原句；
- 明确"结果只对所列试样与参数成立"；
- 指出缺什么（离散度、预处理），不得补造数值；
- 不把条件外推到其他参数。

### 2.2 limitation（解释边界）

触发：段落报告"从 A 到 B"的端点变化或升降趋势，但没有对应机制的直接测量（如孔洞、孔隙率、断口）。

写法要求：
- 引用趋势原句；
- 标注"关联（association），非已测因果"；
- 指出机制句在 Discussion 是解释而非测量；
- 不外推到其他材料体系。

### 2.3 clarification（术语 / 范围澄清）

触发：既无明确标准号也无趋势数字，但段落含有需要界定范围的术语或缩写。

写法要求：
- 引用定义句；
- 把后续论证限定在该段所述材料、条件与端点。

## 3. 证据与定位

- `locator`：`<相对路径>:L<起始行>`，行号以 `show`/`init` 打印的为准。
- `source_quote`：锚点段落（跨行折行已归一为单空格）中的连续子串；校验用 `quote in paragraph_text`。
- `evidence_map.json` 同时记录 `quote_verified` 与 `original_preserved`，二者都必须为真。
- `preserved_facts.json` 记录数字/单位/标准号/引用锚点，并逐一核对在修订稿中仍出现。

## 4. 版本控制与操作序列

1. `import`：登记 case、workorder、章节与锚点数量。
2. `annotate`：按 target 生成/合并注记。
3. `invalid_operation`：尝试"把段落替换为空串"，必须被拒绝，返回 `INVALID_EMPTY_REPLACEMENT`，
   且 `state_sha_before == state_sha_after`。
4. `rollback`：移除全部注记块，重建文本的哈希必须等于原文哈希。
5. `reapply`：重新插入全部注记，逐条 `annotation_id` 必须存在。

`version_compare.md` 与 `operation_log.json` 是上述序列的可读与可机读版本。

## 5. 故障注入与空输入

| 情形 | 行为 |
|---|---|
| `case.json` 缺失 / 坏 JSON | 使用默认 7 键契约；`degradations` 记录 |
| 无工单 | 取前两个锚点段；`degradations` 记录 |
| 章节为空 | 跳过错章并记录；若全空则 `status=insufficient_evidence` |
| 目标锚点不存在 | 逐条记降级，继续处理其余目标 |
| 草稿 quote 非逐字 | 该条草稿丢弃并记录；无可用草稿时回退规则化注记 |
| 输出目录不可写 | 回退到 skill 同级 `_output`，并记录 |
| 任意异常 | 保留已有产物，`errors` 记录，exit 0 |
