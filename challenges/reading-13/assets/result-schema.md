# result.json schema (v5)

一个案例一个文件，UTF-8，缩进 2。字段名冻结；下游可直接读，无需清洗。唯一允许手写的文件是
草稿 `assertions.draft.json`（可选）；把它交给 `--draft` 即可覆盖自动拆分。

## 草稿 → 输出字段映射

| draft（`assertions.draft.json`，可选） | `result.json` |
|-|-|
| `predicate_label`（字符串，必填） | `predicate.label` |
| `predicate`（对象，可选） | `predicate.relation_type`、`predicate.direction` |
| `quantity`（单对象 value/unit/metric/comparator） | `quantities`（数组）以及 `object.value/unit/comparator` |
| `evidence[].quote/page/role` | `evidence[]`，补 `evidence_id`、`char_start`、`char_end`、`match`、`minimal_span`、`verbatim` |
| `excluded[]` | `excluded_claims[]`（自动补 `nearest_candidate` 的定位分数与页） |
| `paper_metadata` | 覆盖 `source.documents[0]` 的启发式元数据 |
| `confidence_basis`（提示） | 由 `np_lint.confidence_for` 重算进 `confidence.basis` |

`subject` / `predicate` / `object` 也接受裸字符串，会被规范化为 `{"label": ...}`。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "skill": {"name","version","extractor","direction"},
  "case_id": "string|null",
  "status": "success | partial | unsupported | failed",
  "status_detail": {"code","blocking","human_takeover_point"},
  "task": {"direction","source","contract"},
  "source": {
    "documents": [{"doc_id","path","sha256","bytes","page_count","backend","title","authors","year","venue","version","identifiers":{"doi","arxiv","url"},"retrieved_via"}],
    "extraction": [{"doc_id","backend","status","page_count","chars","pages_needing_ocr"}]
  },
  "assertions": [{
    "assertion_id": "np:assertion:<sha256-20>",
    "local_id": "a1",
    "text": "one atomic, falsifiable statement",
    "assertion_type": "quantitative|qualitative|comparative|causal|relational|methodological|existence|temporal",
    "subject":   {"label","type","identifier"},
    "predicate": {"label","relation_type","direction","polarity"},
    "object":    {"label","type","value","unit","comparator"},
    "quantities": [{"value","unit","metric"}],
    "conditions": ["..."],
    "qualifiers": ["..."],
    "evidence": [{
      "evidence_id": "np:evidence:<sha256-16>",
      "doc_id","page","section","paragraph","char_start","char_end",
      "quote","matched_text",
      "match": {"method": "exact|normalized|fuzzy|unverified", "score": 0.0},
      "evidence_role": "direct|supporting|contradicting|inferred",
      "minimal_span": {"page","char_start","char_end","text","method"},
      "limitations": "string|null", "verbatim": true
    }],
    "confidence": {"level": "direct_verbatim|direct_reported|inferred|aggregated|ambiguous|unsupported",
                   "basis": ["..."], "rationale": "machine-generated"},
    "quality": {"score","pass","warn","fail","checks": [{"id","status","detail","rule"}]},
    "source": {"doc_id","title","authors","year","venue","version","identifiers","file","retrieved_via"},
    "identifiers": {"assertion_id","assertion_uri","nanopub_uri","evidence_ids"},
    "nanopub": {"assertion": {...}, "provenance": {...}, "publication_info": {...}}
  }],
  "quality_summary": {"assertion_count","evidence_count","verbatim_evidence_count","exact_quote_count",
                      "mean_quality","confidence_levels","field_coverage","controlled_vocab"},
  "excluded_claims": [{"text","reason","nearest_candidate","nearest_score","page"}],
  "uncertainty": ["..."],
  "change_log": [{"at","action","detail"}],
  "contract": {"fields_provided": [{"contract_field","output_field"}], "unmapped_fields": ["..."],
               "min_assertions": null, "notes": ["..."]},
  "reproduce": {"entrypoint","inputs","skill_version","gate": {"pass","problems","warnings"}}
}
```

## 契约回填

`case.json` 的 `output_contract` **逐键处理**：能映射到产物的键写入 `contract.fields_provided`
并把对应值**浅拷贝到顶层**（例如 `assertions` → `result.assertions`）；无法建模的键进入
`contract.unmapped_fields`，同时在顶层建立一个非空、诚实的占位值
（`"unmapped: see contract.unmapped_fields"`），保证"按契约键直读都能命中且非空、不编造"。

## np_build 门禁不变量

1. `case_id`、`status`、`assertions`、`uncertainty`、`change_log`、`contract` 始终存在。
2. 每条断言都带齐七个字段：断言文本、主语-谓语-宾语、证据引文、证据位置、来源元数据、置信依据、标识符。
3. `assertion_id` 唯一且由内容派生（同输入 → 同 id）。
4. 每个定位都成立：`page` 存在且 `char_start < char_end ≤ 该页文本长度`。
5. `match.method` 取四个封闭值之一；`fuzzy` 绝不标 `verbatim`。
6. `status=success` 不能与 `ambiguous`/`unsupported` 的断言并存（否则自动降级为 `partial`）。
7. 被排除的断言保留 `reason`，使"拒绝"可审计。

## 下游注意

- `assertions[]` 是主列表；`evidence` 仅在任务契约点名该字段时于顶层回填其计数。
- `nanopub_uri` 是 `https://w3id.org/np/skill-` 命名空间下的确定性内容 URI，是稳定标识符，不是已注册的 nanopublication。
- 文本为 UTF-8、保留原标点；偏移量指向 `work/corpus.json` 中的原始页文本，而非重排后的渲染。
