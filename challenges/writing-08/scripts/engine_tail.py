def render_manuscript(draft, index=None, meta=None):
    meta = meta or {}
    draft = draft or {}
    lang = _lang_of(draft, meta)
    t = T[lang]
    ph = GAP_PH if lang == "zh" else GAP_PH_EN
    sections = SECTIONS[lang]
    cmap = _conflict_map(draft)
    overrides = draft.get("headings") if isinstance(draft.get("headings"), dict) else {}
    heading = {}
    for key, title in sections:
        heading[key] = _text(overrides.get(key)) or title
    L = []
    title = _text(meta.get("title")) or t["title"]
    L.append("# %s" % title)
    L.append("")
    case_id = _text(draft.get("case_id")) or _text(meta.get("case_id"), "unknown")
    src_note = "；".join(
        "%s=%s" % (m.get("source_id"), m.get("rel")) for m in (index or {}).get("materials", [])[:20])
    L.append(t["case"] % case_id)
    if src_note:
        L.append(t["sources"] % src_note)
    L.append(t["convention"] % (ph % t["field"]))
    L.append("")

    L.append("## %s" % heading["scope"])
    L.append("")
    tu = draft.get("task_understanding") or {}
    if isinstance(tu, dict) and tu:
        for label, key in ((t["genre"], "genre"), (t["audience"], "audience"),
                           (t["language"], "language"), (t["scope"], "scope"),
                           (t["structure"], "sections")):
            val = _text(tu.get(key))
            if val:
                L.append("- %s: %s" % (label, val))
        extra = _text(tu.get("notes"))
        if extra:
            L.append("- %s: %s" % (t["note"], extra))
    else:
        L.append(t["scope_fallback"] % (ph % t["genre"]))
    L.extend(_gap_lines(draft, "scope", t))
    L.append("")

    L.append("## %s" % heading["data"])
    L.append("")
    rows = _list(draft, "datasets")
    if rows:
        for d in rows:
            if isinstance(d, str):
                L.append("- %s" % d)
                continue
            head = _field(d, "name", t["dataset_name"], ph)
            parts = ["%s %s" % (t["version"], _field(d, "version", t["version"], ph)),
                     "%s %s" % (t["size"], _field(d, "size", t["size"], ph)),
                     "%s %s" % (t["preprocess"], _field(d, "preprocess", t["preprocess"], ph)),
                     "%s %s" % (t["split_l"], _field(d, "split", t["split_l"], ph)),
                     "%s %s" % (t["usage"], _field(d, "usage", t["usage"], ph))]
            L.append("- **%s**: %s%s" % (head, "; ".join(parts), cite(_sids(d))))
        L.append("")
        L.append(t["dataset_tbl"])
        L.append("|---|---|---|---|---|---|")
        for d in rows:
            if not isinstance(d, dict):
                continue
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                _field(d, "name", t["dataset_name"], ph), _field(d, "version", t["version"], ph),
                _field(d, "size", t["size"], ph), _field(d, "split", t["split_l"], ph),
                _field(d, "usage", t["usage"], ph), cite_cell(_sids(d))))
    else:
        L.append(t["data_none"] % (ph % "dataset"))
    L.extend(_gap_lines(draft, "data", t))
    L.append("")

    L.append("## %s" % heading["steps"])
    L.append("")
    rows = _list(draft, "steps")
    if rows:
        for i, s in enumerate(rows, 1):
            if isinstance(s, str):
                L.append("%d. %s" % (i, s))
                continue
            sid = _text(s.get("sid") or s.get("id"), "P%d" % i)
            name = _text(s.get("name"), "%s%s" % (t["step"], sid))
            loc = _text(s.get("locator"))
            tail = (" `%s`" % loc) if loc and loc not in name else ""
            L.append("%d. **%s %s**%s%s" % (i, sid, name, cite(_sids(s)), tail))
            for label, key in ((t["inputs"], "inputs"), (t["operation"], "operation"),
                               (t["params"], "params"), (t["output"], "output"),
                               (t["branch"], "branch")):
                val = _text(s.get(key))
                if val:
                    tail = "" if re.search(r"\[S\d+\]", val) else (
                        cite(_sids(s)) if any(ch.isdigit() for ch in val) else "")
                    L.append("   - %s: %s%s" % (label, val, tail))
    else:
        L.append(t["steps_none"] % (ph % "steps"))
    L.extend(_gap_lines(draft, "steps", t))
    L.append("")

    L.append("## %s" % heading["settings"])
    L.append("")
    rows = _list(draft, "settings")
    if rows:
        buckets = {}
        for s in rows:
            if isinstance(s, str):
                buckets.setdefault(t["other"], []).append({"text": s})
                continue
            area = _text(s.get("area"), t["other"])
            buckets.setdefault(area, []).append(s)
        for area in buckets:
            L.append("### %s" % area)
            L.append("")
            for s in buckets[area]:
                L.append("- %s%s" % (_field(s, "text", area, ph), cite(_sids(s))))
            L.append("")
    else:
        L.append(t["settings_none"] % (ph % "setup"))
    L.extend(_gap_lines(draft, "settings", t))
    L.append("")

    L.append("## %s" % heading["params"])
    L.append("")
    rows = _list(draft, "parameters")
    params = [p for p in rows if isinstance(p, dict)]
    if params:
        L.append(t["param_tbl"])
        L.append("|---|---|---|---|---|---|")
        for p in params:
            name = _field(p, "param", t["param_name"], ph)
            conf = bool(p.get("conflict")) or name.lower() in cmap
            state = t["conflict_state"] if conf else _text(p.get("status"), t["taken_from"])
            unit = _text(p.get("unit"), "—")
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                name, _field(p, "value", t["value"], ph), unit,
                _text(p.get("scope"), "—"), cite_cell(_sids(p)), state))
        L.append("")
    else:
        L.append(t["params_none"] % (ph % "parameters"))
    if cmap:
        L.append(t["conflict_head"])
        L.append("")
        for name, c in cmap.items():
            parts = []
            for src in c.get("sources") or []:
                if isinstance(src, dict):
                    parts.append("%s@%s=%s" % (_text(src.get("source") or src.get("source_id"), "?"),
                                               _text(src.get("locator"), "?"),
                                               _text(src.get("value"), "?")))
                else:
                    parts.append(str(src))
            L.append(t["conflict_line"] % (name, "; ".join(parts) or t["conflict_plain"],
                                           cite([(s.get("source_id") or s.get("source"))
                                                 for s in (c.get("sources") or [])
                                                 if isinstance(s, dict)])))
        L.append("")
    L.extend(_gap_lines(draft, "param", t))
    L.append("")

    L.append("## %s" % heading["baseline"])
    L.append("")
    rows = _list(draft, "baselines")
    if rows:
        L.append(t["baseline_tbl"])
        L.append("|---|---|---|---|---|---|---|")
        for b in rows:
            if isinstance(b, str):
                L.append("| %s | — | — | — | — | %s | — |" % (b, t["to_confirm"]))
                continue
            cmp_flag = b.get("comparable")
            comp = t["comparable"] if cmp_flag is True else (
                t["not_comparable"] if cmp_flag is False else t["to_confirm"])
            budget = b.get("budget_match")
            budget_s = "Y" if budget is True else ("N" if budget is False else t["to_confirm"])
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                _field(b, "name", t["baseline_name"], ph), _text(b.get("version"), t["to_confirm"]),
                budget_s, _text(b.get("metric"), t["to_confirm"]),
                _text(b.get("stat"), t["to_confirm"]), comp, cite_cell(_sids(b))))
        bad = [b for b in rows if isinstance(b, dict) and b.get("comparable") is False]
        if bad:
            L.append("")
            L.append(t["baseline_warn"])
    else:
        L.append(t["baseline_none"] % (ph % "baseline"))
    L.extend(_gap_lines(draft, "baseline", t))
    L.append("")

    L.append("## %s" % heading["metric"])
    L.append("")
    rows = _list(draft, "evaluation")
    if rows:
        for e in rows:
            if isinstance(e, str):
                L.append("- %s" % e)
            else:
                L.append("- %s%s" % (_field(e, "text", t["metric_desc"], ph), cite(_sids(e))))
    else:
        derived = []
        for b in _list(draft, "baselines"):
            if isinstance(b, dict) and _text(b.get("metric")):
                derived.append(t["metric_from_baseline"] % (
                    _text(b.get("name"), t["baseline_name"]), _text(b.get("metric")),
                    _text(b.get("stat"), t["to_confirm"]), cite(_sids(b))))
        L.extend(derived or [t["metric_none"] % (ph % "metrics")])
    L.extend(_gap_lines(draft, "metric", t))
    L.append("")

    L.append("## %s" % heading["repro"])
    L.append("")
    rows = _list(draft, "repro")
    required = (["代码版本", "运行环境", "随机种子", "启动命令", "数据获取方式"] if lang == "zh"
                else ["code version", "environment", "random seed", "launch command", "data access"])
    if rows:
        for r in rows:
            if isinstance(r, str):
                L.append("- [ ] %s" % r)
            else:
                L.append("- [%s] %s: %s%s" % (
                    "x" if _text(r.get("value")) else " ",
                    _text(r.get("item"), t["repro_item"]), _field(r, "value", t["value"], ph),
                    cite(_sids(r))))
        have = {_text(r.get("item")).lower() for r in rows if isinstance(r, dict)}
        miss = [k for k in required if not any(k.lower() in h for h in have)]
        if miss:
            L.append("")
            L.append(t["repro_missing"] % "、".join(ph % m for m in miss))
    else:
        L.append(t["repro_none"] % (ph % "reproduction info"))
    L.extend(_gap_lines(draft, "repro", t))
    L.append("")

    L.append("## %s" % heading["limits"])
    L.append("")
    rows = _list(draft, "limitations")
    if rows:
        for lim in rows:
            if isinstance(lim, str):
                L.append("- %s" % lim)
            else:
                L.append("- %s: %s; %s: %s; %s: %s%s" % (
                    t["limit_scope"], _field(lim, "scope", t["limit_scope"], ph),
                    t["limit_fail"], _field(lim, "failure_case", t["limit_fail"], ph),
                    t["limit_reason"], _field(lim, "reason", t["limit_reason"], ph),
                    cite(_sids(lim))))
    else:
        L.append(t["limits_none"] % (ph % "limitations"))
    L.extend(_gap_lines(draft, "limit", t))
    L.append("")

    L.append("## %s" % heading["gaps"])
    L.append("")
    gaps = [g for g in _list(draft, "gaps") if isinstance(g, dict)]
    if gaps:
        L.append(t["gap_tbl"])
        L.append("|---|---|---|---|---|---|")
        for g in gaps:
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                _text(g.get("gid"), "G?"), _text(g.get("kind"), "OTHER"),
                _text(g.get("desc"), ""), _text(g.get("impact"), ""),
                _text(g.get("owner"), "author"), _text(g.get("section"), "—")))
    else:
        L.append(t["gaps_none"] % (ph % t["field"]))
    L.append("")
    return "\n".join(L).rstrip() + "\n"

