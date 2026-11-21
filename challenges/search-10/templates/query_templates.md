# 多语种查询模板 · 题集 · 案例（query_templates）

本文件是 `scripts/main.py` 生成 `lang_queries.md` / `query_plan.json` 的**规范来源**，也可被他人直接复用。

## 1 查询模板

```text
concept_query(lang, cid)     = "term 1" AND "term 2"          # 术语表在该语种的写法，取前两个
known_item_query(lang, cid)  = concept_query(lang, cid) AND (doi OR "title phrase" OR author AND year)
back_translation_check(cid)  = terms(cid, lang) == reverse(terms(cid, other_lang))
```

规则：

- 查询式**只用术语表里该语种实际存在的写法**；术语表没有的语种不生成查询（`invalid_language_queries = 0`）。
- 概念锚点必须来自材料**逐字出现**的术语；`glossary-grounded` 表示该写法在材料里被直接见到，
  `glossary-projected` 表示由术语表跨语种投射（仍可回查术语表行）。
- 专名（人名、机构、期刊、疾病亚型）**不进术语表**，改用四个专名锚点：`DOI` / 引号短语 / 作者姓 / 年份。

## 2 术语扩展规则

| 规则 | 说明 |
|-|-|
| 同义写法 | 术语表单元格用 `;` 分隔同语种多写法（如 `meta-análise;metanálise`），全部纳入查询 |
| 词形变化 | 只做**词面**扩展（复数/性数），不做语义扩展；语义扩展一律标 `review` |
| 复合词 | 用引号短语锁定（`"cross-cultural adaptation"`），避免被拆词 |
| 音译 | 音译形式不自动生成，缺则 `not-in-glossary` → `pending_human` |
| 回译校验 | 逆映射回源语写法；不一致即 `review`，不覆盖原判 |

## 3 回译校验与假阳性拦截

1. 正向：材料里同时出现两个语种的写法 → 记为一条 `term_pair`（双向逐字引文 + locator）。
2. 反向：用同一 `cid` 从目标语查回源语；若术语表无该映射，写 `not-in-glossary`，**不猜**。
3. 拦截：词面对应但语义错配（如 `scale` 被当成「量表」以外的词义）标 `false_positive.verdict = review`，
   进 `pending_human`。

## 4 翻译服务失败 / 限额的降级分支

| 情形 | 分支 |
|-|-|
| 离线（本包默认） | `translation_service = offline-builtin-glossary (no API call)`，`translation_service_calls = 0` |
| 接入后被限流/超时 | 降级为内置术语表；被影响的概念写 `pending_human`，**不把接口直译当作最终结论** |
| 接口返回空/多义 | 保留术语表写法，另把接口结果只作提示，不写入 `term_pairs` |

## 5 跨语种案例（可复跑）

### 案例 A（pt → en，known-item）

题面：`Encontre o artigo original sobre adaptação transcultural de um instrumento de qualidade de vida para idosos.`
材料：`V1_pt_original.md`（原文）、`V2_en_publisher_translation.md`（官方全译）、`V4_en_duplicate`（副本）。
期望：命中 1 个 work；副本去重；`term_pair(G30)` 双向逐字。

### 案例 B（es → de，摘要版陷阱）

题面给出西班牙语关键词；材料里德语视图只有摘要。
期望：卡片仍在，但 `doc_type = abstract_only` 会在台账暴露，**不作为正文命中证据**；`version = abstract_only`。

### 案例 C（fr → en，术语表未收录）

题面含术语表未收录的机构专名。
期望：该专名写 `not-in-glossary` → `pending_human`；命中改用 DOI/作者/年份专名锚点，
不生成任何臆造译法的查询。

## 6 题集（eval questions）

| id | 题面要点 | 期望输出 |
|-|-|-|
| E1 | 给定 pt 题面 + 原文/全译/副本三视图 | 1 个 work、1 张卡、`duplicates=[副本]`、`term_pair` 双向逐字 |
| E2 | 给定 es 题面 + 仅摘要的 de 视图 | 卡片 + `abstract_only` 暴露，不计正文证据 |
| E3 | 题面含术语表未收录专名 | `not-in-glossary` + `pending_human`，查询式不臆造 |
| E4 | 空材料 / 坏 JSON | `status=insufficient_evidence`，契约仍完整回填，`exit 0` |
| E5 | 重复运行同一输入 | 查询计划、术语对齐、命中卡逐字节一致（确定性） |

## 7 评测口径（与 GAIN_EVIDENCE 对齐）

- 质量：非英语语种查询数、术语对齐对数、术语对齐准确率、逐字命中率。
- 效率：翻译服务调用次数、无效语种查询数、人工核对条数、`elapsed_s` / `requests` / `rounds`。
- 所有指标由 `result.gain_metrics` 与 `result.metrics` 直接给出，可逐项复算。
