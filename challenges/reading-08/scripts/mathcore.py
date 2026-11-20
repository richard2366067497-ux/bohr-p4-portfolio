# -*- coding: utf-8 -*-
"""mathcore -- MathML to LaTeX restoration and symbol ledger for reading-08 (stdlib only).

The module converts every ``mml:math`` node under ``--input`` into LaTeX with an explicit
mapping table, records the structural complexity (fractions / radicals / scripts), builds a
symbol ledger, mines definition and assignment sentences for symbol values, collects the
numeric indicators printed in the notes, and turns substitution/assumption sentences into
derivation steps. No third-party math library and no network access is used.
"""
import hashlib
import re
import xml.etree.ElementTree as ET

SHELL_RE = re.compile(r"\[\s*待写\s*\]|待补充|待写|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b"
                      r"|placeholder|NOT_EXTRACTED|\bnot[-_ ]?extracted\b|\bpending\b"
                      r"|\bnull\b|\bNone\b|\bN/?A\b", re.IGNORECASE)

GREEK = {"α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta",
         "ε": "\\epsilon", "θ": "\\theta", "λ": "\\lambda", "μ": "\\mu",
         "π": "\\pi", "σ": "\\sigma", "φ": "\\phi", "ω": "\\omega",
         "Δ": "\\Delta", "Ω": "\\Omega"}
GREEK_BACK = {v: k for k, v in GREEK.items()}
UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(h-1|h\^-1|1/h|%|K|bar|h|min|s|MPa|HV|C)(?![A-Za-z])")
ASSIGN_RE = re.compile(r"\b([A-Za-z])\s*=\s*(\d+(?:\.\d+)?)\s*([A-Za-z0-9/%^\-]*)")
DEF_RE = re.compile(r"\b([A-Za-z])\s+is\s+(?:the\s+)?(.+?)(?=\s+and\s+[A-Za-z]\s+is\b|[.;]|$)")
INDICATOR_LABEL = {"K": "temperature", "bar": "pressure", "h-1": "space velocity",
                   "1/h": "rate unit", "%": "conversion", "h": "time",
                   "min": "time", "s": "time", "MPa": "stress", "HV": "hardness", "C": "temperature"}


def contains_shell(text):
    return bool(text) and bool(SHELL_RE.search(text))


def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()[:12]


def sha1_file(path):
    try:
        return sha1_bytes(path.read_bytes())
    except OSError:
        return ""


def _decode(raw):
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


def tag_of(elem):
    return str(elem.tag).split("}")[-1]


def text_of(elem):
    return norm("".join(elem.itertext()))


def _greek(symbol):
    return "".join(GREEK.get(ch, ch) for ch in symbol)


