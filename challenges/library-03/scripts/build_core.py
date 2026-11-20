#!/usr/bin/env python3
"""build_core -- render step for facet-catalog-curator.

Merges the agent draft with the index, renders facets/entries/reconciliation/views/
provenance, materialises the target library, records rollback + idempotency and
finalises result.json. Every stage degrades instead of failing.
"""
import json
import re
import shutil
from pathlib import Path

import catalog_core as C


# ------------------------------------------------------------------ naming
def sanitize(s, spec):
    n = spec.get("naming") or {}
    for k, v in (n.get("char_map") or {}).items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", n.get("space_to", "_"), s)
    s = re.sub(r"_+", "_", s).strip(n.get("strip_chars", " ._-"))
    mx = int(n.get("max_len", 120))
    return s[: mx - 9].strip(n.get("strip_chars", " ._-")) if len(s) > mx else s


def name_of(entry, spec, template=None):
    n = spec.get("naming") or {}
    tpl = template or n.get("template") or "{first_author}-{year}-{short_title}"
    f = entry.get("facets") or {}
    ident = f.get("identifier") or ""
    tail = re.sub(r"[^A-Za-z0-9]+", "", ident.split("/")[-1])[-12:] if ident else ""
    words = re.findall(r"[A-Za-z0-9\u3400-\u9fff]+", entry.get("title") or "")[: int(n.get("short_title_words", 4))]
    ap = (entry.get("first_author") or "").split()
    vals = {"first_author": re.sub(r"[^A-Za-z\u3400-\u9fff-]+", "", ap[-1]) if ap else "",
            "year": f.get("year") or "", "short_title": "-".join(words), "identifier_tail": tail,
            "doc_type": f.get("doc_type") or "unknown", "project": f.get("project") or "_unassigned",
            "version_state": f.get("version_state") or "",
            "original_stem": Path(entry.get("file") or "file").stem, "language": f.get("language") or "und"}
    ext = Path(entry.get("file") or "").suffix.lower() or ".bin"
    deg = []
    for i, t in enumerate([tpl] + [x for x in (n.get("fallback_order") or []) if x != tpl]):
        try:
            raw = t.format(**vals)
        except (KeyError, IndexError):
            deg.append("bad_template")
            continue
        base = sanitize(raw, spec)
        if not base:
            deg.append("empty_template")
            continue
        if i:
            deg.append("fallback:%s" % t)
        return base + ext, "t%d" % (i + 1), deg
    return sanitize(vals["original_stem"], spec) + "_unresolved" + ext, "tN", deg + ["no_template_matched"]


def target_path(entry, spec, name):
    f = entry.get("facets") or {}
    tpl = (spec.get("naming") or {}).get("dir_template") or "library/{project}/{doc_type}/{year}"
    vals = {"project": f.get("project") or "_unassigned", "doc_type": f.get("doc_type") or "unknown",
            "year": str(f.get("year") or "_undated"), "version_state": f.get("version_state") or "unknown",
            "language": f.get("language") or "und"}
    try:
        d = tpl.format(**vals)
    except (KeyError, IndexError):
        d = "library/_unassigned/unknown/_undated"
    return "%s/%s" % ("/".join(sanitize(x, spec) or "_" for x in d.split("/") if x.strip()), name)


def render_tree(rows):
    tree = {}
    for tp, eid, h in rows:
        node, parts = tree, tp.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = (eid + " " + h).strip()
    lines = ["# target tree rendered deterministically from facets + entries (entry_id sha8)", ""]

    def walk(node, prefix):
        keys = sorted(node)
        for i, k in enumerate(keys):
            last, v = i == len(keys) - 1, node[k]
            branch = "└── " if last else "├── "
            if isinstance(v, dict):
                lines.append(prefix + branch + k)
                walk(v, prefix + ("    " if last else "│   "))
            else:
                lines.append(prefix + branch + k + "   (" + v + ")")
    walk(tree, "")
    return "\n".join(lines) + "\n"


def facet_index(entries):
    idx = {}
    for e in entries:
        for facet, val in (e.get("facets") or {}).items():
            for v in (val if isinstance(val, list) else [val]):
                if v in (None, "", "unknown"):
                    continue
                idx.setdefault(facet, {}).setdefault(str(v), []).append(e["entry_id"])
    return {f: {v: sorted(set(i)) for v, i in sorted(d.items())} for f, d in sorted(idx.items())}


