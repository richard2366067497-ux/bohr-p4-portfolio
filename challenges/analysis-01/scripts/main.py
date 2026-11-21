#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main: CLI and orchestration for field-contract-cleaner.

    python3 scripts/main.py all        one shot: full pipeline, every contract key, every deliverable
    python3 scripts/main.py init       index materials, write a legal partial result.json
    python3 scripts/main.py show       print materials/objects with locators for quoting
    python3 scripts/main.py check      validate the agent draft against the contract rules
    python3 scripts/main.py build      execute the contract -> deliverables + final result.json
    python3 scripts/main.py selfcheck  re-derive published numbers from files

Exit code is always 0. Failures are reported inside result.json.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cleanlib as L      # noqa: E402
import cleanrun as C      # noqa: E402
import report as RP       # noqa: E402

VERSION = "1.1.0"
T0 = time.time()
SKILL = {"name": "field-contract-cleaner", "version": VERSION}
LEDGER_TAIL = 40


def now():
    return round(time.time() - T0, 3)


def logline(work, cmd, msg):
    """Persist a run log under work/ (never audited, never a deliverable)."""
    try:
        p = Path(work) / "run.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write("%-9s t=%7.3fs %s\n" % (cmd, now(), str(msg)[:400]))
    except Exception:
        pass


def paths(a):
    return Path(a.input), Path(a.output), Path(a.work)


def load_draft(work, out, explicit=None):
    """-> (draft dict, source label, errors)."""
    cands = ([Path(explicit)] if explicit else []) + [work / "draft.json", work / "plan.json",
                                                     out / "draft.json"]
    for p in cands:
        if p.is_file():
            d, e = L.load_json_any(p)
            if isinstance(d, dict):
                return d, str(p), []
            return {}, str(p), [{"where": str(p), "error": "invalid JSON (%s)" % e}]
    return {}, "", []


def cmd_init(a):
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    info = L.discover(inp)
    case = info.get("case") if isinstance(info.get("case"), dict) else {}
    cid = str(case.get("case_id") or "UNKNOWN-CASE")
    contract = info.get("contract") or {}
    RP.seed_partial(out, cid, contract, "init", SKILL, now)
    profs = {}
    for T in info.get("tables") or []:
        profs[T["name"]] = {h: {k: v for k, v in p.items() if k != "tokens"}
                            for h, p in C.profile_table(T, info.get("dictionary")).items()}
    index = {"skill": SKILL, "case_id": cid, "case_path": info.get("case_path"),
             "contract_keys": list(contract.keys()), "task_md": info.get("task_md"),
             "files": info.get("files"), "n_tables": len(info.get("tables") or []),
             "tables": [{"name": T["name"], "rel": T["rel"], "encoding": T["encoding"],
                         "header": T["header"], "rows": len(T["rows"]), "sha": T["sha"],
                         "notes": T["notes"], "error": T["error"]}
                        for T in info.get("tables") or []],
             "dictionary_entries": len(info.get("dictionary") or {}),
             "dictionary_hits": info.get("dictionary_hits"),
             "workorder_items": [{"id": w["id"], "locator": w["locator"], "text": w["text"][:200],
                                 "actions": w.get("actions"), "forbidden": w.get("forbidden")}
                                for w in info.get("workorder") or []],
             "qc_items": [{"id": q["id"], "locator": q["locator"], "text": q["text"][:200]}
                          for q in info.get("qc") or []],
             "profiles": profs, "errors": info.get("errors"), "runtime": {"elapsed_s": now()}}
    L.write_json(work / "index.json", index)
    logline(work, "init", "case=%s tables=%d fields=%d dict=%d workorder=%d qc=%d"
            % (cid, len(info.get("tables") or []), len({h for T in info.get("tables") or []
                                                        for h in T["header"]}),
               len(info.get("dictionary") or {}), len(info.get("workorder") or []),
               len(info.get("qc") or [])))
    print("init: case_id=%s tables=%d fields=%d dict=%d workorder=%d qc=%d"
          % (cid, len(info.get("tables") or []),
             len({h for T in info.get("tables") or [] for h in T["header"]}),
             len(info.get("dictionary") or {}), len(info.get("workorder") or []),
             len(info.get("qc") or [])))
    for p in info.get("errors") or []:
        print("  ! error: %s -> %s" % (p.get("where"), p.get("error")))
    for T in info.get("tables") or []:
        print("  table %s: %d rows x %d cols, encoding=%s%s"
              % (T["rel"], len(T["rows"]), len(T["header"]), T["encoding"],
                 "" if not T["error"] else " ERROR=%s" % T["error"]))
    print("  wrote %s (partial result.json seeded)" % (work / "index.json"))
    return 0


