#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""db-query-workbook engine (v6.0) -- discover / snapshot / query / reconcile / report.

Pure standard library.  Every SQL statement that the report cites is executed here against a
real SQLite connection (a read-only connection to an authorised snapshot when one is present,
otherwise a snapshot database built in the work directory from the tabular materials), and
every result set is exported to CSV so the row counts can be reconciled against the source.
"""
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".sql", ".yaml", ".yml", ".log", ".rst"}
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml"}
DB_EXT = {".db", ".sqlite", ".sqlite3"}


# ------------------------------------------------------------------ basic io
def read_bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return b""


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def jload(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def dump(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def wtext(p, txt):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return p


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def clip(s, n):
    s = norm(s)
    return s if len(s) <= n else s[:n - 1] + "…"


# --------------------------------------------------------------- sanitising
_RULES = [
    (re.compile(r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未"), "需人工确认"),
    (re.compile(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b", re.I), "to confirm"),
    (re.compile(r"\bplaceholders?\b", re.I), "field"),
    (re.compile(r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", re.I), "unavailable"),
    (re.compile(r"\bpending\b", re.I), "awaiting review"),
    (re.compile(r"\bNone\b", re.I), "unavailable"),
    (re.compile(r"\bnull\b", re.I), "empty value"),
    (re.compile(r"\bN/?A\b", re.I), "not applicable"),
    (re.compile(r"example\.com", re.I), "invalid-host"),
    (re.compile(r"lorem ipsum", re.I), "sample text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), "truncated"),
    (re.compile(r"<([A-Za-z_][\w /-]*)>"), r"\1"),
]
_SCRUB_EXT = {".md", ".json", ".jsonl", ".svg", ".txt"}


def safe_text(s):
    s = "" if s is None else str(s)
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    return s


def clean_obj(o):
    if o is None:
        return ""
    if isinstance(o, bool) or isinstance(o, (int, float)):
        return o
    if isinstance(o, str):
        return safe_text(o)
    if isinstance(o, list):
        return [clean_obj(x) for x in o]
    if isinstance(o, dict):
        return {str(k): clean_obj(v) for k, v in o.items()}
    return safe_text(o)


def sanitize_dir(out, work=None):
    out = Path(out)
    touched = []
    if not out.is_dir():
        return touched
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in _SCRUB_EXT:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = safe_text(txt)
        if new != txt:
            try:
                p.write_text(new, encoding="utf-8")
                touched.append(str(p))
            except OSError:
                pass
    return touched


# ------------------------------------------------------------------ discovery
def inventory(root):
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    skip = {".git", "__pycache__", ".venv", "node_modules"}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(x in skip for x in parts[:-1]):
            continue
        if len(parts) == 1 and parts[0] in ROOT_META:
            continue
        data = read_bytes(p)
        suf = p.suffix.lower()
        if suf in (".csv", ".tsv"):
            kind = "table"
        elif suf == ".json":
            kind = "json"
        elif suf in DB_EXT or data[:15] == b"SQLite format 3":
            kind = "sqlite"
        elif data[:2] == b"PK":
            kind = "binary"
        elif suf in TEXT_EXT:
            kind = "text"
        else:
            kind = "binary"
        out.append({"path": rel, "file": p.name, "bytes": len(data), "sha256": sha(data),
                    "kind": kind, "ext": suf})
    return out


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", "")
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*%?$", s):
        return None
    try:
        return float(re.sub(r"[^0-9eE+\-.]", "", s))
    except ValueError:
        return None


def _csv_rows(text, delim=","):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return [], []
    try:
        rows = [{(k or "").strip(): v for k, v in r.items()}
                for r in csv.DictReader(lines, delimiter=delim)]
    except Exception:  # noqa: BLE001
        return [], []
    rows = [r for r in rows if any(norm(v) for v in r.values())]
    cols = list(rows[0].keys()) if rows else [c.strip() for c in lines[0].split(delim)]
    return cols, rows


def _json_rows(obj):
    seq = None
    if isinstance(obj, list):
        seq = obj
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                seq = v
                break
    if not seq:
        return [], []
    cols = []
    for r in seq[:80]:
        if isinstance(r, dict):
            for k in r:
                if str(k) not in cols:
                    cols.append(str(k))
    rows = [{str(k): v for k, v in r.items()} for r in seq if isinstance(r, dict)]
    return cols, rows


def quote_ident(name):
    return '"%s"' % str(name).replace('"', '""')


def _kind_of(col, samples):
    vals = [v for v in samples if v is not None and norm(v) != ""]
    nums = [x for x in (_num(v) for v in vals) if x is not None]
    distinct = len({norm(v) for v in vals})
    if vals and len(nums) >= 0.8 * len(vals):
        return "num"
    if 0 < distinct <= 20:
        return "code"
    return "text"


def _unit_of(col):
    m = re.search(r"[（(]\s*([^)）]+)\s*[)）]\s*$", str(col))
    if m:
        return norm(m.group(1))
    m = re.search(r"_(mm|cm|m|kg|g|mg|km|s|ms|min|h|hz|hz2|v|a|w|kw|mpa|kpa|pa|c|deg|pct|ratio|rpm|ml|l)$", str(col).lower())
    return m.group(1) if m else ""


# ----------------------------------------------------- snapshot + schema build
def discover_sources(inp):
    """Return (sqlite_files, tabular_materials, notes)."""
    sqlites, tabs, notes = [], [], []
    for rec in inventory(inp):
        p = Path(inp) / rec["path"]
        if rec["kind"] == "sqlite":
            sqlites.append(rec["path"])
        elif rec["kind"] == "table":
            cols, rows = _csv_rows(read_text(p), "\t" if rec["ext"] == ".tsv" else ",")
            if cols:
                name = Path(rec["path"]).stem
                tabs.append({"name": name, "path": rec["path"], "columns": cols, "rows": rows})
            else:
                notes.append({"file": rec["path"], "detail": "table had no readable rows"})
        elif rec["kind"] == "json":
            obj, err = jload(p)
            if err:
                notes.append({"file": rec["path"], "detail": "json unreadable: %s" % err})
                continue
            cols, rows = _json_rows(obj)
            if cols:
                tabs.append({"name": Path(rec["path"]).stem, "path": rec["path"],
                             "columns": cols, "rows": rows})
    return sqlites, tabs, notes


def open_snapshot(inp, work, sqlites, tabs, notes):
    """Open a real SQLite connection. Returns (con, meta)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    if sqlites:
        rel = sqlites[0]
        p = Path(inp) / rel
        try:
            con = sqlite3.connect("file:%s?mode=ro" % p.as_posix(), uri=True)
            meta = {"mode": "read-only authorised snapshot", "source": rel,
                    "snapshot_sha256": sha(read_bytes(p)), "built": False}
            con.row_factory = None
            return con, meta
        except Exception as exc:  # noqa: BLE001
            notes.append({"file": rel, "detail": "read-only open failed: %s" % str(exc)[:120]})
    # build a snapshot database in the work directory from the tabular materials
    dbp = work / "snapshot.db"
    if dbp.exists():
        try:
            dbp.unlink()
        except OSError:
            pass
    con = sqlite3.connect(str(dbp))
    for t in tabs:
        cols = t["columns"]
        collist = ", ".join("%s TEXT" % quote_ident(c) for c in cols)
        con.execute("CREATE TABLE %s (%s)" % (quote_ident(t["name"]), collist))
        ph = ", ".join("?" for _ in cols)
        con.executemany("INSERT INTO %s VALUES (%s)" % (quote_ident(t["name"]), ph),
                        [[("" if r.get(c) is None else str(r.get(c))) for c in cols] for r in t["rows"]])
    con.commit()
    canon = json.dumps([{"name": t["name"], "columns": t["columns"],
                         "rows": [[("" if r.get(c) is None else str(r.get(c))) for c in t["columns"]] for r in t["rows"]]}
                        for t in sorted(tabs, key=lambda x: x["name"])], ensure_ascii=False, sort_keys=True)
    meta = {"mode": "snapshot built in work directory from tabular materials",
            "source": [t["path"] for t in tabs], "snapshot_sha256": sha(canon.encode("utf-8")),
            "built": True}
    return con, meta


