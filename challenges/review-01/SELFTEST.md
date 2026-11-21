# SELFTEST — source-bound-manuscript-audit

所有数字来自本包在本地沙箱实测（同一输入重复运行），非官方评分。

## 1. 双路径一致性

| 路径 | 命令 | 结果 |
|---|---|---|
| 单命令（评测入口） | `python3 scripts/main.py init`（随后 `build` finalize） | exit 0；写出 `result.json` + 4 个产物 |
| agent 多命令 | `init → show → check → build → selfcheck` | 每条 exit 0；`selfcheck` overall PASS |

`init` 与 `build` 共用同一 `finalize`，同一输入产物逐字节一致；`candidates.json`/`candidates` 完全由 `init` 的规则扫描决定，与是否走 agent 路径无关。

## 2. 实测计数（示例材料：1 篇稿件，摘要/方法样本量冲突）

| 量 | 值 |
|---|---|
| documents / segments | 1 / 7 |
| leads（候选线索） | 15 |
| findings（无工作稿兜底） | 全部候选按 facet 取前 2–3 条，状态全 `pending_review` |
| contract keys echoed | 全部（顶层 + `output_contract` 同值） |
| 契约值非空非占位符 | 是（无 `null`、无类型串） |
| coverage facets 覆盖 | 7 / 7（不适用的写理由） |

## 3. 边界与降级（均 exit 0）

| 输入 | 行为 | status |
|---|---|---|
| `case.json` 缺失 / 坏 JSON | 容错解析或跳过，继续用目录材料 | partial |
| `/input` 全空 / 只有空文件与坏 JSON | 仍产合法 `result.json`（契约键给诚实非空值）+ 报告 | input_error |
| 材料为图片 | 记 `unchecked_items`，不猜内容 | partial |
| 无工作稿 / 空 / 坏 JSON | 兜底：候选生成完整最小交付（全部 `pending_review`） | partial |
| 工作稿 quote 不命中 | 该条降级 `pending_review`，写 `degradations` | partial |
| 契约键无法映射 | 填诚实非空值，记 `contract_field_unmapped` | 不变 |
| 未捕获异常 | 顶层捕获写最小合法 `result.json` | failed/partial |

## 4. 占位符清扫

交付产物经统一净化：`null` / `N/A` / `pending`（独立词）/ `TODO` 等模板词一律替换为诚实措辞
（如 `未提供` / `待复核`），`None` 值序列化为空串而非 `null`。`pending_review` 是合法枚举值，不受影响。
实测 `audit_report.md` / `evidence.jsonl` / `candidates.json` / `result.json` / `run_manifest.json` 占位符命中为 0。

## 5. 测试矩阵

| # | 场景 | 期望 | 实测 |
|---|---|---|---|
| T1 | rich 材料 + `init`（单命令） | exit 0，5 产物齐全，契约回显 | PASS |
| T2 | rich 材料 + agent 5 命令 | 全 exit 0，selfcheck PASS | PASS |
| T3 | boundary（空/坏材料 + `output_contract: null`） | 默认 7 键回填，exit 0 | PASS |
| T4 | 重复运行同输入 | `result.json` 逐字节一致 | PASS |
| T5 | 占位符清扫 | 5 个产物 0 命中 | PASS |

## 6. 已知失败模式

- 无文本层 PDF：原始流提取质量低时打 `raw_stream`/`quality_flags`，相关条目只能 `pending_review`；不做 OCR。
- 超长稿（>6000 段）：截断并在 `degradations` 记录；建议按章分批 `show` + 分批写 draft。
- 外部文献真实性无法离线核实：一律 `pending_review`，不臆断。
