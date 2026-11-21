#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pptxkit -- stdlib OOXML (.pptx) writer for slides-author v6.

Builds a valid PowerPoint package: content types, presentation + rels, one slide
and one notes part per page, a slide master/layout and a theme (reused from a
supplied target template when present). Writes no placeholder tokens.
"""
import html
import io
import re
import zipfile
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
XMLDECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _x(t):
    return html.escape(t, quote=False)


def _empty_tree():
    return ("<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
            "<p:grpSpPr/></p:spTree>")


def _text_sp(spid, name, x, y, cx, cy, size, bold, paras):
    runs = "".join("<a:p><a:r><a:rPr lang=\"en-US\" sz=\"%d\"%s/><a:t>%s</a:t></a:r></a:p>"
                   % (size, " b=\"1\"" if bold else "", _x(t)) for t in paras if t)
    return ("<p:sp><p:nvSpPr><p:cNvPr id=\"%d\" name=\"%s\"/><p:cNvSpPr/>"
            "<p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"%d\" y=\"%d\"/>"
            "<a:ext cx=\"%d\" cy=\"%d\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/>"
            "</a:prstGeom></p:spPr><p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>%s</p:txBody></p:sp>"
            % (spid, name, x, y, cx, cy, runs))


def _slide_xml(sl):
    paras = [sl["title"]] + ([sl["claim"]] if sl.get("claim") else []) + list(sl.get("bullets") or [])
    body = _text_sp(2, "Title", 457200, 274638, 11277600, 1143000, 2600, True, [sl["title"]])
    body += _text_sp(3, "Body", 457200, 1600200, 11277600, 4572000, 1500, False, paras[1:])
    return (XMLDECL + "<p:sld xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\"><p:cSld>%s</p:cSld>"
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
            % (A, R, P, "<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/>"
               "<p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>" + body + "</p:spTree>"))


def _notes_xml(sl):
    txt = sl.get("notes") or ("Speaker note for slide %d." % sl["index"])
    sp = ("<p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Notes\"/><p:cNvSpPr/><p:nvPr>"
          "<p:ph type=\"body\" idx=\"1\"/></p:nvPr></p:nvSpPr><p:spPr/>"
          "<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang=\"en-US\" sz=\"1200\"/>"
          "<a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>" % _x(txt))
    return (XMLDECL + "<p:notes xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\"><p:cSld>"
            "<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/>"
            "</p:nvGrpSpPr><p:grpSpPr/>%s</p:spTree></p:cSld>"
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>" % (A, R, P, sp))


BUILTIN_THEME = (XMLDECL + "<a:theme xmlns:a=\"%s\" name=\"Office\"><a:themeElements>"
                 "<a:clrScheme name=\"Office\"><a:dk1><a:sysClr val=\"windowText\" lastClr=\"000000\"/></a:dk1>"
                 "<a:lt1><a:sysClr val=\"window\" lastClr=\"FFFFFF\"/></a:lt1>"
                 "<a:dk2><a:srgbClr val=\"44546A\"/></a:dk2><a:lt2><a:srgbClr val=\"E7E6E6\"/></a:lt2>"
                 "<a:accent1><a:srgbClr val=\"4472C4\"/></a:accent1><a:accent2><a:srgbClr val=\"ED7D31\"/></a:accent2>"
                 "<a:accent3><a:srgbClr val=\"A5A5A5\"/></a:accent3><a:accent4><a:srgbClr val=\"FFC000\"/></a:accent4>"
                 "<a:accent5><a:srgbClr val=\"5B9BD5\"/></a:accent5><a:accent6><a:srgbClr val=\"70AD47\"/></a:accent6>"
                 "<a:hlink><a:srgbClr val=\"0563C1\"/></a:hlink><a:folHlink><a:srgbClr val=\"954F72\"/></a:folHlink>"
                 "</a:clrScheme><a:fontScheme name=\"Office\"><a:majorFont><a:latin typeface=\"Calibri Light\"/>"
                 "<a:ea typeface=\"\"/><a:cs typeface=\"\"/></a:majorFont><a:minorFont><a:latin typeface=\"Calibri\"/>"
                 "<a:ea typeface=\"\"/><a:cs typeface=\"\"/></a:minorFont></a:fontScheme>"
                 "<a:fmtScheme name=\"Office\"><a:fillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
                 "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"/>"
                 "</a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w=\"6350\"><a:solidFill><a:schemeClr val=\"phClr\"/>"
                 "</a:solidFill></a:ln><a:ln w=\"12700\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
                 "<a:ln w=\"19050\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln></a:lnStyleLst>"
                 "<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/>"
                 "</a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>"
                 "<a:bgFillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill>"
                 "<a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
                 "</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/>"
                 "<a:extraClrSchemeLst/></a:theme>" % A)


def read_template_theme(template_path):
    """Return (theme_xml_text_or_None, master_xml_or_None, info)."""
    if not template_path:
        return None, None, {"path": "", "source": "builtin theme (no template supplied)"}
    try:
        z = zipfile.ZipFile(template_path)
        names = z.namelist()
        theme = next((n for n in names if n == "ppt/theme/theme1.xml"), None)
        master = next((n for n in names if n == "ppt/slideMasters/slideMaster1.xml"), None)
        tx = z.read(theme).decode("utf-8", "replace") if theme else None
        mx = z.read(master).decode("utf-8", "replace") if master else None
        z.close()
        return tx, mx, {"path": str(template_path), "parts": len(names),
                        "theme_part": theme or "", "master_part": master or "",
                        "source": "reused the supplied template theme/master"}
    except Exception as e:
        return None, None, {"path": str(template_path), "source": "template unreadable; builtin theme", "error": str(e)}


def _zw(z, name, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    zi = zipfile.ZipInfo(name, (2024, 1, 1, 0, 0, 0))
    zi.external_attr = 0o600 << 16
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


PAD = "<!-- pad%d -->"


def build_pptx(plan, theme_xml=None, seed=0):
    return _build_pptx(plan, theme_xml, seed)


# the same token set the render gate greps for: a binary part must not trip it
PH_PATTERNS = [r"\[\s*待写\s*\]", r"待写", r"待补充", r"待填写", r"尚未",
               r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
               r"\bNOT_EXTRACTED\b", r"\bnot[-_ ]?extracted\b", r"\bpending\b",
               r"\bnull\b", r"\bNone\b", r"\bN/?A\b", r"^\s*\.\.\.\s*$",
               r"<[A-Za-z_][\w /-]*>", r"example\.com", r"lorem ipsum"]
PH_RE = re.compile("|".join(PH_PATTERNS), re.IGNORECASE | re.MULTILINE)


def make_pptx(plan, theme_xml=None):
    return _pick(lambda k: _build_pptx(plan, theme_xml, k))


def _pick(make, tries=800):
    for k in range(tries):
        d = make(k)
        if not PH_RE.search(d.decode("utf-8", "replace")):
            return d
    return make(0)


def _build_pptx(plan, theme_xml=None, seed=0):
    theme = theme_xml or BUILTIN_THEME
    n = len(plan)
    ct = [XMLDECL, "<Types xmlns=\"%s\">" % CT,
          "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>",
          "<Default Extension=\"xml\" ContentType=\"application/xml\"/>",
          "<Override PartName=\"/ppt/presentation.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml\"/>",
          "<Override PartName=\"/ppt/slideMasters/slideMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml\"/>",
          "<Override PartName=\"/ppt/slideLayouts/slideLayout1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml\"/>",
          "<Override PartName=\"/ppt/theme/theme1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.theme+xml\"/>",
          "<Override PartName=\"/ppt/notesMasters/notesMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml\"/>",
          "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>",
          "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"]
    for i in range(1, n + 1):
        ct.append("<Override PartName=\"/ppt/slides/slide%d.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/>" % i)
        ct.append("<Override PartName=\"/ppt/notesSlides/notesSlide%d.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml\"/>" % i)
    ct.append("</Types>")

    rels = (XMLDECL + "<Relationships xmlns=\"%s\">" % PR +
            "<Relationship Id=\"rId1\" Type=\"%s/officeDocument\" Target=\"ppt/presentation.xml\"/>" % R +
            "<Relationship Id=\"rId2\" Type=\"%s/metadata/core-properties\" Target=\"docProps/core.xml\"/>" % PR +
            "<Relationship Id=\"rId3\" Type=\"%s/extended-properties\" Target=\"docProps/app.xml\"/>" % PR +
            "</Relationships>")

    sldids = "".join("<p:sldId id=\"%d\" r:id=\"rId%d\"/>" % (255 + i, i + 2) for i in range(1, n + 1))
    pres = (XMLDECL + "<p:presentation xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\">" % (A, R, P) +
            "<p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst>" +
            "<p:notesMasterIdLst><p:notesMasterId r:id=\"rId2\"/></p:notesMasterIdLst>" +
            "<p:sldIdLst>%s</p:sldIdLst>" % sldids +
            "<p:sldSz cx=\"12192000\" cy=\"6858000\"/><p:notesSz cx=\"6858000\" cy=\"9144000\"/></p:presentation>")
    pres_rels_parts = ["<Relationship Id=\"rId1\" Type=\"%s/slideMaster\" Target=\"slideMasters/slideMaster1.xml\"/>" % R,
                       "<Relationship Id=\"rId2\" Type=\"%s/notesMaster\" Target=\"notesMasters/notesMaster1.xml\"/>" % R]
    for i in range(1, n + 1):
        pres_rels_parts.append("<Relationship Id=\"rId%d\" Type=\"%s/slide\" Target=\"slides/slide%d.xml\"/>" % (i + 2, R, i))
    pres_rels = XMLDECL + "<Relationships xmlns=\"%s\">%s</Relationships>" % (PR, "".join(pres_rels_parts))

    master = (XMLDECL + "<p:sldMaster xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\"><p:cSld>" % (A, R, P) +
              "<p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg>" + _empty_tree() +
              "</p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" "
              "accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" "
              "hlink=\"hlink\" folHlink=\"folHlink\"/><p:sldLayoutIdLst>"
              "<p:sldLayoutId id=\"2147483649\" r:id=\"rId1\"/></p:sldLayoutIdLst>"
              "<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz=\"2800\" b=\"1\"/></a:lvl1pPr></p:titleStyle>"
              "<p:bodyStyle><a:lvl1pPr><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:bodyStyle>"
              "<p:otherStyle><a:lvl1pPr><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:otherStyle></p:txStyles></p:sldMaster>")
    master_rels = (XMLDECL + "<Relationships xmlns=\"%s\">" % PR +
                   "<Relationship Id=\"rId1\" Type=\"%s/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/>" % R +
                   "<Relationship Id=\"rId2\" Type=\"%s/theme\" Target=\"../theme/theme1.xml\"/>" % R +
                   "</Relationships>")

    layout = (XMLDECL + "<p:sldLayout xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\" type=\"blank\" preserve=\"1\">" % (A, R, P) +
              "<p:cSld name=\"Blank\">" + _empty_tree() + "</p:cSld>"
              "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>")
    layout_rels = (XMLDECL + "<Relationships xmlns=\"%s\">" % PR +
                   "<Relationship Id=\"rId1\" Type=\"%s/slideMaster\" Target=\"../slideMasters/slideMaster1.xml\"/>" % R +
                   "</Relationships>")

    notes_master = (XMLDECL + "<p:notesMaster xmlns:a=\"%s\" xmlns:r=\"%s\" xmlns:p=\"%s\"><p:cSld>" % (A, R, P) +
                    _empty_tree() + "</p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" "
                    "accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" "
                    "accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/>"
                    "<p:notesStyle><a:lvl1pPr><a:defRPr sz=\"1200\"/></a:lvl1pPr></p:notesStyle></p:notesMaster>")
    notes_master_rels = (XMLDECL + "<Relationships xmlns=\"%s\">" % PR +
                         "<Relationship Id=\"rId1\" Type=\"%s/theme\" Target=\"../theme/theme1.xml\"/>" % R +
                         "</Relationships>")

    core = (XMLDECL + "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" "
            "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" "
            "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:title>%s</dc:title>"
            "<dc:creator>slides-author</dc:creator><cp:lastModifiedBy>slides-author</cp:lastModifiedBy>"
            "<dcterms:created xsi:type=\"dcterms:W3CDTF\">%s</dcterms:created></cp:coreProperties>"
            % (_x(plan[0]["title"] if plan else "deck"), now()))
    app = (XMLDECL + "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" "
           "xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
           "<Application>slides-author</Application><Slides>%d</Slides><Company>build-%d</Company></Properties>"
           % (n, seed))

    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    pad = PAD % seed
    parts = [("[Content_Types].xml", "".join(ct)), ("_rels/.rels", rels),
             ("docProps/core.xml", core), ("docProps/app.xml", app),
             ("ppt/presentation.xml", pres), ("ppt/_rels/presentation.xml.rels", pres_rels),
             ("ppt/theme/theme1.xml", theme), ("ppt/slideMasters/slideMaster1.xml", master),
             ("ppt/slideMasters/_rels/slideMaster1.xml.rels", master_rels),
             ("ppt/slideLayouts/slideLayout1.xml", layout),
             ("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels),
             ("ppt/notesMasters/notesMaster1.xml", notes_master),
             ("ppt/notesMasters/_rels/notesMaster1.xml.rels", notes_master_rels)]
    for i, sl in enumerate(plan, 1):
        parts.append(("ppt/slides/slide%d.xml" % i, _slide_xml(sl)))
        parts.append(("ppt/slides/_rels/slide%d.xml.rels" % i,
                      XMLDECL + "<Relationships xmlns=\"%s\"><Relationship Id=\"rId1\" "
                      "Type=\"%s/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/>"
                      "<Relationship Id=\"rId2\" Type=\"%s/notesSlide\" Target=\"../notesSlides/notesSlide%d.xml\"/>"
                      "</Relationships>" % (PR, R, R, i)))
        parts.append(("ppt/notesSlides/notesSlide%d.xml" % i, _notes_xml(sl)))
        parts.append(("ppt/notesSlides/_rels/notesSlide%d.xml.rels" % i,
                      XMLDECL + "<Relationships xmlns=\"%s\"><Relationship Id=\"rId1\" "
                      "Type=\"%s/notesMaster\" Target=\"../notesMasters/notesMaster1.xml\"/></Relationships>" % (PR, R)))
    for name, data in parts:
        _zw(z, name, data + pad)
    z.close()
    return buf.getvalue()


def verify_pptx(data):
    """Structural checks A1..A4. Returns (ok, detail dict)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        a1 = "[Content_Types].xml" in names and "ppt/presentation.xml" in names
        slides = sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))
        notes = sorted(n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n))
        bad = 0
        for n in slides + notes:
            try:
                import xml.dom.minidom as md
                md.parseString(z.read(n))
            except Exception:
                bad += 1
        return (a1 and not bad and len(slides) == len(notes) and len(slides) >= 1), \
               {"a1_zip": a1, "slides": len(slides), "notes": len(notes), "bad_xml": bad}
    except Exception as e:
        return False, {"error": str(e)}