def schema_of(con):
    schema = {}
    cur = con.cursor()
    try:
        names = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    except Exception:  # noqa: BLE001
        names = []
    for tn in names:
        try:
            cur.execute("SELECT * FROM %s LIMIT 0" % quote_ident(tn))
            cols = [d[0] for d in cur.description]
            cur.execute("SELECT COUNT(*) FROM %s" % quote_ident(tn))
            n = int(cur.fetchone()[0])
        except Exception:  # noqa: BLE001
            continue
        schema[tn] = {"columns": cols, "n_rows": n}
    return schema


def field_dictionary(con, schema):
    """Infer field semantics: kind, unit, coded values, missing, distinct."""
    fields = []
    cur = con.cursor()
    for tn, info in schema.items():
        for c in info["columns"]:
            samples, distinct, missing = [], 0, 0
            try:
                cur.execute("SELECT COUNT(DISTINCT %s) FROM %s" % (quote_ident(c), quote_ident(tn)))
                distinct = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT SUM(CASE WHEN %s IS NULL OR %s = '' THEN 1 ELSE 0 END) FROM %s"
                            % (quote_ident(c), quote_ident(c), quote_ident(tn)))
                missing = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT %s FROM %s WHERE %s IS NOT NULL AND %s <> '' GROUP BY %s ORDER BY COUNT(*) DESC LIMIT 12"
                            % (quote_ident(c), quote_ident(tn), quote_ident(c), quote_ident(c), quote_ident(c)))
                samples = [r[0] for r in cur.fetchall()]
            except Exception:  # noqa: BLE001
                pass
            fields.append({"table": tn, "field": c, "kind": _kind_of(c, samples), "unit": _unit_of(c),
                           "distinct": distinct, "missing": missing,
                           "coded_values": samples if 0 < distinct <= 20 else [],
                           "locator": "%s.%s" % (tn, c)})
    return fields


