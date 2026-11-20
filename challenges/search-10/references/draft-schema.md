# 工作稿 schema 与校验规则（draft.json）

工作稿是你（评审/执行 Agent）**读完材料之后**写的唯一判断载体，路径 `/app/work/draft.json`。
脚本只把它变成结构化产物，并在 `check` 阶段机械校验；它不会替你判断相关性、语种或版本。

## 1. 顶层结构

```json
{
  "questions": [ {...} ],
  "view_labels": [ {...} ],
  "matches": [ {...} ],
  "false_positive_checks": [ {...} ],
  "dedup_note": {...},
  "misses": [ {...} ],
  "status_note": "一句话说明本次判断的边界"
}
```

除 `questions` 与 `matches` 外都可省略；缺字段会在 `check` 里以 `D*` 检查项提示。

## 2. 字段字典

### 2.1 `questions[]`（每题一条，对应 `show` 打印的题号）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question_id` | str | 是 | 与题面一致（`Q1`/`Q2`/…或 case.json 自带 id） |
| `source_lang` | str | 是 | 提问所用语言（ISO 639-1 两字母） |
| `target_langs` | list[str] | 是 | 本题**需要覆盖**的目标语种；材料里没有的语种要写进 `misses` |
| `refined` | str | 否 | 你自己的检索意图复述（不改原问题语义） |
| `target_view_hypothesis` | str | 否 | 你想验证的目标视图 id，可被 `matches` 修正 |

### 2.2 `view_labels[]`（每个发现的视图一条）

| 字段 | 类型 | 取值 | 说明 |
|---|---|---|---|
| `view_id` | str | — | `show`/`init` 打印的视图 id |
| `language` | str | pt/en/es/de/fr/zh/ja/it | 正文语言，不是标题语言 |
| `version` | str | `original` / `publisher_translation` / `abstract_only` / `duplicate` / `preprint` / `erratum` / `undetermined` | 版本类型 |
| `doc_type` | str | `full_body` / `abstract_only` / `unstructured` | 正文完整度 |
| `duplicate_of` | str\|null | view_id | 精确或近重复时指向被重复的视图 |
| `basis` | str | — | **判定依据**（原文里的一句话或文件特征），供他人复核 |

### 2.3 `matches[]`（每个命中一条；未找到的问题不要写空壳，写进 `misses`）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `question_id` | str | 是 | 题号 |
| `work_id` | str | 是 | 命中的 work（同一论文的多语种视图共享） |
| `view_id` | str | 是 | 主证据视图（承载目标版本的那一份） |
| `confidence` | str | 否 | `high` / `medium` / `low` |
| `basis` | str | 否 | 命中理由，一句话，须能被材料支撑 |
| `evidence.quote` | str | 是 | 从主视图**逐字**拷贝的一句话（≥15 字符） |
| `evidence.locator` | str | 否 | `materials/x.md#L20` 形式；不写则由脚本按 quote 反查 |
| `evidence.term_pairs[]` | list | 否 | 跨语种术语对齐证据，见 §3 |
| `false_positive` | obj | 否 | `{method, verdict: pass/review, basis}` |

### 2.4 `evidence.term_pairs[]`（跨语言对齐的硬证据）

```json
{"concept": "cross-cultural adaptation", "concept_id": "G30",
 "source_lang": "pt", "source": "adaptação transcultural",
 "source_quote": "A adaptação transcultural do instrumento de qualidade de vida para idosos",
 "source_locator": "materials/V1_pt_original.md#L15",
 "target_lang": "en", "target": "cross-cultural adaptation",
 "target_quote": "This study describes the cross-cultural adaptation of a quality of life instrument for older adults",
 "target_locator": "materials/V2_en_publisher_translation.md#L13",
 "glossary": "builtin:G30"}
```

规则：

- `target_quote` **必须来自材料**（在任一视图里逐字出现），`check` 会逐字回查。
- `source_quote` 可来自题面（`case.json#task_instruction`）；提问用语本身就是源语侧证据。
- `concept_id` 优先用 `references/glossary.md` 的 cid；术语表未收录时填 `null` 并在
  `false_positive.verdict` 写 `review`，不要伪造译法。

### 2.5 `dedup_note`

```json
{"distinct_works": 3, "counted_hits": 3, "views_total": 6, "duplicates": ["V4_en_duplicate"]}
```

`check` 会把它与脚本自己算的 `views_total`/`distinct_works` 对比；不一致写入
`check_report.json.dedup.problems`。

## 3. 引用与定位规则（决定"可核验"分）

