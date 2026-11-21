"""check / build / selfcheck for library-curator (stdlib only).

build merges the Agent draft with the deterministic rule table, executes real directory operations
into a curated tree, writes every artifact and finalises result.json unconditionally; a missing or
broken draft still yields a complete, degraded delivery.
"""

import csv
import json
import os
import re
import shlex
import time
from pathlib import Path

import contract as C
import library_ops as L
import library_text as T


def load_draft(work):
    for name in ("draft.json", "plan.json"):
        p = work / name
        if p.is_file():
            obj, err = C.load_json(p)
            return (obj if isinstance(obj, dict) else None), name, err
    return None, None, "draft.json / plan.json not found"

def build_entries(recs, draft, degr, skip_paths=()):
    entries, auto_count = {}, 0
    for e in (draft or {}).get("classification") or []:
        if not isinstance(e, dict):
            continue
        rec = L.find_rec(recs, e.get("path"))
        if not rec:
            degr.append("draft.classification path not in index, ignored: %s" % str(e.get("path"))[:120])
            continue
        if rec["rel"] in entries:
            degr.append("duplicate draft entry for %s, first kept" % rec["rel"])
            continue
        cp = str(e.get("class_path") or "").strip().strip("/")
        if not cp:
            cp = rec["auto"]["class_path"]
            degr.append("%s: class_path empty -> rule-table value %s" % (rec["rel"], cp))
        tags = [T.norm(str(t)).lower() for t in (e.get("tags") or []) if str(t or "").strip()][:12]
        meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        entries[rec["rel"]] = {"path": rec["rel"], "doc_id": rec["doc_id"], "class_path": cp,
                               "doc_type": e.get("doc_type") or rec.get("doc_type") or cp.split("/")[0],
                               "tags": tags, "basis": e.get("basis") or rec["auto"]["basis"],
                               "quote": e.get("quote") or "", "metadata": meta,
                               "confidence": e.get("confidence") or "medium", "auto": False,
                               "notes": e.get("notes") or ""}
    for rec in recs:
        if rec["rel"] in entries or rec["rel"] in skip_paths:
            continue
        entries[rec["rel"]] = dict(rec["auto"])
        auto_count += 1
    if auto_count:
        degr.append("%d file(s) had no usable draft entry and were classified by the rule table only "
                    "(auto=true, confidence=low)" % auto_count)
    return entries

def build_renames(recs, entries, draft, rules, degr):
    ren, explicit = {}, 0
    for e in (draft or {}).get("renames") or []:
        if not isinstance(e, dict):
            continue
        rec = L.find_rec(recs, e.get("from"))
        if not rec:
            degr.append("draft.renames entry ignored (unknown path): %s" % str(e.get("from"))[:120])
            continue
        to = T.norm(str(e.get("to") or "")).replace("/", "-")
        if not to:
            continue
        if not os.path.splitext(to)[1]:
            to += rec["ext"]
        ren[rec["rel"]] = {"from": rec["rel"], "to": L.sanitize(to),
                           "template": e.get("template") or rules.get("naming_template") or "explicit",
                           "degradation": e.get("degradation") or "", "source": "draft"}
        explicit += 1
    tpl = rules.get("naming_template") or "{first_author}-{year}-{title_short}"
    for rel, ent in entries.items():
        if rel in ren:
            continue
        rec = L.find_rec(recs, rel)
        meta = dict(ent.get("metadata") or {})
        for f, v in (rec.get("meta") or {}).items():
            if v.get("value") and not meta.get(f):
                meta[f] = v["value"]
        if rec["kind"] in ("admin_note", "metadata_table") and not meta.get("title"):
            ren[rel] = {"from": rel, "to": L.sanitize(rec["name"]), "template": "keep_original",
                        "degradation": "note/manifest file without bibliographic fields -> original name kept",
                        "fields_used": [], "source": "auto"}
            continue
        name, dlist, used = L.render_name(tpl, meta, rec["name"], rec.get("sha256"))
        ren[rel] = {"from": rel, "to": name, "template": tpl, "degradation": "; ".join(dlist),
                    "fields_used": used, "source": "auto"}
    if explicit:
        degr.append("%d rename(s) taken from the draft; the rest rendered from the template" % explicit)
    return ren

