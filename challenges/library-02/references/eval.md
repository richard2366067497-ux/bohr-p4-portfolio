# references/eval.md — 基础 Agent 与本 Skill 的对照评估（library-02）

对照条件严格一致：**同一文件库、同一组提问、同一权限**，唯一变量是"是否使用本 Skill"。
所有指标都能由 `output/` 与 `work/` 产物独立复算，不依赖自述。

## 一、两条路径

- **基线（基础 Agent）**：只有通用文件读取工具。列目录 → 按文件名/全文关键词逐一打开候选 → 目视比对页码与版本 → 手工摘抄片段。无章节/段落编号，无哈希去重与版本链，页码靠目视流传。
- **本 Skill**：`python3 -B scripts/main.py all --input /input --out /app/output --work /app/work`。脚本做切分、编码判定、别名/同义扩展、哈希去重与版本链、硬过滤执行、页码映射并预填候选引文；Agent 只裁决，脚本再逐字校验引文与 locator。

## 二、对照指标（同库同问同权限）

| 指标 | 基线 | 本 Skill | 复算方式 |
|---|---|---|---|
| query 命中率（给出可定位答案或如实标 not_found/blocked_by_filter） | 依赖人工不漏项，重名/旧版混入时易答错 | 逐 query 预填候选 + 过滤台账，缺口显式化 | `answers.json` 各 `status` 计数 vs `work/queries.json` 的 query 数 |
| 定位准确率（locator 可回链、页码/段落正确） | 页眉页脚与物理页差 1–3 页时不可靠 | 给出 `page_physical/page_printed`；无固定页声明 `not_applicable` 改用段落号 | 抽查 `evidence[].quote` 能否按空白归一回链 `index.json` 对应段落 |
| 引文逐字率 | 手工摘抄常有改写/省略 | 不匹配即拒收并降级，不虚报 | `verify_report.json → quote_hit_rate` |
| 回链可靠率（哈希/来源/日志） | 无哈希、无操作日志 | 每条证据带 `sha256_16` 与路径；`run.log`、`check_report.json`、`verify_report.json` | 三个文件是否齐全且与 `index.json` 一致 |
| 过滤执行率 | 易被"放宽条件"绕过 | 硬过滤逐条求值，不可满足即 `blocked_by_filter` | `filters_log.json` 与各 answer 的 `rejected_evidence.reason` |
| 副本/旧版误引 | 常把副本或旧版当证据 | 同哈希 `identical_copy`、近似 `version_chain`，只留代表版本 | `dedupe.json` + `index.excluded_evidence[]`（`evidence_ban` 键投影） |
| 异常路径识别 | 加密/扫描件/损坏/权限文件易被当成"读了但没提" | 8 类异常逐项入 `failures.json`/`excluded_evidence` | `work/fixtures_report.json → all_expected`、`duplicate_ok` |
| 人工步骤 / 耗时 | 逐文件翻阅 + 目视比对，随库规模线性增长 | 复核候选 + 裁决；脚本侧 0 次模型请求、秒级 | `result.json → runtime.script_seconds`、`model_requests_by_script` |

## 三、复现命令

```bash
python3 -B scripts/main.py all --input /input --out /app/output --work /app/work
cat /app/output/verify_report.json       # 引文逐字率、locator 一致率、契约键回填、fails[]
cat /app/work/fixtures_report.json       # 异常路径 8/8 与重名去重
cat /app/work/run.log                    # 命令 / 耗时 / 摘要
```

## 四、创新点与边界（对应创新增益维度）

| 方法 | 相对基线的实质改进 | 边界 |
|---|---|---|
| 章节+段落双粒度切分 | 引用落到段落，可回链、可复算 | 无标题层级且无空行的纯文本退化为单段 |
| 页码映射（`/PageLabels` → 页脚抽样 → 偏移假设） | 印刷页/物理页都给，并标注来源 | 无页脚且无 PageLabels 时只能 `assumed_equal`，在 `uncertainties` 声明 |
| 同义/别名扩展 | 术语异写也能命中，提升召回 | 词表外的领域新词需案例在 `synonyms` 声明 |
| 哈希去重 + 版本链 | 副本/旧版不进证据，避免错引 | 改写幅度大的版本不并联（宁缺不错） |
| 硬过滤前置 | 过滤执行可审计，不放宽 | 过滤条件自相矛盾时只能如实报 `blocked_by_filter` |
| 候选预填 + 逐字校验 | Agent 漏写也降级不丢分；改写引文被拒收 | 语义裁决仍由 Agent 负责 |

## 五、结论

同输入同权限下，本 Skill 把"能否定位到章节级证据"从人工目视变成可复核的机械流程：命中率与回链可靠率的提升来自索引与校验，抗干扰能力来自去重/版本链与页码映射，人工成本从"逐文件翻阅"降到"复核裁决"。以上数字均可在 `§三` 命令与产物中复算，不依赖自述。