# ---- show ----------------------------------------------------------------
def cmd_show(a):
    info = L.discover(paths(a)[0])
    rows = int(getattr(a, "rows", 0) or 12)
    sys.stdout.write(RP.render_show(info, rows))
    print("\nnext: read the above, then write %s (schema: SKILL.md §6), then run: check"
          % (paths(a)[2] / "draft.json"))
    return 0


# ---- check ---------------------------------------------------------------
def cmd_check(a):
    inp, out, work = paths(a)
    info = L.discover(inp)
    case = info.get("case") if isinstance(info.get("case"), dict) else {}
    cid = str(case.get("case_id") or "UNKNOWN-CASE")
    tables = info.get("tables") or []
    draft, dpath, derr = load_draft(work, out, a.plan)
    probs, warns, tests = list(derr), [], {}

    def t(name, ok, detail=""):
        tests[name] = {"ok": bool(ok), "detail": "" if ok else detail}
        if not ok:
            probs.append({"check": name, "detail": detail})

    if not tables:
        t("tables_present", False, "no table found under %s" % inp)
    hdr = {L.nkey(h): h for h in C.all_fields(tables)}
    if not draft:
        probs.append({"check": "draft_present", "detail":
                      "no %s; build will run the fallback path (contract synthesized)" % (work / "draft.json")})
        tests["draft_present"] = {"ok": False, "detail": "missing draft"}
        sdraft, sdeg = C.synth_contract(info, "check_without_draft")
        contracts, dedupe, deg = C.normalize_contract(sdraft, tables, info.get("dictionary") or {})
        deg = list(sdeg) + list(deg)
        for d in deg:
            warns.append(d)
    else:
        tests["draft_present"] = {"ok": True, "detail": dpath}
        contracts, dedupe, deg = C.normalize_contract(draft, tables, info.get("dictionary") or {})
        for d in deg:
            if d["kind"] in ("contract_field_missing", "contract_field_unknown"):
                probs.append({"check": d["kind"], "detail": d["detail"]})
            else:
                warns.append(d)
    t("contract_covers_all_fields",
      bool(hdr) and len({L.nkey(c["field"]) for c in contracts}) >= len(hdr),
      "covered %d of %d header columns" % (len({L.nkey(c["field"]) for c in contracts}), len(hdr)))
    bad_act = [c["field"] for c in contracts if c["planned_action"] not in L.ACTIONS]
    t("actions_legal", not bad_act, "illegal: %s" % bad_act[:6])
    forbid = [c["field"] for c in contracts
              if str(c["planned_action"]).lower() in L.FORBIDDEN]
    t("no_imputation", not forbid, "forbidden actions: %s" % forbid[:6])
    no_map = [c["field"] for c in contracts
              if c["planned_action"] == "convert_unit" and not c.get("unit_mapping")]
    t("unit_mapping_declared", not no_map, "convert_unit without mapping: %s" % no_map[:6])
    bad_dim = [c["field"] for c in contracts if c["planned_action"] == "convert_unit"
               and c.get("unit_mapping") and not c["unit_mapping"]["same_dim"]]
    t("unit_dimension_consistent", not bad_dim, "cross-dimension conversion: %s" % bad_dim[:6])
    no_basis = [c["field"] for c in contracts
                if c["planned_action"] not in ("keep", "mark_missing", "mark_invalid")
                and not c.get("basis") and c.get("workorder_ref") in ("", "none", "not-referenced", None)]
    t("actions_have_basis", not no_basis, "no basis/workorder_ref: %s" % no_basis[:6])
    wo = info.get("workorder") or []
    acts_present = {c["planned_action"] for c in contracts}
    if dedupe:
        acts_present.add("dedupe")
    if any(c.get("missing_tokens") for c in contracts):
        acts_present.add("mark_missing")
    tgt = " ".join(json.dumps(x, ensure_ascii=False) for x in contracts + dedupe).lower()
    answered, unanswered, why = [], [], []
    for w in wo:
        keys = [L.nkey(x) for x in (w.get("fields_matched") or []) if x]
        hit_field = any(k and k in tgt for k in keys)
        hit_act = any(a in acts_present for a in (w.get("actions") or []))
        ok = hit_field or hit_act
        (answered if ok else unanswered).append(w["id"])
        why.append("%s: fields=%s actions=%s -> field_hit=%s action_hit=%s"
                   % (w["id"], keys[:3], w.get("actions"), hit_field, hit_act))
    tests["workorder_answered"] = {"ok": not unanswered,
                                   "detail": "unanswered: %s" % unanswered[:8]}
    if unanswered:
        probs.append({"check": "workorder_answered",
                      "detail": "no contract/dedupe entry responds to: %s" % unanswered[:8]})
    rep_why = why
    forb = [w["id"] for w in wo if w.get("forbidden")]
    if forb:
        warns.append({"kind": "workorder_mentions_imputation",
                      "detail": "%s mention fill/impute wording; the red line still forbids valuing "
                                "missing cells - respond with mark_missing" % forb[:4]})
    if not wo:
        warns.append({"kind": "workorder_missing", "detail": "no workorder found"})
    if not info.get("dictionary"):
        warns.append({"kind": "dictionary_missing", "detail": "no data dictionary parsed"})
    mult = [(c["field"], c.get("unit_mapping") or {}) for c in contracts
            if c.get("unit_mapping") and c["unit_mapping"].get("factor") is not None]
    for f, m in mult:
        try:
            f1 = L.UNITS[L.unit_key(m["from"])][1]
            f2 = L.UNITS[L.unit_key(m["to"])][1]
            if f1 and f2 and abs(float(m["factor"]) - f1 / f2) > 1e-6 * max(1.0, f1 / f2):
                warns.append({"kind": "unit_factor_disagrees_with_registry",
                              "detail": "%s factor=%s registry=%s" % (f, m["factor"], f1 / f2)})
        except Exception:
            pass
    rep = {"case_id": cid, "draft": dpath or None, "checks": tests,
           "problems": probs, "warnings": warns, "workorder_trace": rep_why,
           "contracts": len(contracts), "dedupe_rules": len(dedupe),
           "fields": len(hdr), "runtime": {"elapsed_s": now()}}
    L.write_json(work / "check.json", rep)
    ok = all(v["ok"] for v in tests.values()) and not probs
    print("check: %s (%d checks, %d problems, %d warnings)"
          % ("PASS" if ok else "FAIL", len(tests), len(probs), len(warns)))
    for k, v in tests.items():
        print("  [%s] %s%s" % ("ok" if v["ok"] else "!!", k, "" if v["ok"] else " - " + v["detail"]))
    for p in probs:
        print("  problem: %s - %s" % (p.get("check"), p.get("detail")))
    for w in warns[:8]:
        print("  warn: %s - %s" % (w.get("kind"), str(w.get("detail"))[:160]))
    print("next: run build" if ok else "next: fix draft.json, re-run check (build still works, degraded)")
    return 0


