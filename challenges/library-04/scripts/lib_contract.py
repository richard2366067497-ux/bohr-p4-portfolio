#!/usr/bin/env python3
"""lib_contract.py -- output_contract enumeration, type-safe backfill, and the
degraded-but-complete fallback draft (stdlib only).

result.json must carry every key declared by output_contract unchanged. Values
are mapped from the docket content by semantic key patterns and coerced to the
declared type; coercion and unresolved keys are reported honestly.
"""
import json
import re

import lib_index as L


def contract_keys(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract]
    if isinstance(contract, list):
        return [x if isinstance(x, str) else str(x.get("name") or x.get("key") or "field_%d" % (i + 1))
                for i, x in enumerate(contract) if isinstance(x, (str, dict))]
    return []


def spec_of(contract, key):
    if isinstance(contract, dict):
        return contract.get(key)
    if isinstance(contract, list):
        for x in contract:
            if isinstance(x, dict) and str(x.get("name") or x.get("key") or "") == key:
                for tk in ("type", "dtype", "schema", "value_type"):     # field-object contracts
                    if x.get(tk) not in (None, ""):
                        return x[tk]
                return x
    return None


def empty_like(spec):
    if isinstance(spec, list):
        return []
    if isinstance(spec, dict):
        return {}
    if isinstance(spec, str):
        low = spec.strip().lower()
        if low.startswith("[") or any(w in low for w in ("array", "list", "列表", "清单", "数组")):
            return []
        if low.startswith("{") or any(w in low for w in ("object", "dict", "映射", "对象")):
            return {}
        if any(w in low for w in ("int", "float", "number", "数值", "计数")):
            return 0
        if any(w in low for w in ("bool", "布尔")):
            return False
    return None


def kind_of_spec(spec, value=None):
    if isinstance(spec, list):
        return "list"
    if isinstance(spec, dict):
        return "dict"
    low = str(spec or "").strip().lower()
    if any(w in low for w in ("array", "list", "列表", "清单")):
        return "list"
    if any(w in low for w in ("object", "dict", "映射")):
        return "dict"
    if any(w in low for w in ("int", "float", "number", "数值")):
        return "num"
    if any(w in low for w in ("bool", "布尔")):
        return "bool"
    if spec is not None:
        return "str"
    return "list" if isinstance(value, list) else "dict" if isinstance(value, dict) else "str"


def coerce(value, spec):
    want, coerced = kind_of_spec(spec, value), False
    if want == "list" and not isinstance(value, list):
        value, coerced = ([value] if value not in (None, "", {}, []) else []), True
    elif want == "dict" and not isinstance(value, dict):
        value, coerced = ({"value": value} if value not in (None, "", [], {}) else {}), True
    elif want == "str" and not isinstance(value, str):
        value, coerced = ("" if value in (None, [], {}) else json.dumps(value, ensure_ascii=False)[:20000]), True
    elif want == "num" and not isinstance(value, (int, float)):
        value, coerced = 0, True
    elif want == "bool" and not isinstance(value, bool):
        value, coerced = bool(value), True
    if value is None:
        value = empty_like(spec)
    return value, coerced


CONTRACT_MAP = [
    (r"^case|caseid|^id$", "case_id"),
    (r"status|state", "status"),
    (r"index|inventory|manifest|catalog|file_list|library_files|^files$|documents?_(list|table)|登记", "library_index"),
    (r"duplicat|dedup|副本|重复", "duplicates"),
    (r"version|revision|lineage|supersed|history|版本", "version_witness"),
    (r"metadata|meta_|字段", "metadata"),
    (r"permission|access|权限|readable", "permissions"),
    (r"answer|qa|question|finding|答案|问答", "answers"),
    (r"exhibit|evidence|quote|citation|引用|证据", "exhibits"),
    (r"conflict|contradict|冲突", "conflicts"),
    (r"not_found|missing|unsupported|gap|缺证", "not_found"),
    (r"repair|recover|skip|fail|error_log|action|operation|日志|操作", "repair_actions"),
    (r"coverage|stat|count|metric|覆盖", "coverage"),
    (r"summary|report|narrative|overview|摘要", "summary"),
    (r"method|repro|procedure|methodology|方法", "method"),
    (r"artifact|output_file|deliverable|产物", "artifacts"),
    (r"uncertain|limitation|不确定", "uncertainty"),
    (r"pending|human|待办", "pending_human"),
    (r"source|provenance|来源", "sources"),
]


