# draft.json 字段字典与校验代码表

`init` 在 `/app/work/draft.json` 生成模板。**只填值，不删键**。`check` 依据本表判分，`build` 依据本表排版。

---

## 1. 完整结构（注释仅用于说明，不要写入 JSON；字段含义见 §2）

```text
{
  "audience": {"label": "对科学有兴趣的普通读者", "profile": "受过高等教育、无本领域训练",
               "knowledge": "知道 DNA，不懂碱基与脱靶", "goal": "判断成果能否用于治疗",
               "depth": "每个术语首现给一句白话", "term_policy": "缩写首现即展开，不出现仪器名",
               "strength_policy": "体外结果一律标注在细胞模型中"},
  "genre": {"label": "科普文章", "conventions": ["问题切入", "机制白话", "局限单列"],
            "length_target": 800, "length_unit": "字"},
  "headline": "一句话结论（含对象与效果，不夸大）",
  "deck": "可选导语/副标题，一句",
  "sections": [{"id": "S1", "title": "小标题", "text": "成稿正文段落……",
                "cites": ["M1:P3"], "strength": "established"}],
  "retained": [{"id": "R1", "kind": "number", "value": "87.5%", "locator": "M1:P3",
                "quote": "编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01）",
                "where": "S3", "treatment": "kept", "note": "保留起点值，未取整"}],
  "trace":   [{"section_id": "S1", "source_locator": "M1:P3", "source_quote": "逐字原文",
               "decision": "compress", "note": "转写为可理解类比，事实不变"}],
  "changes": [{"action": "compress", "locator": "M1:P6", "original_quote": "逐字原文",
               "revised_quote": "（未进入正文）", "reason": "复现信息，非判断依据"}],
  "dropped": [{"item": "测序平台与深度", "locator": "M1:P6", "why": "方法细节，删去不影响结论适用范围"}],
  "glossary": [{"term": "BE-3", "expansion": "碱基编辑系统（可定点改写单个碱基）",
                "usage": "BE-3", "variants": ["BE3"], "locator": "M1:P3"}],
  "numbers_allow": [{"value": "90%", "reason": "源文 87.5%，按上限取整（待作者确认）"}],
  "open_questions": [{"issue": "题面未指定读者年龄层", "why": "影响解释深度",
                      "action": "作者确认后调整", "owner": "author"}],
  "uncertainty": ["体外结果向体内外推尚未验证"]
}
```

---

## 2. 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `audience.label` | 是 | 受众标签；其余 5 项缺失只提示，不阻断，但适配说明会空 |
| `genre.label` / `length_target` | 是 | `length_target` 是**上限**；超 105% 直接判 `over_budget` |
| `sections` | 是 | ≥3 段为宜；`text` 必须是**成稿正文**，不是要点、不是提纲 |
| `sections[].cites` | 建议 | `M1:P3` 或列表；不存在的 locator 判错 |
| `sections[].strength` | 建议 | `established` / `preliminary` / `hypothesis` 三级，只降不升 |
| `retained` | 是 | 每条 = 值 + locator + 逐字 `quote` + `where` + `treatment` |
| `trace` | 是 | **每个 section 至少 1 条**，否则 `trace_missing_for_section` |
| `changes` | 是 | 每条 `action` + `reason`；`original_quote` 建议逐字 |
| `dropped` | 建议 | 声明删除了什么、为何不是证据；有它才不算"悄悄删证据" |
| `glossary` | 建议 | 面向公众/政策读者时必填；`variants` 列出**禁用**说法 |
| `numbers_allow` | 建议 | 换算/取整的唯一合法出口，会同时进 `open_questions` 语义 |
| `open_questions` / `uncertainty` | 建议 | 直接成为 `result.json.pending_human` / `.uncertainty` |

`kind` 枚举：`conclusion | number | condition | sample | metric | figure | citation | limitation | term`
`treatment` 枚举：`kept | condensed | moved | reworded`（**压缩也算保留**，但 `note` 要写清怎么压的）
`decision` 枚举：`keep | compress | merge | split | drop`

---

## 3. 校验代码表（`work/check.json` 与 `result.json.errors`）

### 3.1 错误（阻断 `status=ok`）

