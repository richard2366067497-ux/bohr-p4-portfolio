# -*- coding: utf-8 -*-
"""staging -- directory plan, verified landing, tree rendering, archive package.

All writes are inside the caller-provided library root. Every copy is re-hashed
at the destination; a mismatch is quarantined instead of being reported as done.
"""
import os
import re
import shutil
import zipfile

import textkit as T
import libscan as L

sha256_file = L.sha256_file
COPY_LIMIT = L.COPY_LIMIT
ZIP_LIMIT = L.ZIP_LIMIT
HASH_LIMIT = L.HASH_LIMIT


# --------------------------------------------------------------- landing/plan
BAD_NAME = re.compile(r"(?i)([\s_\-.]+(copy|\u526f\u672c|\u5907\u4efd|\u65e7\u7248)([\s_\-.]*\d*)?)+")


def safe_name(name, used):
    base = T.nfc(os.path.basename(name)).replace("/", "_").replace("\\", "_").strip()
    if not base:
        base = "unnamed"
    base = BAD_NAME.sub("", base)
    base = re.sub(r"[\x00-\x1f]", "", base).strip(" .")
    if not base:
        base = "unnamed"
    stem, ext = os.path.splitext(base)
    cand, i = base, 1
    while cand.lower() in used:
        i += 1
        cand = "%s__v%d%s" % (stem, i, ext)
    used.add(cand.lower())
    return cand


def plan_default(entries):
    plan = []
    for e in entries:
        if e["status"] == "symlink":
            to = "_quarantine/"
        elif e["status"] in ("corrupt", "unreadable"):
            to = "_quarantine/"
        else:
            to = "_unsorted/"
        plan.append({"from": e["path"], "to": to, "rule_id": "fallback-unsorted"})
    return plan