def partial_result(case, cid, errs, gen, stage="partial"):
    ct = case.get("output_contract") if isinstance(case, dict) else None
    res = {k: empty_like(spec_of(ct, k)) for k in contract_keys(ct)}
    res.update(case_id=cid, status="partial", sources=[], uncertainty=[], pending_human=[], errors=errs,
               degradations=[], changes=[dict(step=stage, note="legal partial result written before any judgement")],
               runtime=dict(skill=gen, stage=stage))
    return res


def fill_contract(case, base, errs):
    ct = case.get("output_contract") if isinstance(case, dict) else None
    out, missing, coerced = {}, [], []
    for k in contract_keys(ct):
        spec, val = spec_of(ct, k), base.get(k)
        empty_ok = False
        if val in (None, "", [], {}):
            for pat, src in CONTRACT_MAP:
                if re.search(pat, k.lower()) and src in base:
                    if base[src] not in (None, "", [], {}):
                        val = base[src]
                        break
                    empty_ok = empty_ok or base[src] in ([], {}, "")
        if val in (None, "", [], {}):
            val = empty_like(spec)
            if not empty_ok:                      # source present but genuinely empty = a real answer
                missing.append(k)
        v, ch = coerce(val, spec)
        coerced += [k] if ch else []
        out[k] = v
    if coerced:
        errs.append({"code": "contract_type_coerced",
                     "detail": "coerced to declared type: %s" % ", ".join(coerced[:12])})
    return out, missing


def auto_draft(idx, degr):
    """Complete but degraded delivery: real inventory and version relations,
    per-question insufficient dockets, no invented quotes."""
    docs, fams, dupes = idx.get("docs") or {}, idx.get("families") or [], idx.get("duplicates") or []
    dropped = {d for g in dupes for d in (g.get("drop") or [])}
    documents, actions = [], []
    for k, d in sorted(docs.items()):
        fam = next((f for f in fams if k in (f.get("members") or [])), {})
        role = ("unreadable" if d.get("readable") is False else "duplicate" if k in dropped else
                "authoritative" if (not fam or fam.get("canonical_doc") == k) else "superseded")
        documents.append({"doc_id": k, "family_id": d.get("family_id"),
                          "version": d.get("version_label") or "v%d" % (d.get("version_rank") or 1), "version_rank": d.get("version_rank"),
                          "role": role, "title": (d.get("meta_hint") or {}).get("title_hint", "")[:120],
                          "metadata": {a: b for a, b in (d.get("meta_hint") or {}).items() if a != "title_hint"},
                          "notes": "; ".join(d.get("notes") or [])})
    for g in dupes:
        actions.append({"action_id": "A%d" % (len(actions) + 1), "op": "dedupe",
                        "target": ",".join(g.get("drop") or []), "to": "",
                        "reason": "与 %s 重复：%s" % (g.get("keep"), g.get("basis")), "evidence": [],
                        "reversible": True})
    for k in sorted(docs):
        if docs[k].get("readable") is False:
            actions.append({"action_id": "A%d" % (len(actions) + 1), "op": "flag", "target": k, "to": "",
                            "reason": "不可读/无文本层：%s" % ",".join(docs[k].get("notes") or []),
                            "evidence": [], "reversible": True})
    questions, scope = [], {}
    chunks = sum(len(v) for v in (idx.get("paras") or {}).values())
    for q in idx.get("questions") or []:
        qid = str(q.get("qid"))
        scope[qid] = {"files": sorted(docs), "keywords": L.tokenize(q.get("question") or "")[:6],
                      "synonyms": [], "chunks_scanned": chunks,
                      "not_found_note": "候选段落已召回但未逐条裁决（本次运行无工作稿）"}
        questions.append({"qid": qid, "question": q.get("question"), "answer_draft": "",
                          "issues": [{"issue_id": "%s-I1" % qid, "issue_text": q.get("question"),
                                      "verdict": "insufficient", "positive_exhibits": [], "counter_exhibits": [],
                                      "missing_evidence": "未产出工作稿：候选段落未逐条核证，缺可引用证据",
                                      "reasoning": "build 兜底：只登记与召回，不作判断"}]})
    degr.append("no_draft: inventory + version relations + insufficient dockets only; candidate paragraphs are "
                "listed for review and never quoted as evidence")
    return {"case_id": idx.get("case_id"), "_auto": True,
            "library": {"documents": documents, "families": fams, "duplicates": dupes, "repair_actions": actions},
            "questions": questions, "exhibits": [], "version_witness": [], "conflicts": [],
            "search_scope": scope, "limitations": [], "uncertainty": []}


def load_register(path):
    """Read the jsonl exhibit register back into a list (tolerant of commas)."""
    out = []
    try:
        for line in open(path, encoding="utf-8").read().splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return out
