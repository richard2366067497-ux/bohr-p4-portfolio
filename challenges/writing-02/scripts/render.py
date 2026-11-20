"""claim-preserving-polish — 定稿与渲染。

把工作稿 + 守卫判定变成可交付产物：polished.md/txt、changes.csv、glossary.csv、
edit_log.md、verification.json、evidence.json、human_review.md、result.json。
任何缺口都以降级方式写出，绝不因为缺东西而不产出。
"""
import json
import os
import platform
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polish_core as pc  # noqa: E402
import pipeline as pl  # noqa: E402

def change_rows(draft, report):
    rows, n = [], 0
    items = [i for i in ((draft or {}).get("items") or []) if isinstance(i, dict)]
    records = report.get("records") or []
    for idx, item in enumerate(items):
        rec = records[idx] if idx < len(records) else {}
        if rec.get("verdict") == "rolled_back":
            continue
        before, after = item.get("before") or "", item.get("after") or ""
        if pc.norm_ws(before) == pc.norm_ws(after):
            continue
        changes = [c for c in (item.get("changes") or []) if isinstance(c, dict)]
        if not changes:
            changes = [{"before_span": before, "after_span": after, "type": "other",
                        "reason": "工作稿未逐条拆分，整条登记"}]
        for ch in changes:
            n += 1
            rows.append({
                "change_id": "C%03d" % n, "paragraph_id": item.get("paragraph_id"),
                "segment_id": item.get("segment_id") or "",
                "locator": rec.get("locator") or str(item.get("paragraph_id")),
                "type": ch.get("type") or "other", "before_span": ch.get("before_span") or "",
                "after_span": ch.get("after_span") or "", "reason": ch.get("reason") or "",
                "guard": rec.get("verdict", "pass"), "similarity": rec.get("similarity", ""),
            })
    return rows

def glossary_rows(draft, state):
    rows, seen = [], set()

    def push(entry, source, decision):
        key = pc.canon(entry.get("concept") or entry.get("locked") or "")
        if not key or key in seen:
            return
        seen.add(key)
        variants = entry.get("variants") or []
        if not isinstance(variants, list):
            variants = [v.strip() for v in re.split(r"[|;、,]", str(variants)) if v.strip()]
        rows.append({"term_id": "T%02d" % (len(rows) + 1),
                     "concept": entry.get("concept") or entry.get("locked") or "",
                     "locked": entry.get("locked") or entry.get("locked_form") or "",
                     "variants": "|".join(variants), "abbr": entry.get("abbr") or "",
                     "first_use": entry.get("first_use") or "", "decision": decision,
                     "note": entry.get("note") or "", "source": source})

    for entry in ((draft or {}).get("glossary") or []):
        if isinstance(entry, dict):
            push(entry, "draft", entry.get("decision") or "工作稿锁定式")
    for entry in state["provided"]:
        push(entry, "input:glossary", "按输入术语表锁定")
    if not rows:
        for entry in state["candidates"][:20]:
            push(entry, "auto:" + str(entry.get("source", "candidate")), "自动候选，未经人工确认")
    return rows

def term_sweep(rows, order, working):
    issues = []
    for row in rows:
        locked = row.get("locked") or ""
        for variant in [v for v in str(row.get("variants") or "").split("|") if v and v != locked]:
            for pid in order:
                if variant in working.get(pid, ""):
                    issues.append({"code": "TERM_DRIFT", "severity": "soft", "paragraph_id": pid,
                                   "concept": row.get("concept"), "variant": variant, "locked": locked,
                                   "detail": "同概念仍出现未锁定写法“%s”，应统一为“%s”" % (variant, locked)})
        abbr = row.get("abbr") or ""
        if abbr and locked:
            first_lock = next((i for i, pid in enumerate(order) if locked in working.get(pid, "")), None)
            first_abbr = next((i for i, pid in enumerate(order)
                               if re.search(r"(?<![A-Za-z])%s(?![a-z])" % re.escape(abbr), working.get(pid, ""))), None)
            if first_lock is not None and first_abbr is not None and first_abbr < first_lock:
                issues.append({"code": "ABBR_BEFORE_DEF", "severity": "soft", "paragraph_id": order[first_abbr],
                               "concept": row.get("concept"),
                               "detail": "缩写 %s 首次出现早于全称“%s”，首现应写全称并附缩写" % (abbr, locked)})
    return issues