def build_groups(recs, draft, degr):
    dupes, chains = [], []
    for g in (draft or {}).get("dedupe") or []:
        if not isinstance(g, dict):
            continue
        ms = [L.find_rec(recs, p) for p in ([g.get("keep")] + list(g.get("archive") or []))]
        ms = [m for m in ms if m]
        if len(ms) < 2:
            degr.append("dedupe group ignored (members not found): %s" % str(g.get("sha256"))[:24])
            continue
        if len({m["sha256"] for m in ms}) > 1:
            degr.append("dedupe group rejected: members differ in sha256 (kept as a version question)")
            continue
        dupes.append({"sha256": ms[0]["sha256"], "keep": ms[0]["rel"],
                      "archive": [m["rel"] for m in ms[1:]],
                      "reason": g.get("reason") or "identical_content",
                      "members": [{"path": m["rel"], "doc_id": m["doc_id"], "size": m["size"]} for m in ms],
                      "source": "draft"})
    for g in L.dedupe_groups(recs):
        if not any(d["sha256"] == g["sha256"] for d in dupes):
            g["source"] = "auto"
            dupes.append(g)
    for c in (draft or {}).get("versions") or []:
        if not isinstance(c, dict):
            continue
        ms = [L.find_rec(recs, p) for p in (c.get("members") or [])]
        ms = [m for m in ms if m]
        if len(ms) < 2:
            degr.append("version chain ignored (<2 known members): %s" % str(c.get("chain_id")))
            continue
        keep = L.find_rec(recs, c.get("keep"))
        rels = [m["rel"] for m in ms]
        keep_rel = keep["rel"] if keep else rels[0]
        rel = c.get("relationship") if c.get("relationship") in L.RELATIONSHIPS else "undetermined"
        chains.append({"chain_id": c.get("chain_id") or "V%d" % (len(chains) + 1), "members": rels,
                       "relationship": rel, "keep": keep_rel,
                       "archive": [r for r in rels if r != keep_rel],
                       "evidence": c.get("evidence") or "", "quote": c.get("quote") or "", "source": "draft"})
    notes = [r for r in recs if r["kind"] == "admin_note"]
    for c in L.version_chains(recs, notes):
        if any(set(c["members"]) & set(x["members"]) for x in chains):
            continue
        c["source"] = "auto"
        chains.append(c)
    return dupes, chains

def build_skips(recs, draft, rules, degr, unc):
    skips = {}
    for s in (draft or {}).get("skipped") or []:
        if not isinstance(s, dict):
            continue
        rec = L.find_rec(recs, s.get("path"))
        if not rec:
            degr.append("skipped entry ignored (unknown path): %s" % str(s.get("path"))[:120])
            continue
        reason = str(s.get("reason") or "").strip()
        if reason not in L.SKIP_CODES:
            degr.append("%s: skip reason %r not in the reason table; kept as given" % (rec["rel"], reason))
        skips[rec["rel"]] = {"path": rec["rel"], "doc_id": rec["doc_id"], "reason": reason or "out_of_scope",
                             "detail": s.get("detail") or "", "sha256": rec["sha256"], "source": "draft"}
    auto_rules = (("permission_denied", lambda r: not r["readable"],
                   "file not readable by the runtime user"),
                  ("encrypted_pdf", lambda r: r["text_quality"] == "encrypted",
                   "PDF is encrypted; no text layer accessible"),
                  ("corrupt_file", lambda r: r["text_quality"] == "corrupt",
                   "header/parse failure; content not usable"),
                  ("unreadable_encoding", lambda r: r["text_quality"] == "unreadable_encoding",
                   "encoding could not be resolved; name-based handling only"),
                  ("unsupported_type", lambda r: r["text_quality"] == "unsupported_type" and r["kind"] == "document",
                   "no extractor for this extension; inventoried by hash only"))
    for rec in recs:
        if rec["rel"] in skips:
            continue
        for reason, pred, detail in auto_rules:
            try:
                if pred(rec):
                    skips[rec["rel"]] = {"path": rec["rel"], "doc_id": rec["doc_id"], "reason": reason,
                                         "detail": detail, "sha256": rec["sha256"], "source": "auto"}
                    break
            except Exception:
                continue
    declared = [d for d in (rules.get("declared") or []) if d]
    if declared:
        known = {r["rel"] for r in recs} | {r["name"] for r in recs}
        missing = [d for d in declared
                   if d not in known and not any(k.endswith(d.lstrip("./")) or d.lstrip("./").endswith(k)
                                                 for k in known)]
        for i, d in enumerate(missing[:80]):
            skips["__missing__%d" % i] = {"path": d, "doc_id": None, "reason": "missing_on_disk",
                                          "detail": "declared in the case manifest but absent from the material root",
                                          "sha256": None, "source": "manifest"}
        if missing:
            unc.append("%d path(s) declared in the case manifest are absent on disk; recorded as missing_on_disk "
                       "instead of being invented" % len(missing))
    return skips

