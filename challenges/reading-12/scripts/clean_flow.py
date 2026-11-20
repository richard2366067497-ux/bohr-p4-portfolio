"""clean_flow.py - pipeline layer: discovery, field resolution, proposals, composition.

The script never decides what the data means: it proposes, the agent decides in
/app/work/draft.json, and this module turns those decisions into a row model.
"""
import csv
import json
import re
from pathlib import Path

from clean_engine import (VERSION, artifact_names, build_objects, canonical, clip, find_rows, fmt,
                          formula_text, group_candidates, is_schema, iter_files,
                          judgment_key, merge_rules, nat, nkey, num, parse_cell,
                          read_table, read_text, rules_of, schema_fields, try_json,
                          verify_quote, walk_strings)

def discover(root, fdict, builtin_rules, units):
    """Inventory every input file, then build objects, column roles and candidate groups."""
    root = Path(root)
    idx = {"version": VERSION, "input_root": str(root), "case_id": None, "output_contract": {},
           "task_instruction": "", "task_md": {}, "materials": [], "tables": [], "objects": [],
           "columns": {"all": [], "roles": {}, "conditions": [], "unmapped": []},
           "schema": {"source": "builtin", "fields": dict(fdict.get("target_fields") or {})},
           "rules": [], "suppressed_rules": [], "groups": [], "notes": [], "errors": [],
           "degradations": [], "artifact_names": artifact_names({})}

    def deg(stage, note, **kw):
        rec = {"stage": stage, "note": note}
        rec.update(kw)
        idx["degradations"].append(rec)

    if not root.exists():
        deg("discover", "input root missing: %s" % root)
        return idx
    files = iter_files(root)
    if not files:
        deg("discover", "input root is empty")
        return idx

    loaded, entries = {}, {}
    for p in files:
        ext, rel = p.suffix.lower(), str(p.relative_to(root))
        entry = {"file": rel, "ext": ext, "bytes": p.stat().st_size, "kind": "other",
                 "rows": 0, "encoding": "binary"}
        if ext in (".json", ".csv", ".tsv", ".md", ".txt", ".yaml", ".yml"):
            try:
                text, enc, bad = read_text(p)
                entry.update(encoding=enc, chars=len(text))
                loaded[rel] = text
                if bad:
                    deg("read", "encoding fallback, %d replacement chars" % bad, file=rel)
            except Exception as exc:                              # noqa: BLE001
                idx["errors"].append({"stage": "read", "file": rel, "error": str(exc)})
        idx["materials"].append(entry)
        entries[rel] = entry

    case_rel, case_obj = None, {}
    for rel in sorted(loaded, key=lambda r: (not r.lower().startswith("case"), r)):
        obj, _ = try_json(loaded[rel])
        if isinstance(obj, dict) and ("output_contract" in obj or "case_id" in obj):
            case_rel, case_obj = rel, obj
            break
    if case_rel:
        entries[case_rel]["kind"] = "case"
        idx["case_id"] = case_obj.get("case_id")
        idx["output_contract"] = case_obj.get("output_contract") or {}
        idx["task_instruction"] = str(case_obj.get("task_instruction")
                                      or case_obj.get("instruction") or "")
        idx["artifact_names"] = artifact_names(idx["output_contract"])
        for key in sorted(case_obj):
            if key in ("dataset_version", "material_version", "schema_version", "case_version",
                       "seed", "version"):
                idx["notes"].append("case.%s=%s" % (key, clip(case_obj.get(key), 80)))
    else:
        deg("discover", "no case.json carrying output_contract/case_id")

    for rel in sorted(loaded):
        if entries[rel]["kind"] != "case" and entries[rel]["ext"] in (".md", ".txt") and (
                "task" in rel.lower() or "\u8bc4\u5206" in loaded[rel][:400]):
            entries[rel]["kind"] = "task"
            heads = [ln.lstrip("#").strip() for ln in loaded[rel].splitlines()
                     if ln.startswith("#")]
            idx["task_md"] = {"file": rel, "chars": len(loaded[rel]), "headings": heads[:24],
                              "excerpt": loaded[rel][:1200]}
            break

    tables, case_rules = [], []
    for rel in sorted(loaded):
        if entries[rel]["kind"] in ("case", "task"):
            continue
        low, text, ext = rel.lower(), loaded[rel], entries[rel]["ext"]
        if ext in (".csv", ".tsv"):
            rows, cols, err = read_table(text, ext)
            entries[rel].update(kind="records", rows=len(rows), columns=cols)
            if err:
                idx["errors"].append({"stage": "read", "file": rel, "error": err})
            if rows:
                tables.append({"file": rel, "rows": rows, "columns": cols})
            else:
                deg("read", "table has no data row", file=rel)
            continue
        if ext != ".json":
            continue
        obj, err = try_json(text)
        if err:
            idx["errors"].append({"stage": "read", "file": rel, "error": err})
            continue
        if isinstance(obj, dict) and "output_contract" in obj:
            continue
        got = rules_of(obj)
        if got or "rule" in low or "\u89c4\u5219" in rel:
            entries[rel].update(kind="rules", rows=len(got))
            case_rules.extend(got)
            continue
        if is_schema(obj, low) and not find_rows(obj):
            entries[rel]["kind"] = "schema"
            if schema_fields(obj):
                idx["schema"] = {"source": rel, "fields": schema_fields(obj)}
            continue
        rows = find_rows(obj)
        if not rows:
            continue
        cols = []
        for row in rows:
            for key in row:
                if key not in cols:
                    cols.append(key)
        entries[rel].update(kind="records", rows=len(rows), columns=cols)
        tables.append({"file": rel, "rows": rows, "columns": cols})
    if case_obj and not tables:
        rows = find_rows({k: v for k, v in case_obj.items() if k != "output_contract"})
        if rows:
            cols = []
            for row in rows:
                for key in row:
                    if key not in cols:
                        cols.append(key)
            tables.append({"file": "%s#records" % (case_rel or "case"), "rows": rows,
                           "columns": cols})
            idx["notes"].append("extraction rows were embedded in case.json")

    idx["tables"] = tables
    if not case_rules:
        deg("discover", "no case-supplied rule file; builtin rule catalog only")
    idx["rules"], idx["suppressed_rules"] = merge_rules(builtin_rules, case_rules)
    objs, cols = build_objects(tables, fdict, idx)
    idx["objects"] = objs
    idx["columns"] = {"all": cols["all"], "roles": dict(cols["roles"]),
                      "conditions": cols["conditions"], "unmapped": cols["unmapped"]}
    idx["groups"] = group_candidates(objs, units, 0.05)
    idx["unit_policy"] = unit_policy(objs, units, fdict, idx["schema"])
    return idx