def fact_ledger_csv(draft, verified_map=None):
    verified_map = verified_map or {}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["fact_id", "statement", "value", "unit", "source_id", "locator", "quote", "status"])
    for i, f in enumerate([x for x in _list(draft, "facts") if isinstance(x, dict)], 1):
        fid = _text(f.get("fact_id"), "F%d" % i)
        status = _text(f.get("status"))
        if not status:
            verdict = verified_map.get(fid)
            status = "verified" if verdict is True else ("unverified" if verdict is False else "unchecked")
        w.writerow([fid, _text(f.get("statement")), _text(f.get("value")),
                    _text(f.get("unit")), _text(_sids(f) and _sids(f)[0]),
                    _text(f.get("locator")), _text(f.get("quote"))[:300], status])
    return buf.getvalue()

def parameter_ledger_csv(draft, index=None):
    detected = {}
    for g in (index or {}).get("groups", []):
        if g.get("status") == "conflict":
            detected[g.get("key")] = "；".join(
                "%s@%s" % (v.get("value"), ",".join(x["locator"] for x in v.get("sources", [])[:2]))
                for v in g.get("values", [])[:3])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["param", "value", "unit", "scope", "source_id", "locator",
                "source_kind", "conflict_flag"])
    idx = {}
    for f in [x for x in _list(draft, "facts") if isinstance(x, dict)]:
        sid = _text(_sids(f) and _sids(f)[0])
        if sid:
            idx.setdefault(_text(f.get("value")).lower(), (sid, _text(f.get("locator"))))
    for p in [x for x in _list(draft, "parameters") if isinstance(x, dict)]:
        sid = _text(_sids(p) and _sids(p)[0])
        loc = _text(p.get("locator"))
        if not sid or not loc:
            hit = idx.get(_text(p.get("value")).lower())
            if hit:
                sid = sid or hit[0]
                loc = loc or hit[1]
        name = _text(p.get("param"))
        key = canon_key(name)
        if p.get("conflict") or _text(p.get("status")) == "conflict":
            flag = "yes_resolved"
        elif key in detected:
            flag = "unresolved_detected(%s)" % detected[key]
        else:
            flag = "no"
        w.writerow([name, _text(p.get("value")), _text(p.get("unit")),
                    _text(p.get("scope")), sid, loc,
                    _text(p.get("source_kind") or p.get("source"), "material"), flag])
    return buf.getvalue()