def plan_jobs(recs, entries, renames, dupes, chains, skips, degr):
    archived = {}
    for g in dupes:
        for a in g.get("archive") or []:
            rec = L.find_rec(recs, a)
            if rec and rec["rel"] != g.get("keep"):
                archived[rec["rel"]] = ("_archive/%s" % (g.get("sha256") or "nosha")[:8],
                                        "duplicate_of:%s" % g.get("keep"))
    for c in chains:
        kept = L.find_rec(recs, c.get("keep")) or {}
        base = (entries.get(kept.get("rel")) or {}).get("class_path") or "_versions"
        for a in c.get("archive") or []:
            rec = L.find_rec(recs, a)
            if rec and rec["rel"] not in archived:
                archived[rec["rel"]] = ("%s/_versions/%s" % (str(base).strip("/"), c.get("chain_id") or "V1"),
                                        "version_of:%s" % c.get("keep"))
    jobs, used = [], set()
    for rec in recs:
        rel = rec["rel"]
        if rel in skips:
            continue
        ent = entries.get(rel) or rec["auto"]
        if rel in archived:
            sub, reason = archived[rel]
            dest_rel = "%s/%s" % (sub.strip("/"), L.sanitize(rec["name"]))
            if rel in renames:
                renames[rel] = {"from": rel, "to": os.path.basename(dest_rel), "template": "keep_original",
                                "degradation": "archived copy keeps its original file name",
                                "fields_used": [], "source": renames[rel].get("source", "auto")}
        else:
            name = (renames.get(rel) or {}).get("to") or rec["name"]
            dest_rel = "%s/%s" % (str(ent.get("class_path") or "other").strip("/"), L.sanitize(name))
            reason = ent.get("basis") or "class_path assignment"
        if dest_rel.lower() in used:
            d, n = os.path.split(dest_rel)
            siblings = {u.split("/")[-1].lower() for u in used if u.rsplit("/", 1)[0] == d.lower()}
            dest_rel = "%s/%s" % (d, L.unique_dest(siblings, n))
        used.add(dest_rel.lower())
        jobs.append({"rel": rel, "src": rec["abs"], "dest_rel": dest_rel, "sha256": rec["sha256"],
                     "reason": reason, "class_path": ent.get("class_path")})
    return jobs

def execute_jobs(jobs, target, rollback, errs):
    ops, target = [], str(target)
    for j in jobs:
        dest = os.path.join(target, j["dest_rel"].replace("/", os.sep))
        try:
            d = os.path.dirname(dest)
            if not os.path.isdir(d):
                missing, cur = [], d
                while cur and not os.path.isdir(cur) and len(cur) > len(target):
                    missing.append(cur)
                    cur = os.path.dirname(cur)
                os.makedirs(d, exist_ok=True)
                for m in reversed(missing):
                    rel = os.path.relpath(m, target).replace(os.sep, "/")
                    ops.append({"seq": len(ops) + 1, "op": "mkdir", "from": None, "to": rel,
                                "sha256": None, "result": "ok", "reason": "class_path directory"})
                    rollback["dirs"].append(rel)
            if os.path.exists(dest):
                if j["sha256"] and T.sha256_file(dest) == j["sha256"]:
                    ops.append({"seq": len(ops) + 1, "op": "noop", "from": j["rel"], "to": j["dest_rel"],
                                "sha256": j["sha256"], "result": "already_present",
                                "reason": "idempotent: identical content already at the destination"})
                    continue
                dd = os.path.dirname(dest)
                dest = os.path.join(dd, L.unique_dest({x.lower() for x in os.listdir(dd)},
                                                      os.path.basename(dest)))
                j["dest_rel"] = os.path.relpath(dest, target).replace(os.sep, "/")
            actual = L.copy_verified(j["src"], dest)
            ok = (actual == j["sha256"]) if j["sha256"] else bool(actual)
            kind = "archive" if ("_archive/" in j["dest_rel"] or "_versions/" in j["dest_rel"]) else "copy"
            ops.append({"seq": len(ops) + 1, "op": kind, "from": j["rel"], "to": j["dest_rel"],
                        "sha256": actual, "expected_sha256": j["sha256"], "verified": ok,
                        "result": "ok" if ok else "hash_mismatch", "reason": j["reason"]})
            rollback["files"].append(j["dest_rel"])
            if not ok:
                errs.append({"stage": "copy", "path": j["rel"], "detail": "sha256 mismatch after copy"})
        except OSError as e:
            ops.append({"seq": len(ops) + 1, "op": "copy", "from": j["rel"], "to": j["dest_rel"],
                        "sha256": None, "result": "failed", "reason": str(e)[:160]})
            errs.append({"stage": "copy", "path": j["rel"], "detail": str(e)[:160]})
    return ops

