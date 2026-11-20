# 检索对账手册（playbook）

本文件两块：**A. 库适配与字段映射**（库识别、记录路径、同义词、语义陷阱、额度口径），
**B. 工作稿 schema 与校验规则**（Agent 要写的 `draft.json`、投票与优先级、check 项、示例）。
改库或加库时先改 A 表，再改 `scripts/ledger.py` 的 `DB_TOKENS`/`SHAPES`/`ADAPTERS`/`SYN`；业务逻辑不动。

## A1. 库识别：两条独立证据

| 证据 | 做法 | 冲突时 |
|---|---|---|
| 文件名元词 | `crossref`、`europepmc`、`epmc`、`scopus`、`wos`、`openalex`、`semanticscholar`、`s2_batch`、`arxiv`、`ieee`、`elsevier`/`sciencedirect`、`springer`/`nature`、`wiley`、`plos`、`mdpi`、`pnas`、`bmj`、`jama`… | 取最长匹配的元词 |
| 响应形状 | `message.items`→Crossref；`resultList.result`→EuropePMC；`search-results.entry`→Scopus；`Data.Records`→WoS；`hits.hits`→Elasticsearch；`response.docs`→Solr；`feed.entry`→Atom；`results`→OpenAlex | 形状证据可覆盖 `unknown`/`publisher` 猜测 |

两条证据都写进 `intake_ledger.md` 的 `库归属依据` 列（`filename` / `+shape:xxx`），
评审能看出每个库的身份是**推断**来的，不是声称的。

## A2. 记录列表路径与字段路径

| 库 | 记录列表 | 题名 | 作者 | 年 | 刊名 | DOI | 标识符 |
|---|---|---|---|---|---|---|---|
| Crossref | `message.items[]` | `title[0]` | `author[].family`+`given` | `issued.date-parts[0][0]` | `container-title[0]` | `DOI` | — |
| EuropePMC | `resultList.result[]` | `title` | `authorList.author[].fullName` | `pubYear` | `journalInfo.journal.title` | `doi` | `pmid`,`pmcid` |
| OpenAlex | `results[]` | `title`/`display_name` | `authorships[].author` | `publication_year` | `primary_location.source.display_name` | `doi` | `ids.pmid` |
| Semantic Scholar | `data[]` | `title` | `authors[].name` | `year` | `venue`/`journal.name` | `externalIds.DOI` | `externalIds.PubMed` |
| Scopus | `search-results.entry[]` | `dc:title` | `dc:creator` | `prism:coverDate` | `prism:publicationName` | `prism:doi` | — |
| Web of Science | `Data.Records.records.REC[]` | `titles.title[0].value` | `names.name[]` | `pub_info.pubyear` | `titles.title[0].title` | `other.identifier` | `other.ids` |
| 出版商 JSON | 顶层数组 / `data` | `title` | `author[]` | `published`/`copyrightYear` | `journal` | `doi` | — |
| 出版商 HTML | `$.meta[]` | `citation_title` | `citation_author`（多行同名） | `citation_publication_date` | `citation_journal_title` | `citation_doi` | — |
| CSV/TSV 导出 | `$.rows[]` | 表头同义词 | 同左 | 同左 | 同左 | 同左 | 同左 |

`pick()` 支持数组广播：路径 `author.family` 在 `author` 为数组时会对每个元素取 `family`，
因此不需要写 `author[].family` 这种语法。

## A3. 语义陷阱（写进 conflicts 的理由来源）

| 陷阱 | 表现 | 处置 |
|---|---|---|
| 年份口径不同 | Crossref `issued` 是最早公开年（可早于卷期年 1 年）；EuropePMC `pubYear`；Scopus `prism:coverDate`；出版商 `published`/`copyright` | 统一取"版本年"，冲突写入 `conflicts[]` 由 N-03 排序，**不得静默取第一个** |
| 题名数组/带标签 | Crossref `title` 是数组；EuropePMC/出版商摘要带 JATS/HTML 标签 | `strip_tags` + 取首元素；长度<8 或整体大写视为 `suspect` |
| 作者表示不同 | `family`+`given` vs `fullName`("Zhang W") vs 整串("Garcia M; Chen L") | 归一为 `Family, Given`；比较时只看首作者姓（去空格小写） |
| 刊名缩写 | `Nature Biotechnology` vs `Nat. Biotechnol.` | N-04 取更长/更完整者，并在 conflicts 保留差异 |
| DOI 前缀与大小写 | `https://doi.org/10.xxxx/ABC` vs `10.xxxx/abc` | N-05 归一为小写裸 DOI，Crossref 形态优先 |
| 标识符嵌层 | S2 的 `externalIds.DOI`、OpenAlex 的 `ids.pmid` | 适配表显式列出，不靠顶层同名键猜 |
| 列表为空 vs 字段不存在 | `"abstract": ""`（导出含列但空） vs 根本没有该列 | 前者 `missing` + note "key present but empty"，后者 `missing` + note "does not expose" |
| 结构未识别 | 未知厂商 JSON、被截断响应 | `unknown`，**不当作 missing**，不计入覆盖率分母的口径要说明 |
| 响应是错误对象 | `{"status":429,...}`、`{"error":{"message":...}}`、`"rate limit"` 文本 | 该库标 `FAILED(reason)`，四处一致（query_matrix / coverage / reconciliation / degradations） |
| 撤回/更正 | `update-to`、`is-retracted`、`commentType` | 当前版本不判定撤回状态，遇到只在 note 记 `retraction-flag present`，不据此删记录 |

