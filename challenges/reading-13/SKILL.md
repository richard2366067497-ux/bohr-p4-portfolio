---
name: nanopub-assertions
description: 把一篇论文（PDF 或纯文本）转成原子化、绑定证据的 nanopublication 记录。拆解 + 引文定位 + 来源元数据 + 由证据推导的置信度 + 确定性标识符，输出可直接被下游解析的 result.json；单条命令即可完成，无需先手写草稿。
---

# nanopub-assertions — 原子断言 + 可核验证据

**一句话**：把论文结论拆成单条可判真假的断言，每条绑定一段**逐字引文**、页码与字符偏移、来源元数据、
由证据推导的置信度与确定性标识符，导出机器可读的 `result.json`。

本技能**不写综述**：它产出的是一份评审一分钟内可抽检的证据台账——翻到该页、看那段 span、
判断断言是否被支撑。

单命令评测入口：

```bash
python3 /skills/weekly-skill/scripts/np_build.py --input /input --out /app/output --work /app/work
```

无 draft.json 时直接运行本命令即可产出完整契约与全部交付物；评测环境按此执行。

## 1. 入口命令（单条命令跑完全流程）

这一条命令完成：清单 → 抽文本（`work/corpus.json`）→ 自动拆分断言（或读 `--draft`）→ 定位与检查
（`work/lint-report.md`）→ 构建（内容哈希 id、AIDA、契约映射）→ 门禁复核 → 写
`/app/output/result.json`、`/app/output/assertions.csv`、`/app/output/build.log`。**不传草稿也能出全契约产物。**

可选：手写草稿以覆盖自动拆分

```bash
python3 scripts/np_build.py --input /input --out /app/output --work /app/work \
  --draft /app/work/assertions.draft.json
```

兼容历史两段式（已有 corpus + checked 时）：

```bash
python3 scripts/np_build.py --corpus /app/work/corpus.json \
  --checked /app/work/assertions.checked.json --out-dir /app/output
```

## 2. 输出契约

- 主产物：`/app/output/result.json`（字段字典见 `assets/result-schema.md`）。
- 附带：`assertions.csv`（locator 台账）、`build.log`（门禁结论 + change_log）。
- 中间产物（`--work`）：`corpus.json`、`assertions.checked.json`、`lint-report.md`。
- `case.json` 的 `output_contract` **逐键处理**：可映射的键写入 `contract.fields_provided` 并把值浅拷贝到顶层；
  不可建模的键进 `contract.unmapped_fields`，顶层建一个非空、诚实的占位值。`case_id` 取自
  `case_id`/`caseId`/`id`/`task_id`，取不到为 `null`。

## 3. 执行工作流

1. **发现输入**：扫描 `--input`（默认 `/input`）下的 `*.pdf` / `*.md` / `*.txt`、`task.md`、`case*.json`；
   非法 `case.json` 只记日志、不中断。
2. **抽文本 + 清单**：PDF 用 stdlib 流解析器（解 `FlateDecode`、抽 `Tj/TJ`），纯文本/`markdown` 直接读并按
   分页/约 3000 字符切页；每页记住原始文本与字符偏移，写入 `corpus.json`。文本量过少的页列入 `pages_needing_ocr`。
3. **拆分断言**：无 `--draft` 时，按 `references/atomicity-rules.md` 从文本自动拆：保留含动词、无回指开头、
   长度合理的陈述句，提取 主语/谓语/宾语、数量、极性、关系类型；受 `output_contract.min_assertions` 与
   12–20 条目标约束。不可绑定的句子进 `excluded`。
4. **定位与检查**（`np_lint.py`）：每条引文按 精确 → 归一化 → `>=0.90` 句子窗口 解析出页号与字符区间；
   运行原子化/极性/方向/词表检查；按证据推导置信级别。输出 `lint-report.md`（只列问题）。
5. **构建**：`np:assertion:<sha256-20>`、`np:evidence:<sha256-16>`、`np:w3id.org/np/skill-*` 由规范内容派生
   （同输入同 id）；填 AIDA（assertion/provenance/publication_info）；映射契约；组装 `result.json`。
6. **门禁**：重开 corpus 复核（见 `assets/result-schema.md` 不变量）；不通过则把 `success` 降为 `partial`，
   并把问题写入 `reproduce.gate.problems` 与 `uncertainty`。

## 4. 状态语义（不得拔高）

| status | 条件 |
|-|-|
| `success` | 每条断言都定位为 verbatim（exact/normalized）、0 个 fail，且无 ambiguous/unsupported |
| `partial` | 有页/断言降级、或仅 fuzzy 命中、或自动拆分产物；限界记入 `uncertainty` |
| `unsupported` | 材料无法在要求的粒度上支撑任何断言 |
| `failed` | 输入不可读或结果不可写（找不到论文） |

置信度为有序、证据推导：`direct_verbatim` > `direct_reported` > `inferred` > `aggregated` > `ambiguous` > `unsupported`；
**由脚本赋值，代理只可给 `confidence_basis` 提示，不得手写等级或 id。**

## 5. 异常与降级

| 情形 | 处置 |
|-|-|
| 无 PDF 文本层 / 扫描页 | 该页进 `pages_needing_ocr`，相关断言排除并写 `excluded_claims`；`partial` |
| 引文两次仍定位不到 | 排除，`reason: no_verbatim_evidence`，保留 `nearest_candidate` 与分数 |
| 两条 span 冲突 | 都保留，角色 `supporting`/`contradicting`，级别 `ambiguous` |
| 契约里有无法建模的字段 | 记入 `contract.unmapped_fields` 与 `uncertainty`，顶层给非空诚实占位 |
| 任务语言 ≠ 论文语言 | 断言文本可用任务语言，但实体标签与引文保持源语言 |
| 找不到论文 / 空输入 | `status=failed`，仍写全部必填键与全部契约键，exit 0 |
| 任意内部异常 | 顶层兜底 `try/except`，打印 stderr，**始终 exit 0** |

## 6. 自查清单

- [ ] 单条命令即产出 `result.json` + `assertions.csv` + `build.log`，无需先手写草稿。
- [ ] 门禁 `PASS`（`reproduce.gate.pass=true`）；不通过须已降级并在 `uncertainty` 说明。
- [ ] 每条断言的 `char_start < char_end ≤` 该页文本长度；`fuzzy` 未标 `verbatim`。
- [ ] `output_contract` 每个键都在顶层非空回填；`null` 不丢键。
- [ ] 空输入 / 坏 `case.json` 均 exit 0 且 `result.json` 合法。

## 7. 文件索引

| 路径 | 作用 |
|-|-|
| `scripts/np_build.py` | 入口与主编排：清单、抽文本、自动拆分、构建、契约映射、门禁、写三件套 |
| `scripts/np_lint.py` | 引文定位（exact/normalized/fuzzy）、原子化/极性/方向/词表检查、证据推导置信度（可独立运行） |
| `assets/controlled-vocab.json` | 关系类型、实体类型、断言类型、置信级别与依据、匹配方法 |
| `assets/result-schema.md` | `result.json` 字段字典、草稿映射、门禁不变量 |
| `references/atomicity-rules.md` | 拆分规则与检查 id 对照 |

## 随包方法论（执行前必读）

执行前先阅读 `references/expert_playbook.md`，按其框架、公式与自查表逐项产出并核验；交付前确认「专家检查表逐项通过」。
