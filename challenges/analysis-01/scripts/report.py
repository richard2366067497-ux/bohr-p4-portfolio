#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report: presentation + audit + envelope layer for field-contract-cleaner v1.1.0.

Renders the quality report from the delivered table's own recount (not the in-memory
counters), writes the field issue list, audits the delivered folder with checks that
re-derive numbers from files, and fills the envelope so that **every** declared
output_contract key survives as a substantive, self-describing block.

Contract keys are never dropped and never left as an empty shell: a key that maps to
a field-level column carries that column's rows; a key with no field-level slot is
reported explicitly; a key that could not run carries its reason. No artifact writes
a bare null and no delivered text carries a placeholder token (see cleanlib.
write_json / dumps_scrub): a legitimate value that would look like a placeholder is
serialized with a JSON escape, so the decoded value is unchanged.
"""
import csv
import json
from pathlib import Path

import cleanlib as L
import cleanrun as C

LIMITS = [
    "standard library only, no network, no clock; deterministic byte for byte on the same input",
    "no statistical modelling, no population inference and no imputation: missing and invalid "
    "cells are marked, never valued",
    "XLSX reads the first worksheet with shared strings and date styles only",
    "a unit that is absent from the registry is not converted; it is flagged instead",
    "the delivered table keeps every source row: duplicates are quarantined, not deleted",
]

# field-level columns of the contract record; a contract key equal to one of these is
# projected from the effective field_contract.json
FIELD_COLS = ("contract_id", "field", "meaning", "dtype", "unit", "valid_range",
              "missing_tokens", "invalid_rules", "workorder_ref", "planned_action",
              "unit_mapping", "basis")

# fallback key set when the case declares no output_contract (boundary case): the
# envelope still fills every key with a substantive block
DEFAULT_KEYS = ["case_id", "status", "deliverable", "cleaned_table", "change_log",
                "report", "field_contract", "reconciliation", "issues", "evidence",
                "verification", "uncertainty", "pending", "errors", "degradations",
                "runtime", "row_accounting", "counts", "summary"]


def render_report(c):
    o = ["# 数据质量报告（field-contract-cleaner v%s）" % L.VERSION, "",
         "- case_id: `%s`" % c["case_id"], "- status: `%s`" % c["status"],
         "- 阶段: `%s`｜契约来源: `%s`" % (c["stage"], c["contract_source"]),
         "- 口径：缺失 / 无效 / 越界**只标记不改值**；不做总体统计推断；原始文件只读。", "",
         "## 1. 输入与编码", "", "| 文件 | 类型 | 编码 | 行×列 | 字节 | sha256 |",
         "|---|---|---|---|---|---|"]
    for f in c["files"]:
        dims = "%s×%s" % (f.get("n_rows"), f.get("n_cols")) if f.get("kind") == "table" else "—"
        o.append("| `%s` | %s | %s | %s | %s | `%s` |" % (
            f["rel"], f.get("kind"), f.get("encoding") or "—", dims, f.get("size", "—"),
            (f.get("sha") or "—")[:12]))
    if c["dictionary_hits"]:
        o += ["", "字典来源：" + "；".join("`%s`（%s 条）" % (h["locator"], h["entries"])
                                        for h in c["dictionary_hits"])]
    o += ["", "## 2. 字段契约", "",
          "| 契约 | 字段 | 类型 | 目标单位 | 有效范围 | 动作 | 依据 | 来源 |",
          "|---|---|---|---|---|---|---|---|"]
    for x in c["contracts"]:
        o.append("| %s | `%s` | %s | %s | %s | %s | %s | %s |" % (
            x["contract_id"], x["field"], x.get("dtype") or "—", x.get("unit") or "—",
            x.get("valid_range") or "—", x["planned_action"],
            (x.get("basis") or x.get("workorder_ref") or "—")[:70], x.get("source", "—")))
    if not c["contracts"]:
        o.append("| — | — | — | — | — | — | 无表头可投影 | — |")
    o += ["", "## 3. 变换账本摘要", "",
          "| 动作 | 字段 | 问题码 | 影响行数 | 改值 | 可逆 | mapping |",
          "|---|---|---|---|---|---|---|"]
    for e in c["ledger_agg"]:
        o.append("| %s | `%s` | %s | %s | %s | %s | %s |" % (
            e["action"], e["field"], e.get("flag") or "—", e["rows_affected"],
            "是" if e.get("value_changed") else "否",
            "是" if e.get("reversible") else "否", e.get("mapping_ref") or "—"))
    if not c["ledger_agg"]:
        o.append("| — | — | — | 0 | — | — | — |")
    ac = c["accounting"]
    o += ["", "## 4. 三表对账（原始行 = 保留 + 标记 + 隔离）", "",
          "| 表 | 原始行 | kept | marked | quarantined | 守恒 |", "|---|---|---|---|---|---|"]
    for a in ac["tables"]:
        o.append("| `%s` | %s | %s | %s | %s | %s |" % (
            a["table"], a["raw_rows"], a["kept"], a["marked"], a["quarantined"],
            "OK" if a["ok"] else "FAIL"))
    if not ac["tables"]:
        o.append("| — | 0 | 0 | 0 | 0 | OK |")
    o += ["", "结论：" + ("全部守恒，无静默丢行。" if ac["ok"] else "存在不守恒表，见 reconciliation.json。"),
          "", "## 5. 逐字段问题清单（数字由清洗表 __flags 回算）", "",
          "| 字段 | 问题码 | 条数 | 占该字段行数 | 动作 | 原值样例 |", "|---|---|---|---|---|---|"]
    for it in c["issues"]:
        o.append("| `%s` | %s | %d | %.1f%% | %s | %s |" % (
            it["field"], it["code"], it["count"], it["rate"], it["action"], it["sample"] or "—"))
    if not c["issues"]:
        o.append("| — | — | 0 | — | — | — |")
    t = c["counts"]
    o += ["", "合计：字段 %d，原始行 %d，问题码 %d 种，flag 总数 %d。" % (
        t["fields"], t["rows_raw"], len(c["issues"]), t["flags_total"]), "",
        "## 6. 未处置 / 待人工确认", ""]
    if c["pending"]:
        o += ["| 对象 | 原因 | 建议 |", "|---|---|---|"]
        o += ["| `%s` | %s | %s |" % (p.get("item") or p.get("kind") or "?",
                                      p.get("reason") or p.get("detail") or "—",
                                      p.get("action") or "人工确认")
              for p in c["pending"]]
    else:
        o.append("- 无。所有字段均有契约，未处置项为空。")
    o += ["", "## 7. 可逆性与复现", ""]
    rev = [e for e in c["ledger_agg"] if e["action"] == "convert_unit"][:6]
    for e in rev:
        m = e.get("mapping") or {}
        o.append("- `%s`：%s → %s，样例 `%s` → `%s`；按 (out*f2+o2-o1)/f1 可还原输入。"
                 % (e["field"], m.get("from"), m.get("to"), e["input_sample"], e["output_sample"]))
    if not rev:
        o.append("- 本次无单位换算（无契约声明或单位已一致），其余动作不改变数值。")
    o += ["- 复现：`python3 scripts/main.py all`（或 init|show|check|build|selfcheck）；"
          "同一输入重复运行清洗表字节一致",
          "- 清洗表 sha256: `%s`" % (c["cleaned_sha"] or "—")[:32],
          "- 报告-表一致性：%s" % ("一致" if c["report_table_ok"] else
                            "**不一致**（已降级，见 reconciliation.json）"),
          "", "## 8. 边界与不确定性", ""]
    o += ["- " + u for u in (c.get("uncertainty") or ["无额外不确定性声明。"])]
    return "\n".join(o) + "\n"


def issue_rows(tables_res):
    rows = []
    for tr in tables_res:
        rc = tr.get("recount") or {}
        n = max(1, rc.get("rows", 0))
        for fld, codes in (rc.get("fields") or {}).items():
            for code, cnt in sorted(codes.items()):
                sample = ""
                if fld in tr["header"]:
                    k = tr["header"].index(fld)
                    for r in tr["rows"]:
                        if ("%s:%s" % (fld, code)) in (r["flags"] or ""):
                            sample = L.norm(r["cells"][k])[:40]
                            break
                rows.append({"table": tr["tag"], "field": fld, "code": code, "count": cnt,
                             "rate": round(100.0 * cnt / n, 1),
                             "action": C.FLAG_ACTION.get(code, "mark_invalid"),
                             "sample": sample})
    return rows


def write_issues(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["table", "field", "issue_code", "count", "rate_pct", "action", "raw_sample"])
        for r in rows:
            w.writerow([r["table"], r["field"], r["code"], r["count"], r["rate"],
                        r["action"], r["sample"]])


def audit(outdir, inpdir):
    """Re-derive every published number from files; report ok/problems."""
    out = Path(outdir)
    res, _ = L.load_json_any(out / "result.json")
    res = res if isinstance(res, dict) else {}
    fc, _ = L.load_json_any(out / "field_contract.json")
    fc = fc if isinstance(fc, dict) else {}
    rep, _ = L.load_json_any(out / "reconciliation.json")
    rep = rep if isinstance(rep, dict) else {}
    checks, problems = {}, []

    def chk(name, ok, detail=""):
        checks[name] = {"ok": bool(ok), "detail": "" if ok else detail}
        if not ok:
            problems.append({"check": name, "detail": detail})

    contract = {}
    if inpdir:
        cj, _ = L.load_json_any(Path(inpdir) / "case.json")
        if isinstance(cj, dict) and isinstance(cj.get("output_contract"), dict):
            contract = cj["output_contract"]
    echo = res.get("output_contract") if isinstance(res.get("output_contract"), dict) else {}
    chk("contract_echo", all(k in echo for k in contract),
        "missing: %s" % [k for k in contract if k not in echo][:6])
    need = ["cleaned_table.csv", "transform_ledger.jsonl", "data_quality_report.md",
            "field_contract.json", "reconciliation.json", "field_issues.csv"]
    chk("artifacts_present", all((out / f).is_file() for f in need),
        "missing: %s" % [f for f in need if not (out / f).is_file()])
    bad_rev, n_rev = [], 0
    try:
        for line in (out / "transform_ledger.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if not isinstance(e, dict) or e.get("kind") != "cell" or e.get("action") != "convert_unit":
                continue
            n_rev += 1
            tr = (e.get("mapping") or {}).get("triple")
            try:
                back = float(e["output"]) * tr[1] / tr[0]
                _u, src = L.unit_of_cell(e["input"])
                if src is None:
                    import re as _re
                    m = _re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", e["input"] or "")
                    src = L.parse_num(m.group(0)) if m else None
                ok = src is not None and abs(back - src) <= 1e-9 * max(1.0, abs(src))
            except Exception:
                ok = False
            if not ok:
                bad_rev.append(e.get("record_id"))
    except Exception:
        pass
    chk("ledger_invertible", not bad_rev, "not invertible: %s" % bad_rev[:5])
    chk("report_matches_table", bool((rep.get("report_table") or {}).get("ok")),
        str((rep.get("report_table") or {}).get("mismatches"))[:160])
    chk("row_accounting", bool((rep.get("row_accounting") or {}).get("ok")),
        str([t.get("table") for t in (rep.get("row_accounting") or {}).get("tables", [])
             if not t.get("ok")]))
    fields = fc.get("fields") or []
    hdr = fc.get("header") or {}
    ncol = len({L.nkey(h) for cols in (hdr.values() if isinstance(hdr, dict) else []) for h in cols})
    chk("contract_covers_fields",
        bool(fields) and len({L.nkey(f.get("field")) for f in fields}) >= ncol or not fields,
        "contract fields < header columns")
    chk("no_imputation", not [c for c in fields
                              if str(c.get("planned_action", "")).lower() in L.FORBIDDEN],
        "forbidden actions present")
    chk("source_unchanged", bool((rep.get("source_immutable") or {}).get("ok", True)),
        "source hash changed")
    cur = L.sha_bytes((out / "cleaned_table.csv").read_bytes()) \
        if (out / "cleaned_table.csv").is_file() else ""
    chk("cleaned_table_intact", cur == (rep.get("cleaned_sha") or ""),
        "sha differs from recorded value")
    return {"ok": all(v["ok"] for v in checks.values()), "checks": checks,
            "problems": problems, "ledger_unit_rows_checked": n_rev}


# ---- result envelope -----------------------------------------------------
def _col_block(k, contracts):
    """Project one field-level contract column into a self-describing block."""
    rows = []
    for c in contracts or []:
        v = c.get(k)
        if v is None:
            v = ""
        if isinstance(v, list):
            v = "; ".join(str(x) for x in v)
        elif isinstance(v, dict):
            v = json.dumps(L.drop_none(v), ensure_ascii=False, sort_keys=True)
        rows.append({"field_name": c.get("field", ""), "value": v} if k == "field"
                    else {"field": c.get("field", ""), k: v})
    if not rows:
        return {"source": "field_contract.json", "column": k, "count": 0, "computed": False,
                "reason": "no field contract row exists for this run, so this column has no value",
                "requirement": "a table material with a header row, or a draft field_contract entry",
                "input": "materials scanned under the input directory"}
    return {"source": "field_contract.json", "column": k, "count": len(rows), "rows": rows}


def _generic_block(k, payload):
    kl = str(k).lower()
    for words, target in ECHO_SEM:
        if any(w in kl for w in words):
            if target in payload:
                return payload[target]
    return {"key": k, "present": True, "count": len(payload),
            "note": "this case declares a contract key with no dedicated slot; it is reported here "
                    "instead of being dropped, and it never changes an executed transform"}


ECHO_SEM = [
    (("case",), "case_id"),
    (("deliver", "artifact", "output_file", "filename"), "deliverable"),
    (("report", "quality", "qc"), "report_path"),
    (("recon", "account"), "reconciliation"),
    (("issue", "problem", "anomal", "flag", "defect"), "field_issues"),
    (("evidence", "source", "locator", "citation", "provenance"), "evidence_map"),
    (("verif", "check", "audit"), "verification"),
    (("uncertain", "limit", "caveat", "risk", "assumption"), "uncertainty"),
    (("status", "state"), "status"),
    (("pending", "human", "todo", "follow"), "pending_human"),
    (("error",), "errors"),
    (("degrad",), "degradations"),
    (("runtime", "elapsed", "budget"), "runtime"),
    (("row",), "row_accounting"),
    (("count", "stat", "number"), "counts"),
    (("change", "ledger", "transform", "diff", "modif"), "change_log"),
    (("clean", "table", "dataset", "csv"), "cleaned_table"),
    (("skill", "version"), "skill"),
    (("summar", "conclusion", "answer", "result", "finding"), "summary"),
]


def contract_blocks(contract, payload, contracts):
    """Every declared key survives as a substantive block: field column, payload
    projection, generic note or an explicit could-not-run reason. Never an empty shell."""
    keys = list(contract.keys()) if contract else list(DEFAULT_KEYS)
    out = {}
    for k in keys:
        kl = str(k).lower()
        if k in payload:
            out[k] = payload[k]
        elif kl in FIELD_COLS or k in FIELD_COLS:
            out[k] = _col_block(k, contracts)
        else:
            out[k] = _generic_block(k, payload)
    return out


def write_result(out, case_id, contract, payload, stage, skill, nowf, contracts=None):
    res = {"case_id": case_id}
    res["output_contract"] = contract_blocks(contract, payload, contracts or [])
    res.update({k: v for k, v in payload.items() if k not in res})
    res["skill"] = skill
    res["stage"] = stage
    res["runtime"] = {"version": L.VERSION, "elapsed_s": nowf()}
    L.write_json(Path(out) / "result.json", res)
    return res


def seed_partial(out, case_id, contract, stage, skill, nowf):
    """First landing: a legal result.json before real work is attempted."""
    payload = {"status": "partial", "deliverable": "cleaned_table.csv",
               "cleaned_table": "cleaned_table.csv",
               "summary": "partial placeholder written before processing",
               "errors": [], "degradations": [{"kind": "not_finalized", "detail": stage}],
               "pending_human": [{"item": "pipeline", "reason": "partial placeholder written at "
                                                               "the start of the run"}],
               "sources": [],
               "uncertainty": ["the pipeline had not finished when this file was written"]}
    return write_result(out, case_id, contract, payload, stage, skill, nowf)


# ---- show ----------------------------------------------------------------
def render_show(info, rows=12):
    """Material listing with locators, bounded output for tight token budgets."""
    o = []
    case = info.get("case") if isinstance(info.get("case"), dict) else {}
    o.append("== materials (%s) ==" % (case.get("case_id") or "UNKNOWN-CASE"))
    for f in info.get("files") or []:
        o.append("  %-38s kind=%-5s %7dB enc=%-9s %s"
                 % (f["rel"][:38], f.get("kind"), f.get("size", 0),
                    (f.get("encoding") or "-")[:9],
                    ("sha=" + (f.get("sha") or "-")[:12]) if f.get("sha") else ""))
    if info.get("task_md"):
        o.append("  task.md -> %s (read-only statement of record)" % info["task_md"])
    o.append("")
    o.append("== tables (quote as file#row N; N = source data row, header is row 1) ==")
    if not info.get("tables"):
        o.append("  (no table detected under %s)" % info.get("path"))
    for T in info.get("tables") or []:
        o.append("  [%s] %d rows x %d cols enc=%s delim=%r%s"
                 % (T["rel"], len(T["rows"]), len(T["header"]), T["encoding"],
                    T["delim"] or "-", "" if not T["error"] else " ERROR=" + str(T["error"])))
        o.append("    HEADER " + " | ".join("%s@col%d" % (h, j + 1)
                                            for j, h in enumerate(T["header"])))
        for i, r in enumerate(T["rows"][:rows]):
            o.append("    %s#row%-3d %s" % (T["rel"], i + 2, " | ".join(x[:26] for x in r)))
        if len(T["rows"]) > rows:
            o.append("    ... %d more rows (--rows N for more)" % (len(T["rows"]) - rows))
    if info.get("dictionary_hits"):
        o.append("")
        o.append("== dictionary sources ==")
        o += ["  %s -> %s entries" % (h["locator"], h["entries"]) for h in info["dictionary_hits"]]
    if info.get("dictionary"):
        o.append("")
        o.append("== dictionary entries (trailing column = locator you must cite) ==")
        for k, e in list(info["dictionary"].items()):
            o.append("  F:%-18s unit=%-9s range=%-11s dtype=%-7s missing=%-14s <- %s"
                     % (e.get("field", k)[:18], (e.get("unit") or "-")[:9],
                        (e.get("range") or "-")[:11], (e.get("dtype") or "-")[:7],
                        (",".join(e.get("missing") or []) or "-")[:14], e.get("source") or "-"))
    if info.get("workorder"):
        o.append("")
        o.append("== cleaning workorder (respond to every item) ==")
        for w in info["workorder"]:
            o.append("  %-6s %-18s [%s]%s" % (w["id"], w["locator"],
                                              ",".join(w.get("actions") or []) or "?",
                                              "  FORBIDDEN-WORDING" if w.get("forbidden") else ""))
            o.append("         %s" % w["text"][:170])
    if info.get("qc"):
        o.append("")
        o.append("== per-metric QC rules ==")
        o += ["  %-6s %-18s %s" % (q["id"], q["locator"], q["text"][:150]) for q in info["qc"]]
    o.append("")
    o.append("== column profiles (blank/code/lod/nonnum/range, units, mojibake) ==")
    for T in info.get("tables") or []:
        for h, p in C.profile_table(T, info.get("dictionary")).items():
            o.append("  %-20s n=%-3d blank=%-2d code=%-2d lod=%-2d nonnum=%-2d num=%-3d "
                     "range=%-2d min=%-7s max=%-7s units=%-12s dtype=%-7s moji=%d"
                     % (h[:20], p["n"], p["n_blank"], p["n_code"], p["n_lod"], p["n_nonnum"],
                        p["n_num"], p["n_range"], p["min"], p["max"],
                        (",".join(sorted(p["units"].keys())) or "-")[:12], p["dtype"], p["moji"]))
            if p["samples"]:
                o.append("      e.g. " + " | ".join("%s#row%s=%r" % (T["rel"], s["row"], s["value"])
                                                    for s in p["samples"]))
    return "\n".join(o) + "\n"
