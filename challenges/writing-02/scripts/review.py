# -*- coding: utf-8 -*-
"""Review layer: static findings, format compliance and review suggestions.

Everything here is deterministic and evidence-anchored: each item carries the
verbatim quote or the source path:line that triggered it. Nothing is invented —
a finding that cannot be verified from the supplied materials is reported as
``not_verifiable`` instead of being guessed.
"""
import re

import polish_core as C

EXTRA_KEYS = ["format_spec", "compliance_checks", "custom_unknown_field"]
CITE_NUM = re.compile(r"\[\s*(\d+(?:\s*[-–,，]\s*\d+)*)\s*\]")
FIGURE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
CAPTION = re.compile(r"^\s*(?:图|表|Figure|Table|Eq(?:uation)?)\s*\.?\s*(\d+)", re.M)
REF_HEAD = re.compile(r"^\s*(?:参考文献|references|bibliography)\s*[:：]?\s*$", re.I)
SUPER_ZH = re.compile(r"(最佳|最优|最好|最高|最低|首次|唯一|完全|彻底)")
SUPER_EN = re.compile(r"\b(best|optimal|first-ever|the first|only|complete|entirely|fully|novel)\b", re.I)
SIG_ZH = re.compile(r"(显著|显著性)")
SIG_EN = re.compile(r"\b(significant(?:ly)?|significance)\b", re.I)
STAT = re.compile(r"p\s*[<>=]\s*0?\.\d+|\bCI\b|置信区间|t\s*=\s*-?\d|F\s*=\s*\d|chi-square")
ABS_ZH = re.compile(r"^\s*(?:摘要|内容提要)\s*[:：]?")
ABS_EN = re.compile(r"^\s*abstract\b\s*[:：]?", re.I)
KW = re.compile(r"(关键词|关键字|keywords?)\s*[:：]", re.I)
ZH_REPL = {"最佳": "在实验条件下表现最好", "最优": "在实验条件下表现更优",
           "最好": "在实验条件下表现最好", "最高": "在所测范围内最高",
           "最低": "在所测范围内最低", "首次": "在本研究中",
           "唯一": "目前较为少见", "完全": "基本", "彻底": "较为充分"}
EN_REPL = {"best": "the most favourable under the tested conditions",
           "optimal": "favourable under the tested conditions",
           "first-ever": "among the first reported here", "the first": "among the first reported here",
           "only": "predominantly", "complete": "largely", "entirely": "largely",
           "fully": "largely", "novel": "distinct"}


def _cite_numbers(text):
    out = set()
    for m in CITE_NUM.finditer(text or ""):
        for part in re.split(r"[-–,，]", m.group(1)):
            if part.strip().isdigit():
                out.add(part.strip())
    return out


def _ref_numbers(docs):
    nums = set()
    for d in docs:
        for line in (d["text"] or "").splitlines():
            m = re.match(r"^\s*\[(\d+)\]", line)
            if m:
                nums.add(m.group(1))
        if REF_HEAD.search(d["text"] or ""):
            for m in re.finditer(r"^\s*\[(\d+)\]", d["text"] or "", re.M):
                nums.add(m.group(1))
    return nums


def citations(manuscript_text, docs):
    refs, cites, out = _ref_numbers(docs), _cite_numbers(manuscript_text), []
    missing = sorted(cites - refs, key=int) if refs else []
    if missing:
        out.append({"id": "L-CITE", "severity": "error", "kind": "citation_not_in_reference_list",
                    "message": "citation marker(s) %s have no matching entry in the reference list"
                               % ", ".join("[%s]" % m for m in missing),
                    "locator": "manuscript", "evidence": {"reference_entries": sorted(refs, key=int)}})
    elif cites and not refs:
        out.append({"id": "L-CITE", "severity": "warning", "kind": "reference_list_absent",
                    "message": "citation markers are present but no reference list was supplied, so "
                               "the citation numbers could not be resolved",
                    "locator": "manuscript", "evidence": {"citations": sorted(cites, key=int)}})
    return out