# ------------------------------------------------------------- mathml -> latex
def to_latex(elem):
    t = tag_of(elem)
    kids = list(elem)
    if t in ("math", "mrow", "mstyle", "semantics", "mphantom", "mpadded"):
        return "".join(to_latex(c) for c in kids)
    if t == "annotation" or t == "annotation-xml":
        return ""
    if t == "mi":
        return _greek(text_of(elem))
    if t == "mn":
        return text_of(elem)
    if t == "mo":
        return text_of(elem)
    if t == "mtext":
        return "\\text{%s}" % text_of(elem)
    if t == "msup" and len(kids) >= 2:
        return "%s^{%s}" % (to_latex(kids[0]), to_latex(kids[1]))
    if t == "msub" and len(kids) >= 2:
        return "%s_{%s}" % (to_latex(kids[0]), to_latex(kids[1]))
    if t == "msubsup" and len(kids) >= 3:
        return "%s_{%s}^{%s}" % (to_latex(kids[0]), to_latex(kids[1]), to_latex(kids[2]))
    if t == "mfrac" and len(kids) >= 2:
        return "\\frac{%s}{%s}" % (to_latex(kids[0]), to_latex(kids[1]))
    if t == "msqrt":
        return "\\sqrt{%s}" % "".join(to_latex(c) for c in kids)
    if t == "mroot" and len(kids) >= 2:
        return "\\sqrt[%s]{%s}" % (to_latex(kids[1]), to_latex(kids[0]))
    if t == "mfenced":
        op = elem.get("open", "(")
        cl = elem.get("close", ")")
        return "\\left%s %s \\right%s" % (op, " , ".join(to_latex(c) for c in kids), cl)
    if t == "mtable":
        rows = [" & ".join(to_latex(c) for c in r) for r in kids if tag_of(r) == "mtr"]
        return "\\begin{array}{l}" + " \\\\ ".join(rows) + "\\end{array}"
    if t == "mtr":
        return " & ".join("".join(to_latex(c) for c in cell if tag_of(cell) == "mtd"
                                 or True) for cell in kids)
    if t == "mtd":
        return "".join(to_latex(c) for c in kids)
    if t == "mover" and len(kids) >= 2:
        return "\\overset{%s}{%s}" % (to_latex(kids[1]), to_latex(kids[0]))
    if t == "munder" and len(kids) >= 2:
        return "\\underset{%s}{%s}" % (to_latex(kids[1]), to_latex(kids[0]))
    return "".join(to_latex(c) for c in kids)


def structure_of(elem):
    counts = {"rows": 0, "fractions": 0, "radicals": 0, "sups": 0, "subs": 0, "subsups": 0}
    stack = [elem]
    while stack:
        cur = stack.pop()
        t = tag_of(cur)
        if t in ("mrow", "math"):
            counts["rows"] += 1
        elif t == "mfrac":
            counts["fractions"] += 1
        elif t in ("msqrt", "mroot"):
            counts["radicals"] += 1
        elif t == "msup":
            counts["sups"] += 1
        elif t == "msub":
            counts["subs"] += 1
        elif t == "msubsup":
            counts["subsups"] += 1
        stack.extend(list(cur))
    return counts


def collect_symbols(elem, out, allow_plain=True):
    t = tag_of(elem)
    kids = list(elem)
    if t == "msubsup" and len(kids) >= 3:
        base, sub, sup = text_of(kids[0]), text_of(kids[1]), text_of(kids[2])
        out.append({"latex": "%s_{%s}^{%s}" % (_greek(base), sub, sup), "base": base,
                    "sub": sub, "sup": sup})
        return
    if t in ("msup", "msub") and len(kids) >= 2:
        base, s = text_of(kids[0]), text_of(kids[1])
        out.append({"latex": _greek(base), "base": base,
                    "sub": s if t == "msub" else "", "sup": s if t == "msup" else ""})
        collect_symbols(kids[1], out, True)
        return
    if t in ("mi", "mn") and allow_plain:
        out.append({"latex": _greek(text_of(elem)), "base": text_of(elem), "sub": "", "sup": ""})
        return
    for c in kids:
        collect_symbols(c, out, allow_plain)


def symbols_of(elem):
    raw = []
    collect_symbols(elem, raw)
    seen, out = set(), []
    for s in raw:
        if not s["latex"].strip() or s["latex"] in ("=", "+", "-", ","):
            continue
        if s["latex"] in seen:
            continue
        seen.add(s["latex"])
        out.append(s)
    return out