| 代码 | 含义 | 修复 |
|---|---|---|
| `draft_not_object` | 顶层不是对象 | 用 `{ }` 包住全部字段 |
| `draft_unreadable` | JSON 语法错误 | 查逗号、引号、括号；中文引号不是 JSON 引号 |
| `missing_field` / `empty_field` | 六大块缺失或为空 | 补齐 `audience/genre/sections/retained/trace/changes` |
| `too_few_sections` / `section_empty` | 只有 1 段 / 某段无正文 | 写真正的段落 |
| `too_short` | 正文 < 目标 45% | 补写成稿，不是扩写标题 |
| `over_budget` | 正文 > 目标 105% | 先删 P2，再压 P1，不动 P0 |
| `locator_not_found` | locator 不在索引 | 回 `init` 段落清单重抄 |
| `*_quote_miss` | quote 在源文找不到 | 换成源文原句；**禁止改源文** |
| `number_not_in_source` | 成稿数字源文没有 | 改回原值，或登记 `numbers_allow` + `open_questions` |
| `figure_mismatch` | 引用了源文没有的图表编号 | 删掉或改用源文编号 |
| `retained_not_in_body` | 必保留项没落进正文 | 补进正文；确需改写则在 `note` 说明并可标 `reworded` |
| `retained_value_missing` / `retained_locator_missing` | 保留项不完整 | 补值/补定位 |
| `trace_section_unknown` / `trace_missing_for_section` | 对照表指向不存在/漏段 | 每段至少一条 |
| `change_action_missing` / `change_reason_missing` | 改动无法复核 | 补 action 与 reason |
| `dropped_reason_missing` | 删除无理由 | 写清"为何是冗余不是证据" |
| `term_variant_used` | 正文用了术语表禁用的变体 | 统一说法 |
| `hedge_lost` | 源文有 ≥3 类限定语，成稿一处未留 | 把"初步/尚需/可能"补回 |

### 3.2 提示（不阻断，但需逐条阅读后接受或修复）

| 代码 | 含义 |
|---|---|
| `short` / `long` | 篇幅在 45–70% 或略超上限 |
| `no_length_target` | 题面未给上限，按体裁常规处理 |
| `section_too_short` / `few_sections` | 某段过短 / 只有 2 段 |
| `audience_field_empty` / `genre_label_missing` | 画像字段没填 |
| `retained_quote_missing` | 有条目没给逐字证据，无法核验 |
| `retained_where_unknown` | `where` 不指向任何 section |
| `retained_reworded_absent` | 标了 reworded 但正文无原值 |
| `preserved_not_in_body` 类（`retained_not_in_body` 的提示态） | 见上 |
| `silent_drop` | 有候选保留项既未进正文也未在 `dropped` 说明 |
| `abbr_not_expanded` | 缩写首现未展开，且术语表未给全称 |
| `strength_upgrade` | 正文出现源文没有的因果/绝对化措辞 |
| `hedge_thin` | 限定语覆盖不足源文 40% |
| `unit_variant` | 数值对得上但单位写法不同 |
| `numbers_allow_used` | 用了白名单数值，需作者确认口径 |
| `meta_discourse` | 出现"本文将……"式元话语 |
| `low_coverage` | 进入对照的源段落 < 15% |
| `contract_missing` | `result.json` 缺契约字段（`build` 前不适用） |

---

## 4. 一条完整示例（示例，非正式案例结果）

源文 `M1:P4`：「编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01），脱靶位点数由 14 个降至 3 个（图 2）。」

```json
{"id": "R2", "kind": "number", "value": "87.5%", "locator": "M1:P4",
 "quote": "编辑效率由 62.1% 提升至 87.5%（n=48，p<0.01）",
 "where": "S3", "treatment": "kept", "note": "起点值与终点值同时保留，未取整"}
```

**反面写法**（`check` 报 `number_not_in_source` / `retained_not_in_body`）：「效率提升到接近九成」
（数值与单位消失）；「效率提升了约 25 个百分点」（源文无此换算，属新增结论）；「脱靶问题已基本
解决」（强度升级，3 个 ≠ 0 个）。

## 5. 写作口径

`text` 不写元话语、一段一义、首句承载结论；数字/单位/样本量/比较基准按原文照搬；源文没有的
商业前景/成本/时间表一律进 `open_questions`；压缩只能到一句话时，被压内容进 `changes`
（`action=compress`）并写理由。