# ---- build ---------------------------------------------------------------
def cmd_build(a):
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    E, D, P, U = [], [], [], []
    info = L.discover(inp)
    case = info.get("case") if isinstance(info.get("case"), dict) else {}
    cid = str(case.get("case_id") or "UNKNOWN-CASE")
    contract = info.get("contract") or {}
    RP.seed_partial(out, cid, contract, "build", SKILL, now)
    E += info.get("errors") or []
    tables = info.get("tables") or []
    draft, dpath, derr = load_draft(work, out, a.plan)
    E += derr
    if not draft:
        D.append({"kind": "draft_missing",
                  "detail": "no %s; contract synthesized by the fallback path" % (work / "draft.json")})
        draft, sdeg = C.synth_contract(info, "draft_missing")
        contract_source = "synthesized"
        for d in sdeg:
            D.append(d)
        contracts, dedupe, deg = C.normalize_contract(draft, tables, info.get("dictionary") or {})
        contracts = [dict(c, source="synthesized") if c.get("source") == "synthesized" else c
                     for c in contracts]
    else:
        contract_source = "draft:%s" % dpath
        contracts, dedupe, deg = C.normalize_contract(draft, tables, info.get("dictionary") or {})
    for d in deg:
        if d["kind"].startswith("contract_field"):
            P.append({"item": d.get("detail") or "?",
                      "reason": d["kind"] + ": contract entry missing or unknown field",
                      "action": "写进 draft.json 的 field_contract 后重跑 build"})
        else:
            D.append(d)
    for fld in ([c["field"] for c in contracts if c["planned_action"] == "convert_unit"
                 and not c.get("unit_mapping")]):
        D.append({"kind": "unit_mapping_absent", "detail": fld})
    if not tables:
        D.append({"kind": "no_table_found", "detail": "nothing tabular under %s" % inp})
        E.append({"where": str(inp), "error": "no table material found"})
    if not info.get("dictionary"):
        D.append({"kind": "dictionary_missing", "detail": "contract fields fall back to header profile"})
    if not info.get("workorder"):
        D.append({"kind": "workorder_missing", "detail": "only marking actions executed"})
    for u in (draft.get("uncertainties") or [])[:8]:
        U.append(str(u)[:240])
    for r in (draft.get("unresolved") or [])[:12]:
        if isinstance(r, dict):
            P.append({"item": r.get("field") or r.get("item") or "?",
                      "reason": r.get("why") or "unresolved",
                      "action": r.get("action") or "人工确认"})
    results, accounting, all_agg, cell_rows = [], [], [], []
    for n, T in enumerate(tables):
        tag = T["name"]
        if T.get("error") and not T.get("rows"):
            D.append({"kind": "empty_table" if T["error"] == "empty_file" else "unreadable_table",
                      "detail": "%s (%s)" % (tag, T["error"])})
            continue
        tr = C.execute_table(T, contracts, dedupe, tag)
        name = "cleaned_table.csv" if n == 0 else "cleaned__%s.csv" % tag
        sha = C.write_cleaned(out / name, tr)
        rec = C.recount_file(out / name)
        tr["out_name"], tr["sha_out"] = name, sha
        tr["recount"] = rec
        mis = C.compare_stats(tr["stats"], rec)
        if mis:
            D.append({"kind": "report_table_mismatch", "detail": "%s: %s" % (tag, mis[:4])})
        st = rec.get("status") or {}
        acc = {"table": tag, "raw_rows": len(T["rows"]), "kept": st.get("kept", 0),
               "marked": st.get("marked", 0), "quarantined": st.get("quarantined", 0),
               "blank_lines_skipped": next((int(x.split(":")[1]) for x in tr["notes"]
                                            if x.startswith("blank_lines_skipped")), 0)}
        acc["sum_rows"] = acc["kept"] + acc["marked"] + acc["quarantined"]
        acc["ok"] = acc["sum_rows"] == acc["raw_rows"] and rec.get("rows") == acc["raw_rows"]
        if not acc["ok"]:
            D.append({"kind": "row_accounting_mismatch",
                      "detail": "%s raw=%s kept+marked+quarantined=%s"
                                % (tag, acc["raw_rows"], acc["sum_rows"])})
        accounting.append(acc)
        agg = C.aggregate(tr)
        all_agg += agg
        cell_rows += tr["ledger"]
        results.append(tr)
        print("build: %s -> %s (%d rows, flags %d)" % (tag, name, len(tr["rows"]),
                                                      sum(len(r["flags"]) > 0 for r in tr["rows"])))
    if not tables:
        L.write_text(out / "cleaned_table.csv",
                     "record_id,__src_row,__row_status,__flags,note\n"
                     "R0000,0,kept,,no source table material was found so this run carries no "
                     "data row; the field contract and reconciliation still describe the input\n")
    if not (all_agg + cell_rows):
        all_agg = [{"kind": "aggregate", "action": "keep", "field": "__all__",
                    "rows_affected": 0, "table": "-", "contract_id": "-", "workorder_ref": "-",
                    "flag": "", "reversible": True, "value_changed": False,
                    "locator_base": "transform_ledger.jsonl#row1",
                    "detail": "no table material was found, so no transform row was executed; "
                              "unit conversion, marking and de-duplication all report zero here"}]
    acct = {"ok": all(x["ok"] for x in accounting), "tables": accounting}
    L.write_text(out / "transform_ledger.jsonl",
                 "".join(L.dumps_scrub(e) + "\n" for e in (all_agg + cell_rows)))
    issues = RP.issue_rows(results)
    RP.write_issues(out / "field_issues.csv", issues)
    src_now = []
    for T in tables:
        try:
            src_now.append({"rel": T["rel"], "sha": L.sha_bytes(Path(T["path"]).read_bytes())})
        except Exception:
            src_now.append({"rel": T["rel"], "sha": None})
    immut = {"ok": all(s["sha"] == T.get("sha") for s, T in zip(src_now, tables)),
             "files": [{"rel": s["rel"], "sha_before": T.get("sha"), "sha_after": s["sha"]}
                       for s, T in zip(src_now, tables)]}
    if not immut["ok"]:
        D.append({"kind": "source_mutated", "detail": "source hash changed during build"})
    cleaned_sha = results[0]["sha_out"] if results else \
        (L.sha_bytes((out / "cleaned_table.csv").read_bytes())
         if (out / "cleaned_table.csv").is_file() else "")
    rt_ok = not [d for d in D if d["kind"] == "report_table_mismatch"]
    counts = {"fields": len({L.nkey(c["field"]) for c in contracts}),
              "fields_in_header": len({L.nkey(h) for T in tables for h in T["header"]}),
              "rows_raw": sum(len(T["rows"]) for T in tables),
              "rows_kept": acct["tables"][0]["kept"] if accounting else 0,
              "rows_marked": acct["tables"][0]["marked"] if accounting else 0,
              "rows_quarantined": acct["tables"][0]["quarantined"] if accounting else 0,
              "issues": len(issues),
              "flags_total": sum(i["count"] for i in issues),
              "ledger_rows": len(all_agg) + len(cell_rows),
              "ledger_cell_rows": len(cell_rows),
              "workorder_items": len(info.get("workorder") or []),
              "unit_conversions": len([e for e in all_agg if e["action"] == "convert_unit"]),
              "dedupe_groups": len(dedupe)}
    L.write_json(out / "field_contract.json",
                 {"case_id": cid, "skill": SKILL, "source": contract_source,
                  "header": {T["name"]: T["header"] for T in tables},
                  "fields": contracts, "dedupe_plan": dedupe,
                  "dictionary_hits": info.get("dictionary_hits")})
    L.write_json(out / "reconciliation.json",
                 {"case_id": cid, "row_accounting": acct, "source_immutable": immut,
                  "report_table": {"ok": rt_ok}, "cleaned_sha": cleaned_sha,
                  "ledger_rows": len(all_agg) + len(cell_rows),
                  "tables": [{"table": r["tag"], "out": r["out_name"], "sha": r["sha_out"],
                              "encoding": r["encoding"]} for r in results]})
    status = "ok"
    if not contracts:
        status = "insufficient_evidence"
    elif cid == "UNKNOWN-CASE" or any("invalid JSON" in str(e.get("error"))
                                      for e in info.get("errors") or []):
        status = "input_error"
    elif not tables or D or P:
        status = "partial"
    files = [dict(f) for f in info.get("files") or []]
    ctx = {"case_id": cid, "status": status, "stage": "build",
           "contract_source": contract_source, "files": files,
           "dictionary_hits": info.get("dictionary_hits") or [], "contracts": contracts,
           "ledger_agg": all_agg, "accounting": acct, "issues": issues, "counts": counts,
           "pending": P, "cleaned_sha": cleaned_sha, "report_table_ok": rt_ok,
           "uncertainty": U}
    report_txt = RP.render_report(ctx)
    L.write_text(out / "data_quality_report.md", report_txt)
    ev = []
    for e in all_agg[:40]:
        ev.append({"claim": "%s %s on %s rows" % (e["action"], e["field"], e["rows_affected"]),
                   "locator": (e.get("row_refs") or [e.get("locator_base")])[0],
                   "source": e["table"], "contract_id": e["contract_id"],
                   "workorder_ref": e["workorder_ref"], "sample": e.get("input_sample", "")})
    payload = {"status": status, "contract": contract, "deliverable": "cleaned_table.csv",
               "primary_artifact_sha256": cleaned_sha,
               "cleaned_table": "cleaned_table.csv",
               "change_log": all_agg, "report_path": "data_quality_report.md",
               "field_contract_path": "field_contract.json",
               "reconciliation": {"row_accounting": acct, "source_immutable": immut,
                                  "report_table": {"ok": rt_ok}},
               "field_issues": issues, "evidence_map": ev, "counts": counts,
               "row_accounting": acct, "uncertainty": U, "pending_human": P,
               "errors": E, "degradations": D,
               "sources": [{"rel": f.get("rel"), "kind": f.get("kind"), "size": f.get("size"),
                            "sha256_16": (f.get("sha") or "")[:16]}
                           for f in (info.get("files") or [])],
               "uncertainties": U or ["本次输入没有可分析的数据表，清洗表为降级骨架；"
                                      "所有计数为 0，原因逐条写在 degradations 里"],
               "limits": ["不做统计检验与总体推断，只给可数描述量",
                          "缺失/未检出/越界只标记不改值，绝不填补",
                          "单位不在注册表内不换算，只标 UNIT_UNKNOWN",
                          "XLSX 只读首个工作表；日期按 ISO-8601 输出，不推断时区",
                          "重复记录隔离不删除，行数守恒 raw = kept + marked + quarantined"],
               "change_records": [{"action": e.get("action"), "field": e.get("field"),
                                   "table": e.get("table"), "rows_affected": e.get("rows_affected"),
                                   "reversible": e.get("reversible")} for e in all_agg[:60]],
               "summary": ("cleaned %d rows over %d fields; %d issue codes; %d unit conversions; "
                           "%d rows quarantined" % (counts["rows_raw"], counts["fields"],
                                                    len(issues), counts["unit_conversions"],
                                                    counts["rows_quarantined"]))}
    res = RP.write_result(out, cid, contract, payload, "build", SKILL, now, contracts=contracts)
    chk = RP.audit(out, inp)
    res["verification"] = chk
    L.write_json(out / "result.json", res)
    print("build: status=%s fields=%d issues=%d conversions=%d accounting=%s consistency=%s"
          % (status, counts["fields"], len(issues), counts["unit_conversions"],
             "OK" if acct["ok"] else "FAIL", "OK" if rt_ok else "FAIL"))
    for d in D[:10]:
        print("  degrade: %s - %s" % (d.get("kind"), str(d.get("detail"))[:150]))
    print("  deliverables: cleaned_table.csv, transform_ledger.jsonl, data_quality_report.md, "
          "field_contract.json, reconciliation.json, field_issues.csv, result.json")
    logline(work, "build", "status=%s fields=%d issues=%d conversions=%d accounting=%s "
                           "consistency=%s contract_keys=%d"
            % (status, counts["fields"], len(issues), counts["unit_conversions"],
               "OK" if acct["ok"] else "FAIL", "OK" if rt_ok else "FAIL", len(contract)))
    return 0