def coverage_of(entries, schema):
    per = {}
    for fc in schema:
        name = fc.get("facet")
        miss = [e["entry_id"] for e in entries if not C.filled((e.get("facets") or {}).get(name))]
        per[name] = {"filled": len(entries) - len(miss), "total": len(entries),
                     "rate": round((len(entries) - len(miss)) / max(1, len(entries)), 4), "missing": miss}
    return {"facets": per, "matrix_total": sum(v["filled"] for v in per.values()),
            "matrix_possible": len(entries) * max(1, len(schema))}


def plan_ops(entries, spec, out_root, src_root, template=None):
    out_root, planned, seen = Path(out_root), [], {}
    for e in entries:
        name, tid, deg = name_of(e, spec, template)
        tp = target_path(e, spec, name)
        k = tp.lower()
        if k in seen:
            base = Path(tp)
            tp = "%s/%s%s%d%s" % (str(base.parent).replace("\\", "/"), base.stem,
                                  (spec.get("naming") or {}).get("dup_suffix", "_dup"), seen[k] + 1, base.suffix)
            deg = deg + ["name_collision"]
        seen[k] = seen.get(k, 0) + 1
        dst = out_root / tp
        status = "planned"
        if dst.exists():
            try:
                status = "noop" if C.sha(C.rd(dst)) == (e.get("sha256") or "") else "conflict"
            except Exception:  # noqa: BLE001
                status = "conflict"
        planned.append({"entry_id": e["entry_id"], "src": str(Path(src_root) / e.get("file", "")),
                        "dst": str(dst), "tp": tp, "sha": e.get("sha256"), "status": status,
                        "template_id": tid, "degradation": deg})
    planned.sort(key=lambda x: (x["tp"], x["entry_id"]))
    return planned


# ------------------------------------------------------------------ merge
def merge_entries(idx, draft, schema, minq):
    texts, by_file, evidence, unc, errs, degr = idx["texts"], {}, [], [], [], []
    for e in draft.get("entries") or []:
        if isinstance(e, dict) and e.get("file"):
            by_file[C.norm(e["file"]).lstrip("./").replace("\\", "/")] = e
    docs = [f for f in idx["files"] if not f.get("_companion")]
    known = {f["file"] for f in docs}
    for bad in sorted(set(by_file) - known):
        errs.append({"stage": "merge", "code": "E03", "detail": "draft entry references unknown file: %s" % bad})
    fcmap = {fc["facet"]: fc for fc in schema}
    entries = []
    for n, f in enumerate(sorted(docs, key=lambda x: x["file"]), 1):
        de = by_file.get(f["file"], {})
        eid = "E%02d" % n
        facets, srcs = dict(f.get("facets") or {}), dict(f.get("cand_src") or {})
        for k, v in (de.get("facets") or {}).items():
            facets[k] = v
            if k not in fcmap:
                degr.append({"stage": "merge", "code": "facet_not_in_schema", "detail": "%s: %s" % (f["file"], k)})
        for k, fc in fcmap.items():
            if not C.valid_value(fc, facets.get(k)):
                unc.append({"entry_id": eid, "field": k, "reason": "value_not_in_allowed_set",
                            "value": facets.get(k), "suggested_action": "改用 allowed_values 中的值或 unknown"})
                facets[k] = [] if fc.get("multi") else None
            facets.setdefault(k, [] if fc.get("multi") else None)
        fs = de.get("field_sources") if isinstance(de.get("field_sources"), dict) else {}
        for k, v in fs.items():
            if isinstance(v, dict) and v.get("locator") and v.get("quote"):
                srcs[k] = {"locator": v["locator"], "quote": v["quote"]}
        unresolved, missing, verified, asked = [], [], 0, 0
        for k in fcmap:
            if not C.filled(facets.get(k)):
                unresolved.append(k)
                continue
            asked += 1
            s = srcs.get(k) or {}
            ok, scope = C.evidence_ok(fc, facets.get(k), s, texts, f["file"], minq)
            evidence.append({"entry_id": eid, "field": k, "locator": s.get("locator"), "quote": s.get("quote"),
                             "verified": ok, "scope": scope})
            if ok:
                verified += 1
            else:
                missing.append(k)
        status = "script_derived" if not de else ("ok" if not missing else "unverified_evidence")
        if de and missing:
            unc.append({"entry_id": eid, "field": ",".join(missing), "reason": "quote_not_verified",
                        "suggested_action": "用 show 的 excerpt 逐字替换 quote，或把该面元改为 null"})
        if de and de.get("sha256") and de["sha256"] != f["sha256"]:
            errs.append({"stage": "merge", "code": "E04", "detail": "%s sha256 mismatch" % f["file"]})
        entries.append({"entry_id": eid, "file": f["file"], "sha256": de.get("sha256") or f["sha256"],
                        "size": f["size"], "magic": f["magic"], "text_layer": f["text_layer"],
                        "title": C.norm(de.get("title") or f["meta"].get("title") or "") or None,
                        "first_author": C.norm(de.get("first_author") or f["meta"].get("first_author") or "") or None,
                        "facets": facets, "field_sources": srcs,
                        "confidence": de.get("confidence") if isinstance(de.get("confidence"), (int, float))
                        else round(0.55 + 0.45 * (verified / max(1, asked)), 2),
                        "status": status, "unresolved": unresolved})
    return entries, evidence, unc, errs, degr


