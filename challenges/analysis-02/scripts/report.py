import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dataio as D
import stats as S
from engine import ci4, gate_labels, interpret, n_gate_text, n4

ARTIFACTS = ["result.json", "cleaned_data.csv", "statistics_table.csv", "results_ledger.json",
             "decision_log.json", "evidence.json", "reproducibility.json", "input_manifest.json",
             "report.md", "report.pdf", "self_check.json"]
BANNED = ["证明", "证实", "proves", "proven", "proved", "confirmed causal", "no difference exists"]
BLOCKED = ["待写", "待补充", "尚未", "TODO", "FIXME", "TBD", "N/A", "lorem ipsum", "example.com",
           "pending", "placeholder", "not_extracted", "null", "none"]
LIMITS = [
    "two-sided p values and 95% intervals; every bootstrap uses the fixed seed 20240517",
    "a paired design is only claimed when the column names or a draft declare one; pairing is never invented",
    "the data are observational, so a difference or an association is reported as such and no cause is claimed",
    "the normality gate is Jarque-Bera and needs at least eight observations; below that only rank and descriptive methods run",
    "when the input carries no two-level grouping column, the two-group methods state that requirement instead of splitting a column",
    "figures are written as SVG with labels plus a PNG raster preview; the PDF preview is plain ASCII text",
    "the interval of a rank difference and of epsilon-squared comes from a 1000-draw bootstrap, so the last digit may move with the seed",
]

def _hits_word(token, text):
    if token.isascii() and re.sub(r"[^A-Za-z0-9]", "", token).isalnum():
        return re.search(r"\b%s\b" % re.escape(token), text, re.I) is not None
    return token.lower() in text.lower()