## A4. 额度与授权口径（写清楚，不绕限制）

| 库 | 常见额度 | 本 Skill 的处理 |
|---|---|---|
| Crossref REST | 公共池礼貌使用，`mailto` 提供联系人可获得更好服务 | 只读离线快照；分页用 `rows`+`cursor` |
| EuropePMC | REST 匿名有限额，`pageSize` ≤1000 | 快照读取；`pageSize`/`cursorMark` 记在 query_matrix |
| OpenAlex | 免费、建议 `mailto`，有 10 万/日上限 | 只读快照 |
| Semantic Scholar | 无 key 约 1 rps，批量导出优先 | 走 CSV 导出，避免逐条请求 |
| Scopus / WoS | 订阅制，配额按机构；429/401 常见 | 只用提供的导出；429 视为失败库并报缺口 |
| 出版商站 | 反爬与 robots 限制 | 不抓取，只解析已给出的 JSON/HTML 快照 |

**不做**：绕过配额、伪造 API key、把未授权数据汇总到未批准服务、用镜像站点绕限制。

## A5. 新增一个库的最小步骤

1. `DB_TOKENS` 加元词（文件名稳定片段）；2. 有特征包装键就在 `SHAPES` 加 `(db, (键…))`；
3. `ADAPTERS` 加字段路径（不写的字段自动走 `SYN` 兜底）；4. 在 A2/A3 补一行；
5. 用 `python3 scripts/main.py init --input <样本>` 看 `records` 视图，确认 `src_field` 指到了正确的原始路径。
6. 跑 `check`/`selfcheck`，确认 locator 回放与 `raw_sha` 一致。

## A6. 字段同义词表（`SYN` 摘要）

- 题名：`title` `titles` `articleTitle` `documentTitle` `primaryTitle` `displayName` `titleText` `mainTitle` `name`
- 作者：`author` `authors` `authorList` `authorName` `creators` `contributors` `byline` `authorships` `names` `person`
- 年：`year` `pubYear` `publicationYear` `published` `issued` `publishedDate` `pubDate` `coverDate` `copyrightYear` `date` `pub_info`
- 刊名：`venue` `journal` `journalTitle` `container-title` `source` `publicationName` `host` `bookTitle` `series`
- DOI：`doi` `dois` `digitalObjectIdentifier` `prism:doi` `articleId`
- 摘要：`abstract` `abstractText` `summary` `description` `teaser`
- 其他：`pmid` `pmcid` `arxiv` `volume` `issue` `page(s)` `type` `url/link/href`

`citation_*` 前缀会自动剥掉再匹配（`citation_journal_title` → `journaltitle` → 刊名），
所以 HTML meta 页不需要额外适配器也能取到题录。

---

## B0. 工作稿是什么

路径 `/app/work/draft.json`（`--draft` 可覆盖）。它是唯一需要 Agent 手写的东西；`build` 只把它
变成结构化产物并校验。**没有工作稿也能 build（降级），但记录会标 `unscreened`、`status=partial`。**

## B1. 字段定义