def land(entries, plan, libroot, dup_skip=None, tag="build"):
    """Materialise the plan; verify every copy by re-hashing the destination."""
    ops, landed, integrity, skipped, collisions, quarantined = [], [], [], [], [], []
    by_path = {e["path"]: e for e in entries}
    dup_skip = dup_skip or set()
    tree = {".": {"type": "dir", "children": []}}
    dirs_made = set()
    try:
        os.makedirs(libroot, exist_ok=True)
    except OSError as ex:
        return {"ops": ops, "landed": landed, "integrity": integrity, "skipped":
                [{"path": libroot, "reason": "mkdir_failed:%s" % type(ex).__name__}],
                "collisions": collisions, "quarantined": quarantined, "tree": tree, "space_ok": False}
    free = 0
    try:
        free = shutil.disk_usage(libroot).free
    except OSError:
        free = 1 << 62
    used_names = {}
    for item in plan:
        src = item.get("from")
        e = by_path.get(src)
        if not e:
            ops.append(_op(tag, "copy", src, None, None, "failed", "path_not_in_index"))
            skipped.append({"path": src, "reason": "path_not_in_index"})
            continue
        todir = (item.get("to") or "_unsorted/").replace("\\", "/").strip("/")
        if e["status"] == "corrupt" or e["status"] == "unreadable" or todir.startswith("_quarantine"):
            todir = "_quarantine" + ("/" + todir.split("_quarantine")[-1].strip("/") if "_quarantine" in todir else "")
        if src in dup_skip:
            ops.append(_op(tag, "dedupe", src, None, e.get("sha256"), "skipped", "duplicate_of_kept_copy"))
            skipped.append({"path": src, "reason": "duplicate_content"})
            continue
        if e["status"] == "too_large":
            ops.append(_op(tag, "copy", src, None, None, "skipped", "exceeds_copy_limit_or_hash_limit"))
            skipped.append({"path": src, "reason": "too_large"})
            continue
        if e["status"] == "symlink":
            ops.append(_op(tag, "copy", src, None, None, "skipped", "symlink_not_followed"))
            skipped.append({"path": src, "reason": "symlink"})
            continue
        if (e.get("size") or 0) > COPY_LIMIT:
            ops.append(_op(tag, "copy", src, None, e.get("sha256"), "skipped", "file_exceeds_copy_limit"))
            skipped.append({"path": src, "reason": "exceeds_copy_limit"})
            continue
        if (e.get("size") or 0) > free:
            ops.append(_op(tag, "copy", src, None, e.get("sha256"), "failed", "insufficient_space"))
            skipped.append({"path": src, "reason": "insufficient_space"})
            continue
        d = os.path.join(libroot, todir) if todir else libroot
        if d not in dirs_made:
            try:
                os.makedirs(d, exist_ok=True)
                dirs_made.add(d)
                ops.append(_op(tag, "mkdir", None, os.path.relpath(d, libroot).replace(os.sep, "/"),
                               None, "ok", "created"))
            except OSError as ex:
                ops.append(_op(tag, "mkdir", None, todir, None, "failed", type(ex).__name__))
                skipped.append({"path": src, "reason": "mkdir_failed"})
                continue
        used = used_names.setdefault(d, set())
        name = safe_name(e["path"], used)
        if T.nfc(os.path.basename(e["path"])) != T.nfc(name):
            collisions.append({"from": e["path"], "as": name, "reason": "name_normalized"})
        dst = os.path.join(d, name)
        trel = os.path.relpath(dst, libroot).replace(os.sep, "/")
        if os.path.exists(dst):
            # idempotent re-run: an identical copy already sits at the target
            prev, _ = sha256_file(dst)
            if prev and prev == e.get("sha256"):
                ops.append(_op(tag, "copy", src, trel, prev, "ok", "already_present_identical"))
                rec = {"source": src, "target": trel, "sha256_src": e.get("sha256"),
                       "sha256_dst": prev, "size": e.get("size"), "verified": True,
                       "kind": e.get("kind"), "note": "idempotent_skip"}
                integrity.append(rec)
                landed.append(rec)
                _add_tree(tree, trel)
                continue
            name = safe_name(e["path"], used)
            dst = os.path.join(d, name)
            trel = os.path.relpath(dst, libroot).replace(os.sep, "/")
            collisions.append({"from": e["path"], "as": name, "reason": "destination_exists_different_bytes"})
        try:
            shutil.copy2(e["_abs"], dst)
        except OSError as ex:
            ops.append(_op(tag, "copy", src, os.path.relpath(dst, libroot).replace(os.sep, "/"),
                           e.get("sha256"), "failed", type(ex).__name__))
            skipped.append({"path": src, "reason": "copy_failed:%s" % type(ex).__name__})
            continue
        free -= e.get("size") or 0
        got, err = sha256_file(dst)
        ok = bool(got) and got == e.get("sha256")
        trel = os.path.relpath(dst, libroot).replace(os.sep, "/")
        ops.append(_op(tag, "copy", src, trel, got, "ok" if ok else "failed",
                       None if ok else "hash_mismatch(%s)" % (err or "content_changed")))
        rec = {"source": src, "target": trel, "sha256_src": e.get("sha256"), "sha256_dst": got,
               "size": e.get("size"), "verified": ok, "kind": e.get("kind")}
        integrity.append(rec)
        if ok:
            landed.append(rec)
            _add_tree(tree, trel)
        else:
            quarantined.append(rec)
            skipped.append({"path": src, "reason": "hash_mismatch"})
            try:
                qd = os.path.join(libroot, "_quarantine")
                os.makedirs(qd, exist_ok=True)
                shutil.move(dst, os.path.join(qd, name))
            except OSError:
                pass
    return {"ops": ops, "landed": landed, "integrity": integrity, "skipped": skipped,
            "collisions": collisions, "quarantined": quarantined, "tree": tree,
            "space_ok": not any(s["reason"] == "insufficient_space" for s in skipped)}