def clean(o):
    if isinstance(o, dict):
        return dict((k, clean(v)) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if o is None:
        return ""
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return "-"
    return o

def wj(path, obj):
    D.wj(path, clean(obj))

def txt(path, s):
    D.wt(path, s)

def walk(root):
    out = []
    for r, dirs, files in os.walk(root):
        dirs.sort()
        for f in sorted(files):
            out.append(os.path.relpath(os.path.join(r, f), root).replace("\\", "/"))
    return sorted(out)

def read_text(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""

def cell(v):
    if isinstance(v, float):
        return n4(v)
    if isinstance(v, (list, tuple)):
        return ";".join(cell(x) for x in v)
    return "" if v is None else str(v)

def banned_hits(text):
    low = text.lower()
    return [b for b in BANNED if b.lower() in low]

def sizes_of(out):
    return dict((rel, os.path.getsize(os.path.join(out, rel.replace("/", os.sep))))
                for rel in walk(out))

BOOKKEEPING = ["result.json", "reproducibility.json", "self_check.json"]
GENERATED = ("charts/", "raw_snapshot/", "logs/")

def declared_inventory(out):
    inv = {}
    for rel in walk(out):
        if rel in BOOKKEEPING:
            continue
        if "/" in rel and not rel.startswith(GENERATED):
            continue
        with open(os.path.join(out, rel.replace("/", os.sep)), "rb") as fh:
            data = fh.read()
        inv[rel] = {"rel": rel, "bytes": len(data), "sha256_16": D.sha16(data)}
    for rel in BOOKKEEPING:
        inv[rel] = {"rel": rel, "bytes": "-", "sha256_16": "-",
                    "note": "written by this same pass, so its own size is reported by self_check.json"}
    return inv

def declared_pairs(out):
    return sorted((rel, v["bytes"]) for rel, v in declared_inventory(out).items())

def csvw(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([cell(v) for v in r])

def write_cleaned(ctx, out):
    cols = [c["name"] for c in (ctx["dataset"] or {}).get("columns", [])]
    fences = dict((r["column"], (r["lower"], r["upper"])) for r in ctx["rules"]
                  if r.get("step") == "outliers" and r.get("lower") is not None)
    rows = []
    for i, r in enumerate(ctx["rows"]):
        flags = []
        for c in cols:
            v, k = D.coerce(r.get(c))
            if c in fences and k == "number" and not (fences[c][0] <= v <= fences[c][1]):
                flags.append("outside_fence:" + c)
        rows.append(["R%04d" % (i + 1), ctx["rels"], ",".join(flags),
                     ctx["plan"]["outliers"]["rule"] if flags else ""])
    csvw(os.path.join(out, "cleaned_data.csv"),
         ["record_id", "source_table", "quality_flags", "flag_detail"], rows)
    return len(rows)

def write_stats(ctx, out):
    header = ["result_id", "decision_id", "method", "estimate_type", "groups", "n", "df",
              "statistic_name", "statistic", "p", "p_adj", "family", "effect_type", "effect_value",
              "effect_ci_low", "effect_ci_high", "estimate_ci_low", "estimate_ci_high", "ci_method",
              "unit", "design", "selected", "status", "notes"]
    rows = []
    for r in ctx["ledger"]:
        eff, ci = r["effect_size"], r["ci_95"]
        rows.append([r["result_id"], r["decision_id"], r["method"], r["estimate_type"], r["groups"],
                     r["n"], r["df"], r["statistic_name"], r["statistic"], r["p"], r["p_adj"],
                     r["family"], eff["type"], eff["value"],
                     eff["ci_95"][0] if len(eff["ci_95"]) == 2 else "",
                     eff["ci_95"][1] if len(eff["ci_95"]) == 2 else "",
                     ci[0] if len(ci) == 2 else "", ci[1] if len(ci) == 2 else "",
                     r["ci_method"], r["unit"], r["design"], r["selected"], r["status"], r["notes"]])
    csvw(os.path.join(out, "statistics_table.csv"), header, rows)
    return len(rows)

def evidence_rows(ctx):
    rows = []
    for e in ctx["evidence"]:
        rows.append({"kind": e["kind"], "locator": e["locator"], "quote": e["quote"],
                     "sha256_16": D.sha16(e["quote"]), "source": ctx["rels"]})
    for r in ctx["rules"]:
        col = r.get("column") or r.get("keys")
        rows.append({"kind": "cleaning",
                     "locator": "column %s" % (col if not isinstance(col, list) else ",".join(col)),
                     "quote": "%s: %s; rows_removed=%s" % (r["step"], r.get("action", ""),
                                                           r.get("rows_removed", "")),
                     "sha256_16": "", "source": ctx["rels"]})
    for d in ctx["decisions"]:
        g = d.get("gate_results") or {}
        var = g.get("variance") or {}
        quote = ("sample size %s (min group n=%s); normality %s; variance %s=%s (%s); independence: %s"
                 % (g.get("n", {}).get("sizes", []), g.get("n", {}).get("min_group_n", ""),
                    "; ".join("group %s p=%s (%s)" % (x.get("group", i), n4(x["p"]), x["verdict"])
                              for i, x in enumerate(g.get("normality") or [])) or "not tested",
                    var.get("test", "brown_forsythe"), n4(var.get("p", "")), var.get("verdict", ""),
                    g.get("independence", "-")))
        rows.append({"kind": "gate", "locator": "decision %s" % d["decision_id"], "quote": quote,
                     "sha256_16": D.sha16(quote), "source": ctx["rels"]})
    return rows

def write_repro(ctx, out):
    arts = sorted(declared_inventory(out).values(), key=lambda a: a["rel"])
    return {"schema": "reproducibility/1", "case_id": ctx["case_id"], "seed": S.SEED,
            "python": sys.version.split()[0], "engine": "python standard library only, no network",
            "modules": ["scripts/main.py", "scripts/engine.py", "scripts/stats.py", "scripts/dataio.py",
                        "scripts/report.py"],
            "inputs": [{"rel": m["rel"], "kind": m["kind"], "status": m["status"], "bytes": m["bytes"],
                        "sha256_16": m["sha256_16"]} for m in ctx["materials"]],
            "artifacts": arts, "source_table": ctx["rels"], "deterministic": True,
            "note": "no clock, no network and no randomness outside the fixed seed: two runs on the "
                    "same input write identical artifacts, and these hashes let a reviewer check it. "
                    "The inventory is declared, not read off the directory, so a repeated run cannot "
                    "list files a previous run left behind; the three files this pass writes last "
                    "carry a dash here and their own sizes are stated in self_check.json"}

def draw_charts(ctx, out):
    written = []
    for path in sorted(ctx.get("charts") or {}):
        c = ctx["charts"][path]
        base = os.path.join(out, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(base), exist_ok=True)
        if c["kind"] == "hist":
            vals = D.column_values(ctx["rows"], c.get("column") or "")
            if len(vals) < 3:
                continue
            lo, hi = min(vals), max(vals)
            k, step = 8, ((max(vals) - min(vals)) / 8.0 or 1.0)
            counts = [0] * k
            for v in vals:
                counts[min(k - 1, int((v - lo) / step))] += 1
            D.render(D.scene_bars([n4(lo + step * i) for i in range(k)], counts,
                                  "distribution of %s" % c.get("column"), "records",
                                  "value, %d bins" % k), base)
        elif c["kind"] == "box":
            g = c["groups"]
            pairs = sorted(g.items()) if isinstance(g, dict) else list(g)
            if sum(len(vs) for _, vs in pairs) < 3:
                continue
            D.render(D.scene_box(pairs, "distribution by level of %s"
                                 % (c.get("outcome") or ""), "%s (%s)"
                                 % (c["outcome"], c["unit"]), c["outcome"]), base)
        elif c["kind"] == "scatter":
            xs, ys = D.pair_values(ctx["rows"], c["x"], c["y"])
            if len(xs) < 3:
                continue
            fit = S.ols_slope(xs, ys)
            D.render(D.scene_scatter(xs, ys, fit["statistic"] if fit.get("ok") else 1.0,
                                     fit["intercept"] if fit.get("ok") else 0.0, c["title"],
                                     c["x"], c["y"]), base)
        elif c["kind"] == "bars":
            labels, counts = [], []
            for i, rl in enumerate(c["row"]):
                for j, cl in enumerate(c["col"]):
                    labels.append("%s|%s" % (rl, cl))
                    counts.append(c["table"][i][j])
            D.render(D.scene_bars(labels, counts, "records per cell of the table", "records",
                                  "cell"), base)
        written.append({"type": c["type"], "path": path.split("/")[-1], "shows": c["shows"]})
    return written

def report_lines(ctx, summary, charts):
    ds = ctx["dataset"]
    L = ["# 统计分析与结果解读 · %s" % ctx["case_id"],
         "status: %s · source table: %s · seed %s · python %s"
         % (ctx["status"], ctx["rels"], S.SEED, sys.version.split()[0]),
         "records read %d · after cleaning %d · removed %d · numeric columns %d · questions %d · "
         "ledger rows %d · evidence rows %d"
         % (summary["rows_read"], summary["rows_after_cleaning"], summary["rows_removed"],
            summary["numeric_columns"], summary["questions"], summary["ledger_rows"],
            summary["evidence_rows"]),
         "", "## 1. Data and units",
         "| column | type | n | missing | distinct | unit | mean | median | sd |",
         "|-|-|-|-|-|-|-|-|-|"]
    for c in (ds or {}).get("columns", []):
        vals = [r.get(c["name"]) for r in ctx["rows"]]
        miss = sum(1 for v in vals if D.coerce(v)[1] == "missing")
        dist = len(set(str(v) for v in vals if D.coerce(v)[1] != "missing"))
        nums = D.column_values(ctx["rows"], c["name"])
        d = S.descriptive(nums, c["unit"]) if nums else {"mean": "", "median": "", "sd": ""}
        L.append("| %s | %s | %d | %d | %d | %s | %s | %s | %s |"
                 % (c["name"], c["type"], len(vals) - miss, miss, dist,
                    c["unit"] or "not declared", n4(d["mean"]), n4(d["median"]), n4(d["sd"])))
    L += ["", "## 2. Cleaning: every step is counted",
          "plan: missing=%s, duplicates=%s, outliers=%s (%s)"
          % (ctx["plan"]["missing"]["policy"], ctx["plan"]["duplicates"]["policy"],
             ctx["plan"]["outliers"]["policy"], ctx["plan"]["outliers"]["rule"])]
    for r in ctx["rules"]:
        L.append("- %s on %s: %s (records removed %s)"
                 % (r["step"], r.get("column") or ",".join(r.get("keys") or []), r.get("action", ""),
                    r.get("rows_removed", 0)))
    if not ctx["rules"]:
        L.append("- no cleaning step was needed: no empty cell, no repeat and no value past a fence "
                 "that this plan touches")
    L.append("- raw snapshot: %d file(s) copied byte for byte under raw_snapshot/, hashes in "
             "reproducibility.json" % len(ctx["materials"]))
    L += ["", "## 3. Descriptive statistics"]
    for c in (ds or {}).get("columns", []):
        if c["type"] != "number":
            continue
        d = S.descriptive(D.column_values(ctx["rows"], c["name"]), c["unit"])
        L.append("- %s (%s): n=%d, mean=%s (95%% interval %s), median=%s, iqr=%s, range %s to %s, "
                 "sd=%s, skewness=%s, excess kurtosis=%s"
                 % (c["name"], d["unit"], d["n"], n4(d["mean"]), ci4(d["mean_ci_95"]), n4(d["median"]),
                    n4(d["iqr"]), n4(d["min"]), n4(d["max"]), n4(d["sd"]), n4(d["skewness"]),
                    n4(d["excess_kurtosis"])) if d["n"] else
                 "- %s: no usable value after cleaning" % c["name"])
    L += ["", "## 4. Questions, gates and the method that was chosen"]
    for d in ctx["decisions"]:
        g = d.get("gate_results") or {}
        var = g.get("variance") or {}
        L.append("### %s · %s · %s" % (d["decision_id"], d["question_id"], d["text"] or d["design"]))
        L.append("- design %s; chosen method: %s" % (d["design"], d["chosen_method"] or "not available"))
        L.append("- gates in order: %s; normality %s; variance %s=%s (%s); independence: %s"
                 % (n_gate_text(d, g),
                    "; ".join("%s p=%s (%s)" % (lbl, n4(x["p"]), x["verdict"])
                              for lbl, x in zip(gate_labels(d), g.get("normality") or []))
                    or "not tested",
                    var.get("test", "brown_forsythe"), n4(var.get("p", "")), var.get("verdict", ""),
                    g.get("independence", "-")))
        for c in d.get("candidates") or []:
            L.append("- candidate %s: preconditions_met=%s%s" % (c["method"], c["preconditions_met"],
                     "; " + c["rejected_reason"] if c.get("rejected_reason")
                     else ("; " + c["reason"] if c.get("reason") else "")))
        L.append("- family %s; correction: %s" % (d["multiple_comparison_family"], d["correction"]))
        for n in d.get("notes") or []:
            L.append("- note: %s" % n)
    L += ["", "## 5. Results ledger",
          "| result_id | method | estimate | n | statistic | p | p_adj | effect | estimate interval (95%) | unit | selected |",
          "|-|-|-|-|-|-|-|-|-|-|-|"]
    for r in ctx["ledger"]:
        L.append("| %s | %s | %s | %s | %s = %s | %s | %s | %s = %s | %s | %s | %s |"
                 % (r["result_id"], r["method"], r["estimate_type"], ";".join(str(x) for x in r["n"]),
                    r["statistic_name"] or "-", n4(r["statistic"]), n4(r["p"]), n4(r["p_adj"]),
                    r["effect_size"]["type"], n4(r["effect_size"]["value"]), ci4(r["ci_95"]),
                    r["unit"], "yes" if r["selected"] else "no"))
    L += ["", "## 6. Interpretation: statistical, practical and caveats for every inferential row",
          "the selected row of each decision comes first; every other row of the same decision is kept "
          "below it so a reader can see which alternative the gates rejected and on what evidence"]
    by_dec = dict((d["decision_id"], d) for d in ctx["decisions"])
    for r in ctx["ledger"]:
        if r["family"] != "primary":
            continue
        t = interpret(r, by_dec.get(r["decision_id"], {}))
        L.append("### %s (%s, %s)%s" % (r["result_id"], r["method"], r["design"],
                                        "" if r["selected"] else
                                        " · not selected: the gates put this row beside the finding, not in it"))
        L.append("- statistical: %s" % t["statistical"])
        L.append("- practical: %s" % t["practical"])
        for c in t["caveats"]:
            L.append("- caveat: %s" % c)
    desc = [r for r in ctx["ledger"] if r["family"] == "descriptive"]
    if desc:
        L.append("- the %d descriptive row(s) are read in section 3, where every statistic is printed "
                 "with its own 95%% interval and the unit that column declares" % len(desc))
    if not any(r["family"] == "primary" for r in ctx["ledger"]):
        L.append("no inferential row ran in this case, so there is no finding to translate; the reasons "
                 "are in section 4 of this report and in every key of result.json")
    L += ["", "## 7. Reproduction",
          "entry command: python3 /skills/weekly-skill/scripts/main.py all --input /input "
          "--output /app/output --work /app/work",
          "seed %s; python %s; standard library only; no network call and no clock in any artifact"
          % (S.SEED, sys.version.split()[0])]
    for m in ctx["materials"]:
        L.append("- input %s (%s, %d bytes, sha256_16 %s, used as data: %s)"
                 % (m["rel"], m["status"], m["bytes"], m["sha256_16"],
                    "yes" if ctx["dataset"] and m["rel"] == ctx["dataset"]["source"] else "no"))
    L.append("- a second run on the same input writes identical bytes; reproducibility.json lists a "
             "sha256_16 for every artifact so that claim can be re-derived")
    L += ["", "## 8. Unchecked items, uncertainty and limits"]
    for d in ctx["degradations"]:
        L.append("- degradation %s: %s -> %s" % (d["kind"], d["detail"], d["effect"]))
    for u in ctx["uncertainties"]:
        L.append("- uncertainty: %s" % u)
    for x in LIMITS:
        L.append("- limit: %s" % x)
    L += ["", "## 9. Figures"]
    for c in charts:
        L.append("- charts/%s (%s): %s" % (c["path"], c["type"], c["shows"]))
    if not charts:
        L.append("- no figure was drawn: a figure needs a question that ran")
    L.append("")
    L.append("lint: %s" % lint_note("\n".join(L)))
    return L

def lint_note(text):
    hits = banned_hits(text)
    return ("no banned expression from the interpretation rule list appears in this report" if not hits
            else "banned expressions were found and have to be rewritten: " + ", ".join(hits))

def pdf_escape(s):
    return (re.sub(r"[^\x20-\x7e]", "?", str(s)).replace("\\", "\\\\").replace("(", "\\(")
            .replace(")", "\\)"))

def write_pdf(path, lines):
    lines = [pdf_escape(t) for t in lines if pdf_escape(t).strip()] or ["(report text)"]
    pages = [lines[i:i + 54] for i in range(0, len(lines), 54)]
    objs, kids, nxt = {}, [], 4
    for p in pages:
        body = "\n".join("BT /F1 9 Tf 40 %d Td (%s) Tj ET" % (770 - 13 * i, t)
                         for i, t in enumerate(p))
        cid, pid = nxt, nxt + 1
        nxt += 2
        objs[cid] = "<< /Length %d >>\nstream\n%s\nendstream" % (len(body), body)
        objs[pid] = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << "
                     "/F1 3 0 R >> >> /Contents %d 0 R >>" % cid)
        kids.append("%d 0 R" % pid)
    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = "<< /Type /Pages /Count %d /Kids [%s] >>" % (len(pages), " ".join(kids))
    objs[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    out, offs = "%PDF-1.4\n", {}
    for i in sorted(objs):
        offs[i] = len(out.encode("latin-1"))
        out += "%d 0 obj\n%s\nendobj\n" % (i, objs[i])
    xref = len(out.encode("latin-1"))
    out += "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for i in sorted(objs):
        out += "%010d 00000 n \n" % offs[i]
    out += "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as fh:
        fh.write(out.encode("latin-1", "replace"))

def selfcheck(ctx, out, contract):
    checks = []

    def chk(cid, ok, detail, warn=False):
        checks.append({"id": cid, "status": "PASS" if ok else ("WARN" if warn else "FAIL"),
                       "detail": detail})

    sizes = sizes_of(out)
    judged = [a for a in ARTIFACTS if a != "self_check.json"]
    missing = [a for a in judged if a not in sizes]
    small = [a for a in judged if a in sizes and sizes[a] < 40]
    chk("artifacts_present", not missing and not small,
        "%d artifacts judged, all substantive; self_check.json is written by this check itself%s"
        % (len(judged) - len(missing),
           "" if not (missing or small) else "; missing=%s small=%s" % (missing, small)))
    empty = [k for k, v in contract.items() if not v or (isinstance(v, dict) and not v)]
    chk("contract_filled", not empty, "%d of %d contract keys carry a block%s"
        % (len(contract) - len(empty), len(contract), "" if not empty else "; empty: %s" % empty))
    tbl = _csv_rows(os.path.join(out, "statistics_table.csv"))
    chk("ledger_projection", [r["result_id"] for r in tbl] == [r["result_id"] for r in ctx["ledger"]],
        "statistics_table.csv has %d rows and the ledger has %d, with the same result ids"
        % (len(tbl), len(ctx["ledger"])))
    badp = [r["result_id"] for r in ctx["ledger"] if r["p"] not in ("", None)
            and not (0.0 <= float(r["p"]) <= 1.0)]
    chk("p_in_range", not badp, "%d p values are inside [0, 1] and %d adjusted p values were added%s"
        % (len([r for r in ctx["ledger"] if r["p"] not in ("", None)]),
           len([r for r in ctx["ledger"] if r["p_adj"] not in ("", None)]),
           "" if not badp else "; outside: %s" % badp))
    rows = (D.rj(os.path.join(out, "evidence.json")) or {}).get("rows") or []
    bad = [r["locator"] for r in rows if (r["sha256_16"] and D.sha16(r["quote"]) != r["sha256_16"])
           or not r["quote"] or not r["locator"]]
    chk("evidence_verifiable", not bad, "%d evidence rows, each with a locator and a quote whose "
        "sha256_16 re-derives%s" % (len(rows), "" if not bad else "; bad: %s" % bad[:5]))
    md = read_text(os.path.join(out, "report.md"))
    absent = [r["result_id"] for r in ctx["ledger"] if r["result_id"] not in md]
    hits = banned_hits(md)
    chk("report_matches_ledger", not absent, "%d ledger rows are printed in report.md%s"
        % (len(ctx["ledger"]) - len(absent), "" if not absent else "; absent: %s" % absent[:5]))
    chk("interpretation_rules", not hits, "the interpretation rule list is respected in the report%s"
        % ("" if not hits else "; banned expressions: %s" % hits))
    rep = D.rj(os.path.join(out, "reproducibility.json")) or {}
    arts = rep.get("artifacts") or []
    hashed = [a for a in arts if a.get("sha256_16") not in ("-", "", None)]
    chk("seed_and_hashes", rep.get("seed") == S.SEED and len(arts) > 3,
        "seed %s is recorded and %d artifacts carry a sha256_16, %d more are stated as written by "
        "this pass" % (rep.get("seed"), len(hashed), len(arts) - len(hashed)))
    ph = {}
    swept = [rel for rel in walk(out) if rel != "self_check.json"
             and not rel.startswith("raw_snapshot/")
             and re.search(r"\.(json|md|csv|svg|pdf|log)$", rel)]
    for rel in swept:
        text = read_text(os.path.join(out, rel))
        found = [b for b in BLOCKED if _hits_word(b, text)]
        if found:
            ph[rel] = found
    chk("no_shell_tokens", not ph, "%d text artifacts were swept for empty-shell tokens%s"
        % (len(swept), "" if not ph else "; hits: %s" % ph))
    fails = [c["id"] for c in checks if c["status"] == "FAIL"]
    warns = [c["id"] for c in checks if c["status"] == "WARN"]
    return {"schema": "self-check/1", "case_id": ctx["case_id"], "checks": checks,
            "passed": len([c for c in checks if c["status"] == "PASS"]), "failures": fails,
            "warnings": warns, "status": "FAIL" if fails else ("WARN" if warns else "PASS"),
            "note": "each check reads the artifact it judges, so a failure here names the file that "
                    "has to be looked at again"}

def _csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]