def decide_status(state, report, has_draft):
    if not (state["doc_text"] or "").strip():
        return "input_error", "输入中没有可读原稿文本：未做任何改写"
    if len(pc.norm_ws(state["doc_text"])) < 60:
        return "insufficient_evidence", "原稿有效字符不足 60：材料不足以支撑润色判断"
    if not has_draft:
        return "partial", "工作稿 draft.json 缺失：按原文保守交付（未改写），缺口见 degradations"
    if report["hard_count"] or report["rolled_back"]:
        return "partial", "有 %d 条被守恒守卫回退原文（%s），其余已交付" % (
            report["hard_count"], "、".join(report["rolled_back"]) or "-")
    if report["missing_coverage"]:
        return "partial", "有 %d 段未在工作稿中处理：%s" % (
            len(report["missing_coverage"]), "、".join(report["missing_coverage"][:8]))
    if state["material_fallback"]:
        return "partial", "未找到原稿文件，材料回退自 task.md"
    return "answered", "全部可编辑段落已处理，保护性原子与观点强度守卫均通过"

def finalize(a, state, draft, phase, has_draft):
    segments = state["segments"]
    profile = state["profile"]
    order = [p["id"] for p in segments["paragraphs"]]
    texts = {p["id"]: p["text"] for p in segments["paragraphs"]}
    report = pl.verify_draft(draft, segments, profile) if has_draft else pl.empty_report(segments)
    working = report["working"]
    polished = "\n\n".join(working[pid] for pid in order)
    rows = change_rows(draft, report) if has_draft else []
    grows = glossary_rows(draft, state)
    issues = term_sweep(grows, order, working)
    pending = [dict(p) for p in report["pending"]]
    for issue in issues:
        if issue["severity"] == "soft":
            pending.append({"id": "T%03d" % len(pending), "paragraph_id": issue.get("paragraph_id", ""),
                            "issue": "%s：%s" % (issue["code"], issue.get("detail", "")),
                            "need": "确认术语锁定形式", "options": ["按 locked 统一", "保留现写法并说明"],
                            "severity": "medium"})
    uncertainties = [u for u in ((draft or {}).get("uncertainties") or []) if isinstance(u, dict)]
    degradations = list(state["degradations"])
    if not has_draft:
        degradations.append("draft.json 缺失：未做任何语义改写，polished 与原文一致（保守交付）")
    status, reason = decide_status(state, report, has_draft)
    counts = report["counts"]
    coverage = dict(counts)
    coverage["coverage_ratio"] = round(counts["covered"] / float(counts["editable"]), 3) if counts["editable"] else 0.0
    cov_paras = report["paragraphs"]
    orig_atoms = pc.extract_spans(state["doc_text"])
    pol_atoms = pc.extract_spans(polished)
    lost_all, added_all = pc.diff_atoms(orig_atoms, pol_atoms)
    verification = {
        "case_id": state["case_id"], "phase": phase, "mode": profile["mode"], "genre": profile["genre"],
        "language": profile["language"],
        "thresholds": {"min_item_similarity": 0.50,
                       "hedge_scale": "0 unresolved < 1 associative < 2 possible < 3 indicative < 4 assertive",
                       "hard_atoms": list(pc.HARD_ATOM_CLASSES)},
        "coverage": coverage,
        "items": report["records"],
        "paragraph_checks": [{"paragraph_id": pid, "changed": data["changed"], "similarity": data["similarity"],
                              "atoms_lost": data["atoms_lost"], "atoms_added": data["atoms_added"],
                              "hedge_before": data["hedge_before"], "hedge_after": data["hedge_after"],
                              "negation_before": data["negation_before"], "negation_after": data["negation_after"],
                              "reverted": data.get("reverted", False)}
                             for pid, data in cov_paras.items()],
        "global_conservation": {
            "atoms_lost_total": len(lost_all), "atoms_added_total": len(added_all),
            "numbers_original": len(orig_atoms["number"]), "numbers_polished": len(pol_atoms["number"]),
            "citations_original": len(orig_atoms["citation"]), "citations_polished": len(pol_atoms["citation"]),
            "pointers_original": len(orig_atoms["pointer"]), "pointers_polished": len(pol_atoms["pointer"]),
            "equations_original": len(orig_atoms["equation"]), "equations_polished": len(pol_atoms["equation"]),
            "conserved": not lost_all,
        },
        "terminology_sweep": issues, "untouched_declared": report["untouched"],
        "missing_coverage": report["missing_coverage"], "rolled_back": report["rolled_back"],
    }
    bilingual = [{"paragraph_id": pid, "source": texts.get(pid, ""), "target": working[pid]} for pid in order]
    limits = [
        "只做语言层最小编辑：不改写研究设计、不补数据、不新增引用、不调整期刊排版。",
        "守卫基于词表与正则：限定强度、否定、原子守恒是可复算的机械判据，语义等价仍需人工抽查。",
        "回退是安全结果：被判违规的段落保留原文，而不是交付一个可能改坏作者主张的版本。",
    ]
    if profile["mode"] == "translate":
        limits.append("跨语言模式：限定强度无法逐词比对，相关条目只做提示并进入人工确认清单。")

    out = a.out
    pc.ensure(out)
    files = {}
    polished_md = os.path.join(out, "polished.md")
    pc.write_text(polished_md, polished + ("\n" if polished else ""))
    files["polished_markdown"] = polished_md
    plain = os.path.join(out, "polished.txt")
    pc.write_text(plain, polished + ("\n" if polished else ""))
    files["polished_text"] = plain

    lines = ["# 逐段修改记录", "", "案例：`%s`　状态：**%s**" % (state["case_id"], status), "",
             "> 每处改动给出：原文 → 改文 → 类型 → 理由 → 守卫判定。被判违规的条目已回退原文，见 `human_review.md`。", ""]
    if not rows:
        lines += ["本次未登记任何文本改动。", ""]
    for pid in order:
        data = cov_paras.get(pid, {})
        lines.append("## %s（%s，%d 字符，相似度 %.2f）"
                     % (pid, "已改" if data.get("changed") else "未改", len(texts.get(pid, "")), data.get("similarity", 1.0)))
        rows_p = [r for r in rows if r["paragraph_id"] == pid]
        if not rows_p:
            skip_reason = report["untouched"].get(pid) or ("无需修改：语法、术语与语域已合规" if data.get("changed") is False
                                                          else "见 human_review.md")
            lines += ["- 未改动。理由：%s" % skip_reason, ""]
            continue
        for row in rows_p:
            lines += ["- `%s` **%s**" % (row["change_id"], row["type"]),
                      "  - 原文：%s" % (row["before_span"] or "(整段)"),
                      "  - 改文：%s" % (row["after_span"] or "(整段)"),
                      "  - 理由：%s" % row["reason"],
                      "  - 守卫：%s　定位：`%s`" % (row["guard"], row["locator"])]
        lines.append("")
    edit_md = os.path.join(out, "edit_log.md")
    pc.write_text(edit_md, "\n".join(lines))
    files["edit_log_markdown"] = edit_md

    changes_csv = os.path.join(out, "changes.csv")
    pc.write_csv(changes_csv,
                 ["change_id", "paragraph_id", "segment_id", "locator", "type", "before_span", "after_span",
                  "reason", "guard", "similarity"],
                 [[r["change_id"], r["paragraph_id"], r["segment_id"], r["locator"], r["type"], r["before_span"],
                   r["after_span"], r["reason"], r["guard"], r["similarity"]] for r in rows])
    files["changes_csv"] = changes_csv

    glossary_csv = os.path.join(out, "glossary.csv")
    pc.write_csv(glossary_csv,
                 ["term_id", "concept", "locked", "variants", "abbr", "first_use", "evidence_paragraph",
                  "decision", "note", "source"],
                 [[r["term_id"], r["concept"], r["locked"], r["variants"], r["abbr"], r["first_use"],
                   r["first_use"], r["decision"], r["note"], r["source"]] for r in grows])
    files["glossary_csv"] = glossary_csv

    ver_path = os.path.join(out, "verification.json")
    pc.jdump(ver_path, verification)
    files["verification_json"] = ver_path

    evidence = {
        "case_id": state["case_id"],
        "method": "每处改动以逐字 quote + 文档定位（段落 id 与字符区间）为证据；术语决定以首现段落为证据。",
        "items": [{"change_id": r["change_id"], "paragraph_id": r["paragraph_id"], "locator": r["locator"],
                   "type": r["type"], "before_quote": r["before_span"][:400], "after_quote": r["after_span"][:400],
                   "reason": r["reason"], "guard": r["guard"]} for r in rows],
        "glossary_evidence": [{"concept": g["concept"], "locked": g["locked"],
                               "evidence_paragraph": g["first_use"], "decision": g["decision"],
                               "source": g["source"]} for g in grows],
        "protected_spans": [{"class": cls, "value": val, "count": orig_atoms[cls].count(val)}
                            for cls in pc.HARD_ATOM_CLASSES for val in sorted(set(orig_atoms.get(cls, [])))[:12]],
        "sources": state["sources"],
    }
    ev_path = os.path.join(out, "evidence.json")
    pc.jdump(ev_path, evidence)
    files["evidence_json"] = ev_path

    rl = ["# 人工确认清单", "", "案例：`%s`　运行阶段：`%s`" % (state["case_id"], phase), ""]
    high = [p for p in pending if p.get("severity") == "high"]
    medium = [p for p in pending if p.get("severity") != "high"]
    rl.append("## 必须处理（%d）" % len(high))
    if not high:
        rl.append("- 无：没有条目触发守恒硬性回退。")
    for item in high:
        rl += ["- **[%s] %s** %s" % (item["id"], item.get("paragraph_id", ""), item.get("issue", "")),
               "  - 需要你做什么：%s" % item.get("need", ""),
               "  - 可选处理：%s" % "；".join(item.get("options") or [])]
    rl += ["", "## 建议复核（%d）" % len(medium)]
    rl.append("- 无。" if not medium else "")
    for item in medium[:40]:
        rl.append("- [%s] %s %s → %s" % (item["id"], item.get("paragraph_id", ""), item.get("issue", ""),
                                         item.get("need", "")))
    rl += ["", "## 材料缺口与降级（%d）" % len(degradations)]
    rl += ["- %s" % d for d in degradations] or ["- 无。"]
    if report["missing_coverage"]:
        rl += ["", "## 未处理段落", "- " + "、".join(report["missing_coverage"])]
    if uncertainties:
        rl += ["", "## 工作稿声明的存疑项"]
        for item in uncertainties[:20]:
            rl.append("- %s" % json.dumps(item, ensure_ascii=False)[:300])
    review_md = os.path.join(out, "human_review.md")
    pc.write_text(review_md, "\n".join(rl) + "\n")
    files["human_review_markdown"] = review_md

    wants_bilingual = (profile["mode"] in ("translate", "bilingual") or
                       any(("双语" in str(f)) or ("bilingual" in str(f).lower()) for f in profile.get("contract_fields") or []))
    if wants_bilingual:
        bi_csv = os.path.join(out, "bilingual.csv")
        pc.write_csv(bi_csv, ["paragraph_id", "source_text", "target_text"],
                     [[b["paragraph_id"], b["source"], b["target"]] for b in bilingual])
        files["bilingual_csv"] = bi_csv

    notes = ("在 %d 段可编辑文本上登记 %d 处修改；%d 条被守卫回退；术语表 %d 条；覆盖率 %s。"
             % (coverage["editable"], coverage["changed"], coverage["rolled_back_items"], len(grows),
                coverage["coverage_ratio"]))
    ctx = {"polished_text": polished, "edit_log": rows, "glossary": grows, "bilingual": bilingual,
           "verification": coverage, "pending_human": pending, "uncertainty": uncertainties,
           "sources": state["sources"], "limits": limits,
           "structure": [{"paragraph_id": p["id"], "kind": p["kind"], "chars": p["chars"],
                          "sentences": len(p["sentences"]), "changed": cov_paras.get(p["id"], {}).get("changed", False)}
                         for p in segments["paragraphs"]],
           "status": status, "notes": notes, "case_id": state["case_id"]}
    result, contract_report, unmapped = {}, [], []
    fields = pc.shape_contract(state["contract"]) or [(n, None) for n in
                                                      ("polished_text", "edit_log", "glossary", "uncertainty", "pending_human")]
    raw_overrides = (draft or {}).get("result_fields")
    overrides = {pc.canon(k): v for k, v in raw_overrides.items()} if isinstance(raw_overrides, dict) else {}
    for name, declared in fields:
        kind = pc.resolve_kind(name)
        value = overrides.get(pc.canon(name))
        if value is None and kind:
            value = pc.fill_value(declared, kind, ctx)
        if value is None and kind:
            value = ctx.get(kind)
        result[name] = value
        contract_report.append({"field": name, "resolved_as": kind or "unmapped",
                                "filled": value is not None,
                                "empty_payload": value in ([], "", {}),
                                "declared_type": type(declared).__name__ if declared is not None else None})
        if not kind:
            unmapped.append(name)

    digest = {"original_sha256": pc.sha256_text(state["doc_text"]), "polished_sha256": pc.sha256_text(polished),
              "original_chars": len(state["doc_text"]), "polished_chars": len(polished),
              "char_delta": len(polished) - len(state["doc_text"]),
              "changed_paragraphs": coverage["changed"], "paragraphs": coverage["paragraphs_total"],
              "numbers_original": len(orig_atoms["number"]), "guard_version": pc.SKILL_VERSION}
    envelope = {
        "case_id": state["case_id"], "status": status, "status_reason": reason,
        "errors": state["errors"], "degradations": degradations, "uncertainties": uncertainties,
        "pending_human": pending,
        "runtime": {"skill": pc.SKILL_NAME, "version": pc.SKILL_VERSION, "phase": phase,
                    "finished_at": pc.now_iso(), "python": platform.python_version(),
                    "input_dir": a.input, "work_dir": a.work, "out_dir": a.out,
                    "commands": pc.jload(os.path.join(a.work, "cmd_log.json"), []) or [],
                    "budget_note": "单案例只需 5 次确定性命令 + Agent 读写工作稿；不联网、无第三方包。"},
        "sources": state["sources"], "verification": coverage, "coverage": coverage,
        "before_after_digest": digest,
        "deliverables": {k: {"path": v, "bytes": (os.path.getsize(v) if os.path.exists(v) else 0)}
                         for k, v in files.items()},
        "terminology_sweep": issues, "change_count": len(rows), "glossary_count": len(grows),
        "limits": limits, "notes": notes, "skill": {"name": pc.SKILL_NAME, "version": pc.SKILL_VERSION},
        "_contract_report": contract_report, "_contract_source": ".output_contract",
        "_unmapped_contract_fields": unmapped,
    }
    for key, value in envelope.items():
        if key not in result or result[key] in (None, "", [], {}):
            result[key] = value
    result_path = os.path.join(out, "result.json")
    pc.jdump(result_path, result)
    return {"result": result, "report": report, "rows": rows, "glossary": grows, "issues": issues,
            "polished": polished, "result_path": result_path, "status": status}