def merge_decisions(idx, draft, entries):
    rec = idx["spec"].get("reconciliation") or {}
    rel_ok, dec_ok = set(rec.get("relations") or []), set(rec.get("decisions") or [])
    bas_ok = set(rec.get("bases") or [])
    names = {e["file"] for e in entries}
    out, unc, errs, seen = [], [], [], set()
    for d in draft.get("reconciliation") or []:
        if not isinstance(d, dict):
            continue
        fs = [C.norm(x).lstrip("./").replace("\\", "/") for x in (d.get("files") or []) if x]
        if len(fs) < 2:
            errs.append({"stage": "reconciliation", "code": "E07", "detail": "decision needs 2+ files"})
            continue
        bad = [x for x in fs if x not in names]
        if bad:
            errs.append({"stage": "reconciliation", "code": "E03", "detail": "unknown file: %s" % bad})
        rel = d.get("relation") if d.get("relation") in rel_ok else "needs_human"
        dec = d.get("decision") if d.get("decision") in dec_ok else "needs_human"
        bas = d.get("basis") if d.get("basis") in bas_ok else None
        loc, quote = d.get("evidence_locator"), d.get("evidence_quote")
        ok = C.quote_ok(idx["texts"], loc, quote)[0] if (loc and quote) else None
        if bas == "sha256" and quote:
            ok = any(C.tol(quote) in (e.get("sha256") or "") for e in entries)
        if bas is None or not d.get("rollback_action"):
            unc.append({"decision_id": "D%02d" % (len(out) + 1), "field": "basis/rollback_action",
                        "reason": "decision_missing_basis_or_rollback",
                        "suggested_action": "补 basis 与 rollback_action（见 SKILL.md 错误码 E07）"})
        out.append({"decision_id": "D%02d" % (len(out) + 1), "files": fs, "relation": rel, "decision": dec,
                    "basis": bas, "evidence_locator": loc, "evidence_quote": quote, "evidence_verified": ok,
                    "decided_by": "agent", "rollback_action": d.get("rollback_action"),
                    "note": C.norm(d.get("note") or "")})
        seen.add(tuple(sorted(fs)))
    for p in idx["pairs"]:
        if tuple(sorted(p["files"])) not in seen:
            for d in C.default_decisions([p]):
                d["decision_id"] = "D%02d" % (len(out) + 1)
                out.append(d)
    for d in out:
        if d["decision"] == "needs_human":
            unc.append({"decision_id": d["decision_id"], "field": "relation", "reason": "evidence_insufficient",
                        "suggested_action": "人工确认重复/版本关系；文件保持原状"})
    return out, unc, errs


def primary_archive(decisions, entries):
    fm = {e["file"]: e for e in entries}
    archive, why = set(), {}
    for d in decisions:
        if d["decision"] not in ("archive", "version_chain", "merge") or len(d["files"]) < 2:
            continue
        cand = [x for x in d["files"] if x in fm]
        if not cand:
            continue
        best = sorted(cand, key=lambda x: (0 if fm[x]["facets"].get("version_state") in ("published", "postprint")
                                           else 1, -(fm[x].get("size") or 0), x))[0]
        for x in cand:
            if x != best:
                archive.add(x)
                why[x] = d["decision_id"]
    return archive, why