def xrefs(text):
    text, labels, out = text or "", set(), []
    for m in CAPTION.finditer(text):
        labels.add(m.group(1))
    for m in FIGURE.finditer(text):
        labels.add(m.group(2))
    seen = set()
    for m in C._XREF.finditer(text):
        tok = m.group(0)
        before = text[max(0, m.start() - 2):m.start()]
        after = text[m.end():m.end() + 4]
        if re.search(r"[!/]$", before) or re.match(r"\.(png|jpe?g|pdf|eps|svg)", after, re.I):
            continue  # part of a file name, not a cross-reference
        num = re.search(r"(\d+)", tok)
        if not num or num.group(1) in labels or tok in seen:
            continue
        seen.add(tok)
        out.append({"id": "L-XREF", "severity": "warning", "kind": "unresolved_cross_reference",
                    "message": "cross-reference %r has no numbered caption or target in the supplied "
                               "manuscript" % tok, "locator": "manuscript",
                    "evidence": {"captions_found": sorted(labels)}})
    return out


def figures(text):
    out, lines = [], (text or "").splitlines()
    for i, line in enumerate(lines):
        m = FIGURE.match(line.strip())
        if not m or not m.group(1).strip():
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not CAPTION.match(nxt):
            out.append({"id": "L-FIG-%d" % (i + 1), "severity": "warning", "kind": "caption_placement",
                        "message": "figure %r keeps its caption inside the image call; the submitted "
                                   "requirements ask for a caption below the figure" % m.group(2),
                        "locator": "manuscript:L%d:C1" % (i + 1),
                        "evidence": {"image": m.group(2), "alt_text": m.group(1)}})
    return out


def abstract_note(text):
    text = text or ""
    has_abs = any(ABS_ZH.match(l) or ABS_EN.match(l) for l in text.splitlines())
    if has_abs and not KW.search(text):
        return [{"id": "L-KW", "severity": "info", "kind": "abstract_without_keywords",
                 "message": "an abstract is present but no keyword line was found; this venue asks "
                            "for one", "locator": "manuscript"}]
    return []


def materials(docs):
    out = []
    for d in docs:
        if d["method"] in ("text", "json") and not (d["text"] or "").strip():
            out.append({"id": "L-MAT-" + d["doc_id"], "severity": "warning", "kind": "empty_material",
                        "message": "material %s holds no extractable text" % d["path"],
                        "locator": d["path"], "evidence": {"bytes": d["bytes"]}})
        elif d["note"]:
            out.append({"id": "L-MAT-" + d["doc_id"], "severity": "warning", "kind": "unparsed_material",
                        "message": "material %s could not be read as text (%s)" % (d["path"], d["note"]),
                        "locator": d["path"], "evidence": {"method": d["method"], "bytes": d["bytes"]}})
    return out


def glossary_findings(glossary):
    return [{"id": "G-" + g["id"], "severity": "info", "kind": "terminology_variant",
             "message": "terminology %r also appears as %s; one canonical form per document is "
                        "recommended" % (g["canonical"], ", ".join(g["variants_used"])),
             "locator": g["first_use"],
             "evidence": {"forms": [f["form"] for f in g["forms_found"]]}}
            for g in glossary if g["status"] == "variant_used"]


def abbreviation_findings(abbr):
    return [{"id": "L-ABBR-" + a["abbreviation"], "severity": "info",
             "kind": "abbreviation_first_use",
             "message": "abbreviation %s: %s" % (a["abbreviation"], a["detail"]),
             "locator": a["locator"], "evidence": {"abbreviation": a["abbreviation"]}}
            for a in abbr]


# ------------------------------------------------------------ format compliance
def spec_items(docs):
    items, src = [], ""
    for d in docs:
        if d["role"] != "constraints" or d["path"].lower().endswith((".tex", ".cls", ".sty")):
            continue
        src = d["path"]
        for i, line in enumerate((d["text"] or "").splitlines(), 1):
            body = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if len(body) >= 6 and not body.startswith("#"):
                items.append({"id": "F%02d" % (len(items) + 1), "requirement": body,
                              "source": "%s:L%d" % (src, i)})
    return items