def evidence_matrix_csv(coverage):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["element", "label", "items", "cited_items", "status", "locators"])
    for row in coverage.get("rows", []):
        w.writerow([row["element"], row["label"], row["items"], row["cited"],
                    row["status"], ";".join(row.get("locators", []))[:400]])
    return buf.getvalue()

def gaps_md(draft, index=None):
    lang = _lang_of(draft)
    t = T[lang]
    ph = GAP_PH if lang == "zh" else GAP_PH_EN
    L = [t["gaps_title"], ""]
    gaps = [g for g in _list(draft, "gaps") if isinstance(g, dict)]
    if not gaps:
        L.append(t["gaps_none2"] % (ph % t["field"]))
    for g in gaps:
        L.append("## %s · %s" % (_text(g.get("gid"), "G?"), _text(g.get("kind"), "OTHER")))
        L.append("")
        L.append(t["what_missing"] % _text(g.get("desc"), "—"))
        L.append(t["impact"] % _text(g.get("impact"), "—"))
        L.append(t["who"] % _text(g.get("owner"), "author"))
        L.append(t["which"] % _text(g.get("section"), "—"))
        q = _text(g.get("question") or g.get("author_question"))
        L.append(t["ask"] % (q if q else t["ask_default"]))
        L.append("")
    auto = (index or {}).get("unreadable") or []
    if auto:
        L.append(t["auto_unreadable"])
        L.append("")
        for m in auto:
            L.append("- `%s` (%s)" % (m.get("rel"), m.get("note") or "unreadable"))
        L.append("")
    return "\n".join(L).rstrip() + "\n"