def _init(inp, work, out, args):
    import main
    return main.run_init(inp, work, out, args, quiet=True)

def pick_target(rules, work, args, degr, errs):
    cand = getattr(args, "target", None) or rules.get("target_root")
    default = work / "library"
    if cand:
        p = Path(cand)
        try:
            if str(p.resolve()).startswith("/input"):
                degr.append("target_root %s points into /input (read-only evidence); using %s instead"
                            % (cand, default))
                return default
            p.mkdir(parents=True, exist_ok=True)
            return p.resolve()
        except OSError as e:
            degr.append("target_root %s not writable (%s); using %s" % (cand, str(e)[:80], default))
            errs.append({"stage": "target", "detail": str(e)[:120]})
    return default

def cmd_build(args):
    inp, work, out = C.paths(args)
    errs, degr, unc = [], [], []
    idx, ierr = C.load_index(work)
    if not idx:
        idx = _init(inp, work, out, args)
        degr.append("index.json rebuilt inside build (%s)" % (ierr or "missing"))
    recs = idx.get("recs") or []
    rules = idx.get("rules") or {}
    keys = idx.get("contract_keys") or []
    draft, dname, derr = load_draft(work)
    if draft is None:
        degr.append("work draft not found (%s): every file handled by the deterministic rule table; "
                    "classification, tags and version relations are not Agent-verified" % (derr or "missing"))
    elif not (draft.get("classification") or []):
        degr.append("draft has no classification entries: rule-table fallback used")
    skips = build_skips(recs, draft, rules, degr, unc)
    entries = build_entries(recs, draft, degr, set(skips))
    renames = build_renames(recs, entries, draft, rules, degr)
    dupes, chains = build_groups(recs, draft, degr)
    target = pick_target(rules, work, args, degr, errs)
    jobs = plan_jobs(recs, entries, renames, dupes, chains, skips, degr)
    rollback = {"files": [], "dirs": []}
    ops = execute_jobs(jobs, target, rollback, errs)
    planned = 0
    for j in jobs:
        dest = os.path.join(str(target), j["dest_rel"].replace("/", os.sep))
        try:
            if not os.path.exists(dest) or (j["sha256"] and T.sha256_file(dest) != j["sha256"]):
                planned += 1
        except OSError:
            planned += 1
    dest_set = {j["dest_rel"] for j in jobs}
    orphans = []
    if os.path.isdir(str(target)):
        for dirpath, dirnames, filenames in os.walk(str(target)):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fn), str(target)).replace(os.sep, "/")
                if rel not in dest_set:
                    orphans.append(rel)
    if orphans:
        unc.append("%d file(s) in the target tree are not part of this run's plan (left by an earlier "
                   "classification); they are kept, never deleted - see result.orphans" % len(orphans))
    stats = L.dir_stats(target) if os.path.isdir(str(target)) else {"dirs": 0, "files": 0, "bytes": 0}
    tree = L.tree_lines(target, 300) if os.path.isdir(str(target)) else []
    answers = [a for a in (draft or {}).get("answers") or [] if isinstance(a, dict)]
    have = {str(a.get("question_id")) for a in answers}
    for q in rules.get("questions") or []:
        if q["question_id"] not in have:
            answers.append({"question_id": q["question_id"], "question": q["question"], "answer": None,
                            "basis": None, "note": "unanswered: no supporting evidence in the supplied material"})
            unc.append("question %s left unanswered; see answers[].note" % q["question_id"])
    cov = C.coverage(recs, entries, skips, ops, renames, dupes, chains)
    status = C.compute_status(recs, draft, entries, cov, ops)
    copied = len([o for o in ops if o.get("result") == "ok" and o.get("op") in ("copy", "archive")])
    already = len([o for o in ops if o.get("op") == "noop"])
    result = {"inventory": C.cap([C.inv_row(r) for r in recs]),
              "classification": C.cap(list(entries.values())),
              "renames": C.cap(list(renames.values())), "duplicates": C.cap(dupes),
              "versions": C.cap(chains), "operations": C.cap(ops),
              "skipped": C.cap(list(skips.values())), "answers": C.cap(answers),
              "coverage": cov, "tree": C.cap(tree, 200), "target_root": str(target),
              "orphans": C.cap(sorted(orphans), 100),
              "indexes": {"by_class": C.by_key(entries, "class_path"), "by_year": C.by_year(entries),
                          "by_sha256": C.by_sha(recs)},
              "stats": {"files_scanned": len(recs),
                        "classes": len({e.get("class_path") for e in entries.values()}),
                        "operations": len([o for o in ops if o.get("op") != "noop"]),
                        "noop": len([o for o in ops if o.get("op") == "noop"]),
                        "target_dirs": stats["dirs"], "target_files": stats["files"],
                        "target_bytes": stats["bytes"], "second_run_planned_ops": planned}}
    doc = C.envelope(idx.get("case_id"), status, result, keys, errs, degr, unc,
                     [{"id": r["doc_id"], "path": r["rel"], "sha256": r["sha256"],
                       "locator": "file:%s" % r["rel"], "text_quality": r["text_quality"]} for r in recs[:200]],
                     "classification, tags and version relations come from the Agent draft where present and "
                     "from the deterministic rule table otherwise; every metadata value keeps its locator and "
                     "missing fields stay null",
                     [{"action": "build", "detail": "%d copy ops, %d skipped, %d duplicate groups, %d version chains"
                       % (copied, len(skips), len(dupes), len(chains))}])
    write_artifacts(out, recs, entries, renames, dupes, chains, skips, ops, rollback, planned, target, idx)
    C.write_result(out, doc)
    print(json.dumps({"ok": True, "command": "build", "status": status, "target_root": str(target),
                      "files": len(recs), "copied": copied, "already_present": already, "skipped": len(skips),
                      "duplicate_groups": len(dupes), "version_chains": len(chains),
                      "coverage": {k: cov[k] for k in ("files_expected", "files_processed", "skipped",
                                                       "classified", "coverage_ratio")},
                      "second_run_planned_ops": planned, "result": str(out / "result.json")},
                     ensure_ascii=False, indent=1))
    return doc