def _op(tag, op, src, dst, sha, result, reason):
    return {"ts": T.now(), "step": tag, "op": op, "from": src, "to": dst,
            "sha256": sha, "result": result, "reason": reason}


def _add_tree(tree, trel):
    parts = trel.split("/")
    node = tree["."]
    for i, p in enumerate(parts):
        child_key = "/".join(parts[:i + 1]) + ("/" if i < len(parts) - 1 else "")
        if child_key not in tree:
            tree[child_key] = {"type": "dir" if i < len(parts) - 1 else "file",
                               "children": [] if i < len(parts) - 1 else None}
            node["children"].append(child_key)
        node = tree[child_key] if i < len(parts) - 1 else node


def tree_lines(tree):
    """Render the landed tree; keys are cumulative paths, labels are path tails."""
    out = ["library/"]

    def walk(key, level):
        node = tree.get(key)
        if not node:
            return
        label = key.rstrip("/").split("/")[-1] or key
        is_dir = node.get("type") == "dir"
        out.append("  " * level + ("+ " if is_dir else "- ") + label + ("/" if is_dir else ""))
        for c in node.get("children") or []:
            walk(c, level + 1)
    for c in tree["."]["children"]:
        walk(c, 1)
    return out


def archive_manifest(landed, libroot, rules=None):
    rules = rules or {}
    members = [{"path": r["target"], "sha256": r["sha256_dst"], "size": r.get("size"),
                "source": r["source"], "verified": r.get("verified", False)} for r in landed]
    total = sum(m.get("size") or 0 for m in members)
    man = {"created": T.now(), "root": "library/", "member_count": len(members),
           "total_bytes": total, "members": members,
           "checksum_alg": "sha256",
           "retention": rules.get("retention") or "project_lifecycle_5y",
           "permission_scope": rules.get("permission_scope") or "internal_project_team",
           "provenance": rules.get("provenance") or "organizer_provided_input_library",
           "verified": all(m["verified"] for m in members) and bool(members),
           "zip": None}
    return man


def write_zip(man, libroot, zpath):
    if not man["members"] or man["total_bytes"] > ZIP_LIMIT:
        return None, "skipped(size=%d,limit=%d)" % (man["total_bytes"], ZIP_LIMIT)
    try:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for m in man["members"]:
                p = os.path.join(libroot, m["path"])
                if os.path.isfile(p):
                    z.write(p, m["path"])
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
        if len(names) != len(man["members"]):
            return None, "member_count_mismatch(%d!=%d)" % (len(names), len(man["members"]))
        return os.path.basename(zpath), "members=%d" % len(names)
    except Exception as e:
        return None, "zip_failed:%s" % type(e).__name__


# ------------------------------------------------------- build-time assembly
def template_of(idx):
    rules = idx.get("rules") or {}
    for k in ("directory_template", "template", "tree", "pattern", "目录模板"):
        v = L.pick(rules, [k])
        if isinstance(v, str) and v.strip():
            return v
    return "{project}/{year}/{doc_type}/"


def merge_dups(detected, draft_dups):
    """Keep script-detected groups; adopt the agent's keep/archive choice when given."""
    by = {d["sha256"]: d for d in detected}
    for d in draft_dups or []:
        if not isinstance(d, dict) or not d.get("sha256"):
            continue
        h = d["sha256"]
        if h in by:
            if d.get("keep"):
                by[h]["keep"] = d["keep"]
            by[h]["basis"] = "identical_content_hash+draft_selection"
        else:
            by[h] = {"sha256": h, "count": 1 + len(T.as_list(d.get("archive"))),
                     "keep": d.get("keep"), "archive": T.as_list(d.get("archive")),
                     "members": [x for x in [d.get("keep")] + T.as_list(d.get("archive")) if x],
                     "basis": "draft_asserted_same_hash", "size": None}
    return [by[k] for k in sorted(by)]