# ---------------------------------------------------------------- canonicity
def resolve_field(indicator, fdict, schema):
    label, hit = canonical(indicator, (fdict.get("synonyms") or {}).get("indicator") or {})
    if hit:
        return label, "synonym"
    if label and label in (schema.get("fields") or {}):
        return label, "schema"
    return label or "unmapped_indicator", "derived"


def target_unit(field, unit, units, fdict, schema, policy):
    """Target unit: case schema first, then the observed-majority policy, then the table."""
    spec = (schema.get("fields") or {}).get(field) or {}
    for key in ("unit", "canonical_unit", "target_unit"):
        if spec.get(key):
            return str(spec[key])
    parsed = units.parse(unit)
    if parsed.get("ok") and policy:
        hit = policy.get("%s|%s" % (field, parsed["sig"]))
        if hit:
            return hit
    return (fdict.get("target_units") or {}).get(field)


def unit_policy(objs, units, fdict, schema):
    """One unit label per (field, dimension): the label most rows already use.

    Rows already using that label are untouched; the rest get an affine
    conversion with its formula logged. No scientific convention is invented.
    """
    if str((fdict.get("policy") or {}).get("unit_normalisation", "majority")) == "off":
        return {}
    counts = {}
    for obj in objs:
        unit = (obj["cells"].get("unit") or "").strip()
        parsed = units.parse(unit)
        if not parsed.get("ok"):
            continue
        field, _ = resolve_field(obj["cells"].get("indicator") or "", fdict, schema)
        slot = counts.setdefault("%s|%s" % (field, parsed["sig"]), {})
        slot[parsed["text"]] = slot.get(parsed["text"], 0) + 1
    out = {}
    for key in sorted(counts):
        out[key] = sorted(counts[key].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out


# -------------------------------------------------------------------- propose
def propose(obj, units, idx, fdict):
    """Mechanical first pass for one row; every field can be overridden by the agent."""
    cells = obj["cells"]
    p = parse_cell(cells.get("value"))
    if cells.get("value_low") and cells.get("value_high"):
        lo, hi = num(cells["value_low"]), num(cells["value_high"])
        if lo is not None and hi is not None:
            p = dict(p, kind="range", low=min(lo, hi), high=max(lo, hi))
    field, fsrc = resolve_field(cells.get("indicator") or "", fdict, idx["schema"])
    unit = (cells.get("unit") or "").strip() or p["unit_inline"]
    out = {"decision": "accept", "field": field, "field_source": fsrc, "unit": unit,
           "value": None, "low": None, "high": None, "err": None, "rules": ["R004"],
           "status": "ok", "reason": "", "reason_code": "", "factor": None, "offset": None,
           "target": unit, "kind": p["kind"], "parsed": p}
    if p["kind"] == "missing":
        out.update(decision="missing", status="missing", rules=["R008"],
                   reason="missing token in source cell")
        return out
    if p["kind"] == "text":
        out.update(decision="hold", status="needs_review", rules=["R006"],
                   reason="cell is not numeric: %s" % clip(p["text"], 60),
                   reason_code="unparsed_value")
        return out
    out.update(value=p["value"], low=p["low"], high=p["high"], err=p["err"])
    if not unit:
        out.update(decision="hold", status="needs_review", rules=["R013"],
                   reason="numeric value without a unit", reason_code="missing_unit")
        return out
    parsed = units.parse(unit)
    if not parsed.get("ok"):
        code = "ambiguous_unit" if parsed.get("reason") == "ambiguous_token" else "unknown_unit"
        out.update(decision="hold", status="needs_review", rules=["R012"],
                   reason="unit %r not resolvable (%s)" % (unit, parsed.get("token", "")),
                   reason_code=code)
        return out
    tgt = target_unit(field, unit, units, fdict, idx["schema"], idx.get("unit_policy"))
    if not tgt:
        out.update(rules=["R004"], reason="no target unit declared; source unit kept verbatim")
        return out
    tp = units.parse(tgt)
    if tp.get("ok") and tp.get("text") == parsed.get("text"):
        out.update(rules=["R004"], target=tgt, reason="source unit already matches the field unit")
        return out
    conv = units.convert(unit, tgt)
    if not conv.get("ok"):
        out.update(decision="hold", status="needs_review", rules=["R020"],
                   reason="cannot convert %s -> %s (%s)" % (unit, tgt, conv.get("reason")),
                   reason_code=conv.get("reason", "dim_mismatch"))
        return out
    out.update(decision="convert", status="converted", rules=["R011"], target=tgt,
               factor=conv["factor"], offset=conv["offset"],
               reason="converted %s -> %s" % (unit, tgt))
    return out


# ---------------------------------------------------------------- composition
def draft_rows(draft):
    rows = draft.get("rows") or draft.get("row_decisions") or []
    out = {}
    if isinstance(rows, dict):
        for rid, dec in rows.items():
            if isinstance(dec, dict):
                out[str(rid)] = dec
    elif isinstance(rows, list):
        for dec in rows:
            if isinstance(dec, dict) and (dec.get("row_id") or dec.get("locator")):
                out[str(dec.get("row_id") or dec.get("locator"))] = dec
    return out


def _rules(current, extra):
    items = [x for x in str(current or "").replace(",", ";").split(";") if x.strip()]
    if extra and extra.strip() and extra.strip() not in items:
        items.append(extra.strip())
    return ";".join(items)


def _note(current, extra):
    if not extra:
        return current or ""
    return (current + " | " + extra) if current else extra


def _pend(row, code, reason, action):
    return {"row_id": row["row_id"], "field": row.get("field", ""), "reason_code": code,
            "reason": clip(reason, 300), "suggested_action": clip(action, 200),
            "original_value": row.get("original_value", ""),
            "original_unit": row.get("original_unit", ""),
            "source_document_id": row.get("source_document_id", ""),
            "source_locator": row.get("source_locator", "")}


def _pend_obj(obj, field, code, reason, action):
    return _pend({"row_id": obj["row_id"], "field": field,
                  "original_value": obj["cells"].get("value", ""),
                  "original_unit": obj["cells"].get("unit", "") or obj["cells"].get("value", ""),
                  "source_document_id": obj["source_document_id"],
                  "source_locator": obj["source_locator"]}, code, reason, action)


def _dedupe_pending(pending):
    seen, out = set(), []
    for p in pending:
        key = (p["row_id"], p["reason_code"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return sorted(out, key=lambda p: (nat(p["row_id"]), p["reason_code"]))


def _dedupe_pending(pending):
    seen, out = set(), []
    for p in pending:
        key = (p["row_id"], p["reason_code"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return sorted(out, key=lambda p: (nat(p["row_id"]), p["reason_code"]))


def _migrate(obj, first, others, action, reason):
    """Drop a column-mapping row into the change log (field / material normalisation)."""
    for row in [first] + list(others):
        if row.get("before") == row.get("after"):
            continue
        action.append({"row_id": obj["row_id"], "field": row["field"], "before": row["before"],
                       "after": row["after"], "unit_before": "", "unit_after": "", "factor": "",
                       "offset": "", "formula": "synonym table lookup", "precision": "",
                       "rule_id": "R014", "source_document_id": obj["source_document_id"],
                       "source_locator": obj["source_locator"], "note": reason})


def resolve_row(obj, prop, dec, units, fdict, idx, pdec=None):
    """One output row: mechanical proposal, overridden by an explicit agent decision."""
    cells = obj["cells"]
    decision = str(dec.get("decision") or dec.get("action") or prop["decision"]).lower()
    field = str(dec.get("field") or prop["field"])
    src_unit = prop["unit"]
    tgt = str(dec.get("unit_target") or dec.get("unit") or prop["target"] or src_unit)
    rule_ids = _rules(";".join(prop["rules"]), str(dec.get("rule_id") or ""))
    value, low, high, err = prop["value"], prop["low"], prop["high"], prop["err"]
    status, note, pend, chg = prop["status"], "", None, []

    pdec = pdec or {}
    if decision in ("hold", "review", "pending"):
        value = low = high = err = None
        status = "needs_review"
        code = str(dec.get("reason_code") or pdec.get("reason_code") or prop.get("reason_code")
                   or "needs_review")
        reason = str(dec.get("reason") or pdec.get("reason") or prop.get("reason")
                     or "flagged for human review")
        pend = _pend_obj(obj, field, code, reason,
                         str(dec.get("suggested_action") or pdec.get("suggested_action")
                             or "open the source locator and decide by hand"))
    elif decision == "missing":
        value = low = high = err = None
        status = "missing"
        note = str(dec.get("reason") or prop.get("reason") or "missing in source")
    else:
        if decision == "convert" or (tgt and src_unit and nkey(tgt) != nkey(src_unit)):
            conv = units.convert(src_unit, tgt)
            if not conv.get("ok"):
                value = low = high = err = None
                status = "needs_review"
                rule_ids = _rules(rule_ids, "R020")
                pend = _pend_obj(obj, field, conv.get("reason", "dim_mismatch"),
                                 "cannot convert %s -> %s (%s)"
                                 % (src_unit, tgt, conv.get("reason")),
                                 "confirm the unit pair or supply the missing factor")
                tgt = src_unit
            else:
                factor, offset = conv["factor"], conv["offset"]
                prec = prop["parsed"]["decimals"]
                for fname, before in (("value", value), ("value_low", low),
                                      ("value_high", high), ("value_err", err)):
                    if before is None:
                        continue
                    use_off = 0.0 if fname == "value_err" else offset
                    after = before * factor + use_off
                    chg.append({"row_id": obj["row_id"], "field": fname, "before": before,
                                "after": after, "unit_before": src_unit, "unit_after": tgt,
                                "factor": factor, "offset": use_off,
                                "formula": formula_text(before, src_unit, factor, use_off,
                                                        after, tgt),
                                "precision": "source dp=%d" % prec, "rule_id": "R011",
                                "source_document_id": obj["source_document_id"],
                                "source_locator": obj["source_locator"],
                                "note": ("1:1 unit label normalisation (same dimension)"
                                         if (factor == 1.0 and not use_off)
                                         else "affine conversion; original retained in before")})
                value = None if value is None else value * factor + offset
                low = None if low is None else low * factor + offset
                high = None if high is None else high * factor + offset
                err = None if err is None else err * factor
                status = "converted"
                rule_ids = _rules(rule_ids, "R011")
                note = "converted %s -> %s" % (src_unit, tgt)
        else:
            status = "ok"
            note = str(dec.get("reason") or "") or prop.get("reason", "")
    if isinstance(dec.get("value"), (int, float)) and status in ("ok", "converted"):
        value = float(dec["value"])
    if dec.get("note"):
        note = _note(note, clip(dec["note"], 200))

    indicator, material = cells.get("indicator") or "", cells.get("material") or ""
    if prop["field_source"] == "synonym" and indicator and field != indicator:
        chg.append({"row_id": obj["row_id"], "field": "field", "before": indicator,
                    "after": field, "unit_before": "", "unit_after": "", "factor": "",
                    "offset": "", "formula": "synonym table lookup", "precision": "",
                    "rule_id": "R014", "source_document_id": obj["source_document_id"],
                    "source_locator": obj["source_locator"],
                    "note": "indicator normalised to a target field label"})
    mat_label, mat_hit = canonical(material, (fdict.get("synonyms") or {}).get("material") or {})
    if mat_hit and mat_label != material:
        chg.append({"row_id": obj["row_id"], "field": "material", "before": material,
                    "after": mat_label, "unit_before": "", "unit_after": "", "factor": "",
                    "offset": "", "formula": "synonym table lookup", "precision": "",
                    "rule_id": "R014", "source_document_id": obj["source_document_id"],
                    "source_locator": obj["source_locator"],
                    "note": "material spelling normalised; original kept in before"})
        material = mat_label

    row = {"row_id": obj["row_id"], "source_document_id": obj["source_document_id"],
           "source_locator": obj["source_locator"], "field": field, "indicator": indicator,
           "material": material,
           "condition_summary": ";".join("%s=%s" % (k, v) for k, v in
                                         sorted(obj["conditions"].items()) if v),
           "value": value, "value_low": low, "value_high": high, "value_err": err,
           "unit": "" if status in ("needs_review", "missing") else tgt,
           "original_value": cells.get("value", ""), "original_unit": cells.get("unit", ""),
           "rule_ids": rule_ids, "judgment_key": judgment_key(obj), "status": status,
           "duplicate_of": "", "note": note, "_auto": not bool(dec)}
    return row, chg, pend


def _group_decisions(draft):
    out = {}
    for g in draft.get("groups") or []:
        if not isinstance(g, dict):
            continue
        ids = g.get("row_ids") or g.get("rows") or []
        if isinstance(ids, str):
            ids = [ids]
        if ids:
            out[tuple(sorted(str(i) for i in ids))] = g
    return out


def compose(idx, draft, units, fdict):
    """Turn agent decisions plus mechanical defaults into rows, changes and pending items."""
    decisions = draft_rows(draft)
    pdec = {str(p.get("row_id")): p for p in draft.get("pending") or [] if isinstance(p, dict)}
    rows, changes, pending, auto_rows, decided = [], [], [], [], 0
    ind_map, mat_map = {}, {}
    for obj in idx["objects"]:
        dec = decisions.get(obj["row_id"]) or decisions.get(obj["locator"]) or {}
        prop = propose(obj, units, idx, fdict)
        decided += 1 if dec else 0
        if not dec:
            auto_rows.append(obj["row_id"])
        row, chg, pend = resolve_row(obj, prop, dec, units, fdict, idx, pdec.get(obj["row_id"]))
        rows.append(row)
        changes.extend(chg)
        if pend:
            pending.append(pend)
        ind_map.setdefault(obj["cells"].get("indicator") or "", row["field"])
        if obj["cells"].get("material"):
            mat_map.setdefault(obj["cells"]["material"], row["material"])

    gdec = _group_decisions(draft)
    row_by_id = {r["row_id"]: r for r in rows}
    gstats = {"total": len(idx["groups"]), "decided": 0, "merged": 0, "replicate": 0,
              "conflict": 0, "separate": 0, "undecided": 0}
    for grp in idx["groups"]:
        dec = gdec.get(tuple(sorted(grp["row_ids"]))) or gdec.get(tuple(sorted(grp["locators"])))
        action = str((dec or {}).get("action") or (dec or {}).get("decision") or "").lower()
        members = [row_by_id[r] for r in grp["row_ids"] if r in row_by_id]
        if not dec or not action:
            gstats["undecided"] += 1
            for row in members:
                row["note"] = _note(row["note"], "group undecided; kept separate (safe default)")
            continue
        gstats["decided"] += 1
        reason = clip(str(dec.get("reason") or "").strip(), 180)
        if action == "merge":
            members.sort(key=lambda r: nat(r["row_id"]))
            keep = members[0]
            for row in members[1:]:
                row["status"] = "merged_duplicate"
                row["duplicate_of"] = keep["row_id"]
                row["rule_ids"] = _rules(row["rule_ids"], "R016")
                row["note"] = _note(row["note"], "merged into %s: %s" % (keep["row_id"], reason))
            gstats["merged"] += max(len(members) - 1, 0)
            keep["note"] = _note(keep["note"], "retained representative of %s" % grp["group_id"])
        elif action in ("replicate", "keep_separate", "separate"):
            for row in members:
                if action == "replicate":
                    row["status"] = "replicate"
                    row["rule_ids"] = _rules(row["rule_ids"], "R017")
                row["note"] = _note(row["note"], "kept separate (%s): %s" % (action, reason))
            gstats["replicate" if action == "replicate" else "separate"] += 1
        elif action == "conflict":
            for row in members:
                row["status"] = "conflict"
                row["rule_ids"] = _rules(row["rule_ids"], "R018")
                row["note"] = _note(row["note"], "source conflict: %s" % reason)
                pending.append(_pend({"row_id": row["row_id"], "field": row["field"],
                                      "original_value": row["original_value"],
                                      "original_unit": row["original_unit"],
                                      "source_document_id": row["source_document_id"],
                                      "source_locator": row["source_locator"]},
                                     "value_conflict",
                                     "same judgment key, incompatible values: %s" % reason,
                                     "adjudicate against the paper; keep both values"))
            gstats["conflict"] += 1
        else:
            gstats["undecided"] += 1

    claims, cstats = build_claims(idx, draft, changes)
    counts = _counts(idx, rows, changes, pending, auto_rows, decided, gstats, cstats)
    return {"rows": rows, "changes": changes, "pending": _dedupe_pending(pending),
            "claims": claims, "counts": counts, "groups": idx["groups"],
            "group_stats": gstats, "indicator_map": ind_map, "material_map": mat_map,
            "auto_rows": auto_rows}


def build_claims(idx, draft, changes):
    """Agent claims first (quote-verified); mechanical provenance claims as a floor."""
    by_id = {o["row_id"]: o for o in idx["objects"]}
    out, agent_n, auto_n = [], 0, 0
    for i, c in enumerate(draft.get("claims") or [], start=1):
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") or {}
        quote = ev.get("quote") or c.get("quote") or ""
        loc = ev.get("locator") or c.get("locator") or ""
        rid = str(c.get("row_id") or (loc.split("#", 1)[1] if "#" in loc else ""))
        obj = by_id.get(rid) or next((o for o in idx["objects"] if o["locator"] == loc), None)
        ok, how = verify_quote(obj["blob"], quote) if obj else (False, "locator_unresolved")
        out.append({"claim_id": str(c.get("claim_id") or "C%03d" % i),
                    "kind": c.get("kind") if c.get("kind") in
                            ("reported", "inferred", "undetermined") else "inferred",
                    "statement": str(c.get("statement") or ""), "origin": "agent",
                    "row_id": obj["row_id"] if obj else rid,
                    "evidence": {"quote": quote,
                                 "locator": loc or (obj["locator"] if obj else ""),
                                 "rule_id": ev.get("rule_id") or c.get("rule_id") or ""},
                    "quote_verified": ok, "quote_match": how})
        agent_n += 1
    covered = {c["row_id"] for c in out}
    for ch in changes:
        if ch["field"] not in ("value", "value_low", "value_high", "value_err"):
            continue
        if ch["row_id"] in covered or len(out) >= 240:
            continue
        obj = by_id.get(ch["row_id"])
        if not obj:
            continue
        out.append({"claim_id": "M%03d" % (len(out) + 1), "kind": "inferred", "origin": "script",
                    "row_id": ch["row_id"],
                    "statement": "%s: %s %s -> %s %s by %s"
                                 % (ch["row_id"], fmt(ch["before"]), ch["unit_before"],
                                    fmt(ch["after"]), ch["unit_after"], ch["rule_id"]),
                    "evidence": {"quote": obj["cells"].get("value", ""),
                                 "locator": ch["source_locator"] or obj["locator"],
                                 "rule_id": ch["rule_id"]},
                    "quote_verified": True, "quote_match": "exact"})
        auto_n += 1
    return out[:240], {"agent": agent_n, "script": auto_n}


def _counts(idx, rows, changes, pending, auto_rows, decided, gstats, cstats):
    total = len(rows) or 1
    vals = [c for c in changes if c["field"] in ("value", "value_low", "value_high", "value_err")]
    return {"input_rows": len(idx["objects"]), "cleaned_rows": len(rows),
            "analytic_rows": len([r for r in rows if r["status"] in
                                  ("ok", "converted", "replicate")]),
            "changed_values": len(vals), "changed_labels": len(changes) - len(vals),
            "change_log_rows": len(changes),
            "pending_review": len(_dedupe_pending(pending)),
            "merged_duplicates": gstats["merged"], "conflicts": gstats["conflict"],
            "missing_values": len([r for r in rows if r["status"] == "missing"]),
            "needs_review": len([r for r in rows if r["status"] == "needs_review"]),
            "range_values": len([r for r in rows if r["value_low"] is not None]),
            "error_term_values": len([r for r in rows if r["value_err"] is not None]),
            "unmapped_columns": len(idx["columns"].get("unmapped") or []),
            "groups": gstats["total"], "groups_decided": gstats["decided"],
            "agent_rows_decided": decided, "auto_rows": len(auto_rows),
            "agent_coverage_pct": round(100.0 * decided / total, 2),
            "claims_agent": cstats["agent"], "claims_script": cstats["script"]}