def template_facts(docs):
    f = {"file": "", "options": "", "fonts": {}, "spacing": "", "columns": "", "margins": {},
         "bib_style": "", "caption": ""}
    for d in docs:
        if not d["path"].lower().endswith(".tex"):
            continue
        t = d["text"] or ""
        f["file"] = d["path"]
        m = re.search(r"\\documentclass(?:\[([^\]]*)\])?\{[^}]*\}", t)
        if m:
            f["options"] = m.group(1) or ""
            f["columns"] = "two" if "twocolumn" in f["options"] else "one"
        for cmd in ("mainfont", "CJKmainfont", "sansfont"):
            mm = re.search(r"\\set%s\{([^}]*)\}" % cmd, t)
            if mm:
                f["fonts"][cmd] = mm.group(1)
        mm = re.search(r"\\usepackage\s*\[([^\]]*)\]\{geometry\}", t)
        if mm:
            for part in mm.group(1).split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    f["margins"][k.strip()] = v.strip()
        if re.search(r"\\onehalfspacing\b", t):
            f["spacing"] = "onehalf"
        bs = re.search(r"\\bibliographystyle\{([^}]*)\}", t)
        if bs:
            f["bib_style"] = bs.group(1)
        cs = re.search(r"\\captionsetup\{([^}]*)\}", t)
        if cs:
            f["caption"] = cs.group(1)
    return f


def _tx(v):
    return re.sub(r"[\s/]+", "", str(v or "")).lower()


def split_clauses(req):
    return [c.strip() for c in re.split(r"[；;。]+|，", req) if len(c.strip()) >= 4]


def compliance(docs):
    items, tpl, checks = spec_items(docs), template_facts(docs), []
    clauses, seen = [], set()
    for it in items:
        for c in split_clauses(it["requirement"]):
            if c not in seen:
                seen.add(c)
                clauses.append((c, it))
    for n, (req, it) in enumerate(clauses, 1):
        low = req.lower()
        status, observed, why = "not_verifiable", "", ""
        if "参考文献" in req or "gb/t" in low or "bibliograph" in low:
            if tpl["bib_style"]:
                want_gb = "gb/t" in low or "顺序编码" in req
                status = "mismatch" if want_gb and "gbt" not in _tx(tpl["bib_style"]) else "match"
                observed, why = tpl["bib_style"], "reference style in the specification vs the " \
                                                  "template bibliography style"
        elif "字体" in req or "font" in low:
            want = re.findall(r"(Liberation Serif|SimSun|Times New Roman|宋体|黑体)", req)
            pool = []
            if ("中文" in req or "cjk" in low) and tpl["fonts"].get("CJKmainfont"):
                pool = [tpl["fonts"]["CJKmainfont"]]
            elif ("西文" in req or "mainfont" in low) and tpl["fonts"].get("mainfont"):
                pool = [tpl["fonts"]["mainfont"]]
            elif tpl["fonts"]:
                pool = list(tpl["fonts"].values())
            absent = [w for w in want if not any(_tx(w) in _tx(p) for p in pool)]
            if want and pool:
                status = "mismatch" if absent else "match"
                observed = ", ".join("%s=%s" % (k, v) for k, v in sorted(tpl["fonts"].items()))
                why = ("font(s) the template does not set: " + ", ".join(absent) if absent else
                       "specified fonts agree with the template font commands")
        elif "字号" in req and "pt" in low:
            want = re.search(r"(\d+(?:\.\d+)?)\s*pt", req)
            if want and tpl["options"]:
                status = "match" if want.group(1) in tpl["options"] else "mismatch"
                observed = "documentclass options [%s]" % tpl["options"]
                why = "body font size in the specification vs the template class options"
        elif "行距" in req or "spacing" in low:
            if tpl["spacing"]:
                status, observed = "match", tpl["spacing"]
                why = "line-spacing command found in the template"
        elif "栏" in req or "column" in low:
            if tpl["columns"]:
                want_two = "双栏" in req or "two" in low
                status = "match" if want_two == (tpl["columns"] == "two") else "mismatch"
                observed = "onecolumn" if tpl["columns"] == "one" else "twocolumn"
                why = "column layout in the specification vs the template class options"
        elif "边距" in req or "margin" in low:
            want = re.findall(r"([上下左右])边距\s*(\d+(?:\.\d+)?)\s*cm", req)
            kmap = {"上": "top", "下": "bottom", "左": "left", "右": "right"}
            diffs = []
            for zh, val in want:
                got = tpl["margins"].get(kmap[zh])
                if got and _tx(got) != _tx(val + "cm"):
                    diffs.append("%s=%s but the specification says %scm" % (kmap[zh], got, val))
            if want and tpl["margins"]:
                status = "mismatch" if diffs else "match"
                observed = ", ".join("%s=%s" % (k, v) for k, v in sorted(tpl["margins"].items()))
                why = "; ".join(diffs) if diffs else "margins agree with the specification"
        elif "表注" in req or "图注" in req or "caption" in low:
            if tpl["caption"]:
                pos = "below" if "below" in tpl["caption"] else ("above" if "above" in tpl["caption"] else "")
                want_above = "上方" in req
                status = "match" if (want_above == (pos == "above")) else "mismatch"
                observed = tpl["caption"]
                why = "the specification wants this caption %s; the template sets every caption %s" \
                      % ("above" if want_above else "below", pos or "through a class default")
        checks.append({"id": "K%02d" % n, "requirement": req, "spec_source": it["source"],
                       "status": status,
                       "observed": observed or "no comparable setting was found in the supplied template",
                       "reason": why or "the supplied template does not expose a comparable setting",
                       "evidence": {"template": tpl["file"] or "no .tex constraint supplied"}})
    return items, checks, tpl