def build_metadata(idx, draft, ctx):
    """Agent metadata wins; files without draft metadata are filled from sidecar tables."""
    meta, seen = [], set()
    files = {e["path"]: e for e in idx["files"]}
    for m in T.as_list(draft.get("metadata")):
        if not isinstance(m, dict) or m.get("path") not in files:
            continue
        raw = m.get("fields")
        if not isinstance(raw, dict):
            continue
        fields = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                val, src = v.get("value"), v.get("source")
                conf = "agent_located" if src else ("agent_unlocatable" if val not in (None, "") else "empty")
            else:
                val, src, conf = v, None, "agent_unlocatable"
            if val in (None, ""):
                conf = "empty"
            fields[k] = {"value": val, "source": src, "confidence": conf,
                         "rule_id": "draft" if src else "draft_no_locator"}
        if fields:
            meta.append({"path": m["path"], "sha256": files[m["path"]].get("sha256"), "fields": fields})
            seen.add(m["path"])
    by_file = {}
    for r in idx.get("metadata_rows") or []:
        e = L.resolve_ref(r.get("file") or "", idx["files"])
        if e:
            by_file.setdefault(e["path"], []).append(r)
    for path, rs in sorted(by_file.items()):
        if path in seen:
            continue
        fields = {}
        for r in rs:
            f = str(r.get("field") or "").strip().lower()
            if f and f not in fields:
                fields[f] = {"value": r.get("value"), "source": r.get("source"),
                             "confidence": "sidecar_table", "rule_id": "sidecar"}
        if fields:
            meta.append({"path": path, "sha256": files.get(path, {}).get("sha256"), "fields": fields})
    if not meta:
        ctx["degradations"].append({"code": "metadata_empty",
                                    "detail": "no metadata in draft and no sidecar rows resolved"})
    elif by_file:
        ctx["degradations"].append({"code": "metadata_partly_from_sidecar", "count": len(by_file),
                                    "detail": "files without draft metadata filled from sidecar tables"})
    return meta


def build_queries(idx, draft):
    """Verify agent hits verbatim; answer undeclared-but-declared queries deterministically."""
    deg, out = [], []
    files = {e["path"]: e for e in idx["files"]}
    used = set()
    for q in T.as_list(draft.get("queries")):
        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
            continue
        qn = str(q["question"]).strip()
        rec = {"question": qn, "origin": "agent", "hits": [], "status": "unresolved"}
        for h in T.as_list(q.get("hits")):
            if not isinstance(h, dict):
                continue
            p, quote = h.get("path"), h.get("quote")
            e = files.get(p)
            if not e:
                rec["hits"].append({"path": p, "locator": h.get("locator"), "quote": quote,
                                    "verified": False, "issue": "path_not_in_index"})
                continue
            span = T.find_quote((e.get("_text") or {}).get("lines") or [], str(quote or ""))
            rec["hits"].append({"path": p,
                                "locator": h.get("locator") or ("%s#L%d" % (p, span[0]) if span else None),
                                "quote": quote, "verified": bool(span),
                                "matched_text": T.snippet((e.get("_text") or {}).get("lines") or [], span),
                                "issue": None if span else "quote_not_found"})
        if not rec["hits"]:
            rec["miss_reason"] = q.get("miss_reason") or q.get("no_hit_reason")
            rec["status"] = "miss" if rec["miss_reason"] else "unresolved"
        else:
            rec["status"] = "hit" if any(h["verified"] for h in rec["hits"]) else "unverified"
        out.append(rec)
        used.add(T.norm(qn)[:16])
    for q0 in idx.get("queries") or []:
        qn = (q0.get("question") or "").strip()
        if not qn or T.norm(qn)[:16] in used:
            continue
        rec = {"question": qn, "origin": "script_keyword_fallback", "hits": [], "status": "unresolved"}
        for c in keyword_search(idx["files"], qn, top=3):
            span = T.find_quote((files[c["path"]].get("_text") or {}).get("lines") or [], c["quote"])
            rec["hits"].append({"path": c["path"], "locator": c["locator"], "quote": c["quote"],
                                "verified": bool(span), "origin": "script",
                                "issue": None if span else "quote_not_found"})
        if rec["hits"]:
            rec["status"] = "hit"
            rec["note"] = "declared query not answered by the agent; deterministic keyword result"
            deg.append({"code": "query_answered_by_script", "detail": qn[:80]})
        else:
            rec["status"] = "no_match"
            rec["miss_reason"] = "no searchable text matched the query tokens in the scanned material"
        out.append(rec)
    return out, deg