def emergency(a, exc):
    detail = "%s: %s" % (type(exc).__name__, exc)
    try:
        case = pc.jload(a.case, {}) or {}
        contract = pl.find_key(case, "output_contract") or {}
        name = pl.find_key(case, "case_id") or pl.find_key(case, "id") or "unknown-case"
        result = {field: None for field, _ in pc.shape_contract(contract)}
        result.update({
            "case_id": str(name), "status": "input_error",
            "status_reason": "脚本异常，已写出最小合法交付；主产物未生成",
            "errors": [detail], "degradations": ["异常路径：仅写出 result.json 与空 polished.md"],
            "uncertainties": [], "pending_human": [],
            "runtime": {"skill": pc.SKILL_NAME, "version": pc.SKILL_VERSION, "emergency": True,
                        "finished_at": pc.now_iso(), "python": platform.python_version()},
            "sources": [],
            "_contract_report": [{"field": field, "resolved_as": "emergency:null", "filled": False}
                                 for field, _ in pc.shape_contract(contract)],
        })
        pc.ensure(a.out)
        pc.jdump(os.path.join(a.out, "result.json"), result)
        pc.write_text(os.path.join(a.out, "polished.md"), "")
        pc.log("[ERROR] %s" % detail)
        pc.log(traceback.format_exc(limit=4))
        pc.log("[FALLBACK] 已写出最小合法 result.json 与空 polished.md")
    except Exception as exc2:  # noqa: BLE001
        pc.log("[FATAL] 应急写出也失败: %s" % exc2)