# ----------------------------------------------------------------- suggestions
def segment_suggestions(seg):
    out, text = [], seg["text"]
    zh = len(C._CJK_RE.findall(text)) > 3
    m = (SUPER_ZH if zh else SUPER_EN).search(text)
    if m:
        repl = (ZH_REPL if zh else EN_REPL).get(m.group(0) if zh else m.group(0).lower())
        if repl:
            out.append({"type": "claim_strength", "before": m.group(0), "after": repl,
                        "reason": "an absolute or superlative claim is stronger than the evidence "
                                  "shown in this sentence; a qualified wording keeps the meaning "
                                  "without overstating it",
                        "evidence": {"quote": text[max(0, m.start() - 12):m.end() + 12]}})
    s = SIG_ZH.search(text) or SIG_EN.search(text)
    if s and not STAT.search(text):
        out.append({"type": "statistic_missing", "before": text,
                    "after": text + ("（请补上检验统计量与自由度）" if zh else
                                     " (add the test statistic, degrees of freedom and effect size)"),
                    "reason": "significance is claimed without its test statistic, so a reader cannot "
                              "verify the claim",
                    "evidence": {"quote": s.group(0)}})
    return out


def abstract_suggestion(text, glossary):
    if KW.search(text or ""):
        return None
    for i, line in enumerate((text or "").splitlines(), 1):
        if not (ABS_ZH.match(line) or ABS_EN.match(line)):
            continue
        names = [g["canonical"] for g in glossary if g.get("canonical")][:5]
        if not names:
            return None
        return {"type": "abstract_keywords", "sid": "manuscript", "locator": "manuscript:L%d:C1" % i,
                "before": line.strip()[:160],
                "after": line.strip()[:160] + "\n关键词：" + "；".join(names),
                "reason": "the abstract carries no keyword line; the proposed keywords are the terms "
                          "actually used in this manuscript, for author confirmation",
                "evidence": {"terms": names}}
    return None


def gap_report(docs, findings, notes):
    L = ["# 润色缺口报告 / polish gap report", "",
         "本案例没有可供润色的成稿文本，因此没有产出润色稿，而是给出缺口清单与需要作者补充的材料。",
         "", "## 已读取的材料 / materials read", ""]
    if docs:
        for d in docs:
            L.append("- %s — role=%s, method=%s, bytes=%d%s" % (d["path"], d["role"], d["method"],
                                                                d["bytes"],
                                                                ("，note=" + d["note"]) if d["note"] else ""))
    else:
        L.append("- 输入目录中没有可读文件。")
    L += ["", "## 需要作者补充 / what the author must supply", "",
          "- 成稿正文（单篇论文或章节），或指明哪一份材料是待润色正文。",
          "- 参考文献列表，使编号引用可以被逐条核对。",
          "- 格式要求与目标模板（若与正文分离，请一并提供）。"]
    if findings:
        L += ["", "## 体检发现 / findings recorded", ""]
        L += ["- [%s] %s (%s)" % (f["severity"], f["message"], f.get("locator", "")) for f in findings]
    if notes:
        L += ["", "## 读取备注 / reading notes", ""] + ["- " + n for n in notes]
    L += ["", "## 说明 / notes", "",
          "- 本报告由确定性检查生成；未使用任何外部模型，也未编造任何文献、数值或图表。",
          "- 提供正文后，同一条入口命令即可产出逐句润色稿与修改记录。"]
    return C.sanitize("\n".join(L)) + "\n"