def build_recovery(idx, entries, dups, chains, land, draft):
    """Two-way reconciliation: disk issues, index conservation, note-edge gaps."""
    deg, items = [], []
    for e in entries:
        if e["status"] in ("corrupt", "unreadable", "too_large", "symlink", "empty"):
            items.append({"type": {"corrupt": "corrupt_file", "unreadable": "unreadable_file",
                                   "too_large": "oversized_file", "symlink": "symlink",
                                   "empty": "empty_file"}[e["status"]],
                          "path": e["path"], "reason": e.get("reason"),
                          "action": "quarantined" if e["status"] in ("corrupt", "unreadable") else "recorded_only"})
    for d in dups:
        items.append({"type": "duplicate_content", "sha256": d["sha256"], "keep": d.get("keep"),
                      "archive": d.get("archive"), "action": "archive_copy_not_landed"})
    for x in idx.get("note_issues") or []:
        items.append({"type": x["type"], "locator": x.get("locator"), "detail": x.get("detail"),
                      "action": "recorded_only; not linked", "resolution": "unresolved"})
    landed = len(land["landed"])
    dup_n = sum(len(d.get("archive") or []) for d in dups)
    skip_n = len([s for s in land["skipped"] if s["reason"] != "duplicate_content"])
    total = len(entries)
    conserved = (landed + dup_n + skip_n) == total
    if not conserved:
        deg.append({"code": "index_conservation_mismatch",
                    "detail": "landed=%d dup=%d skipped=%d total=%d" % (landed, dup_n, skip_n, total)})
    acts = []
    for r in T.as_list(draft.get("recovery")):
        if not isinstance(r, dict):
            continue
        a = str(r.get("action") or "").lower()
        rec = {"file": r.get("file"), "action": a, "pre_state": r.get("pre_state"),
               "expect": r.get("expect"), "note": r.get("note"), "result": "acknowledged"}
        if a == "restore":
            rec["result"] = "not_executed"
            rec["note"] = ((r.get("note") or "") +
                           " | restore requires a byte-identical backup copy; none was verified")
            deg.append({"code": "restore_not_executed", "detail": str(r.get("file"))})
        acts.append(rec)
    return {"generated": T.now(), "issues": items, "draft_actions": acts,
            "index_rebuild": {"method": "rebuilt from disk inventory", "entries": total,
                              "landed": landed, "duplicates_not_landed": dup_n,
                              "skipped_other": skip_n, "conserved": conserved,
                              "chain_members": sum(len(c["members"]) for c in chains)},
            "policy": "nothing is reported recovered unless a byte-identical copy was verified"}, deg


def final_status(ctx, entries, land, draft, fixes, meta, queries, chains):
    if not entries:
        return "failed"
    if ctx["errors"] or not draft or fixes or not land["landed"] or not meta:
        return "partial"
    if any(not i["verified"] for i in land["integrity"]):
        return "partial"
    if any(q.get("status") in ("unresolved", "unverified", "miss") for q in queries):
        return "partial"
    if any(c["confidence"] == "low" for c in chains):
        return "partial"
    return "ok"