def materialise(ctx, idx, entries, naming, no_mat):
    ops = []
    if no_mat:
        return [{"entry_id": n["entry_id"], "op": "planned", "src": n["old_name"], "dst": n["target_path"],
                 "sha_before": None, "sha_after": None, "status": "planned"} for n in naming]
    out = Path(ctx["out"])
    for n in naming:
        e = next((x for x in entries if x["entry_id"] == n["entry_id"]), {})
        src, dst = Path(idx["input_root"]) / n["old_name"], out / n["target_path"]
        op = "copy+rename" if Path(n["old_name"]).name != Path(n["target_path"]).name else "copy"
        before = e.get("sha256")
        if dst.exists():
            try:
                same = C.sha(C.rd(dst)) == before
            except Exception:  # noqa: BLE001
                same = False
            if same:
                ops.append({"entry_id": n["entry_id"], "op": op, "src": str(src), "dst": str(dst),
                            "sha_before": before, "sha_after": before, "status": "noop"})
                continue
            alt = dst.with_name(dst.stem + (idx["spec"].get("naming") or {}).get("dup_suffix", "_dup") + dst.suffix)
            dst, n["target_path"], n["new_name"] = alt, str(alt.relative_to(out)), alt.name
            n["degradation"] = (n["degradation"] + ";name_collision_resolved") if n["degradation"] != "none" \
                else "name_collision_resolved"
        after = None
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)
                after = C.sha(C.rd(dst))
            status = "applied" if after and after == before else ("mismatch" if after else "src_missing")
        except Exception as exc:  # noqa: BLE001 - permission/IO failure degrades one file only
            status = "error:%s" % type(exc).__name__
        ops.append({"entry_id": n["entry_id"], "op": op, "src": str(src), "dst": str(dst),
                    "sha_before": before, "sha_after": after, "status": status})
    return ops


def idempotency(ctx, naming, ops, entries):
    p = Path(ctx["out"]) / "provenance" / "idempotency.json"
    prior, _ = C.ljson(p)
    runs = (prior or {}).get("runs") if isinstance(prior, dict) else None
    runs = runs if isinstance(runs, list) else []
    digest = C.sha(("\n".join("%s|%s" % (n["entry_id"], n["new_name"]) for n in naming)).encode("utf-8"))
    applied = len([o for o in ops if o["status"] == "applied"])
    prev = runs[-1] if runs else None
    stable = 1.0 if not prev or prev.get("naming_digest") == digest else 0.0
    concl = "first_run" if not prev else ("idempotent" if (applied == 0 and stable == 1.0) else "changed")
    rec = {"run_index": len(runs) + 1, "entries": len(entries), "ops_applied": applied, "ops_total": len(ops),
           "naming_digest": digest, "naming_stability": stable, "conclusion": concl,
           "note": "同一输入重复 build 应得 ops=0 且命名摘要不变（视图与命名由 entries+模板确定性生成）"}
    runs.append({k: rec[k] for k in ("run_index", "entries", "ops_applied", "naming_digest", "conclusion")})
    C.wjson(p, dict(rec, definition="幂等性：第二次 build 实际变更数为 0、命名摘要不变", runs=runs[-10:]))
    return rec