```jsonc
{
  "schema": "federated-search-reconcile/draft@1",   // 可选，仅标识
  "research_question": "一句话研究问题 + 时间窗 + 物种/领域限制",   // 判断 1
  "scope": {
    "databases": ["crossref", "europepmc"],           // 实际可用的库（失败库另在 gaps 说明）
    "time_window": "2018-2024",
    "inclusion": ["用碱基编辑器改造作物农艺性状的原始研究"],
    "exclusion": ["非作物物种", "仅 Cas9 敲除"]
  },
  "query_matrix_notes": [                             // 判断 2：逐库查询适配（不是同一条查询复制）
    {"db": "crossref", "topic_terms": "base editing crop",
     "field_scope": "query.bibliographic", "time_window": "2018-2024",
     "paging": "rows=20, cursor=*", "query_sent": "query.bibliographic=...&filter=from-pub-date:...",
     "calls": 1, "locator": "materials/crossref_q1.json#$.status",
     "note": "Crossref 不支持 TITLE_ABS，改用 bibliographic 字段"}
  ],
  "normalization_overrides": [                        // 判断 3：改写/补充字段语义
    {"rule_id": "N-03", "db": "crossref", "field": "year",
     "semantic": "issued 视为版本年，不作卷期年推断",
     "reason": "抽样核对与 EuropePMC pubYear 一致", "locator": "materials/crossref_q1.json#$.message.items[0]"}
  ],
  "cluster_decisions": [                              // 判断 4：同文判定
    {"pair": ["R-0001", "R-0003"], "decision": "duplicate",
     "reason": "DOI 相同 + 标题一致", "quote": "题名逐字证据（可选，会被校验命中）"},
    {"pair": "P-0007", "decision": "distinct", "reason": "同作者同年的不同研究"},
    {"pair": ["R-0005", "R-0006"], "decision": "maybe", "reason": "疑似同文但缺 DOI，需人工仲裁"}
  ],
  "conflict_resolutions": [                           // 判断 5：冲突取值（优先于规则）
    {"cluster": "C-0001", "field": "abstract", "value": "改写后的取值",
     "reason": "EuropePMC 版本含章节词污染", "locator": "materials/crossref_q1.json#$.message.items[0]"}
  ],
  "screening": [                                      // 判断 6：相关性（脚本不代判）
    {"cluster": "C-0001", "verdict": "include", "reason": "直接对应作物性状", "locator": "..."},
    {"rid": "R-0004", "verdict": "exclude", "reason": "非作物物种"}
  ],
  "coverage_notes": [                                 // 判断 7：缺口归因
    {"db": "semanticscholar", "field": "abstract", "state": "missing",
     "reason": "导出 CSV 的 abstract 列为空", "locator": "materials/s2.csv#$.rows[0]"}
  ],
  "gaps": [
    {"item": "Scopus 429 配额耗尽", "kind": "failed_database", "note": "需恢复配额重跑",
     "locator": "materials/scopus_q2.json#$.status"}
  ],
  "ranked": [                                         // 排序（缺省按 verdict→完整度→年份）
    {"cluster": "C-0001", "rank": 1, "reason": "证据最完整（3 库一致）"}
  ],
  "status_note": "一句话说明本次完成度与未完成项"
}
```

`verdict` 允许：`include` / `exclude` / `uncertain`（也接受 in/keep/out/drop/unclear/maybe）。
`decision` 允许：`duplicate` / `distinct` / `maybe`（也接受 dup/same/merge/different/split/unsure）。
`pair` 可写 `["R-0001","R-0003"]` 或候选对 id `"P-0002"`。`screening` 的键可以是 `cluster` 或 `rid`。

## B2. 去重投票（`check` 会复算，可与 `show` 对账）

| 信号 | 权重 |
|---|---|
| DOI 归一值相同 | +3 |
| 标识符族相同（pmid / pmcid / arxiv 任一） | +2 |
| 标题相似度 ≥0.92 | +2 |
| 标题相似度 ∈[0.80, 0.92) | +1 |
| 首作者姓 + 年份同时一致 | +1 |

- 相似度 = `max(difflib.SequenceMatcher.ratio, 词元 Jaccard)`，比较前做小写、去标签、去停用词。
- 阈值：`≥4` duplicate，`=3` maybe（不合并，等签字），`≤2` distinct。
- 候选对由分块产生（共享 DOI / 标识符族 / 首作者姓+年 / 标题 bigram），不是全量 O(n²)。
- 工作稿的 `cluster_decisions` **覆盖**同一条规则判定；`maybe` 判成 `duplicate` 即视为人工签字合并。

## B3. 字段优先级（`normalize_rules.json` 的规则来源）

| 规则 | 字段 | 优先级 |
|---|---|---|
| N-01 | title | 非 suspect > 库优先级 > 字符串更长 |
| N-02 | authors | 结构化 family/given > 库优先级 > 作者数更多 |
| N-03 | year | 库优先级（出版商/Crossref > 聚合器），同级取更早 |
| N-04 | venue | 非 suspect > 库优先级 > 更长（完整刊名） |
| N-05 | doi | Crossref 注册形态优先，免得大小写/前缀差异制造假冲突 |
| N-06 | abstract | 库优先级 > 更长 |
| N-07 | identifiers | 各标识符族独立保留，**不做跨族换算** |
| N-08 | missing vs unknown | schema 应有而没有=`missing`；结构未识别=`unknown` |
| N-09 | 其他字段 | 仅用于核对，不参与投票 |