def csv_inventory(entries):
    cols = ["path", "size", "sha256", "mtime", "ext", "kind", "status", "reason", "depth", "mode"]
    lines = [",".join(cols)]
    for e in entries:
        row = []
        for c in cols:
            v = "" if e.get(c) is None else str(e.get(c))
            if any(ch in v for ch in ',"\n'):
                v = '"' + v.replace('"', '""') + '"'
            row.append(v)
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------- dedupe

def dedupe(entries):
    groups = {}
    for e in entries:
        if e.get("sha256"):
            groups.setdefault(e["sha256"], []).append(e)
    out = []
    for h, mem in sorted(groups.items()):
        if len(mem) < 2:
            continue
        mem = sorted(mem, key=lambda x: (len(x["path"]), x["path"]))
        out.append({"sha256": h, "count": len(mem), "keep": mem[0]["path"],
                    "archive": [m["path"] for m in mem[1:]],
                    "members": [m["path"] for m in mem],
                    "basis": "identical_content_hash", "size": mem[0].get("size")})
    return out


# -------------------------------------------------------------- show command


def _inv(e):
    return {k: e.get(k) for k in ("path", "size", "sha256", "mtime", "ext", "kind",
                                  "status", "reason", "depth", "mode")}


def _cks(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract.keys()]
    return [str(x) for x in (contract or [])]

def cmd_show(a, cli_paths):
    """Located listing: materials, note edges, queries, numbered text for quoting."""
    inp, work, out = cli_paths(a)
    idx, rebuilt = L.load_index(work, inp, with_text=True)
    entries, lim = idx["files"], a.limit or 200
    if rebuilt:
        print("[show] index.json missing -> rebuilt in memory; run `init` to persist")
    if a.text:
        e = next((x for x in entries if x["path"] == a.text), None) or L.resolve_ref(a.text, entries)
        if not e:
            print("[show] not found: %s (use `show --json` for exact paths)" % a.text)
            return 0
        t = _text_of(e)
        lines = t.get("lines") or []
        print("[show] %s kind=%s mode=%s lines=%d sha256=%s" % (
            e["path"], e["kind"], t.get("mode"), len(lines), (e.get("sha256") or "-")[:16]))
        for i, ln in enumerate(lines[:lim]):
            print("%4d| %s" % (i + 1, ln[:400]))
        if len(lines) > lim:
            print("... %d more lines (raise --limit)" % (len(lines) - lim))
        return 0
    if a.json:
        print(json.dumps({"case_id": idx.get("case_id"), "stats": idx.get("stats"),
                          "files": [dict(_inv(e), text={"mode": _text_of(e).get("mode"),
                                                           "lines": _text_of(e).get("n_lines")})
                                    for e in entries],
                          "alias": idx["alias"], "versions": idx["versions"],
                          "note_issues": idx["note_issues"], "queries": idx["queries"],
                          "contract": idx.get("contract"), "rules": idx.get("rules"),
                          "metadata_rows": idx.get("metadata_rows"),
                          "dup_groups": dedupe(entries),
                          "chains": L.build_chains(entries, idx["alias"], idx["versions"], [])[0]},
                         ensure_ascii=False, indent=1)[:180000])
        return 0
    if a.notes:
        print("[show] alias edges:")
        for i, x in enumerate(idx["alias"][:lim]):
            print("  A%02d %-9s %s  %r -> %r%s" % (i + 1, x["status"], x["locator"], x["alias"],
                                                   x["canonical"],
                                                   "" if x["status"] == "resolved" else "  [DANGLING]"))
        print("[show] version edges (prev = superseded file, cur = newer file):")
        for i, x in enumerate(idx["versions"][:lim]):
            print("  V%02d %-9s %s  prev=%r cur=%r" % (i + 1, x["status"], x["locator"],
                                                       x["supersedes"], x["file"]))
        print("[show] unresolved=%d" % len(idx["note_issues"]))
        for x in idx["note_issues"][:lim]:
            print("  ! %s %s %s" % (x["type"], x.get("locator"), x.get("detail")))
        return 0
    if a.queries:
        print("[show] declared queries: %d" % len(idx["queries"]))
        for i, q in enumerate(idx["queries"]):
            print("  Q%d [%s] %s" % (i + 1, q.get("id") or "-", q.get("question")))
            cands = keyword_search(entries, q["question"], top=3)
            for h in cands:
                print("     cand %s  %r" % (h["locator"], h["quote"][:150]))
            if not cands:
                print("     cand NONE -> decide and write miss_reason")
        return 0
    st = {}
    for e in entries:
        st[e["status"]] = st.get(e["status"], 0) + 1
    print("[show] case_id=%s input=%s files=%d status=%s" % (idx.get("case_id"), inp, len(entries), st))
    print("[show] contract keys: %s" % _cks(idx.get("contract")))
    print("[show] materials (status kind size path):")
    for e in entries[:lim]:
        print("  %-9s %-6s %8s  %s%s" % (e["status"], e["kind"], e.get("size"), e["path"],
                                         "" if e["status"] == "ok" else "  reason=%s" % e.get("reason")))
    if len(entries) > lim:
        print("  ... %d more" % (len(entries) - lim))
    print("[show] aliases=%d versions=%d unresolved=%d" % (
        len(idx["alias"]), len(idx["versions"]), len(idx["note_issues"])))
    for d in dedupe(entries)[:20]:
        print("  dup %s x%d keep=%s archive=%s" % (d["sha256"][:12], d["count"], d["keep"], d["archive"]))
    ch, _ = L.build_chains(entries, idx["alias"], idx["versions"], [])
    print("[show] candidate chains=%d" % len(ch))
    for c in ch[:20]:
        print("  %s conf=%s %s" % (c["chain_id"], c["confidence"], " -> ".join(c["order"])))
    print("[show] NEXT: `show --notes` / `show --queries` / `show --text <path>`; then write draft.json")
    return 0