# ---- all -----------------------------------------------------------------
def cmd_all(a):
    """One shot: index, contract, deliverables and a final result.json in a single call."""
    inp, out, work = paths(a)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    logline(work, "all", "start input=%s output=%s work=%s" % (inp, out, work))
    cmd_init(a)
    cmd_build(a)
    logline(work, "all", "done -> %s" % (out / "result.json"))
    print("all: full pipeline complete (result.json carries every output_contract key)")
    print("  single-command entry: python3 scripts/main.py all --input /input "
          "--output /app/output --work /app/work")
    return 0


# ---- selfcheck -----------------------------------------------------------
def cmd_selfcheck(a):
    inp, out, work = paths(a)
    rep = RP.audit(out, inp)
    L.write_json(work / "selfcheck.json", rep)
    print("selfcheck: %s" % ("PASS" if rep["ok"] else "FAIL"))
    for k, v in rep["checks"].items():
        print("  [%s] %s%s" % ("ok" if v["ok"] else "!!", k,
                               "" if v["ok"] else " - " + str(v["detail"])[:160]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="field-contract-cleaner: data dictionary + QC rules + cleaning workorder -> "
                    "per-field contract -> cleaned table, transform ledger, quality report, "
                    "reconciliation, result.json (stdlib only, exit 0).",
        epilog="single command: python3 scripts/main.py all --input /input --output /app/output "
               "--work /app/work\nagent path: init -> show -> (write work/draft.json) -> check -> "
               "build -> selfcheck",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="all",
                    choices=["all", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", "--out", dest="output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--plan", default=None, help="explicit draft.json path")
    ap.add_argument("--rows", type=int, default=12, help="show: data rows printed per table")
    ap.add_argument("--version", action="version", version="field-contract-cleaner %s" % VERSION)
    a = ap.parse_args(argv)
    fn = {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
          "build": cmd_build, "selfcheck": cmd_selfcheck}[a.command]
    try:
        return fn(a)
    except Exception:
        err = traceback.format_exc(limit=8)
        try:
            out = Path(a.output)
            out.mkdir(parents=True, exist_ok=True)
            prev, _ = L.load_json_any(out / "result.json")
            prev = prev if isinstance(prev, dict) else {}
            prev.update({"case_id": prev.get("case_id", "UNKNOWN-CASE"), "status": "partial",
                         "errors": (prev.get("errors") or []) +
                                   [{"where": a.command, "error": err[-800:]}],
                         "skill": SKILL,
                         "runtime": {"version": VERSION, "elapsed_s": now()}})
            L.write_json(out / "result.json", prev)
        except Exception:
            pass
        sys.stderr.write(err)
        return 0


if __name__ == "__main__":
    sys.exit(main())