# ------------------------------------------------------------------ build
def cmd_build(ctx, opts):
    idx, res, spec, out = ctx["idx"], ctx["res"], ctx["idx"]["spec"], Path(ctx["out"])
    draft, derr = ctx["draft"], ctx["draft_err"]
    schema, origin = C.schema_of(draft, spec)
    entries, evidence, unc, errs, degr = merge_entries(
        idx, draft, schema, int((spec.get("limits") or {}).get("min_quote_chars", 8)))
    decisions, unc2, errs2 = merge_decisions(idx, draft, entries)
    unc, errs, degr = unc + unc2, errs + errs2, list(degr)
    if derr:
        degr.append({"stage": "build", "code": derr.split(":")[0], "detail": derr})
    archive, why = primary_archive(decisions, entries)
    tpl = draft.get("naming_template") if isinstance(draft.get("naming_template"), str) else None
    planned = plan_ops(entries, spec, out, idx["input_root"], tpl)
    naming = []
    for e in entries:
        p = next((x for x in planned if x["entry_id"] == e["entry_id"]), None)
        name, tid, deg = name_of(e, spec, tpl)
        tp = p["tp"] if p else target_path(e, spec, name)
        if e["file"] in archive and tp.startswith("library/"):
            tp = "library/_archive/" + tp.split("library/", 1)[1]
            deg = deg + ["archived_by:%s" % why[e["file"]]]
        naming.append({"entry_id": e["entry_id"], "old_name": e["file"], "new_name": Path(tp).name,
                       "target_path": tp, "template_id": tid, "degradation": ";".join(deg) or "none"})
    naming.sort(key=lambda x: (x["target_path"], x["entry_id"]))
    ops = materialise(ctx, idx, entries, naming, opts.get("no_materialize"))
    cov = coverage_of(entries, schema)
    sch = [dict(fc, fill_rate=(cov["facets"].get(fc["facet"]) or {}).get("rate", 0.0),
                filled=(cov["facets"].get(fc["facet"]) or {}).get("filled", 0)) for fc in schema]
    C.wjson(out / "facets" / "facet_schema.json",
            {"schema_origin": origin, "facets": sch,
             "naming_template": tpl or (spec.get("naming") or {}).get("template"),
             "dir_template": (spec.get("naming") or {}).get("dir_template"),
             "counts": {"facets": len(sch), "entries": len(entries)}})
    C.wjson(out / "facets" / "facet_coverage.json", cov)
    C.wtext(out / "entries" / "catalog_entries.jsonl",
            "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in entries))
    C.wtext(out / "reconciliation" / "reconciliation_ledger.jsonl",
            "".join(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n" for d in decisions))
    sha8 = {e["entry_id"]: (e["sha256"] or "")[:8] for e in entries}
    C.wtext(out / "views" / "directory_tree.txt",
            render_tree([(n["target_path"], n["entry_id"], sha8.get(n["entry_id"], "")) for n in naming]))
    C.wtext(out / "views" / "naming_view.tsv",
            "entry_id\told_name\tnew_name\ttemplate_id\tdegradation\ttarget_path\n" + "".join(
                "%s\t%s\t%s\t%s\t%s\t%s\n" % (n["entry_id"], n["old_name"], n["new_name"], n["template_id"],
                                              n["degradation"], n["target_path"]) for n in naming))
    C.wjson(out / "views" / "facet_index.json", facet_index(entries))
    C.wtext(out / "provenance" / "operations.log",
            "op\tsrc\tdst\tsha256_before\tsha256_after\tstatus\tentry_id\n" + "".join(
                "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (o["op"], o["src"], o["dst"], o["sha_before"], o["sha_after"],
                                                  o["status"], o["entry_id"]) for o in ops))
    skipped = [{"file": e["file"], "reason": "unreadable: corrupt/encrypted; hash+size registered only"}
               for e in entries if e["text_layer"] == "unreadable"]
    skipped += [{"file": e["file"], "reason": "no_text_layer: scan/image; facets rely on filename+companion metadata"}
                for e in entries if e["text_layer"] == "no_text_layer"]
    skipped += [{"file": s["file"], "reason": C.norm(s.get("reason") or "agent reported skip")}
                for s in (draft.get("skipped") or []) if isinstance(s, dict) and s.get("file")]
    seen_skip, uniq = set(), []
    for s_ in skipped:
        if s_["file"] in seen_skip:
            continue
        seen_skip.add(s_["file"])
        uniq.append(s_)
    skipped = uniq
    C.wjson(out / "provenance" / "skipped.json", {"count": len(skipped), "items": skipped})
    created = [o["dst"] for o in ops if o["status"] == "applied"]
    C.wjson(out / "provenance" / "rollback.json",
            {"source_untouched": True, "created": created,
             "note": "全部操作为 copy（输入目录只读）；回滚=删除本次副本，原始文件从未被修改或删除",
             "steps": [{"op": "remove", "path": p} for p in created]})
    C.wtext(out / "provenance" / "rollback.sh",
            "#!/bin/sh\n# facet-catalog-curator rollback (generated). Input files are never modified.\nset -e\n"
            + "".join('rm -f "%s"\n' % p for p in created) + 'echo "rolled back %d copy/copies"\n' % len(created))
    idem = idempotency(ctx, naming, ops, entries)
    applied = [o for o in ops if o["status"] == "applied"]
    res["sources"] = [{"file": f["file"], "sha256": f["sha256"], "size": f["size"], "magic": f["magic"],
                       "text_layer": f["text_layer"]} for f in idx["files"]]
    res["evidence_index"], res["uncertainties"] = evidence, unc
    res["errors"], res["degradations"] = (res["errors"] or []) + errs, (res["degradations"] or []) + degr
    res["changes"] = [{"op": o["op"], "src": o["src"], "dst": o["dst"], "status": o["status"]} for o in applied]
    res["result"] = {
        "facets": sch, "entries": entries, "reconciliation": decisions, "naming_view": naming,
        "operations": ops, "skipped": skipped, "coverage": cov,
        "stats": {"files": len(idx["files"]), "documents": len(entries), "facets": len(sch),
                  "facets_filled": cov["matrix_total"], "decisions": len(decisions),
                  "needs_human": len([d for d in decisions if d["decision"] == "needs_human"]),
                  "ops": len(applied), "ops_noop": len([o for o in ops if o["status"] == "noop"]),
                  "skipped": len(skipped), "archive": len(archive),
                  "quote_verified": sum(1 for x in evidence if x["verified"]), "quote_checked": len(evidence)},
        "artifacts": {"facet_schema": "facets/facet_schema.json", "coverage": "facets/facet_coverage.json",
                      "entries": "entries/catalog_entries.jsonl",
                      "reconciliation": "reconciliation/reconciliation_ledger.jsonl",
                      "directory_tree": "views/directory_tree.txt", "naming_view": "views/naming_view.tsv",
                      "facet_index": "views/facet_index.json", "operations": "provenance/operations.log",
                      "rollback": "provenance/rollback.json", "rollback_script": "provenance/rollback.sh",
                      "skipped": "provenance/skipped.json", "idempotency": "provenance/idempotency.json",
                      "library_root": "library/"}}
    res["method_notes"] = [
        "四层闭合：facet schema(%d) -> entries(%d) -> reconciliation(%d) -> views(树/命名/倒排)"
        % (len(sch), len(entries), len(decisions)),
        "可核验：%d/%d 个已填面元值有逐字 quote 命中（evidence_index），对账以 %s 为 basis"
        % (sum(1 for x in evidence if x["verified"]), max(1, len(evidence)), "sha256/doi/metadata/version_note"),
        "可回滚：真实创建 %d 个副本，provenance/rollback.sh 一键撤销；输入目录只读" % len(applied),
        "幂等：第 %d 次运行 ops=%d，命名一致率 %.2f" % (idem["run_index"], idem["ops_applied"], idem["naming_stability"])]
    status = "failed" if not entries else ("partial" if (derr or skipped or unc or res["degradations"]) else "ok")
    ctx["finalize"](ctx, status)
    print("[build] entries=%d decisions=%d ops=%d archive=%d skipped=%d status=%s"
          % (len(entries), len(decisions), len(applied), len(archive), len(skipped), status))
    print("[build] artifacts -> %s" % out)
    print("[build] result.json contract fields filled: %d" % len(ctx["res"].get("contract_fields") or {}))


# ------------------------------------------------------------------ selfcheck
def cmd_selfcheck(ctx):
    """Re-verify artefacts from disk; never rewrites the substantive result."""
    out = Path(ctx["out"])
    rep = {"checks": {}, "passed": 0, "failed": 0}

    def put(name, ok, detail=""):
        rep["checks"][name] = {"ok": bool(ok), "detail": detail}
        rep["passed" if ok else "failed"] += 1

    def jl(p):
        try:
            return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:  # noqa: BLE001
            return []

    entries = jl(out / "entries" / "catalog_entries.jsonl")
    decisions = jl(out / "reconciliation" / "reconciliation_ledger.jsonl")
    naming = []
    try:
        lines = (out / "views" / "naming_view.tsv").read_text(encoding="utf-8").splitlines()
        head = lines[0].split("\t") if lines else []
        naming = [dict(zip(head, l.split("\t"))) for l in lines[1:]]
    except Exception:  # noqa: BLE001
        pass
    put("entries_present", len(entries) > 0, "%d entries" % len(entries))
    put("entries_unique", len({e.get("entry_id") for e in entries}) == len(entries))
    put("decisions_have_basis", all(d.get("basis") and d.get("rollback_action") for d in decisions),
        "%d decisions" % len(decisions))
    put("naming_complete", len(naming) == len(entries) and all(n.get("new_name") for n in naming))
    try:
        tree = (out / "views" / "directory_tree.txt").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        tree = ""
    ids = re.findall(r"\((E\d+) [0-9a-f]*\)", tree)
    put("tree_matches_entries", sorted(ids) == sorted(n["entry_id"] for n in naming) and bool(ids), "%d nodes" % len(ids))
    logged = {n.get("entry_id"): (n.get("new_name") or "") for n in naming}
    same = 0
    for e in entries:
        want, logged_name = Path(name_of(e, ctx["spec"])[0]).stem, Path(logged.get(e.get("entry_id"), "")).stem
        same += 1 if logged_name == want or logged_name.startswith(want) else 0
    order_ok = [n.get("target_path") for n in naming] == sorted(n.get("target_path") for n in naming)
    put("naming_stability", same == len(entries) and order_ok,
        "%d/%d names reproduced from entries+template, fixed ordering" % (same, len(entries)))
    ops = []
    try:
        ops = [l.split("\t") for l in (out / "provenance" / "operations.log").read_text(
            encoding="utf-8").splitlines()[1:] if l.strip()]
    except Exception:  # noqa: BLE001
        pass
    put("ops_logged", len(ops) == len(naming), "%d ops" % len(ops))
    put("copies_verified", all(o[3] == o[4] for o in ops if len(o) >= 6 and o[5] != "noop"), "sha256 before==after")
    texts = {}
    try:
        texts = (ctx["load_index"](ctx) or {}).get("texts") or {}
    except Exception as exc:  # noqa: BLE001
        rep["texts_error"] = "%s: %s" % (type(exc).__name__, exc)
    rep["texts_indexed"] = len(texts)
    kinds = {}
    try:
        sch, _ = C.ljson(out / "facets" / "facet_schema.json")
        kinds = {f.get("facet"): (f.get("evidence_kind") or "quote") for f in (sch or {}).get("facets") or []}
    except Exception:  # noqa: BLE001
        pass
    hit = tot = judged = 0
    for e in entries:
        for k, v in (e.get("facets") or {}).items():
            if not C.filled(v):
                continue
            if kinds.get(k) in ("judgment", "path_or_judgment"):
                judged += 1
                continue
            tot += 1
            hit += 1 if C.quote_ok(texts, (e.get("field_sources") or {}).get(k, {}).get("locator"),
                                   (e.get("field_sources") or {}).get(k, {}).get("quote"))[0] else 0
    rep["judgment_values"] = judged
    put("quotes_verified", tot > 0 and hit == tot, "%d/%d quoted facets verified (%d judgment/path values)"
        % (hit, tot, judged))
    idem, _ = C.ljson(out / "provenance" / "idempotency.json")
    put("idempotency_recorded", isinstance(idem, dict) and "runs" in idem, str((idem or {}).get("conclusion")))
    contract = ctx["case"].get("output_contract") or {}
    rj, _ = C.ljson(out / "result.json")
    put("contract_keys_present",
        isinstance(rj, dict) and all(k in rj for k in contract)
        and (not ctx["case"].get("case_id") or rj.get("case_id") == ctx["case"].get("case_id")),
        "%d keys" % len(contract))
    put("result_valid_json", isinstance(rj, dict))
    rep["quote_hit_rate"] = round(hit / max(1, tot), 4)
    rep["verdict"] = "pass" if rep["failed"] == 0 else "attention_needed"
    C.wjson(out / "provenance" / "verify_report.json", rep)
    if isinstance(rj, dict):
        rj.setdefault("result", {})["verify"] = rep
        C.wjson(out / "result.json", rj)
    print("[selfcheck] passed=%d failed=%d quote_hit=%s verdict=%s"
          % (rep["passed"], rep["failed"], rep["quote_hit_rate"], rep["verdict"]))
    for k, v in rep["checks"].items():
        if not v["ok"]:
            print("  FAIL %s %s" % (k, v["detail"]))