| 规则 | 具体要求 |
|---|---|
| 逐字性 | quote 必须是材料里的连续片段；空白归一化后完全匹配，不改语序、不拼接两段 |
| 最小长度 | ≥15 字符；短于此的 quote 会被 `find_quote` 拒答 |
| 精确性 | 不要把摘要改写成释义；要解释就写在 `basis` 字段 |
| locator | 文件 `materials/<file>#L<行号>`；JSON 容器 `materials/views.json::$.views[2]::sN`；题面 `case.json#task_instruction#L<n>` |
| 一致性 | 同一 quote 在同一视图多处出现时，以首次出现行为准 |

## 4. `check` 判定表

| 编号 | 检查 | 级别 | 失败含义 |
|---|---|---|---|
| D0 | 工作稿存在且是 JSON 对象 | warn | 未写工作稿 → build 走降级分支 |
| D1 | 每题都有 `questions[]` 条目 | warn | 有题未复述意图 |
| D2 | 每题写 `source_lang` | warn | 语种路由缺失 |
| D3 | 每题写 `target_langs` 列表 | warn | 无法统计语种覆盖 |
| D4 | 每个视图都有 `view_labels` | warn | 有视图没判语种/版本 |
| D5 | `view_labels` 的 view_id 都可解析 | warn | 写了不存在的 id（错别字） |
| D6 | `matches` 的 question_id 都在题面内 | warn | 越界题号 |
| D7 | `matches` 的 view_id 可解析 | **error** | 指向不存在的视图 |
| D8 | 每条 match 都带逐字 quote | warn | 无证据命中 |
| K1 | 契约键可回填 | info | 契约键无法映射到产物 |
| K2 | 去重口径与脚本一致 | warn | `dedup_note` 数字错误 |
| K3 | 工作稿全部 quote 逐字命中 | **error** | 引文改写/编造 |
| K4 | 每题都有命中卡 | warn | 有题无结论（未写 `misses` 也算） |

`check` 永远退出 0，报告写到 `/app/work/check_report.json`；`build` 不因 check 失败而中止。

## 5. 版本判定词典（写 `basis` 时引用原文）

| version | 触发信号（原文/文件） | 注意 |
|---|---|---|
| `original` | `versão original` / `original article` / `artigo original` / 文件名含 original | 原文正文，不是摘要 |
| `publisher_translation` | `tradução oficial/autorizada` / `translated by … publisher` / `official translation` | 与原文同 DOI，计同一 work |
| `abstract_only` | `abstract only` / `somente o resumo` / `full text not available` | 不能当正文证据 |
| `duplicate` | 内容 sha 相同或近重复 / `cópia` / `duplicate copy` | 计入台账，不计入命中数 |
| `preprint` / `erratum` | `preprint` / `erratum` / `corrigendum` | 与正式版冲突时写 `uncertainties` |

## 6. 语种判定优先级

1. 材料里声明的元数据（`language:` / `language_of_text`）——最高；
2. 文件名语言标记（`V2_en_…`）；
3. 正文检测（脚本用停用词比值 + 文字系统判定，输出 `confidence` 与命中词证据）；
4. 声明与检测冲突时：以声明为准，但把冲突写进 `view_labels.basis`，并在
   `result.uncertainties` 保留（脚本自动记录 `label_conflict`）。

## 7. 常见反模式（会被 check 抓住）

- 把摘要改写成一句通顺的英文再当 `quote` → K3 失败。
- 用 `view_id` 写文件夹名或 work_id → D7 失败。
- 同一论文的原文与全译各算一条命中 → K2 报 `counted_hits_exceeds_distinct_works`。
- 把"仅摘要"记录当正文证据 → 卡片仍在，但 `doc_type=abstract_only` 会在台账暴露，
  评审会判"证据不足"。
- 术语表没收录就自己编一个译法 → `false_positive.verdict` 必须写 `review`。

## 8. 评分维度 → 工作稿字段

| 评分点 | 工作稿里必须出现的东西 |
|---|---|
| 完成度（3 题都有卡） | `questions[]` + 每题 `matches[]` 或 `misses[]` |
| 正确性（语种/版本/命中） | `view_labels[].language/version/basis` + `matches[].basis` |
| 完整性（双向证据 / 去重口径） | `evidence.term_pairs[]` 成对出现 + `dedup_note` |
| 可核验 | 每条 `quote` + `locator` 能在材料里逐字找到 |
| 使用增益 | `target_langs` 覆盖真实存在的语种，不虚报 |
| 创新 | `term_pairs` 覆盖术语表未直译的词（转发/复合词/音译） |
| 可靠 | 无结果写 `misses` + 原因；冲突写 `false_positive.verdict=review` |