def _text_of(e):
    return e.get("_text") or T.extract(e.get("_abs") or "", e.get("kind"))


# ------------------------------------------------------------ text search

def keyword_search(entries, question, top=3):
    """Deterministic pre-search: returns candidate hits with verbatim lines."""
    tk = tokens(question)
    if not tk:
        return []
    scored = []
    for e in entries:
        t = e.get("_text") or {}
        lines = t.get("lines") or []
        if not lines:
            continue
        best = (0, None)
        for i, ln in enumerate(lines):
            key = T.norm(ln)
            if not key:
                continue
            hit = sum(1 for g in tk if T.norm(g) and T.norm(g) in key)
            if hit > best[0]:
                best = (hit, i + 1)
        if best[0] > 0:
            scored.append((best[0], e, best[1], len(tk)))
    scored.sort(key=lambda x: (-x[0], x[1]["path"]))
    out = []
    for score, e, ln, ntk in scored[:top]:
        lines = e["_text"]["lines"]
        out.append({"path": e["path"], "locator": "%s#L%d" % (e["path"], ln),
                    "quote": lines[ln - 1].strip()[:400],
                    "score": "%d/%d" % (score, ntk), "mode": e["_text"].get("mode"),
                    "origin": "script_presearch"})
    return out

def tokens(q):
    q = T.nfc(q or "").lower()
    latin = re.findall(r"[a-z0-9][a-z0-9_.\-]{1,}", q)
    cjk = re.findall(r"[\u4e00-\u9fff]+", q)
    grams = []
    for run in cjk:
        if len(run) <= 2:
            grams.append(run)
        else:
            grams.extend([run[i:i + 2] for i in range(len(run) - 1)])
    stop = {"the", "and", "for", "with", "what", "which", "how", "does", "was", "were",
            "the", "of", "in", "on", "is", "are", "any", "all", "file", "which"}
    return [t for t in latin if t not in stop and len(t) > 1] + grams