def write_artifacts(out, recs, entries, renames, dupes, chains, skips, ops, rollback, planned, target, idx):
    prev_rb, _ = C.load_json(os.path.join(str(out), "rollback.json"))
    prev_idem, _ = C.load_json(os.path.join(str(out), "idempotency.json"))
    runs = int((prev_idem or {}).get("runs") or 0) + 1
    keep_files = list(dict.fromkeys(list((prev_rb or {}).get("remove_files") or []) + rollback["files"]))
    keep_dirs = list(dict.fromkeys(list((prev_rb or {}).get("remove_dirs") or [])
                                   + list(reversed(rollback["dirs"]))))
    cols = ["doc_id", "path", "size", "sha256", "mtime", "ext", "kind", "readable", "permission", "text_quality"]
    with open(out / "inventory.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in recs:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    with open(out / "classification.jsonl", "w", encoding="utf-8") as fh:
        for e in entries.values():
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    C.dump_json(out / "renames.json", list(renames.values()))
    C.dump_json(out / "dedupe_versions.json", {"duplicate_groups": dupes, "version_chains": chains})
    with open(out / "operations.log", "a", encoding="utf-8") as fh:
        for o in ops:
            fh.write(json.dumps(dict(o, run=runs), ensure_ascii=False) + "\n")
    C.dump_json(out / "skipped.json", list(skips.values()))
    C.dump_json(out / "index.json", {"case_id": idx.get("case_id"), "target_root": str(target),
                                     "by_class": C.by_key(entries, "class_path"), "by_year": C.by_year(entries),
                                     "by_type": C.by_key(entries, "doc_type"), "by_sha256": C.by_sha(recs)})
    C.dump_json(out / "rollback.json",
                {"target_root": str(target), "runs": runs, "remove_files": keep_files, "remove_dirs": keep_dirs,
                 "note": "sources under /input are never modified; reversing every copy recorded here restores "
                         "the state that existed before the first run"})
    lines = ["#!/bin/sh", "# generated by library-curator 1.0.0 - reverses every copy into the curated tree",
             "set -u", 'TARGET="${1:-%s}"' % str(target).replace('"', ""),
             'cd "$TARGET" 2>/dev/null || exit 0']
    for f in keep_files:
        lines.append("rm -f %s" % shlex.quote(f))
    for d in keep_dirs:
        lines.append("rmdir %s 2>/dev/null || true" % shlex.quote(d))
    lines.append("echo 'rollback done (sources under /input untouched)'")
    (out / "rollback.sh").write_text("\n".join(lines) + "\n", encoding="utf-8")
    C.dump_json(out / "idempotency.json",
                {"runs": runs, "second_run_planned_ops": planned, "idempotent": planned == 0,
                 "method": "each destination is compared by sha256 before copying; identical content is logged "
                           "as op=noop so a re-run plans 0 jobs",
                 "noop_ops_in_this_run": len([o for o in ops if o.get("op") == "noop"])})
    return True

def cmd_selfcheck(args):
    inp, work, out = C.paths(args)
    res, err = C.load_json(os.path.join(str(out), "result.json"))
    issues = []
    if not isinstance(res, dict):
        issues.append({"level": "FIX", "code": "result_missing", "detail": str(err)})
        res = {}
    idx = C.load_index(work)[0] or {}
    keys = idx.get("contract_keys") or []
    for k in keys:
        if k not in res:
            issues.append({"level": "FIX", "code": "contract_key_missing", "detail": k})
    if not res.get("case_id") and idx.get("case_id"):
        issues.append({"level": "WARN", "code": "case_id_null", "detail": "case.json did not provide an id"})
    r = res.get("result") or {}
    cov = r.get("coverage") or {}
    if cov:
        tot = cov.get("files_processed", 0) + cov.get("skipped", 0)
        if tot < cov.get("files_expected", 0):
            issues.append({"level": "FIX", "code": "coverage_shortfall",
                           "detail": "%d processed+skipped < %d expected from the scan"
                                     % (tot, cov.get("files_expected", 0))})
    cls = [e for e in (r.get("classification") or []) if isinstance(e, dict)]
    ev = len([e for e in cls if e.get("basis") and e.get("quote")])
    ops = [o for o in (r.get("operations") or []) if isinstance(o, dict) and o.get("op") in ("copy", "archive", "noop")]
    okops = [o for o in ops if C.materialised(o)]
    rb, _ = C.load_json(os.path.join(str(out), "rollback.json"))
    rbf = len((rb or {}).get("remove_files") or [])
    if rbf < len(okops):
        issues.append({"level": "WARN", "code": "rollback_incomplete",
                       "detail": "%d rollback entries for %d copy ops" % (rbf, len(okops))})
    tgt = r.get("target_root")
    stats = L.dir_stats(tgt) if tgt and os.path.isdir(str(tgt)) else {"files": 0}
    if tgt and stats["files"] < len(okops):
        issues.append({"level": "FIX", "code": "tree_incomplete",
                       "detail": "%d files on disk for %d recorded copies" % (stats["files"], len(okops))})
    idem, _ = C.load_json(os.path.join(str(out), "idempotency.json"))
    rep = {"status": res.get("status"), "contract_keys": len(keys), "evidence_quoted": ev,
           "evidence_ratio": round(ev / max(1, len(cls)), 3), "operations": len(ops),
           "rollback_entries": rbf, "target_files": stats["files"],
           "idempotent": (idem or {}).get("idempotent"), "issues": issues[:40],
           "verdict": "ok" if not [i for i in issues if i["level"] == "FIX"] else "needs_attention"}
    C.dump_json(work / "selfcheck.json", rep)
    print(json.dumps({"command": "selfcheck", **rep}, ensure_ascii=False, indent=1))
    return rep