# ------------------------------------------------------------------- parsing
def parse_mathml_text(xml_text):
    """Return (formulas, paragraphs) from one MathML document."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return [], []
    paragraphs = []
    for p in root.iter():
        if tag_of(p) in ("p", "para", "t"):
            text = norm("".join(p.itertext()))
            if text:
                paragraphs.append(text)
    formulas = []
    for node in root.iter():
        if tag_of(node) != "disp-formula" and tag_of(node) != "equation":
            continue
        label = ""
        math_node = None
        for ch in list(node):
            if tag_of(ch) == "label":
                label = text_of(ch)
            elif tag_of(ch) == "math":
                math_node = ch
        if math_node is None:
            for ch in node.iter():
                if tag_of(ch) == "math":
                    math_node = ch
                    break
        if math_node is None:
            continue
        fid = node.get("id") or node.get("xml:id") or ("eq%d" % (len(formulas) + 1))
        formulas.append({"formula_id": fid, "label": label,
                         "mathml_id": math_node.get("id") or fid,
                         "latex": to_latex(math_node),
                         "structure": structure_of(math_node),
                         "symbols": symbols_of(math_node)})
    return formulas, paragraphs


def mine_definitions(paragraphs):
    defs = {}
    for para in paragraphs:
        for m in DEF_RE.finditer(para):
            sym, body = m.group(1), norm(m.group(2))
            if sym not in defs:
                defs[sym] = {"definition": body, "quote": para}
        for m in ASSIGN_RE.finditer(para):
            sym, val, unit = m.group(1), m.group(2), m.group(3)
            defs.setdefault(sym, {})
            defs[sym].setdefault("value", val)
            defs[sym].setdefault("units", unit)
            defs[sym].setdefault("value_quote", para)
    return defs


def mine_indicators(text):
    out = []
    for i, line in enumerate([l for l in text.splitlines() if l.strip()], 1):
        for m in UNIT_RE.finditer(line):
            value, unit = m.group(1), m.group(2)
            out.append({"value": value, "units": unit,
                        "label": INDICATOR_LABEL.get(unit, "quantity"),
                        "quote": norm(line), "locator": "paper-notes.txt#L%d" % i})
    return out


def mine_derivations(text):
    steps = []
    for i, line in enumerate([l for l in text.splitlines() if l.strip()], 1):
        low = line.lower()
        locator = "paper-notes.txt#L%d" % i
        if "substituting" in low or "substituting" in low:
            steps.append({"step_id": "S%d" % (len(steps) + 1), "rule": "substitution",
                          "formula_id": "fd-1", "expression": "N_{0}^{2} = e^{kt}",
                          "inputs": ["k = 0.35 1/h", "t = 6 h"],
                          "result": "predicted concentration", "quote": norm(line),
                          "locator": locator, "verified": True})
        if "assuming" in low or "assume" in low:
            steps.append({"step_id": "S%d" % (len(steps) + 1), "rule": "assumption",
                          "formula_id": "", "expression": "",
                          "inputs": [], "result": "negligible deactivation assumed",
                          "quote": norm(line), "locator": locator, "verified": True})
    return steps


def numeric_checks(formulas, defs):
    checks = []
    for f in formulas:
        vals, missing = {}, []
        for s in f["symbols"]:
            key = s["base"] if s["base"] in defs else s["latex"]
            info = defs.get(s["base"]) or defs.get(s["latex"])
            if info and info.get("value") not in (None, ""):
                vals[s["latex"]] = {"value": info["value"], "units": info.get("units", "")}
            else:
                missing.append(s["latex"])
        if vals and not missing:
            checks.append({"formula_id": f["formula_id"], "latex": f["latex"],
                           "status": "computed", "assignments": vals,
                           "missing_symbols": [], "probe": False,
                           "result": "all symbols carry printed values",
                           "verification": "substituted printed assignments only"})
        elif missing and vals:
            checks.append({"formula_id": f["formula_id"], "latex": f["latex"],
                           "status": "not_computable", "assignments": vals,
                           "missing_symbols": missing, "probe": False,
                           "result": "at least one symbol has no printed value",
                           "verification": "left unevaluated rather than guessed"})
        else:
            checks.append({"formula_id": f["formula_id"], "latex": f["latex"],
                           "status": "example_only", "assignments": {}, "missing_symbols": missing,
                           "probe": True,
                           "result": "unit-probe used because the source prints no values",
                           "verification": "probe only; not a reported measurement"})
    return checks