库优先级：出版商/PLOS/MDPI/PNAS/BMJ/JAMA…=9 > Crossref=8 > PubMed/EuropePMC=7 > Scopus/WoS=6 >
OpenAlex=5 > S2/DOAJ/J-STAGE=4 > arXiv=3 > 其他=2。

## B4. `check` 的校验项（真实返回 PASS/FAIL）

| 检查 | 含义 |
|---|---|
| `draft-present` | 工作稿可解析（JSON 坏掉会报 `errors[]`） |
| `draft-sections` | 关键段落空 ≤3 个 |
| `locators` | 工作稿里每个 `文件#指针` 都能在原始输入上回放 |
| `quotes` | 每个 `quote` 能在某份材料里逐字命中（归一化大小写与标签后） |
| `contract-keys` | `output_contract` 键都有语义落点（列出未映射键） |
| `cluster-coverage` | 聚类非空（有记录时） |
| 计数 | `records / pairs / duplicates / maybe / canonical / screened / conflicts` |

`check_report.json` 里的 `problems[]` 是硬错误（对引用不存在、verdict 非法、locator 不解析），
`warnings[]` 是软问题（段落缺失、quote 未命中）。**问题要改工作稿，不要改断言。**

## B5. 最小调用示例（示例数据，非正式案例结果）

输入（`/input`）：

```text
case.json
task.md
materials/crossref_q1.json      # message.items[] 2 条
materials/europepmc_q1.json     # resultList.result[] 2 条（含 1 条与 Crossref 同 DOI）
```

`case.json`：

```json
{"case_id": "demo-01",
 "task_instruction": "检索碱基编辑在作物中的应用（2020-2024）",
 "output_contract": {"merged_records": "去重后的记录", "field_coverage": "库×字段覆盖", "status": "状态"}}
```

命令与预期输出（示意）：

```text
$ python3 scripts/main.py init
[init] files=3 records=4 databases=crossref,europepmc pairs=1 rule_duplicates=1
[init] partial result.json written -> /app/output/result.json

$ python3 scripts/main.py show --view records
R-0001 [crossref] materials/crossref_q1.json#message.items[0]
    title    present  title.0   Precision base editing in rice
...

$ python3 scripts/main.py check      # 写完 draft.json 之后
[PASS] draft-present / [PASS] locators 12 tested, 0 failed / [PASS] contract-keys 3 keys, 0 unmapped

$ python3 scripts/main.py build
[build] records=4 pairs=1 dup=1 maybe=0 canonical=3 conflicts=1 gaps=2
[build] status=ok contract_keys=3 unmapped=0
```

产物：`intake_ledger.md`、`query_matrix.csv`、`normalize_rules.json`、`merge_cluster.jsonl`、
`reconciliation.md`、`result.json`。契约键示例值（示意，不是任何正式案例的答案）：

```json
{"case_id": "demo-01", "status": "ok",
 "merged_records": [{"cluster_id": "C-0001", "title": "Precision base editing in rice",
                     "year": 2021, "doi": "10.0000/demo", "source_dbs": ["crossref", "europepmc"],
                     "evidence": {"title": {"src_db": "crossref", "locator": "materials/crossref_q1.json#message.items[0]", "rule": "N-01"}},
                     "relevance": {"verdict": "include", "reason": "作物性状改良"}}],
 "field_coverage": {"matrix": [{"db": "crossref", "records": 2}]},
 "counts": {"records_raw": 4, "clusters": 3}}
```

## B6. 常见错误

1. **只跑 build 不写工作稿** → 记录表有了，但 `screening`/`conflict_resolutions` 全空，`status=partial`，
   相关性列全是 `unscreened`。这在"结果正确性/完整性"上直接掉档。
2. **把 locator 写成文件名**：必须是 `文件#指针`，指针用 `$.message.items[3]` 或 `message.items[3]`。
3. **quote 用自己的话复述**：`check` 会做逐字（归一化后）命中，改写过的句子会失败；不确定就别写 quote，写 locator。
4. **pair 用不存在的 rid**：候选对只包含分块命中的组合，跨块自行拼的对会报 `pair not in candidate set`。
5. **把 `missing` 写成 `unknown`（或反之）**：前者是"库确实没给"，后者是"结构没识别"。混用会让覆盖缺口报告失真。
6. **把 `maybe` 当 `duplicate` 合并**：等同伪造同一性判定；要么给理由签字，要么留着待仲裁。
