#!/usr/bin/env python3
"""library-curator driver: init | show | check | build | selfcheck.

init      index /input (case.json, task.md, materials) and write a legal partial result.json
show      print locator-tagged objects so the Agent can quote real text
check     mechanical validation of the Agent's work draft (/app/work/draft.json)
build     turn the draft into a real curated tree + all artifacts + final result.json
selfcheck re-verify what was delivered

Exit code is always 0; problems are reported in errors/degradations inside result.json.
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import contract as C

OK = True
LIBERR = ""
try:
    import library_ops as L
    import library_text as T
    import build_cmd as B
except Exception as _e:
    OK = False
    LIBERR = "%s: %s" % (type(_e).__name__, _e)


def run_init(inp, work, out, args, quiet=False):
    errs, degr = [], []
    case, cerr = C.load_case(inp)
    if cerr:
        errs.append({"stage": "case", "detail": cerr})
        degr.append("case.json missing or invalid -> output_contract empty, envelope still written")
    keys = C.contract_keys(case)
    rules = C.extract_rules(case)
    root, rdegr = C.material_root(case, inp)
    if rdegr:
        degr.append(rdegr)
    if not (Path(inp) / "task.md").is_file():
        degr.append("task.md not present in %s (task instruction read from case.json only)" % inp)
    recs, d2, e2 = L.build_records(root, args.max_files, args.max_depth) if OK else ([], [], [])
    degr.extend(d2)
    errs.extend(e2)
    hits = L.apply_companion_tables(recs) if recs else 0
    if hits:
        degr.append("%d document(s) enriched from companion metadata tables" % hits)
    for r in recs:
        if r["text_quality"] in ("encrypted", "no_text_layer", "corrupt", "unreadable_encoding"):
            degr.append("%s: text layer %s -> classified from file name/metadata only"
                        % (r["rel"], r["text_quality"]))
    idx = {"case_id": case.get("case_id") or case.get("id"), "contract_keys": keys, "rules": rules,
           "material_root": str(root), "recs": recs,
           "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "limits": {"max_files": args.max_files, "max_depth": args.max_depth},
           "task_instruction": str(case.get("task_instruction") or case.get("instruction") or "")[:4000]}
    C.save_index(work, idx)
    skel = {"_instructions": [
        "Copy to draft.json, then replace the empty/auto fields with your own judgement.",
        "classification[].basis must be a locator printed by `show`; quote must be verbatim from it.",
        "Never invent authors/year/journal/doi: leave null and explain in notes.",
        "Files that cannot be used go to skipped[] with a reason code from references/rules-and-templates.md.",
        "Answer every question listed by `show` in answers[] with basis+quote."],
        "case_id": idx["case_id"],
        "classification": [{"path": r["rel"], "doc_id": r["doc_id"], "class_path": r["auto"]["class_path"],
                            "doc_type": r["auto"]["doc_type"], "tags": r["auto"]["tags"],
                            "basis": r["auto"]["basis"], "quote": "", "metadata": r["auto"]["metadata"],
                            "confidence": "low", "notes": ""} for r in recs],
        "renames": [], "dedupe": [], "versions": [], "skipped": [], "answers": [], "notes": ""}
    C.dump_json(work / "draft.skeleton.json", skel)
    status = "partial" if recs else "failed"
    result = {"inventory": C.cap([C.inv_row(r) for r in recs]), "classification": [], "renames": [],
              "duplicates": [], "versions": [], "operations": [], "skipped": [], "answers": [],
              "coverage": {"files_expected": len(recs), "files_processed": 0, "skipped": 0,
                           "classified": 0, "metadata_fields_filled": 0, "metadata_fields_missing": 0},
              "tree": [], "target_root": None}
    doc = C.envelope(idx["case_id"], status, result, keys, errs, degr,
                     ["classification judgement not written yet; run show then write /app/work/draft.json"],
                     [{"id": r["doc_id"], "path": r["rel"], "locator": "file:%s" % r["rel"],
                       "sha256": r["sha256"], "text_quality": r["text_quality"]} for r in recs[:60]],
                     "inventory and hashes come from a bounded scan; classification, tags and version "
                     "relations need Agent judgement in the work draft",
                     [{"action": "init", "detail": "%d files indexed under %s" % (len(recs), root)}])
    C.write_result(out, doc)
    if not quiet:
        print(json.dumps({"ok": True, "command": "init", "case_id": idx["case_id"], "files": len(recs),
                          "material_root": str(root), "contract_keys": keys,
                          "naming_template": rules["naming_template"], "questions": len(rules["questions"]),
                          "declared_manifest": len(rules["declared"]),
                          "index": str(C.index_path(work)), "skeleton": str(work / "draft.skeleton.json"),
                          "result": str(out / "result.json"), "kernel": "ok" if OK else LIBERR},
                         ensure_ascii=False, indent=1))
    return idx


def cmd_show(args):
    inp, work, out = C.paths(args)
    idx = C.load_index(work)[0]
    if not idx:
        idx = run_init(inp, work, out, args, quiet=True)
    rules = idx.get("rules") or {}
    recs = idx.get("recs") or []
    print("CASE: %s" % idx.get("case_id"))
    print("CONTRACT KEYS: %s" % (", ".join(idx.get("contract_keys") or []) or "(none declared)"))
    print("MATERIAL ROOT: %s   FILES: %d" % (idx.get("material_root"), len(recs)))
    print("NAMING TEMPLATE: %s   (default {first_author}-{year}-{title_short})"
          % (rules.get("naming_template") or "default"))
    print("TARGET ROOT: %s" % (rules.get("target_root") or "/app/work/library (default)"))
    if idx.get("task_instruction"):
        print("TASK INSTRUCTION (case.json): %s" % idx["task_instruction"][:600])
    if rules.get("declared"):
        d = rules["declared"]
        print("DECLARED MANIFEST: %d entries, e.g. %s" % (len(d), ", ".join(d[:5])))
    if rules.get("questions"):
        print("\nQUESTIONS FROM case.json (answer each in draft.answers[] with basis+quote):")
        for q in rules["questions"][:20]:
            print("  [%s] %s" % (q["question_id"], q["question"][:300]))
    notes = [r for r in recs if r["kind"] in ("admin_note", "metadata_table")]
    if notes:
        print("\nADMIN NOTES / METADATA TABLES (cite as note:<path>#L<line>):")
        for n in notes[:6]:
            print("  [note] %s  (%d lines, quality=%s)" % (n["rel"], len(n.get("lines") or []), n["text_quality"]))
            for i, line in enumerate((n.get("lines") or [])[:args.note_lines]):
                if line.strip():
                    print("    note:%s#L%d  %s" % (n["rel"], i + 1, line.strip()[:220]))
    lim = max(1, args.show_limit)
    print("\nOBJECTS (first %d of %d; these locators are safe to quote):" % (min(lim, len(recs)), len(recs)))
    for r in recs[:lim]:
        meta = r.get("meta") or {}
        print("\n[%s] file:%s | text:%s#p1" % (r["doc_id"], r["rel"], r["rel"]))
        print("     %d bytes | sha256 %s | perm %s | readable=%s | text=%s"
              % (r["size"], (r["sha256"] or "")[:16] + "...", r["permission"], r["readable"], r["text_quality"]))
        print("     kind=%s  doc_type=%s (%s)" % (r["kind"], r.get("doc_type"), r.get("doc_type_rule")))
        bits = ["%s=%r (%s,%s)" % (f, str(meta[f]["value"])[:90], meta[f].get("locator"), meta[f].get("confidence"))
                for f in ("title", "authors", "year", "journal", "doi", "arxiv_id")
                if f in meta and meta[f].get("value")]
        print("     meta: " + (" | ".join(bits) if bits else "(no sourced metadata)"))
        if "title_name_only" in meta:
            print("     note: title only from file name -> %r (unverified)" % str(meta["title_name_only"]["value"])[:90])
        missing = [f for f in ("title", "authors", "year", "journal", "doi") if not (meta.get(f) or {}).get("value")]
        if missing:
            print("     meta missing: %s (keep null, do not invent)" % ",".join(missing))
        print("     auto: class_path=%s tags=%s" % (r["auto"]["class_path"], r["auto"]["tags"]))
        if r.get("pages"):
            print("     head: %r" % r["pages"][0][:args.head])
        else:
            print("     head: (no text layer: %s)" % r["text_quality"])
    if len(recs) > lim:
        print("\nREMAINING (one line each):")
        for r in recs[lim:lim + 60]:
            print("  [%s] %s | %s | %s | auto=%s" % (r["doc_id"], r["rel"], (r["sha256"] or "")[:8],
                                                     r.get("doc_type"), r["auto"]["class_path"]))
        if len(recs) > lim + 60:
            print("  ... %d more files (full list in /app/work/index.json)" % (len(recs) - lim - 60))
    print("\nNEXT: write %s then run `check`, then `build`." % (work / "draft.json"))
    print("The script does not read for you: classification, tags, version relations and answers must "
          "come from the material above.")
    return 0


def resolve_locator(recs, loc, rec=None):
    if not loc or ":" not in str(loc):
        return None, ""
    kind, _, rest = str(loc).partition(":")
    path, _, frag = rest.partition("#")
    target = L.find_rec(recs, path) or rec
    if not target:
        return None, ""
    if kind == "file":
        return True, " ".join([target["rel"], target["name"]])
    if kind in ("text", "note"):
        if frag.startswith("L"):
            try:
                i = int(re.sub(r"\D", "", frag) or "1") - 1
            except ValueError:
                return None, ""
            lines = target.get("lines") or []
            return (True, lines[i]) if 0 <= i < len(lines) else (None, "")
        pages = target.get("pages") or []
        if not pages:
            return None, ""
        m = re.search(r"p(\d+)", frag)
        n = int(m.group(1)) - 1 if m else 0
        return True, pages[min(max(n, 0), len(pages) - 1)]
    if kind == "meta":
        val = (target.get("meta") or {}).get(frag.strip())
        return (True, str(val.get("value"))) if val else (None, "")
    return None, ""


def tag_present(tag, text):
    """A tag counts as evidenced by a literal hit, a >=5-char stem hit, or a lexicon surface form."""
    t = str(tag).lower().strip()
    if not t:
        return True
    if T.hit_level(t, text) != "none":
        return True
    hay = (text or "").lower()
    for k in range(min(len(t), 9), 4, -1):
        if t[:k] in hay:
            return True
    for form in L.TOPIC_LEXICON.get(t, []) or []:
        if form.lower().strip("\\b") in hay:
            return True
    return False


def evidence_text(rec, qt):
    return (qt or "") + "\n" + "\n".join(rec.get("pages") or [])


def cmd_check(args):
    inp, work, out = C.paths(args)
    idx = C.load_index(work)[0]
    if not idx:
        idx = run_init(inp, work, out, args, quiet=True)
    recs = idx.get("recs") or []
    draft, dname, derr = B.load_draft(work)
    issues = []

    def add(level, code, path, detail):
        issues.append({"level": level, "code": code, "path": path, "detail": detail})

    if draft is None:
        add("FIX", "draft_missing", None, "no readable draft: %s" % derr)
        return finish_check(work, issues, 0)
    for key in ("classification", "renames", "dedupe", "versions", "skipped", "answers"):
        v = draft.get(key)
        if v is not None and not isinstance(v, list):
            add("FIX", "schema_type", key, "%s must be a list" % key)
    cls = [e for e in draft.get("classification") or [] if isinstance(e, dict)]
    covered = set()
    for e in cls:
        rec = L.find_rec(recs, e.get("path"))
        if not rec:
            add("FIX", "unknown_path", str(e.get("path")), "path is not in the index; use a locator from show")
            continue
        covered.add(rec["rel"])
        cp = str(e.get("class_path") or "").strip()
        if not cp:
            add("FIX", "class_path_missing", rec["rel"], "every entry needs a class_path")
        elif re.search(r"\s", cp):
            add("WARN", "class_path_shape", rec["rel"], "use <doc_type>/<year>/<topic> without spaces: %r" % cp)
        if not (e.get("tags") or []):
            add("WARN", "tags_empty", rec["rel"], "no tag assigned; tags drive retrieval")
        basis = str(e.get("basis") or "")
        qt = ""
        if not basis:
            add("FIX", "basis_missing", rec["rel"], "basis locator required (file:/text:/note:/meta:)")
        else:
            ok, qt = resolve_locator(recs, basis, rec)
            if not ok:
                add("FIX", "locator_unresolved", rec["rel"], "locator not resolvable: %s" % basis)
            else:
                quote = str(e.get("quote") or "")
                if not quote:
                    add("WARN", "quote_missing", rec["rel"], "no verbatim quote for the assignment basis")
                else:
                    lvl = T.hit_level(quote, qt)
                    if lvl == "none":
                        add("FIX", "quote_not_found", rec["rel"], "quote not found at %s: %r" % (basis, quote[:90]))
                    elif lvl == "fuzzy":
                        add("WARN", "quote_fuzzy", rec["rel"], "quote only fuzzy-matches the locator text")
                for tag in (e.get("tags") or [])[:8]:
                    if not tag_present(tag, qt):
                        add("WARN", "tag_unverified", rec["rel"],
                            "tag %r has no surface form at %s" % (str(tag), basis))
        meta = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        doi = meta.get("doi")
        if doi:
            if not re.match(r"^10\.\d{4,9}/", str(doi)):
                add("FIX", "doi_malformed", rec["rel"], "doi does not parse: %r" % doi)
            elif T.hit_level(str(doi), evidence_text(rec, qt)) == "none":
                add("FIX", "doi_not_in_evidence", rec["rel"], "doi %r absent from %s (possible fabrication)"
                    % (doi, basis))
        year = meta.get("year")
        if year is not None and str(year) != "":
            if not re.search(r"(19|20)\d{2}", str(year)):
                add("WARN", "year_shape", rec["rel"], "year %r is not a 4-digit year" % year)
            elif T.hit_level(str(year), evidence_text(rec, qt)) == "none":
                add("WARN", "year_not_in_evidence", rec["rel"], "year %r absent from the quoted evidence" % year)
    skipped_paths = {str(s.get("path")) for s in (draft.get("skipped") or []) if isinstance(s, dict)}
    missing = [r["rel"] for r in recs if r["rel"] not in covered and r["rel"] not in skipped_paths]
    if missing:
        add("FIX", "coverage_gap", None, "%d file(s) neither classified nor skipped: %s"
            % (len(missing), ", ".join(missing[:8])))
    seen = {}
    for e in draft.get("renames") or []:
        if not isinstance(e, dict):
            continue
        to = str(e.get("to") or "")
        if not to:
            add("FIX", "rename_empty", str(e.get("from")), "rename target empty")
            continue
        if re.search(r'[\\/:*?"<>|]', to):
            add("FIX", "rename_illegal_char", to, "contains a reserved file-name character")
        if len(to) > 180:
            add("WARN", "rename_too_long", to, "%d chars; truncate the title segment" % len(to))
        if not os.path.splitext(to)[1]:
            add("WARN", "rename_no_ext", to, "extension dropped")
        if to.lower() in seen:
            add("WARN", "rename_collision", to, "same target name as %s" % seen[to.lower()])
        seen[to.lower()] = str(e.get("from"))
        if e.get("template") and not e.get("degradation") and e.get("to"):
            rec = L.find_rec(recs, e.get("from"))
            if rec and not all((rec.get("meta") or {}).get(f) for f in ("title", "year")):
                add("WARN", "degradation_undocumented", str(e.get("from")),
                    "template used with missing metadata but no degradation record")
    by_sha = {r["sha256"] for r in recs if r.get("sha256")}
    for g in draft.get("dedupe") or []:
        if not isinstance(g, dict):
            continue
        sha = g.get("sha256")
        if sha and sha not in by_sha:
            add("FIX", "dedupe_hash_unknown", str(g.get("keep")), "sha256 not present in the index")
        for p in (g.get("archive") or []):
            rec = L.find_rec(recs, p)
            if not rec:
                add("FIX", "dedupe_member_unknown", str(p), "archived member not in the index")
            elif sha and rec["sha256"] != sha:
                add("FIX", "dedupe_hash_mismatch", rec["rel"], "member hash differs from the group hash")
    for c in draft.get("versions") or []:
        if not isinstance(c, dict):
            continue
        if c.get("relationship") not in L.RELATIONSHIPS:
            add("FIX", "relationship_enum", str(c.get("chain_id")),
                "relationship %r not in %s" % (c.get("relationship"), list(L.RELATIONSHIPS)))
        if len(c.get("members") or []) < 2:
            add("FIX", "chain_too_small", str(c.get("chain_id")), "a version chain needs >= 2 members")
        ev = str(c.get("evidence") or "")
        if c.get("relationship") in ("preprint", "accepted", "published", "supplement", "revision") and not ev:
            add("FIX", "chain_evidence_missing", str(c.get("chain_id")),
                "relationship claimed without an evidence locator")
        if ev.startswith("note:"):
            ok, qt = resolve_locator(recs, ev)
            if not ok:
                add("FIX", "chain_locator_unresolved", ev, "evidence locator not found")
            elif c.get("quote") and T.hit_level(str(c.get("quote")), qt) == "none":
                add("FIX", "chain_quote_not_found", ev, "quote absent from the cited note line")
    answered = {str(a.get("question_id")) for a in (draft.get("answers") or []) if isinstance(a, dict)}
    for q in ((idx.get("rules") or {}).get("questions") or []):
        if q["question_id"] not in answered:
            add("FIX", "question_unanswered", q["question_id"], q["question"][:120])
    for s in draft.get("skipped") or []:
        if isinstance(s, dict) and str(s.get("reason") or "") not in L.SKIP_CODES:
            add("WARN", "skip_reason_unknown", str(s.get("path")), "reason %r not in the reason table"
                % str(s.get("reason")))
    return finish_check(work, issues, len(recs))


def finish_check(work, issues, n_files):
    fix = [i for i in issues if i["level"] == "FIX"]
    warn = [i for i in issues if i["level"] == "WARN"]
    rep = {"files": n_files, "issues": len(issues), "FIX": len(fix), "WARN": len(warn),
           "verdict": "ready_for_build" if not fix else "fix_before_build", "items": issues[:120]}
    C.dump_json(work / "check_report.json", rep)
    print("check: %d file(s) indexed, FIX=%d WARN=%d -> %s" % (n_files, len(fix), len(warn), rep["verdict"]))
    for i in issues[:40]:
        print("  [%s] %-22s %s :: %s" % (i["level"], i["code"], i["path"], i["detail"]))
    if len(issues) > 40:
        print("  ... %d more in %s" % (len(issues) - 40, work / "check_report.json"))
    print("report: %s" % (work / "check_report.json"))
    return rep


def fallback(args, err):
    """Last resort: a legal partial result.json, so the case never ends as an empty directory."""
    try:
        inp, work, out = C.paths(args)
        case = {}
        try:
            case, _ = C.load_case(inp)
        except Exception:
            case = {}
        keys = C.contract_keys(case) if isinstance(case, dict) else []
        errs = [{"stage": "fatal", "detail": "%s: %s" % (type(err).__name__, str(err)[:300]),
                 "trace": traceback.format_exc()[-900:]}]
        result = {"inventory": [], "classification": [], "renames": [], "duplicates": [], "versions": [],
                  "operations": [], "skipped": [], "answers": [],
                  "coverage": {"files_expected": 0, "files_processed": 0, "skipped": 0},
                  "note": "the driver failed before producing artifacts; no result is claimed"}
        prev, _ = C.load_json(os.path.join(str(out), "result.json"))
        if isinstance(prev, dict) and isinstance(prev.get("result"), dict):
            prev.setdefault("errors", []).extend(errs)
            prev.setdefault("degradations", []).append(
                "this command aborted before writing new artifacts; the previous result.json is kept intact")
            C.write_result(out, prev)
            print("fatal handled: previous result.json kept, error appended (%s)" % errs[0]["detail"][:120])
            return 0
        doc = C.envelope(case.get("case_id"), "partial", result, keys, errs,
                         ["internal error; deliverable is an honest empty skeleton"],
                         ["no analysis was produced in this run"], [], "fatal fallback path",
                         [{"action": "fallback"}])
        C.write_result(out, doc)
        print("fatal handled: legal partial result.json written to %s" % (out / "result.json"))
    except Exception as e:
        print("fatal and fallback failed: %s" % e)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="library-curator: classify, rename, de-duplicate and version-repair a research document "
                    "library into a reversible curated tree with a contract-compliant result.json.",
        epilog="Sequence: init -> show -> (write /app/work/draft.json) -> check -> build -> selfcheck. "
               "Exit code is always 0.")
    ap.add_argument("command", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", help="input dir (/input, /app/input, ./input)")
    ap.add_argument("--work", help="work dir (/app/work, ./work)")
    ap.add_argument("--output", help="output dir (/app/output, ./output)")
    ap.add_argument("--draft", help="accepted for compatibility; the draft is <work>/draft.json")
    ap.add_argument("--target", help="curated tree root (default <work>/library)")
    ap.add_argument("--max-files", type=int, default=4000, dest="max_files")
    ap.add_argument("--max-depth", type=int, default=8, dest="max_depth")
    ap.add_argument("--show-limit", type=int, default=24, dest="show_limit")
    ap.add_argument("--note-lines", type=int, default=14, dest="note_lines")
    ap.add_argument("--head", type=int, default=220, help="characters of page-1 text printed per object")
    args = ap.parse_args(argv)
    try:
        if not OK:
            return fallback(args, RuntimeError("kernel import failed: " + LIBERR))
        inp, work, out = C.paths(args)
        if args.command == "init":
            run_init(inp, work, out, args)
        elif args.command == "show":
            cmd_show(args)
        elif args.command == "check":
            cmd_check(args)
        elif args.command == "build":
            B.cmd_build(args)
        else:
            B.cmd_selfcheck(args)
    except Exception as e:
        return fallback(args, e)

    try:
        import finalize
        finalize.run(out)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print("soft failure: %s" % exc)
    sys.exit(0)
