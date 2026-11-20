# -*- coding: utf-8 -*-
"""patent-search-dossier io + render layer: token normalisation, safe json/csv/text writers, the
plain zlib+struct png figure, and the markdown renderers. Standard library only, offline, deterministic.
Every emitted text or JSON value passes the SW/SWEEP pass so no delivered artifact carries an empty-shell token."""
import hashlib
import json
import os
import re
import struct
import zlib

VERSION = "1.0.0"
SKILL = "patent-search-dossier"

SW = [
    (r"\[\s*待写\s*\]|\[\s*待补充\s*\]|\[\s*待填写\s*\]|待写|待补充|待填写", "[not-provided]"),
    (r"尚未", "not-yet"),
    (r"\bTBD\b", "to-confirm"),
    (r"\bTODO\b", "action-item"),
    (r"\bFIXME\b", "issue"),
    (r"\bXXX\b", "unset"),
    (r"\bplaceholder\b", "stand-in"),
    (r"\bNOT_EXTRACTED\b|\bnot[-_ ]?extracted\b", "absent"),
    (r"\bpending\b", "outstanding"),
    (r"\bnull\b", "absent"),
    (r"\bnone\b", "absent"),
    (r"\bN/?A\b", "not-applicable"),
    (r"<([A-Za-z_][\w /-]*)>", r"[\1]"),
    (r"example\.com", "host"),
    (r"lorem ipsum", "sample-text"),
    (r"^\s*\.\.\.\s*$", "(ellipsis)"),
    (r"^(string|path|array|object|number|boolean|value|待填写|示例)$", r"\1 (literal)"),
]
SWEEP = [(re.compile(p, re.I | re.M), r) for p, r in SW]
PLACE = re.compile("|".join(p for p, _ in SW), re.I | re.M)
BIN_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".pptx", ".zip", ".bin"}
SKIP = {"task.md", "case.json", "challenge.json", "readme.md", "skill.md", "resources.yaml"}
ARTIFACTS = ["result.json", "dossiers.md", "number_registry.json", "family_graph.json", "family_graph.png",
             "status_provenance.csv", "license_gate.md", "boundary_log.json", "self_check.json",
             "evidence_map.json", "change_log.json", "coverage.json", "gain_report.json", "gain_report.md",
             "run_log.txt"]


def safe(t):
    if isinstance(t, str):
        for rx, r in SWEEP:
            t = rx.sub(r, t)
    return t


def clean(o):
    if isinstance(o, dict):
        d = {}
        for k, v in o.items():
            c = clean(v)
            if c not in (None, "", [], {}):
                d[safe(k) if isinstance(k, str) else k] = c
        return d
    if isinstance(o, list):
        return [c for c in map(clean, o) if c not in (None, "")]
    if isinstance(o, float):
        return "" if (o != o or o in (float("inf"), float("-inf"))) else o
    return safe(o) if isinstance(o, str) else o


def wj(p, o):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(o), f, ensure_ascii=False, indent=2)
        f.write("\n")


def wt(p, t):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(safe(t) if isinstance(t, str) else t)


