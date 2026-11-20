# 工作稿 `/app/work/draft.json` schema 与判定码

工作稿是 **Agent 亲手写的判断层**。脚本只校验格式与证据，不替你判断归属、版本关系、检索命中与跳过失因。

## 1. 路径写法

所有 `path` 一律使用 **相对 `/input` 的 POSIX 路径**，与 `init` / `show` 打印的完全一致（例如 `library/raw/2019/sampleA_v2.pdf`）。不要写绝对路径、不要写 `./` 前缀、不要把材料根重复拼接。

## 2. 完整字段

```json
{
  "case_id": "C01",
  "files": [
    {"path": "library/raw/a.pdf", "doc_type": "raw_data", "project": "P-001",
     "year": 2019, "is_version_of": "library/raw/a_v1.pdf", "notes": "归属依据"}
  ],
  "organization_plan": [
    {"from": "library/raw/a.pdf", "to": "P-001/2019/raw_data/", "rule_id": "dir-template-v1"}
  ],
  "metadata": [
    {"path": "library/raw/a.pdf",
     "fields": {"author": {"value": "Li Na", "source": "library/meta.csv#r4"},
                "year": {"value": "2019", "source": "library/raw/a.pdf#p1"}}}
  ],
  "versions": [
    {"chain_id": "C1", "members": ["library/raw/a_v1.pdf", "library/raw/a_v2.pdf"],
     "supersedes": "library/raw/a_v2.pdf",
     "basis": "note:supersedes library/versions.csv#r2", "confidence": "high",
     "diff_note": "v2 修订了容量保持率并剔除 2 个电芯"}
  ],
  "duplicates": [{"sha256": "…", "keep": "library/raw/a.pdf",
                  "archive": ["library/raw/a copy.pdf"], "reason": "same sha256"}],
  "queries": [{"question": "…", "hits": [{"path": "library/raw/a.pdf",
               "locator": "library/raw/a.pdf#L12", "quote": "逐字原文"}],
               "miss_reason": "无命中时写检索范围与原因"}],
  "recovery": [{"file": "library/raw/a.pdf", "action": "reindex", "pre_state": "…",
                "expect": "entry conserved", "note": "…"}],
  "skipped": [{"path": "library/raw/b.pdf", "reason": "corrupt"}],
  "uncertainties": ["仍需人工确认的点"],
  "method_notes": "目录模板来源、字段优先级、版本链证据、去重策略"
}
```

### 字段别名（脚本可识别）

| 标准名 | 也接受 |
|---|---|
| `organization_plan` | `plan` |
| `from` / `to` | `source` / `target` |
| `members` | `files`（版本条内） |
| `hits[].quote` | `text` / `evidence` |
| `miss_reason` | `no_hit_reason` |
| `basis` | `evidence` |

## 3. 枚举值

- `files[].doc_type`：`raw_data | paper | supplement | analysis | admin | instrument | other`
- `skipped[].reason`：`permission_denied | corrupt | too_large | empty | symlink | unsupported | duplicate_content`
- `versions[].confidence`：`high`（哈希+备注）/ `medium`（别名或单侧备注）/ `low`（仅命名+时间）
- `recovery[].action`：`restore | reindex | quarantine | none`

## 4. `check` 判定码

**FIX（必须修，否则 `status` 降为 `partial`）**

| 码 | 含义 |
|---|---|
| `draft_missing` | 没有工作稿，`build` 只能走兜底 |
| `path_not_in_index` | `files[].path` 不在扫描结果里（多半是路径写法不对） |
| `plan_source_not_in_index` | `organization_plan[].from` 不在索引里 |
| `plan_target_empty` | 目标目录为空 |
| `metadata_path_not_in_index` | 元数据指向的文件不存在 |
| `metadata_fields_not_object` | `fields` 不是对象 |
| `version_members_too_few` | 版本链成员少于 2 |
| `version_member_not_in_index` | 成员路径不存在 |
| `version_without_evidence` | 版本关系没有任何 `basis`（禁止只按文件名断言） |
| `duplicate_hash_unknown` | 该 sha256 在索引中从未出现 |
| `duplicate_keep_not_in_index` | 保留项路径不存在 |
| `query_hit_path_not_in_index` | 命中指向的文件不存在 |
| `query_hit_quote_empty` | 命中没有引文 |
| `quote_not_found` | 引文在该文件中**逐字找不到**（空白/弯引号已归一化，仍找不到即伪引文） |
| `query_miss_undocumented` | 没有命中也未写 `miss_reason` |

**WARN（记录，不阻断）**

`plan_incomplete`（有文件未归位→回落 `_unsorted/`）、`metadata_source_missing`（字段无出处）、`metadata_value_not_in_source`（值在出处附近找不到，可能被改写）、`metadata_source_path_unknown`、`query_hit_no_text_layer`（该文件无可抽文本，如扫描件 PDF）、`locator_drift`（行号与真实命中行不一致，脚本以真实行为准）、`declared_query_unanswered`（`case.json` 声明的检索问题没被回答）、`recovery_target_unknown`、`uncertainties_empty_with_open_issues`（有悬空备注却不承认不确定）、`case_id_mismatch`。

## 5. 正反例

反例（会被 FIX）：

```json
{"path": "/input/library/raw/a.pdf"}                       // 绝对路径
{"path": "./library/raw/a.pdf"}                            // 相对写法不对
{"members": ["a.pdf", "a_v2.pdf"], "basis": "看起来是同一篇"} // 无 locator、无哈希
{"hits": [{"path": "library/raw/a.pdf", "quote": "容量保持率为 86.2%"}]} // 原文写作 "86.2 % capacity"
```

正例：

```json
{"path": "library/raw/a.pdf"}
{"members": ["library/raw/a.pdf", "library/raw/a_v2.pdf"],
 "basis": "note:supersedes library/versions.csv#r2（v2 supersedes v1）", "confidence": "high"}
{"hits": [{"path": "library/raw/a.pdf", "locator": "library/raw/a.pdf#L7",
           "quote": "The cell retained 86.2% capacity after 200 cycles at 1C."}]}
```

## 6. 兜底行为（不是你想要的正常路径）

`draft.json` 缺失/坏 JSON/全为 FIX 时，`build` 仍然产出：契约字段全回填的 `result.json`、`_unsorted/`+`_quarantine/` 的最小目录树、按哈希的去重、按备注边的版本链、关键词检索的引文、`status=partial`，并把 `draft_missing` / `plan_missing` / `draft_versions_missing` / `query_answered_by_script` 写进 `degradations`。这些条目在评审里等于"没有判断层"，会损失完成度与增益分。