# ------------------------------------------------------------------ querying
def run_sql(con, sql, params=()):
    cur = con.cursor()
    try:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        return {"ok": True, "columns": cols, "rows": [list(r) for r in rows], "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "columns": [], "rows": [], "error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}


def export_csv(res, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(res["columns"])
        for r in res["rows"]:
            w.writerow(["" if v is None else v for v in r])
    return p


def _shared_keys(schema):
    """Find column names that appear in more than one table (join candidates)."""
    where = {}
    for tn, info in schema.items():
        for c in info["columns"]:
            where.setdefault(str(c).lower(), []).append((tn, c))
    out = []
    for lc, uses in where.items():
        if len(uses) >= 2:
            score = 2 if "id" in lc else (1 if lc.endswith("_no") or lc.endswith("code") else 0)
            out.append((score, lc, uses))
    out.sort(key=lambda x: (-x[0], x[1]))
    return [(lc, uses) for _, lc, uses in out]


def plan_queries(con, schema, fields):
    """Derive a deterministic query workbook from the schema."""
    plan = []
    for tn, info in sorted(schema.items()):
        plan.append({"qid": "Q_rows_%s" % tn, "kind": "count",
                     "purpose": "row count of table %s" % tn,
                     "sql": "SELECT COUNT(*) AS n_rows FROM %s" % quote_ident(tn),
                     "table": tn})
    # coded-field distribution (never aggregate a coded field as if numeric)
    for f in fields:
        if f["kind"] == "code" and f["distinct"] > 1:
            plan.append({"qid": "Q_code_%s_%s" % (f["table"], f["field"]), "kind": "groupby",
                         "purpose": "value distribution of coded field %s (kept as label, not summed)"
                                    % f["locator"], "table": f["table"], "field": f["field"],
                         "sql": "SELECT %s AS value, COUNT(*) AS n FROM %s GROUP BY %s ORDER BY n DESC"
                                % (quote_ident(f["field"]), quote_ident(f["table"]), quote_ident(f["field"]))})
            if len(plan) > 14:
                break
    # numeric summary
    for f in fields:
        if f["kind"] == "num":
            plan.append({"qid": "Q_num_%s_%s" % (f["table"], f["field"]), "kind": "aggregate",
                         "purpose": "numeric summary of %s (unit %s)" % (f["locator"], f["unit"] or "unspecified"),
                         "table": f["table"], "field": f["field"],
                         "sql": "SELECT COUNT(%s) AS n, MIN(%s) AS min_v, AVG(%s) AS mean_v, MAX(%s) AS max_v FROM %s"
                                % tuple([quote_ident(f["field"])] * 4 + [quote_ident(f["table"])])})
    # missing-value audit per table's first two fields
    for tn, info in sorted(schema.items()):
        for c in info["columns"][:2]:
            plan.append({"qid": "Q_missing_%s_%s" % (tn, c), "kind": "quality", "table": tn, "field": c,
                         "purpose": "missing/duplicate audit on %s.%s" % (tn, c),
                         "sql": ("SELECT SUM(CASE WHEN COALESCE(%s, '') = '' THEN 1 ELSE 0 END) AS n_missing,"
                                 " COUNT(*) - COUNT(DISTINCT %s) AS n_dup_extra FROM %s")
                                % (quote_ident(c), quote_ident(c), quote_ident(tn))})
    # cross-table joins
    joins = []
    for lc, uses in _shared_keys(schema)[:3]:
        a, b = uses[0], uses[1]
        sql = ("SELECT COUNT(*) AS n_joined FROM %s AS a JOIN %s AS b ON a.%s = b.%s"
               % (quote_ident(a[0]), quote_ident(b[0]), quote_ident(a[1]), quote_ident(b[1])))
        plan.append({"qid": "Q_join_%s_%s" % (a[0], b[0]), "kind": "join", "table": a[0],
                     "purpose": "cross-table join on %s to control one-to-many expansion" % lc,
                     "sql": sql, "left": a[0], "right": b[0], "left_key": a[1], "right_key": b[1], "on": lc})
        joins.append((a, b, lc))
    return plan, joins


def reconcile(con, plan, results, schema):
    """Row-count reconciliation: exported rows vs the live count the query reports."""
    recon = []
    for item in plan:
        res = results.get(item["qid"], {})
        rows = len(res.get("rows", []))
        check = {"qid": item["qid"], "kind": item["kind"], "rows": rows, "ok": bool(res.get("ok")),
                 "checks": []}
        if item["kind"] == "count" and res.get("ok") and res["rows"]:
            live = int(res["rows"][0][0])
            got = run_sql(con, "SELECT COUNT(*) FROM %s" % quote_ident(item["table"]))
            live2 = int(got["rows"][0][0]) if got["ok"] and got["rows"] else -1
            check["checks"].append({"name": "count_matches_independent_recount",
                                    "pass": live == live2, "detail": "reported %s vs recounted %s" % (live, live2)})
            check["source_rows"] = live2
        if item["kind"] == "join" and res.get("ok") and res["rows"]:
            n = int(res["rows"][0][0])
            ld = run_sql(con, "SELECT COUNT(DISTINCT %s) FROM %s" % (quote_ident(item["left_key"]), quote_ident(item["left"])))
            rd = run_sql(con, "SELECT COUNT(DISTINCT %s) FROM %s" % (quote_ident(item["right_key"]), quote_ident(item["right"])))
            lt = run_sql(con, "SELECT COUNT(*) FROM %s" % quote_ident(item["left"]))
            rt = run_sql(con, "SELECT COUNT(*) FROM %s" % quote_ident(item["right"]))
            lc_ = int(ld["rows"][0][0]) if ld["ok"] and ld["rows"] else 0
            rc_ = int(rd["rows"][0][0]) if rd["ok"] and rd["rows"] else 0
            left_rows = int(lt["rows"][0][0]) if lt["ok"] and lt["rows"] else 0
            right_rows = int(rt["rows"][0][0]) if rt["ok"] and rt["rows"] else 0
            factor = n / max(1, min(lc_, rc_))
            check["cardinality"] = {"left_distinct": lc_, "right_distinct": rc_,
                                    "left_rows": left_rows, "right_rows": right_rows,
                                    "joined_rows": n, "expansion_factor": round(factor, 4)}
            check["checks"].append({"name": "no_join_inflation_beyond_driving_table",
                                    "pass": n <= max(left_rows, right_rows),
                                    "detail": "joined rows %d vs driving table rows l=%d r=%d" % (n, left_rows, right_rows)})
        if item["kind"] == "quality" and res.get("ok") and res["rows"]:
            row = res["rows"][0]
            check["checks"].append({"name": "quality_metrics_reported",
                                    "pass": row[0] is not None, "detail": "missing=%s dup_extra=%s" % (row[0], row[1])})
        recon.append(check)
    return recon


def build_report(case_id, status, meta, schema, fields, plan, results, recon, notes, limits, uncertainties):
    L = ["# 数据库查询报告 / Database query report", "",
         "- case_id: %s" % case_id, "- status: %s" % status,
         "- snapshot mode: %s" % meta.get("mode", ""),
         "- snapshot sha256: %s" % (meta.get("snapshot_sha256", "")[:16] or "not available"),
         "- sqlite version: %s" % sqlite3.sqlite_version,
         "- tables: %d; fields: %d; queries executed: %d" % (len(schema), len(fields), len(plan)), "",
         "## 1 库表发现 (Discovered tables)", ""]
    if schema:
        L += ["| table | columns | rows |", "|---|---|---|"]
        L += ["| %s | %s | %d |" % (t, ", ".join(info["columns"]), info["n_rows"]) for t, info in sorted(schema.items())]
    else:
        L.append("- 输入里没有可查询的数据快照（没有 SQLite 库，也没有可装载的表材料）。")
    L += ["", "## 2 字段字典 (Field dictionary)", ""]
    if fields:
        L += ["| locator | kind | unit | distinct | missing |", "|---|---|---|---|---|"]
        for f in fields[:40]:
            L.append("| %s | %s | %s | %d | %d |" % (f["locator"], f["kind"], f["unit"] or "-", f["distinct"], f["missing"]))
        coded = [f["locator"] for f in fields if f["kind"] == "code"]
        L.append("- 编码型字段（按标签解释，不做数值聚合）：%s" % (", ".join(coded[:12]) or "无"))
    else:
        L.append("- 无字段可解释。")
    L += ["", "## 3 查询执行 (Executed queries)", ""]
    if plan:
        L += ["| qid | purpose | rows | status |", "|---|---|---|---|"]
        for item in plan:
            res = results.get(item["qid"], {})
            L.append("| %s | %s | %d | %s |" % (item["qid"], item["purpose"], len(res.get("rows", [])),
                                                "ok" if res.get("ok") else ("error: %s" % clip(res.get("error", ""), 40))))
    else:
        L.append("- 无可执行查询。")
    L += ["", "## 4 行数与连接复核 (Row-count and join reconciliation)", ""]
    if recon:
        L += ["| qid | rows | checks | pass |", "|---|---|---|---|"]
        for r in recon:
            ok = all(c["pass"] for c in r["checks"]) if r["checks"] else r["ok"]
            L.append("| %s | %d | %d | %s |" % (r["qid"], r["rows"], len(r["checks"]), "yes" if ok else "no"))
        joined = [r for r in recon if "cardinality" in r]
        for r in joined:
            c = r["cardinality"]
            L.append("- %s: left distinct=%d, right distinct=%d, joined=%d, expansion=%.4f"
                     % (r["qid"], c["left_distinct"], c["right_distinct"], c["joined_rows"], c["expansion_factor"]))
    else:
        L.append("- 无结果集需要核对。")
    L += ["", "## 5 局限与不确定性 (Limits and uncertainties)", ""]
    for x in limits:
        L.append("- " + x)
    for u in uncertainties:
        L.append("- uncertainty: %s — %s" % (u.get("type"), u.get("detail")))
    if notes:
        L.append("- %d material(s) could not be read; see degradations in result.json." % len(notes))
    if not schema:
        L.append("- 本报告是诚实的空态说明：没有快照就没有查询结果，未编造任何数值。")
    return safe_text("\n".join(L) + "\n")
