#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanrun: execution layer for field-contract-cleaner.

profile -> contract (draft or synthesized) -> cell execution -> cleaned table +
transform ledger + field issues + quality report + reconciliation -> audit.

Rules enforced here: missing / invalid cells never receive a value, only a flag;
every value-changing transform is declared, reversible and recorded per cell; no
source row is ever dropped from the cleaned table.
"""
import csv
import json
from pathlib import Path

import cleanlib as L

RAIL = ("record_id", "__src_row", "__row_status", "__flags")
FLAG_ACTION = {"MISSING_BLANK": "mark_missing",
               "MISSING_CODE": "mark_missing",
               "BELOW_LOD": "mark_missing",
               "NON_NUMERIC": "mark_invalid",
               "OUT_OF_RANGE": "mark_invalid",
               "UNIT_CONVERTED": "convert_unit",
               "DATE_CONVERTED": "convert_date",
               "ENCODING_FIXED": "fix_encoding",
               "DUP_DROPPED": "dedupe",
               "NO_USABLE_VALUE": "quarantine",
               "UNIT_ABSENT": "mark_missing",
               "UNIT_UNKNOWN": "mark_missing",
               "ENCODING_SUSPECT": "mark_invalid"}
ACTION_FLAG = {"mark_missing": "MISSING_CODE", "mark_invalid": "OUT_OF_RANGE",
               "convert_unit": "UNIT_CONVERTED", "convert_date": "DATE_CONVERTED",
               "fix_encoding": "ENCODING_FIXED", "dedupe": "DUP_DROPPED",
               "quarantine": "NO_USABLE_VALUE", "keep": ""}
VALUE_CODES = {"UNIT_CONVERTED", "DATE_CONVERTED", "ENCODING_FIXED", "DUP_DROPPED",
               "NO_USABLE_VALUE"}
DEFAULT_CTR = {"field": "", "dtype": None, "planned_action": "keep", "unit": "",
               "valid_range": "", "unit_mapping": None, "contract_id": "FC-UNSET",
               "workorder_ref": "not-referenced", "basis": ""}
BUSY = ("numeric", "date")


def rid(tag, i):
    return "%s-R%04d" % (tag, i + 1)


def profile_table(T, dentries=None):
    """Per-column value profile; used by `show` and by contract synthesis."""
    out, rows = {}, T.get("rows") or []
    for j, h in enumerate(T.get("header") or []):
        e = (dentries or {}).get(L.nkey(h)) or {}
        rng = L.parse_range(e.get("range")) if e.get("range") else None
        p = {"field": h, "n": 0, "n_blank": 0, "n_code": 0, "n_lod": 0, "n_nonnum": 0,
             "n_num": 0, "n_date": 0, "n_range": 0, "min": None, "max": None, "tokens": {},
             "units": {}, "moji": 0, "samples": [], "dict_unit": e.get("unit", ""),
             "dict_range": e.get("range", "")}
        for i, r in enumerate(rows):
            c = r[j] if j < len(r) else ""
            p["n"] += 1
            ci = L.classify(c, {})
            tok = L.norm(c)[:20] or "<blank>"
            p["tokens"][tok] = p["tokens"].get(tok, 0) + 1
            code = ci["code"]
            if code == "MISSING_BLANK":
                p["n_blank"] += 1
            elif code == "BELOW_LOD":
                p["n_lod"] += 1
            elif code == "MISSING_CODE":
                p["n_code"] += 1
            elif code == "NON_NUMERIC":
                p["n_nonnum"] += 1
            else:
                if ci["num"] is not None:
                    p["n_num"] += 1
                    p["min"] = ci["num"] if p["min"] is None else min(p["min"], ci["num"])
                    p["max"] = ci["num"] if p["max"] is None else max(p["max"], ci["num"])
                    if not L.in_range(ci["num"], rng):
                        p["n_range"] += 1
                    if ci["unit"]:
                        p["units"][ci["unit"]] = p["units"].get(ci["unit"], 0) + 1
                if L.norm_date(c):
                    p["n_date"] += 1
            if L.moji_score(c):
                p["moji"] += 1
            if len(p["samples"]) < 3 and L.norm(c):
                p["samples"].append({"row": i + 2, "value": L.norm(c)[:40]})
        p["dtype"] = e.get("dtype") or L.infer_dtype(p)
        p["dominant_unit"] = max(p["units"].items(), key=lambda kv: kv[1])[0] if p["units"] else ""
        p["numeric_col"] = p["n_num"] >= max(1, int(0.4 * max(1, p["n"])))
        out[h] = p
    return out


def all_fields(tables):
    seen, out = set(), []
    for T in tables:
        for h in T.get("header") or []:
            k = L.nkey(h)
            if k and k not in seen:
                seen.add(k)
                out.append(h)
    return out


def norm_mapping(m):
    if not isinstance(m, dict):
        return None
    f, t = L.norm(m.get("from")), L.norm(m.get("to"))
    if not f or not t:
        return None
    try:
        sig = int(m.get("sig_digits")) if m.get("sig_digits") not in (None, "", 0) else None
    except Exception:
        sig = None
    kf, kt = L.unit_key(f), L.unit_key(t)
    known = kf in L.UNITS and kt in L.UNITS
    return {"from": f, "to": t, "factor": m.get("factor"), "sig_digits": sig,
            "same_dim": bool(known and L.UNITS[kf][0] == L.UNITS[kt][0])}


def normalize_contract(draft, tables, dentries):
    """draft.field_contract -> validated contracts + degradations."""
    deg = []
    hdrs = {L.nkey(h): h for h in all_fields(tables)}
    by = {}
    raw = draft.get("field_contract") if isinstance(draft, dict) else None
    for i, c in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(c, dict):
            continue
        k = L.nkey(c.get("field"))
        if k not in hdrs:
            dent = dentries.get(k) if isinstance(dentries, dict) else None
            if dent and c.get("source") in ("synthesized", "synthesized:dictionary_only"):
                # a field the data dictionary declares but no table header carries: the entry
                # is kept (projected from the dictionary) rather than dropped
                hdrs = dict(hdrs)
                hdrs[k] = c.get("field")
            else:
                deg.append({"kind": "contract_field_unknown",
                            "detail": L.norm(c.get("field")) or "FC-%d" % (i + 1)})
                continue
        act = (L.norm(c.get("planned_action")) or "keep").lower()
        if act in L.FORBIDDEN:
            deg.append({"kind": "forbidden_action_rejected", "detail": "%s:%s" % (hdrs[k], act)})
            act = "keep"
        if act not in L.ACTIONS:
            deg.append({"kind": "unknown_action", "detail": "%s:%s" % (hdrs[k], act)})
            act = "keep"
        ent = {"contract_id": L.norm(c.get("contract_id")) or "FC-%02d" % (len(by) + 1),
               "field": hdrs[k], "meaning": L.norm(c.get("meaning")),
               "dtype": (L.norm(c.get("dtype")) or "").lower() or None,
               "unit": L.norm(c.get("unit")), "valid_range": L.norm(c.get("valid_range")),
               "missing_tokens": [L.norm(x) for x in (c.get("missing_tokens") or []) if L.norm(x)],
               "invalid_rules": c.get("invalid_rules") or [],
               "workorder_ref": L.norm(c.get("workorder_ref")) or "not-referenced",
               "planned_action": act, "unit_mapping": norm_mapping(c.get("unit_mapping")),
               "basis": L.norm(c.get("basis")), "evidence": c.get("evidence") or [],
               "source": "draft"}
        if act == "convert_unit":
            mm = ent["unit_mapping"]
            if not mm:
                deg.append({"kind": "unit_mapping_absent", "detail": ent["field"]})
                ent["planned_action"] = "keep"
            elif not mm["same_dim"]:
                deg.append({"kind": "unit_dimension_mismatch",
                            "detail": "%s %s->%s" % (ent["field"], mm["from"], mm["to"])})
                ent["planned_action"], ent["unit_mapping"] = "keep", None
        if not ent["basis"] and ent["planned_action"] not in ("keep", "mark_missing", "mark_invalid"):
            deg.append({"kind": "action_without_basis", "detail": ent["field"]})
        by[k] = ent
    for k, h in hdrs.items():
        if k in by:
            continue
        e = dentries.get(k) or {}
        by[k] = {"contract_id": "FC-S%d" % (len(by) + 1), "field": h,
                 "meaning": e.get("meaning", ""), "dtype": e.get("dtype") or None,
                 "unit": e.get("unit", ""), "valid_range": e.get("range", ""),
                 "missing_tokens": e.get("missing") or [], "invalid_rules": [],
                 "workorder_ref": "not-referenced", "planned_action": "keep", "unit_mapping": None,
                 "basis": e.get("source") or "synthesized:field_missing_in_draft",
                 "evidence": [], "source": "synthesized"}
        deg.append({"kind": "contract_field_missing", "detail": h})
    order = {L.nkey(h): i for i, h in enumerate(all_fields(tables))}
    contracts = sorted(by.values(), key=lambda c: order.get(L.nkey(c["field"]), 999))
    dedupe = []
    dp = draft.get("dedupe_plan") if isinstance(draft, dict) else None
    for d in (dp if isinstance(dp, list) else []):
        if not isinstance(d, dict):
            continue
        kf = [L.norm(x) for x in (d.get("key_fields") or []) if L.norm(x)]
        ok = [hdrs[L.nkey(x)] for x in kf if L.nkey(x) in hdrs]
        if not ok:
            deg.append({"kind": "dedupe_key_absent", "detail": ",".join(kf) or "(empty)"})
            continue
        dedupe.append({"key_fields": ok, "keep": (L.norm(d.get("keep")) or "first").lower(),
                       "tiebreak": L.norm(d.get("tiebreak")), "basis": L.norm(d.get("basis"))})
    return contracts, dedupe, deg


def synth_contract(info, reason):
    """Fallback contract: flag + repair only; conversion only within one dimension."""
    deg, tables = [], info.get("tables") or []
    dent, wo, qc = info.get("dictionary") or {}, info.get("workorder") or [], info.get("qc") or []
    hdrs = {L.nkey(h): h for h in all_fields(tables)}
    profs = {}
    for T in tables:
        for h, p in profile_table(T, dent).items():
            profs.setdefault(h, p)
    fc, seen = [], set()
    for T in tables:
        for h in T.get("header") or []:
            k = L.nkey(h)
            if k in seen:
                continue
            seen.add(k)
            e, p = dent.get(k) or {}, profs.get(h) or {}
            act, mapping = "keep", None
            basis = e.get("source") or "synthesized:header_only"
            if p.get("moji", 0) > 0:
                act = "fix_encoding"
                basis = "%s; profile:mojibake_observed(%d)" % (basis, p["moji"])
            units = list((p.get("units") or {}).keys())
            tgt = L.norm(e.get("unit", ""))
            same_dim = (len(units) == 1 and bool(tgt)
                        and L.unit_key(units[0]) in L.UNITS and L.unit_key(tgt) in L.UNITS
                        and L.UNITS[L.unit_key(units[0])][0] == L.UNITS[L.unit_key(tgt)][0]
                        and L.unit_key(units[0]) != L.unit_key(tgt))
            if same_dim:
                act, mapping = "convert_unit", {"from": units[0], "to": tgt,
                                                "factor": None, "sig_digits": None}
                basis = "%s; inferred:dictionary_unit_vs_profile" % basis
                deg.append({"kind": "unit_mapping_inferred",
                            "detail": "%s %s->%s" % (h, units[0], tgt)})
            elif tgt and len(units) > 1:
                deg.append({"kind": "unit_mapping_absent",
                            "detail": "%s(mixed:%s)" % (h, ",".join(sorted(units)[:4]))})
            rng = L.norm(e.get("range", ""))
            if not rng:
                for q in qc:
                    if k in L.nkey(q.get("text", "")) and L.parse_range(q.get("text", "")):
                        rng = q.get("text")
                        break
            ref = "not-referenced"
            for w in wo:
                if k in {L.nkey(x) for x in (w.get("fields_matched") or [])}:
                    ref = w.get("id") or "not-referenced"
                    break
            fc.append({"contract_id": "FC-%02d" % (len(fc) + 1), "field": h,
                       "meaning": e.get("meaning", ""), "dtype": e.get("dtype") or p.get("dtype"),
                       "unit": tgt, "valid_range": rng, "missing_tokens": e.get("missing") or [],
                       "invalid_rules": [], "workorder_ref": ref, "planned_action": act,
                       "unit_mapping": mapping, "basis": basis, "evidence": [],
                       "source": "synthesized"})
    from_dict = 0
    for k, e in (dent or {}).items():
        if k in seen:
            continue
        seen.add(k)
        ref = "not-referenced"
        for w in wo:
            if k in {L.nkey(x) for x in (w.get("fields_matched") or [])}:
                ref = w.get("id") or "not-referenced"
                break
        fc.append({"contract_id": "FC-%02d" % (len(fc) + 1), "field": e.get("field") or k,
                   "meaning": e.get("meaning", ""), "dtype": e.get("dtype") or None,
                   "unit": L.norm(e.get("unit", "")), "valid_range": L.norm(e.get("range", "")),
                   "missing_tokens": e.get("missing") or [], "invalid_rules": [],
                   "workorder_ref": ref, "planned_action": "keep", "unit_mapping": None,
                   "basis": e.get("source") or "synthesized:dictionary_only",
                   "evidence": [], "source": "synthesized:dictionary_only"})
        from_dict += 1
    if from_dict:
        deg.append({"kind": "contract_from_dictionary_only",
                    "detail": "%d field(s) declared by the data dictionary but by no table header; "
                              "their contract is projected from the dictionary entry alone" % from_dict})
    dedupe = []
    for w in wo:
        if "dedupe" in (w.get("actions") or []):
            kf = [hdrs[L.nkey(x)] for x in (w.get("fields_matched") or []) if L.nkey(x) in hdrs]
            if kf:
                dedupe.append({"key_fields": kf[:3], "keep": "first",
                               "tiebreak": "earlier_src_row", "basis": w.get("locator", "")})
    return {"case_id": (info.get("case") or {}).get("case_id"), "field_contract": fc,
            "dedupe_plan": dedupe, "synth_reason": reason,
            "unresolved": [{"field": h, "why": "no draft: contract synthesized by fallback",
                            "action": "mark_only"} for h in all_fields(tables)][:12],
            "uncertainties": ["contract synthesized (%s); conversion only within one dimension"
                              % reason]}, deg


def cell_row(tag, c, rec, a, b, action, mapping):
    return {"kind": "cell", "table": tag, "field": c.get("field", ""),
            "contract_id": c.get("contract_id", ""), "workorder_ref": c.get("workorder_ref", "not-referenced"),
            "action": action, "record_id": rid(tag, rec.get("row", 0)),
            "row": rec.get("src"), "input": str(a)[:200], "output": str(b)[:200],
            "reversible": True, "mapping": mapping}


def fmt_flag(x):
    """(field, code[, note]) -> 'field:code' or 'field:code(note)'."""
    note = x[2] if len(x) > 2 and x[2] else ""
    return "%s:%s%s" % (x[0], x[1], ("(" + str(note) + ")") if note else "")


def key_norm(ctr, raw):
    ci = L.classify(raw, ctr or {})
    if ci["num"] is not None:
        mm = (ctr or {}).get("unit_mapping")
        if mm and ci["unit"] and L.unit_key(ci["unit"]) == L.unit_key(mm["from"]):
            cv, _, ok = L.unit_convert(ci["num"], mm["from"], mm["to"])
            if ok:
                return L.fmt_num(cv, mm.get("sig_digits"))
        return L.fmt_num(ci["num"])
    return L.nkey(raw)


def execute_table(T, contracts, dedupe, tag):
    hdr, rows = T.get("header") or [], T.get("rows") or []
    cmap = {L.nkey(c["field"]): c for c in contracts}
    ctrs = [cmap.get(L.nkey(h)) or dict(DEFAULT_CTR, field=h) for h in hdr]
    dom = {}
    for j, h in enumerate(hdr):
        u = {}
        for r in rows:
            cu = L.unit_of_cell(r[j] if j < len(r) else "")[0]
            if cu:
                u[cu] = u.get(cu, 0) + 1
        dom[h] = max(u.items(), key=lambda kv: kv[1])[0] if u else ""
    cells, ledger = [], []
    stats = {h: {} for h in hdr}
    for i, r in enumerate(rows):
        rec = {"row": i, "src": i + 2, "cells": [], "codes": [], "flags": []}
        for j, c in enumerate(ctrs):
            raw = r[j] if j < len(r) else ""
            ci = L.classify(raw, c)
            out, code, num = raw, ci["code"], ci["num"]
            obs = ci["unit"] or dom.get(c["field"], "")
            if L.moji_score(raw) and (code in ("NON_NUMERIC", "INVALID_TOKEN")
                                      or c.get("planned_action") == "fix_encoding"
                                      or c.get("dtype") in ("text", "categorical")):
                rep, ch = L.repair_mojibake(raw)
                if ch:
                    ci2 = L.classify(rep, c)
                    ledger.append(cell_row(tag, c, rec, raw, rep, "fix_encoding",
                                           {"encoding": "legacy_codepage->utf8"}))
                    out, code = rep, "ENCODING_FIXED"
                    if ci2["num"] is not None:
                        num = ci2["num"]
                        obs = ci2["unit"] or obs
                else:
                    code = "ENCODING_SUSPECT"
            mm = c.get("unit_mapping")
            if c.get("planned_action") == "convert_unit" and mm and num is not None \
                    and code in ("", "OUT_OF_RANGE"):
                if not obs:
                    code = code or "UNIT_ABSENT"
                elif L.unit_key(obs) == L.unit_key(mm["from"]):
                    cv, triple, ok = L.unit_convert(num, mm["from"], mm["to"])
                    if ok:
                        out, code = L.fmt_num(cv, mm.get("sig_digits")), "UNIT_CONVERTED"
                        rng = L.parse_range(c.get("valid_range") or c.get("range") or "")
                        if not L.in_range(cv, rng):
                            rec["flags"].append((c["field"], "OUT_OF_RANGE"))
                            stats.setdefault(c["field"], {})
                            stats[c["field"]]["OUT_OF_RANGE"] = \
                                stats[c["field"]].get("OUT_OF_RANGE", 0) + 1
                        ledger.append(cell_row(tag, c, rec, raw, out, "convert_unit",
                                               {"from": mm["from"], "to": mm["to"],
                                                "factor": mm.get("factor"),
                                                "triple": [triple[0], triple[1]],
                                                "inverse": "(out*f2+o2-o1)/f1"}))
                    else:
                        code = "UNIT_UNKNOWN"
                elif L.unit_key(obs) != L.unit_key(mm["to"]):
                    code = code or "UNIT_UNKNOWN"
            if not code and (c.get("planned_action") == "convert_date" or c.get("dtype") == "date"):
                nd = L.norm_date(out)
                if nd and nd != L.norm(out):
                    ledger.append(cell_row(tag, c, rec, raw, nd, "convert_date",
                                           {"format": "ISO-8601"}))
                    out, code = nd, "DATE_CONVERTED"
            rec["cells"].append(out)
            rec["codes"].append(code)
            if code:
                stats.setdefault(c["field"], {})
                stats[c["field"]][code] = stats[c["field"]].get(code, 0) + 1
                rec["flags"].append((c["field"], code))
        cells.append(rec)
    busy = [j for j, c in enumerate(ctrs) if c.get("dtype") in BUSY]
    if not busy:
        busy = [j for j in range(len(hdr))
                if sum(1 for r in rows if L.parse_num(r[j] if j < len(r) else "") is not None)
                >= max(1, int(0.4 * len(rows)))] or list(range(len(ctrs)))
    for rec in cells:
        if busy and all(rec["codes"][j] for j in busy):
            rec["codes"].append("NO_USABLE_VALUE")
            rec["flags"].append(("__row__", "NO_USABLE_VALUE"))
            stats.setdefault("__row__", {})
            stats["__row__"]["NO_USABLE_VALUE"] = stats["__row__"].get("NO_USABLE_VALUE", 0) + 1
    dup_n = 0
    for rule in dedupe:
        idxs = [j for j, h in enumerate(hdr) if h in rule["key_fields"]]
        if len(idxs) != len(rule["key_fields"]):
            continue
        groups = {}
        for rec in cells:
            if "DUP_DROPPED" in rec["codes"]:
                continue
            groups.setdefault(tuple(key_norm(ctrs[j], rec["cells"][j]) for j in idxs), []).append(rec)
        for key, g in groups.items():
            if len(g) < 2:
                continue
            keep = g[-1] if rule["keep"] == "latest" else g[0]
            for rec in g:
                if rec is keep:
                    continue
                rec["codes"].append("DUP_DROPPED")
                rec["flags"].append(("__row__", "DUP_DROPPED", "dup_of:%s" % rid(tag, keep["row"])))
                dup_n += 1
                ledger.append(cell_row(tag, {"field": ",".join(rule["key_fields"]),
                                             "contract_id": "DEDUPE",
                                             "workorder_ref": rule.get("basis") or "not-referenced"},
                                       rec, json.dumps(list(key), ensure_ascii=False),
                                       "quarantined", "dedupe",
                                       {"keeper": rid(tag, keep["row"]), "keep": rule["keep"]}))
    stats.setdefault("__row__", {})["DUP_DROPPED"] = dup_n
    out_rows = []
    for rec in cells:
        codes = [x for x in rec["codes"] if x]
        status = "quarantined" if ("DUP_DROPPED" in codes or "NO_USABLE_VALUE" in codes) else \
            ("marked" if codes else "kept")
        out_rows.append({"record_id": rid(tag, rec["row"]), "src": rec["src"], "status": status,
                         "cells": rec["cells"],
                         "flags": "; ".join(fmt_flag(x) for x in rec["flags"] if x[1])})
    return {"tag": tag, "rel": T.get("rel"), "header": hdr, "rows": out_rows, "stats": stats,
            "ledger": ledger, "contracts": ctrs, "encoding": T.get("encoding"),
            "sha_in": T.get("sha"), "notes": T.get("notes") or []}


def aggregate(table_res):
    """cell rows -> aggregate rows; flag-only codes get one aggregate row each."""
    agg = {}
    for e in table_res["ledger"]:
        k = (e["field"], e["action"])
        a = agg.get(k)
        if a is None:
            a = agg[k] = {"kind": "aggregate",
                          "ledger_id": "L-%s-%02d" % (table_res["tag"], len(agg) + 1),
                          "table": table_res["tag"], "field": e["field"],
                          "contract_id": e["contract_id"], "workorder_ref": e["workorder_ref"],
                          "action": e["action"], "flag": ACTION_FLAG.get(e["action"], ""),
                          "value_changed": e["action"] in ("convert_unit", "convert_date",
                                                           "fix_encoding", "dedupe"),
                          "rows_affected": 0, "input_sample": e["input"],
                          "output_sample": e["output"], "samples": [], "row_refs": [],
                          "reversible": True,
                          "mapping_ref": "M-%s-%02d" % (table_res["tag"], len(agg) + 1),
                          "mapping": e["mapping"], "locator_base": table_res["tag"]}
        a["rows_affected"] += 1
        if len(a["samples"]) < 3:
            a["samples"].append({"row": e["row"], "input": e["input"], "output": e["output"]})
        if len(a["row_refs"]) < 20:
            a["row_refs"].append("%s#row%s" % (table_res["tag"], e["row"]))
    out = list(agg.values())
    for fld, codes in (table_res.get("stats") or {}).items():
        for code, n in (codes or {}).items():
            if not n or code in VALUE_CODES:
                continue
            ctr = next((c for c in table_res["contracts"] if c["field"] == fld), {})
            out.append({"kind": "aggregate",
                        "ledger_id": "L-%s-m%02d" % (table_res["tag"], len(out) + 1),
                        "table": table_res["tag"], "field": fld,
                        "contract_id": ctr.get("contract_id", ""),
                        "workorder_ref": ctr.get("workorder_ref", "not-referenced"),
                        "action": FLAG_ACTION.get(code, "mark_invalid"), "flag": code,
                        "value_changed": False, "rows_affected": n,
                        "input_sample": "", "output_sample": "", "samples": [],
                        "reversible": True, "mapping_ref": "", "mapping": None,
                        "locator_base": table_res["tag"],
                        "row_refs": [r["record_id"] for r in table_res["rows"]
                                     if ("%s:%s" % (fld, code)) in (r["flags"] or "")][:10]})
    return out


def write_cleaned(path, table_res):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([str(h) for h in table_res["header"]] + list(RAIL))
        for r in table_res["rows"]:
            w.writerow([str(x) for x in r["cells"]] +
                       [r["record_id"], r["src"], r["status"], r["flags"]])
    return L.sha_bytes(path.read_bytes())


def recount_file(path):
    """Independent recount from the delivered file. Report numbers come from here."""
    per, rows, status = {}, 0, {"kept": 0, "marked": 0, "quarantined": 0}
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows += 1
                st = r.get("__row_status") or "kept"
                status[st] = status.get(st, 0) + 1
                for part in str(r.get("__flags") or "").split(";"):
                    part = part.strip()
                    if not part or ":" not in part:
                        continue
                    fld, code = part.split(":", 1)
                    code = code.split("(")[0].strip()
                    if code:
                        per.setdefault(fld, {})
                        per[fld][code] = per[fld].get(code, 0) + 1
    except Exception as e:
        return {"error": "%s:%s" % (type(e).__name__, e), "rows": 0,
                "status": status, "fields": {}}
    return {"rows": rows, "status": status, "fields": per}


def compare_stats(mem, rc):
    """in-memory counts vs counts re-derived from the written table."""
    mis = []
    for fld, codes in (mem or {}).items():
        if fld == "__row__":
            continue
        for code, n in (codes or {}).items():
            if not n:
                continue
            got = ((rc.get("fields") or {}).get(fld) or {}).get(code, 0)
            if n != got:
                mis.append({"field": fld, "code": code, "memory": n, "table": got})
    return mis
