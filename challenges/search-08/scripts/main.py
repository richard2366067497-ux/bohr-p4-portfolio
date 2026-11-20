#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search-08 systematic-screening-ledger -- five-command, agent-first screening pipeline.

init      index records / criteria versions / reviewer labels / query strings, pre-cluster
          duplicates, write a legal partial result.json first.
show      print records with locators so the agent can quote them verbatim.
check     mechanically validate the agent work draft (/app/work/draft.json).
build     render flow ledger / decision cards / arbitration docket / audit closure + result.json.
selfcheck re-verify emitted artefacts.

Standard library only, no network, no CWD dependency, exit code always 0.
"""
import argparse, difflib, json, re, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ingest as G  # noqa: E402
import screen as S  # noqa: E402

VERSION = G.VERSION
T0 = time.time()


def now():
    return round(time.time() - T0, 3)


def build_index(inp, skip=()):
    inp = Path(inp)
    skip = tuple(str(Path(s).resolve()) for s in skip if s)
    info = {"errors": [], "degradations": [], "files": [], "case": {}, "task": "",
            "records": [], "labels": [], "inline": [], "crit_items": [], "query_files": []}
    info["task"] = G.read_text(inp / "task.md")
    for p in G.walk(inp):
        try:
            rp = str(p.resolve())
        except Exception:
            rp = str(p)
        if skip and any(rp.startswith(s + "/") or rp.startswith(s + "\\") for s in skip):
            continue
        rel = G.relof(p, inp)
        suf = p.suffix.lower()
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        if p.name.lower() in ("case.json", "challenge.json") or (suf == ".json" and "case" in p.name.lower()):
            d, e = G.load_json(p)
            if e:
                info["errors"].append({"where": rel, "error": "invalid JSON (%s)" % e})
            elif isinstance(d, dict):
                if d.get("output_contract") is not None or d.get("case_id"):
                    info["case"] = d
                if not info["task"] and isinstance(d.get("task_instruction"), str):
                    info["task"] = d["task_instruction"]
            info["files"].append({"path": rel, "role": "case", "bytes": size})
            continue
        role = None
        if suf in (".json", ".jsonl", ".ndjson", ".csv"):
            recs = G.parse_structured(p, rel)
            if recs:
                nlab = sum(1 for r in recs if r["reviewer"] and r["label"])
                nab = sum(1 for r in recs if len(r["abstract"]) > 40)
                if nlab and nlab * 2 >= len(recs) and nab * 2 < len(recs):
                    info["labels"] += recs
                    role = "labels"
                else:
                    info["records"] += recs
                    info["inline"] += [r for r in recs if r["reviewer"] and r["label"]]
                    role = "records"
            else:
                labs = G.parse_labels(p, rel)
                if labs:
                    info["labels"] += labs
                    role = "labels"
        elif suf in G.TEXT_EXT:
            t = G.read_text(p)
            low = (p.name + " " + t[:4000]).lower()
            if re.search(r"纳入|排除|inclusion|exclusion|eligib", low):
                items = G.parse_criteria_text(p, rel)
                if items:
                    info["crit_items"] += items
                    role = "criteria"
            if re.search(r"检索式|search (string|strategy|query)|pubmed|web of science|scopus|embase|数据库", low):
                info["query_files"].append(rel)
                role = role or "query"
            if role is None:
                recs = G.records_from_text(p, rel)
                if recs:
                    info["records"] += recs
                    role = "records_text"
        info["files"].append({"path": rel, "role": role or "other", "bytes": size})

    case = info["case"] if isinstance(info["case"], dict) else {}
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid = G.clean(case.get("case_id") or case.get("id") or (inp.name or "UNKNOWN-CASE"))

    recs = sorted(info["records"], key=lambda r: (r["source_file"], r["source_line"]))
    for i, r in enumerate(recs, 1):
        r["record_id"] = "R%03d" % i
        r["flags"] = G.flags_of(r)
        r["lang"] = G.lang_of(r["title"] + " " + r["abstract"])
        r["locator"] = r["record_id"]
    nid = {}
    for r in recs:
        if r["native_id"]:
            nid[r["native_id"].lower()] = nid.get(r["native_id"].lower(), 0) + 1
    for r in recs:
        if r["native_id"] and nid.get(r["native_id"].lower(), 0) > 1:
            r["flags"].append("dup_native_id")

    clusters = []
    for k, ids in enumerate(G.cluster_groups(recs), 1):
        dois = [recs[i]["doi"] for i in ids]
        strong = bool(dois) and all(dois) and len(set(dois)) == 1
        tsim = 1.0
        if len(ids) > 1:
            tsim = difflib.SequenceMatcher(None, G.norm_title(recs[ids[0]]["title"]),
                                           G.norm_title(recs[ids[1]]["title"])).ratio()
        clusters.append({"group_id": "D%02d" % k,
                         "members": [recs[i]["record_id"] for i in ids],
                         "basis": (["doi_match"] if strong else
                                   ["doi_" + ("partial" if any(dois) else "absent")]) +
                                  ["title_similar_%.2f" % tsim],
                         "recommend": "merge" if strong else "review",
                         "titles": [recs[i]["title"][:140] for i in ids],
                         "dois": dois})

    sets = {}
    for it in info["crit_items"] + G.parse_criteria_case(case):
        sets.setdefault(it["version"], []).append(it)
    dedup_sets = {}
    for ver, items in sets.items():
        seen, keep = set(), []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            keep.append(it)
        dedup_sets[ver] = keep
    versions = sorted(dedup_sets)
    active = versions[-1] if versions else ""

    pos = {(r["source_file"], r["source_line"]): r for r in recs}
    labels = []
    for L in info["labels"] + info["inline"]:
        r = pos.get((L["source_file"], L["source_line"]))
        rid = r["record_id"] if r else ""
        if not rid and L["native_id"]:
            for r2 in recs:
                if r2["native_id"] and r2["native_id"].lower() == L["native_id"].lower():
                    rid = r2["record_id"]
                    break
        if not rid and L["title"]:
            nt = G.norm_title(L["title"])
            for r2 in recs:
                if G.norm_title(r2["title"]) == nt:
                    rid = r2["record_id"]
                    break
        labels.append({"record_id": rid, "reviewer": L["reviewer"] or "input",
                       "label": L["label"], "label_norm": G.norm_label(L["label"]),
                       "reason_code": L["reason_code"],
                       "criteria_version": L["criteria_version"] or active,
                       "study_ref": L["study"], "source_file": L["source_file"],
                       "line": L["source_line"]})

    anomalies = []
    for r in recs:
        for f in r["flags"]:
            anomalies.append({"record_id": r["record_id"], "flag": f,
                              "gloss": (G.RC.get("anomaly_gloss") or {}).get(f, f)})
    nt_map = {}
    for r in recs:
        if r["title"]:
            nt_map.setdefault(G.norm_title(r["title"]), []).append(r)
    for nt, rs in nt_map.items():
        dois = {x["doi"] for x in rs if x["doi"]}
        if len(rs) > 1 and len(dois) > 1:
            anomalies.append({"record_id": rs[0]["record_id"], "flag": "same_title_diff_doi",
                              "records": [x["record_id"] for x in rs]})

    if not recs:
        info["degradations"].append({"kind": "records_missing",
                                     "detail": "no bibliographic records parsed from the input"})
    if not versions:
        info["degradations"].append({"kind": "criteria_missing",
                                     "detail": "no inclusion/exclusion criteria found; declare criteria in the draft"})
    if not labels:
        info["degradations"].append({"kind": "reviewer_labels_missing",
                                     "detail": "no second reviewer labels in the input; agreement cannot be computed"})

    return {
        "version": VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_id": cid,
        "task_instruction": G.norm(case.get("task_instruction"))[:2000] or G.norm(info["task"])[:2000],
        "output_contract": contract,
        "case_meta": {k: G.clean(v)[:300] for k, v in case.items()
                      if k not in ("output_contract", "content", "task_instruction")},
        "research_question": G.research_question(case, info["task"]),
        "files": info["files"],
        "records": recs,
        "clusters": clusters,
        "criteria": {"versions": versions, "active": active, "sets": dedup_sets},
        "criteria_fingerprint": (G.sha1("|".join("%s:%s:%s" % (i["id"], i["kind"], G.norm(i["text"]))
                                                  for i in dedup_sets.get(active, [])))
                                 if dedup_sets.get(active) else ""),
        "labels": labels,
        "query": G.extract_query(info["query_files"], inp),
        "anomalies": anomalies,
        "errors": info["errors"],
        "degradations": info["degradations"],
        "counts": {"records": len(recs), "clusters": len(clusters),
                   "records_in_clusters": sum(len(c["members"]) for c in clusters),
                   "criteria_versions": len(versions),
                   "criteria_items": len(dedup_sets.get(active, [])),
                   "input_labels": len([l for l in labels if l["label_norm"]]),
                   "anomalies": len(anomalies)},
    }


def ensure(a):
    out, work = Path(a.output), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    idx = build_index(a.input, skip=(out, work))
    G.write_json(work / "index.json", idx)
    return idx, out, work


def cmd_init(a):
    idx, out, work = ensure(a)
    S.write_partial(idx, out)
    c = idx["counts"]
    print("[init] case_id=%s contract_keys=%d" % (idx["case_id"], len(idx["output_contract"])))
    print("[init] records=%d clusters=%d criteria_versions=%s labels=%d anomalies=%d"
          % (c["records"], c["clusters"], ",".join(idx["criteria"]["versions"]) or "-",
             c["input_labels"], c["anomalies"]))
    for d in idx["degradations"]:
        print("[init] degradation: %s (%s)" % (d["kind"], d["detail"]))
    print("[init] partial result.json -> %s" % (out / "result.json"))
    print("[init] next: python3 scripts/main.py show  (then write %s)" % (work / "draft.json"))
    return 0


def cmd_show(a):
    idx, out, work = ensure(a)
    L = []
    ap = L.append
    ap("# screening index - case %s" % idx["case_id"])
    if idx.get("research_question"):
        ap("research_question: %s" % idx["research_question"])
    ap("output_contract keys (%d): %s" % (len(idx["output_contract"]),
                                          ", ".join(idx["output_contract"]) or "-"))
    ap("files: %s" % ", ".join("%s[%s]" % (f["path"], f["role"]) for f in idx["files"][:12]))
    ap("criteria versions: %s | suggested active=%s | fingerprint=%s"
       % (", ".join(idx["criteria"]["versions"]) or "-", idx["criteria"]["active"] or "-",
          idx["criteria_fingerprint"]))
    for v in idx["criteria"]["versions"]:
        ap("## criteria %s" % v)
        for it in idx["criteria"]["sets"][v]:
            ap("  %-4s %-8s %s" % (it["id"], it["kind"], it["text"][:160]))
    if idx["query"]:
        ap("## query strings seen in materials")
        for q in idx["query"]:
            ap("  - %s" % q["raw"][:220])
    if idx["clusters"]:
        ap("## duplicate candidates (decide merge / keep_separate in draft)")
        for c in idx["clusters"]:
            ap("  %s members=%s basis=%s recommend=%s"
               % (c["group_id"], ",".join(c["members"]), ",".join(c["basis"]), c["recommend"]))
            for t in c["titles"][:3]:
                ap("      - %s" % t)
    if idx["labels"]:
        ap("## reviewer labels already in materials")
        for l in idx["labels"][:40]:
            ap("  %s reviewer=%s label=%s reason=%s v=%s [%s]"
               % (l["record_id"] or "?", l["reviewer"], l["label"], l["reason_code"] or "-",
                  l["criteria_version"], l["source_file"]))
    ap("## records (quote verbatim; locator = R###@title|abstract)")
    for r in idx["records"]:
        ap("%s | yr=%s | doi=%s | flags=%s" % (r["record_id"], r["year"] or "-",
                                               r["doi"] or "-", ",".join(r["flags"]) or "-"))
        ap("  title: %s" % r["title"][:200])
        ap("  abstract: %s" % (r["abstract"][:260] if r["abstract"] else "<empty>"))
    if idx["anomalies"]:
        ap("## anomalies")
        for x in idx["anomalies"][:30]:
            ap("  %s %s" % (x["record_id"], x["flag"]))
    ap("## next step")
    ap("read the records above, decide each one, then write %s"
       " (schema: references/draft_schema.md); then run check and build." % (work / "draft.json"))
    txt = "\n".join(L)
    G.write_text(work / "show.txt", txt)
    print(txt)
    return 0


def cmd_check(a):
    idx, out, work = ensure(a)
    draft, path, err = S.load_draft(work, a.draft)
    rep = S.check_draft(idx, draft, path, err)
    G.write_json(work / "check_report.json", rep)
    for c in rep["checks"]:
        print("[%-4s] %-22s %s" % (c["status"].upper()[:4], c["id"], c["detail"]))
    print("[check] draft=%s ok=%s errors=%d warnings=%d -> %s"
          % (path or "-", rep["ok"], rep["errors"], rep["warnings"], work / "check_report.json"))
    if not rep["ok"]:
        print("[check] fix the FAIL lines above and re-run check; build still runs with fallbacks.")
    return 0


def cmd_build(a):
    idx, out, work = ensure(a)
    draft, path, err = S.load_draft(work, a.draft)
    res, summary = S.build(idx, draft, path, err, out, work)
    G.write_json(out / "result.json", res)
    print("[build] case_id=%s status=%s draft=%s" % (res["case_id"], res["status"], path or "none"))
    for k in ("identified", "duplicates_removed", "screened", "included", "excluded", "pending",
              "conflicts_total", "arbitrated", "conflicts_open", "coverage", "quote_hit_rate"):
        print("[build] %-18s %s" % (k, summary["counts"].get(k)))
    print("[build] identity: %s" % ", ".join("%s=%s" % (e["id"], e["status"]) for e in summary["equations"]))
    print("[build] artefacts: %s" % ", ".join("%s(%dB)" % (x["name"], x["bytes"]) for x in summary["artifacts"]))
    for d in res["degradations"]:
        print("[build] degradation: %s (%s)" % (d["kind"], d["detail"]))
    print("[build] result.json -> %s" % (out / "result.json"))
    return 0


def cmd_selfcheck(a):
    idx, out, work = ensure(a)
    rep = S.selfcheck(idx, out)
    for c in rep["checks"]:
        print("[%-4s] %-24s %s" % (c["status"].upper()[:4], c["id"], c["detail"]))
    print("[selfcheck] ok=%s checks=%d fail=%d" % (rep["ok"], len(rep["checks"]), rep["fail"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="systematic-screening-ledger: records + criteria + reviewer labels -> flow ledger, "
                    "decision cards, arbitration docket, audit closure, result.json (stdlib, exit 0).",
        epilog="init -> show -> (write draft.json) -> check -> build -> selfcheck; "
               "draft schema: references/draft_schema.md",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="init",
                    choices=["init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--draft", default=None)
    ap.add_argument("--version", action="version", version="systematic-screening-ledger %s" % VERSION)
    a = ap.parse_args(argv)
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check,
                "build": cmd_build, "selfcheck": cmd_selfcheck}[a.command](a)
    except Exception:
        err = traceback.format_exc(limit=6)
        try:
            out = Path(a.output)
            out.mkdir(parents=True, exist_ok=True)
            prev, _ = G.load_json(out / "result.json")
            prev = prev if isinstance(prev, dict) else {}
            prev.setdefault("case_id", "UNKNOWN-CASE")
            prev["status"] = "partial"
            prev.setdefault("errors", []).append({"where": "main", "error": err[-600:]})
            prev.setdefault("degradations", []).append(
                {"kind": "script_error", "detail": (err.splitlines() or [""])[-1][:200]})
            prev["runtime"] = {"version": VERSION, "elapsed_s": now()}
            G.write_json(out / "result.json", prev)
        except Exception:
            pass
        sys.stderr.write(err)
        return 0


if __name__ == "__main__":
    sys.exit(main())