def conflicts_md(draft, index=None):
    lang = _lang_of(draft)
    t = T[lang]
    L = [t["conflicts_title"], ""]
    rows = [c for c in _list(draft, "conflicts") if isinstance(c, dict)]
    if not rows:
        L.append(t["conflicts_none"])
        L.append("")
    for c in rows:
        L.append("## %s · %s" % (_text(c.get("cid"), "C?"), _text(c.get("item"), "unnamed")))
        L.append("")
        L.append("| %s | %s | %s |" % (t["src"], t["locator"], t["val"]))
        L.append("|---|---|---|")
        for src in c.get("sources") or []:
            if isinstance(src, dict):
                L.append("| %s | %s | %s |" % (
                    _text(src.get("source") or src.get("source_id"), "?"),
                    _text(src.get("locator"), "?"), _text(src.get("value"), "?")))
            else:
                L.append("| %s | — | — |" % src)
        L.append("")
        L.append(t["impact"] % _text(c.get("impact"), t["impact_default"]))
        L.append(t["disposal"] % _text(c.get("resolution"), t["disposal_default"]))
        L.append("")
    detected = [g for g in (index or {}).get("groups", []) if g.get("status") == "conflict"]
    if detected:
        L.append(t["detected_head"])
        L.append("")
        for g in detected:
            vals = "；".join(
                "%s=%s @%s" % (v["value"], v.get("unit") or "", ",".join(
                    s["locator"] for s in v.get("sources", []))) for v in g.get("values", [])[:4])
            L.append("- `%s`: %s" % (g.get("key"), vals))
        L.append("")
    return "\n".join(L).rstrip() + "\n"

def _has_content(item):
    if isinstance(item, str):
        return bool(item.strip())
    if not isinstance(item, dict):
        return False
    keys = ("value", "text", "name", "desc", "operation", "statement", "param")
    return any(_text(item.get(k)) for k in keys)

def coverage(draft):
    draft = draft or {}
    lang = _lang_of(draft)
    elements = ELEMENTS[lang]
    rows, covered, total = [], 0, len(elements)
    for key, label in elements:
        items, cited, gap_items, locs = 0, 0, 0, []
        for k in ELEMENT_KEYS[key]:
            for item in _list(draft, k):
                if not _has_content(item):
                    continue
                if not isinstance(item, dict):
                    items += 1
                    continue
                items += 1
                if _text(item.get("status")) == "gap" or item.get("gap"):
                    gap_items += 1
                sids = _sids(item)
                if sids:
                    cited += 1
                if item.get("locator"):
                    locs.append(_text(item.get("locator")))
                for src in item.get("sources") or []:
                    if isinstance(src, dict) and src.get("locator"):
                        locs.append(_text(src["locator"]))
        if items == 0:
            status = "missing"
        elif gap_items == items:
            status = "gap"
        elif cited == 0:
            status = "unsourced"
        elif cited < items or gap_items:
            status = "partial"
        else:
            status = "covered"
        if status == "covered":
            covered += 1
        rows.append({"element": key, "label": label, "items": items, "cited": cited,
                     "gap_items": gap_items, "status": status, "locators": locs[:12]})
    return {"elements": {r["element"]: r["status"] for r in rows},
            "covered": covered, "total": total,
            "ratio": round(covered / float(total), 3) if total else 0.0,
            "rows": rows}