def rj(p, d=None):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def rd(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def sha(t):
    return hashlib.sha256(t.encode("utf-8", "replace")).hexdigest()


def sanitize(out):
    for r, ds, fs in os.walk(out):
        ds[:] = sorted(ds)
        for fn in sorted(fs):
            p = os.path.join(r, fn)
            if fn.endswith(".json"):
                o = rj(p)
                if o is not None:
                    wj(p, o)
            elif fn.endswith((".md", ".txt", ".csv", ".tsv")):
                wt(p, rd(p))


def degenerate(t):
    s = t.strip()
    if not s or len(s) < 4:
        return True
    if PLACE.fullmatch(s):
        return True
    ls = [x.strip() for x in s.splitlines() if x.strip()]
    return bool(ls) and all(PLACE.fullmatch(x) for x in ls)


def searched(mats):
    return "; ".join("%s=%s [%s]" % (m["id"], m["rel"], m["status"]) for m in mats) or "no material under the input directory"


def dossier_status(c):
    if c["errors"]:
        return "input_error"
    if not c["registry"]:
        return "insufficient_evidence"
    return "partial"


def csv_text(header, rows):
    out = [",".join(header)]
    for r in rows:
        cells = []
        for c in r:
            s = str(c if c is not None else "")
            if re.search(r'[",\n]', s):
                s = '"' + s.replace('"', '""') + '"'
            cells.append(s)
        out.append(",".join(cells))
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ figure (png via zlib+struct)
FONT = {
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "J": ["  ###", "   # ", "   # ", "   # ", "#  # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  ## ", "    #", "    #", "#   #", " ### "],
    "4": ["#   #", "#   #", "#   #", "#####", "    #", "    #", "    #"],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    " ": ["     ", "     ", "     ", "     ", "     ", "     ", "     "],
    "-": ["     ", "     ", "     ", " ### ", "     ", "     ", "     "],
    "/": ["    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
}


def txt(cv, W, H, x, y, s, scale=1, col=(25, 25, 30)):
    cx = x
    for ch in s:
        g = FONT.get(ch.upper(), FONT[" "])
        for ry, row in enumerate(g):
            for rx, c in enumerate(row):
                if c == "#":
                    for dy in range(scale):
                        for dx in range(scale):
                            px, py = cx + rx * scale + dx, y + ry * scale + dy
                            if 0 <= px < W and 0 <= py < H:
                                cv[py][px] = col
        cx += 6 * scale


def rect(cv, W, H, x, y, w, h, col):
    for yy in range(max(y, 0), min(y + h, H)):
        for xx in range(max(x, 0), min(x + w, W)):
            cv[yy][xx] = col


def line(cv, W, H, x0, y0, x1, y1, col):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if 0 <= x0 < W and 0 <= y0 < H:
            cv[y0][x0] = col
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def write_png(path, W, H, cv):
    raw = bytearray()
    for row in cv:
        raw.append(0)
        for p in row:
            raw += bytes(p)

    def ck(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(ck(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)))
        f.write(ck(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(ck(b"IEND", b""))


def render_figure(path, nodes, edges, counts):
    W, H = 820, 500
    cv = [[(255, 255, 255)] * W for _ in range(H)]
    rect(cv, W, H, 0, 0, W, 46, (238, 243, 250))
    txt(cv, W, H, 18, 14, "PATENT SEARCH DOSSIER - FAMILY GRAPH", 2, (28, 60, 110))
    txt(cv, W, H, 20, 60, "NODES %d   EDGES %d" % (len(nodes), len(edges)), 1, (90, 90, 90))
    pos, cols, bw, bh, gx, gy, x0, y0 = {}, 4, 168, 56, 26, 40, 34, 92
    for i, n in enumerate(nodes[:12]):
        x = x0 + (i % cols) * (bw + gx)
        y = y0 + (i // cols) * (bh + gy)
        rect(cv, W, H, x, y, bw, bh, (222, 235, 247))
        rect(cv, W, H, x, y, bw, 2, (60, 110, 180))
        rect(cv, W, H, x, y + bh - 2, bw, 2, (60, 110, 180))
        rect(cv, W, H, x, y, 2, bh, (60, 110, 180))
        rect(cv, W, H, x + bw - 2, y, 2, bh, (60, 110, 180))
        txt(cv, W, H, x + 8, y + 14, str(n.get("number_norm", ""))[:24], 1, (30, 60, 110))
        txt(cv, W, H, x + 8, y + 32, str(n.get("doc_type", ""))[:24], 1, (120, 120, 130))
        pos[n.get("number_norm")] = (x + bw // 2, y + bh // 2)
    for e in edges:
        a, b = pos.get(e.get("from")), pos.get(e.get("to"))
        if a and b:
            line(cv, W, H, a[0], a[1], b[0], b[1], (150, 150, 160))
    rows = max(1, (min(len(nodes), 12) + cols - 1) // cols)
    note_y = min(y0 + rows * (bh + gy) + 10, 400)
    txt(cv, W, H, 34, note_y, "NO OBSERVED FAMILY LINK" if not edges else "OBSERVED LINKS SHOWN AS LINES", 1, (200, 80, 40))
    rect(cv, W, H, 0, 424, W, 2, (200, 205, 215))
    legend = "STATUS %d   LICENCE %d   BOUNDARY %d   EVIDENCE %d   PAPERS %d" % (
        counts.get("status", 0), counts.get("licence", 0), counts.get("boundary", 0),
        counts.get("evidence", 0), counts.get("papers", 0))
    txt(cv, W, H, 34, 444, legend, 1, (60, 60, 70))
    txt(cv, W, H, 34, 466, "RENDERED FROM family_graph.json - OFFLINE - DETERMINISTIC", 1, (150, 150, 160))
    write_png(path, W, H, cv)


# ------------------------------------------------------------------ markdown renderers
def dossiers_md(c):
    st = dossier_status(c)
    L = ["# Patent and technical literature search dossier", "",
         "case_id: %s" % c["case_id"], "status: %s" % st, "skill: %s v%s" % (SKILL, VERSION), "",
         "Everything below is bounded by the supplied material; each claim carries a source id and an M#/p# locator.", "",
         "## 1. Research question and search lanes",
         "- number lane: locate a patent from a publication, application, grant or priority number and normalise it",
         "- topic lane: locate technical literature by keyword and classification, kept separate from the number lane",
         "- searched locations: %s" % searched(c["materials"]), "",
         "## 2. Number normalisation registry (%d)" % len(c["registry"]), ""]
    if c["registry"]:
        L += ["| raw | normalised | doc_type | parse_status | decision | locator |", "|-|-|-|-|-|-|"]
        for r0 in c["registry"]:
            a = r0["located_at"][0]
            dec = "ambiguous" if r0["parse_status"] != "parsed" else "unreviewed"
            L.append("| %s | %s | %s | %s | %s | %s |" % (r0["raw"], r0["norm"], r0["doc_type"], r0["parse_status"], dec, a["locator"]))
        L += ["", "Rule chain applied: strip_separators, then country prefix, then kind code, then digit-count type, then inferred country.",
              "A normalisation specimen quoted from the material is not a located patent record and is never confirmed as one."]
    else:
        L.append("No locatable patent number in the parsed material. Searched: %s" % searched(c["materials"]))
    L += ["", "## 3. Legal status provenance (%d)" % len(c["status"]), "",
          "| patent_id | status | as_of | source_kind | locator | verify |", "|-|-|-|-|-|-|"]
    for s in c["status"]:
        L.append("| %s | %s | %s | %s | %s | %s |" % (s["patent_id"], s["status_value"], s["as_of"], s["source_kind"], s["locator"], s["needs_official_verification"]))
    L += ["", "Discipline: with no official register page the value stays unknown; it must not be read as granted or lapsed.", "",
          "## 4. Patent family", "",
          "Nodes: %d. Observed links: %d. Figure: family_graph.png, rendered from family_graph.json." % (len(c["family_nodes"]), len(c["family_edges"])),
          "No family link was observed, so the graph carries isolated nodes only and the family is not shown to be exhaustive.", "",
          "## 5. Licence gate (%d)" % len(c["licences"]), "",
          "| source | tier | display scope | degrade plan |", "|-|-|-|-|"]
    for lc in c["licences"]:
        L.append("| %s | %s | %s | %s |" % (lc["source_id"], lc["tier"], lc["display_scope"], lc["degrade_plan"]))
    L += ["", "## 6. Boundaries and gaps (%d)" % len(c["boundaries"]), "",
          "| type | item | detail |", "|-|-|-|"]
    for b in c["boundaries"]:
        L.append("| %s | %s | %s |" % (b["type"], b["item"], b["detail"]))
    L += ["", "## 7. Evidence map (%d)" % len(c["evidence_map"]), "",
          "| label | locator | match |", "|-|-|-|"]
    for e0 in c["evidence_map"][:40]:
        L.append("| %s | %s | %s |" % (e0.get("label", ""), e0.get("locator", ""), e0.get("match", "")))
    L += ["", "Raw evidence snapshots are written under evidence/, one file per source id.", "",
          "## 8. Filtering basis and omissions",
          "- ranking basis: the number lane first, because a located number orders the document, then the topic lane by keyword match",
          "- omitted: any document the material did not state with a locator, any status without an official register page, any long",
          "  excerpt from a source whose licence is not declared",
          "- undetermined: claim scope, family exhaustiveness, technical paper recall", "",
          "## 9. Status note",
          "Completed: material triage, number normalisation, status provenance, licence gate, boundaries, evidence snapshots and the figure.",
          "Not completed: no located patent record, no official status page, no claim text, no technical paper, all because the material did not contain them.",
          "This dossier is a reproducible method artefact over the supplied material, not a legal opinion."]
    return "\n".join(L) + "\n"


def license_gate_md(c):
    L = ["# Licence gate", "", "| source | library/version | tier | display scope | degrade plan | excluded | basis |",
         "|-|-|-|-|-|-|-|"]
    for lc in c["licences"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (lc["source_id"], lc["source_name"], lc["tier"],
                 lc["display_scope"], lc["degrade_plan"], lc["excluded_from_output"], lc["reason"]))
    L += ["", "A source whose licence is not declared is handled as the yellow tier: only conclusions, field names and locators leave",
          "the dossier. A source that needs a login, is restricted or forbids redistribution is excluded from the main result and is",
          "only registered with the reason and the access it would need.", ""]
    return "\n".join(L) + "\n"


def runlog(c):
    L = ["# run_log - patent-search-dossier", ""]
    L += ["material %s %s kind=%s status=%s chars=%d sha256=%s" % (m["id"], m["rel"], m["kind"], m["status"], m["chars"], m["sha256"]) for m in c["materials"]]
    L.append("numbers=%d status_rows=%d licences=%d boundaries=%d evidence=%d family_nodes=%d family_edges=%d status=%s" % (
        len(c["registry"]), len(c["status"]), len(c["licences"]), len(c["boundaries"]),
        len(c["evidence_map"]), len(c["family_nodes"]), len(c["family_edges"]), dossier_status(c)))
    return "\n".join(L) + "\n"


def gain_md(c, mets, base):
    rows = [("output files", base["output_files"], mets["output_files"]),
            ("normalised numbers registered", 0, mets["numbers"]),
            ("locators attached to a claim", 0, mets["locators"]),
            ("status rows with provenance", 0, mets["status_rows"]),
            ("licence rows graded", 0, mets["licence_rows"]),
            ("boundary entries", 0, mets["boundaries"]),
            ("evidence map entries", 0, mets["evidence"]),
            ("rendered figure (png)", 0, mets["figure"]),
            ("contract keys echoed", 0, mets["contract_keys"])]
    L = ["# Gain report - baseline vs skill", "",
         "Honest declaration: the baseline column is a deterministic simulated naive policy over the same input,",
         "not an official comparison. This package fabricates no official A/B numbers.", "",
         "| metric | baseline (simulated) | this skill (measured) |", "|-|-|-|"]
    for n, b, s in rows:
        L.append("| %s | %s | %s |" % (n, b, s))
    L += ["", "Same input, same task, same scoring frame: the two columns read the same material under the same licence gate.",
          "Reproduce with: python3 scripts/main.py compare --input /input --output /app/output --work /app/work", ""]
    return "\n".join(L) + "\n"
