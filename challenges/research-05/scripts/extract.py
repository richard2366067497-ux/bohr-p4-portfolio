# -*- coding: utf-8 -*-
"""five-gate research evaluator: material parsing (sections / cells / rule extraction).

Standard library only; deterministic. Reads each section of a material by its heading
and pulls out the five gates, thresholds, codes, enums and rubric rows, each with a
locator and a verbatim quote.
"""
import hashlib, json, os, re

# ---------------------------------------------------------------- extraction
def sections(oid, text):
    out, cur = [], None
    for i, l in enumerate(text.split("\n"), 1):
        m = re.match(r"^#{1,4}\s*(.+?)\s*$", l)
        if m:
            cur = {"oid": oid, "title": m.group(1), "start": i, "lines": []}
            out.append(cur)
        if cur is not None:
            cur["lines"].append((i, l.rstrip()))
    return out


def sec_of(secs, key):
    for s in secs:
        if key in s["title"]:
            return s
    return None


def rows_of(s):
    return [(ln, l) for ln, l in s["lines"] if l.strip().startswith("|")]


def cells(l):
    return [c.strip() for c in l.strip().strip("|").split("|")]


def deback(s):
    return re.sub(r"`", "", s).strip()


def sub_of(line, marker):
    i = line.find(marker)
    return line[i:] if i >= 0 else line


class Doc(object):
    def __init__(self, oid, oid_label, text):
        self.oid, self.text = oid, text
        self.secs = sections(oid, text)

    def loc(self, ln):
        return "%s/p%d" % (self.oid, ln)


def extract(m):
    """Read the five-gate rules out of one material; every item keeps locator+quote."""
    d = Doc(m["id"], m["name"], m["text"])
    R = {"doc": d, "gates": [], "thresholds": [], "errors": [], "warns": [], "enums": [],
         "vague": {}, "modes": [], "number_units": [], "bounds": [], "rubric": [],
         "fields": [], "matrix_fields": [], "basis": []}
    s = sec_of(d.secs, "五门与四类交付的映射") or sec_of(d.secs, "映射")
    if s is not None:
        for ln, l in s["lines"]:
            if l.strip().startswith("题面的四项交付") or l.strip().startswith("题面的"):
                R["basis"].append({"locator": d.loc(ln), "quote": l.strip()})
            c = cells(l)
            if len(c) == 5 and re.fullmatch(r"G[1-5]", c[0]):
                R["gates"].append({"gate_id": c[0], "name": c[1], "question": c[2],
                                   "deliverable": c[3], "fields": deback(c[4]),
                                   "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "verdict 阈值") or sec_of(d.secs, "阈值")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) == 4 and re.fullmatch(r"G[1-5]", c[0]):
                R["thresholds"].append({"gate_id": c[0], "go": deback(c[1]), "conditional": deback(c[2]),
                                        "no_go": deback(c[3]), "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "错误码")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) >= 2:
                codes = re.findall(r"`([A-Z][A-Z_0-9]+)`", c[0])
                for cd in codes:
                    R["errors"].append({"code": cd, "trigger": deback(" ".join(c[1:-1])), "fix": deback(c[-1]),
                                        "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "警告码")
    if s is not None:
        seen = []
        for ln, l in s["lines"]:
            for cd in re.findall(r"`(W_[A-Z0-9_]+)`", l):
                if cd not in seen:
                    seen.append(cd)
                    R["warns"].append({"code": cd, "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "枚举词表")
    if s is not None:
        for ln, l in s["lines"]:
            m = re.match(r"^-\s*`([a-z_.]+)`\s*[:：]\s*(.+)$", l.strip())
            if m:
                R["enums"].append({"key": m.group(1), "values": [v.strip() for v in deback(m.group(2)).split("/")],
                                   "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "模糊措辞")
    if s is not None:
        for ln, l in s["lines"]:
            if "｜" in l and "`" in l:
                inner = l[l.find("`") + 1:l.rfind("`")]
                R["vague"] = {"terms": [t for t in inner.split("｜") if t.strip()],
                              "locator": d.loc(ln), "quote": l.strip()}
    s = sec_of(d.secs, "证据核验")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) == 3 and c[0].startswith("`"):
                R["modes"].append({"mode": deback(c[0]), "meaning": c[1], "admissible": c[2],
                                   "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "数字溯源")
    if s is not None:
        for ln, l in s["lines"]:
            m = re.search(r"`([^`]*｜[^`]*)`", l)
            if m:
                R["number_units"] = {"units": [u.strip() for u in m.group(1).split("｜") if u.strip()],
                                     "locator": d.loc(ln), "quote": l.strip()}
    s = sec_of(d.secs, "输入对象表")
    if s is not None:
        R["object_reconcile"] = [{"locator": d.loc(ln), "quote": l.strip()} for ln, l in s["lines"]
                                 if re.match(r"^\d+\.\s*\*\*", l.strip())]
    s = sec_of(d.secs, "评分维度")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) == 2 and deback(c[0]):
                R["rubric"].append({"point": deback(c[0]), "implementation": deback(c[1]),
                                    "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "不适用的场景") or sec_of(d.secs, "边界")
    if s is not None:
        for ln, l in s["lines"]:
            if l.strip().startswith("- "):
                R["bounds"].append({"locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "顶层")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) == 4 and deback(c[0]) and deback(c[0]) != "字段":
                R["fields"].append({"field": deback(c[0]), "type": c[1], "required": deback(c[2]),
                                    "note": c[3], "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "对齐矩阵长表")
    if s is not None:
        for ln, l in rows_of(s):
            c = cells(l)
            if len(c) == 3 and deback(c[0]) and deback(c[0]) != "字段":
                R["matrix_fields"].append({"field": deback(c[0]), "values": c[1], "note": c[2],
                                           "locator": d.loc(ln), "quote": l.strip()})
    s = sec_of(d.secs, "最小可用工作稿")
    if s is not None:
        for ln, l in s["lines"]:
            if l.strip().startswith("##"):
                R["sample_note"] = {"locator": d.loc(ln), "quote": l.strip()}
    return R


# ---------------------------------------------------------------- build one context
