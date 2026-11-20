# 审查清单、严重度判据与误读抑制（claim-graph-auditor）

## 1. 六类检查项（facet）

| facet | 检查什么 | 典型 finding |
|---|---|---|
| `fact` | 数值、单位、方向是否与正文一致 | 数字无出处、方向相反 |
| `citation` | 引用的文献是否支持被引的那句话 | 引用不支持观点、引用句无对应证据 |
| `method` | 方法能否回答研究问题 | 设计无法支持结论、样本与结论不匹配 |
| `statistics` | 样本量、离散度、显著性是否报告 | 只有均值没有 SD/CI、p 值缺失 |
| `argument` | 前提→结论是否存在跳跃、因果/相关混用 | 相关当因果、替代解释未排除 |
| `structure` | 前言承诺是否交付、章节口径是否一致 | 承诺未交付、摘要与结论不一致 |

## 2. 节点与边的判据

节点：`claim`、`cited_view`、`hypothesis`、`evidence`、`definition`、`obligation`。
边：

- `supports`：证据单元与主张共享主题词，或证据报告了测量数字。
- `overclaims`：主张强度 ≥3 而同一节内无离散度/显著性统计；或主张带引用但同节无证据单元。
- `unaddressed`：`obligation` 无匹配 `claim`；或 `cited_view` 在同节没有证据支撑。
- `contradicts`：两条主张对同一主题词给出相反方向（升/降），且极性一致（同为正述或同为否定）。
- `delivers`：前言承诺与后续主张共享 ≥2 个主题词。

## 3. 严重度判据

| 严重度 | 判据 |
|---|---|
| `critical` | 因果确定级主张无统计支撑，直接影响主结论 |
| `major` | 断言级主张无统计支撑；承诺未交付；跨句方向矛盾 |
| `minor` | 数值缺离散度；引用句缺同节证据 |
| `suggestion` | 规范性改进，不影响主结论（可执行即可） |

## 4. 误读抑制清单（必须逐条排除）

1. 明确标注的假设情形（`assume/hypothesis/假设`）不报为"证据不足"。
2. 转述他人观点（`cited_view`）不计入作者主张的强度问题。
3. 有意设置的对照组、安慰剂组不报为自相矛盾。
4. 只报有原文逐字引用的条目；定位不到句子的一律进 `review_pending`。
5. 无法判断的（缺全文、扫描版无文本、超长截断）写降级，不补结论。

## 5. 降级矩阵

| 情形 | 行为 |
|---|---|
| 材料无文本 / 扫描版 | 记降价，`truncated_sections` 标 `no readable material`，status `insufficient_evidence` |
| 超长文件 | 只审前若干单元，明确记 `truncated`，不宣称全文审完 |
| PDF 无 `pdftotext` | 内置流解析，标 `builtin-pdf-lowconf` 并提示人工核对 |
| 单文件解析失败 | 只降级该文件，其余继续 |
| `case.json` 缺失/坏 | 用默认契约键并记录 |
| 任意异常 | 保留已有产物，`errors` 记录，exit 0 |

## 6. 维护

- 脚本仅用标准库；确定性、可重复。
- 新增 facet 需同时更新 `audit_core.py` 的 `FACETS`/`FACET_RULES` 与本文件表格。
- 改脚本后重跑：`all`（exit 0）、空输入（exit 0 + 合法 `result.json`）、坏 JSON（exit 0）。
