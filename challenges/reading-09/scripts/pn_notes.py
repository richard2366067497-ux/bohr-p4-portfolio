#!/usr/bin/env python3
"""pn_notes.py — note, card, answer, metric and rendering helpers for reading-09.

Split out of paper_notes.py so every module stays small; imported only by the
entry script. Standard library only, no network.
"""
import csv
import re
from pathlib import Path

import pn_sections as pn  # noqa: E402

CARD_KEYS = ("research_question", "data", "methods", "key_findings",
             "conditions", "limitations", "conclusion")
ROLE_ZH = {"abstract": "摘要", "introduction": "引言", "related_work": "相关工作",
           "methods": "方法", "results": "结果", "discussion": "讨论",
           "conclusion": "结论", "limitations": "局限", "other": "正文",
           "appendix": "附录"}


def norm(text):
    return pn.norm(text)


def clip(text, limit=240):
    text = norm(text)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "\u2026"


def make_anchor_store(doc_id):
    """Anchor registry: one entry per distinct (page, quote); ids A01, A02, …"""
    entries, index, counts = [], {}, {}

    def anchor_for(section, sentence):
        key = (sentence["page"], norm(sentence["quote"]).lower())
        if key in index:
            return index[key]
        title = section.get("title", "")
        if counts.get(title, 0) >= 8:
            return None
        counts[title] = counts.get(title, 0) + 1
        aid = "A%02d" % (len(entries) + 1)
        index[key] = aid
        entries.append({"anchor_id": aid, "doc_id": doc_id, "kind": "text",
                        "page": sentence["page"], "section": title,
                        "para": sentence.get("para"), "quote": norm(sentence["quote"])[:240],
                        "claim": ROLE_ZH.get(section.get("role"), "正文")})
        return aid

    def page_of(aid):
        for entry in entries:
            if entry["anchor_id"] == aid:
                return entry["page"]
        return 1

    return anchor_for, entries, page_of


def build_notes(sections, doc_id, anchor_for):
    notes, anchor_pages = [], {}
    prev_title = None
    for section in sections:
        if section["role"] in pn.SKIP_ROLES or not section["sentences"]:
            continue
        sid = "S%02d" % (len(notes) + 1)
        anchors = []
        for sentence in pn.choose_anchors(section, 3):
            aid = anchor_for(section, sentence)
            if aid and aid not in anchors:
                anchors.append(aid)
                anchor_pages[aid] = sentence["page"]
        purpose = pn.field_sentence(section, pn.METHOD_CUES + pn.CONCL_CUES)
        methods = pn.field_sentence(section, pn.METHOD_CUES)
        results = pn.field_sentence(section, pn.RESULT_CUES)
        conclusions = pn.field_sentence(section, pn.CONCL_CUES)
        if not purpose:
            purpose = section["sentences"][0]["quote"]
        role_zh = ROLE_ZH.get(section["role"], "正文")
        note = {
            "doc_id": doc_id, "section_id": sid, "title": section["title"],
            "role": section["role"], "page_start": section["page_start"],
            "page_end": section["page_end"],
            "purpose": "本节（%s）属于%s部分，内容以“%s”为线索。" % (
                section["title"], role_zh, clip(purpose, 120)),
            "methods": ("方法要点：" + clip(methods, 200)) if methods else "",
            "results": ("结果：" + clip(results, 200)) if results else "",
            "conclusions": ("作者据此认为：" + clip(conclusions, 200)) if conclusions else "",
            "anchors": anchors,
        }
        if prev_title is None:
            note["link_from_previous"] = "本节为正文首节（%s），没有前序章节。" % section["title"]
        else:
            how = purpose if section["role"] != "abstract" else section["sentences"][0]["quote"]
            note["link_from_previous"] = "承接「%s」：%s" % (prev_title, clip(how, 120))
        page = anchor_pages.get(anchors[0]) if anchors else section["page_start"]
        note["citation"] = "p.%d" % page
        notes.append(note)
        prev_title = section["title"]
    return notes, anchor_pages


def gather_text(sections, cues, limit=3):
    picked = []
    for section in sections:
        if section["role"] in pn.SKIP_ROLES:
            continue
        for sentence in pn.pick_sentences(section, cues, limit):
            quote = sentence["quote"]
            if quote not in picked:
                picked.append(quote)
            if len(picked) >= limit:
                return picked
    return picked


def metric_items(sections):
    """Stated conditions: hyper-parameters, splits, metrics (each item is quoted)."""
    items = []
    pattern = re.compile(
        r"((?:momentum|learning rate|batch size|weight decay|dropout|epochs?|"
        r"window size|temperature)\s*(?:=|of|was|is|:)?\s*[0-9.]+(?:\s*epochs?)?"
        r"|\d+\s*epochs?|(?:on|under)\s+(?:the\s+)?[A-Za-z0-9\- ]{2,30}?"
        r"(?:split|set|dataset|corpus|benchmark|participants?)"
        r"|held-out\s+(?:split|set)|[A-Za-z0-9\- ]{2,24}(?:accuracy|f1|precision|recall|bleu))",
        re.I)
    for section in sections:
        if section["role"] in pn.SKIP_ROLES:
            continue
        for sentence in section["sentences"]:
            for m in pattern.finditer(sentence["quote"]):
                item = norm(m.group(1))
                if len(item) >= 3 and item.lower() not in {i.lower() for i in items}:
                    items.append(item)
    return items[:6]


def build_card(sections, anchor_for):
    card, missing = {}, []

    def field(cues, fallback=""):
        for section in sections:
            if section["role"] in pn.SKIP_ROLES:
                continue
            picked = pn.pick_sentences(section, cues, 2)
            if picked:
                aid = anchor_for(section, picked[0])
                return {"text": "；".join(clip(s["quote"], 180) for s in picked), "anchors": [aid] if aid else []}
        return {"text": fallback, "anchors": []}

    card["research_question"] = field(("research question", "we study", "we investigate",
                                       "this paper", "we address", "aim", "we propose"),
                                      "所给材料未陈述显式研究问题；笔记只记录其实际报告的内容。")
    if not card["research_question"]["text"].startswith("所给"):
        pass
    else:
        missing.append({"item": "research_question", "why_expected": "论文通常会在摘要或引言交代研究问题"})
    card["data"] = field(pn.DATA_CUES, "所给材料未陈述数据来源或规模。")
    if card["data"]["text"].startswith("所给"):
        missing.append({"item": "data", "why_expected": "实证论文应说明数据来源与划分"})
    card["methods"] = field(pn.METHOD_CUES, "所给材料未陈述方法细节。")
    card["key_findings"] = field(pn.RESULT_CUES, "所给材料未报告带数值的结果。")
    conditions = metric_items(sections)
    card["conditions"] = {"text": "；".join(conditions) if conditions else "所给材料未陈述成立条件。",
                          "anchors": card["methods"]["anchors"][:1]}
    limit_sents = gather_text(sections, pn.LIMIT_CUES, 2)
    if limit_sents:
        card["limitations"] = {"text": "；".join(clip(s, 160) for s in limit_sents),
                               "anchors": card["key_findings"]["anchors"][:1]}
    else:
        card["limitations"] = {
            "text": "所给材料未见显式局限；未报告：重复次数与方差、基线对照、数据来源。",
            "anchors": card["key_findings"]["anchors"][:1]}
        missing += [{"item": "limitations", "why_expected": "读者需要知道结论在何种范围内成立"},
                    {"item": "repeat_runs", "why_expected": "单次数值无法判断稳定性"},
                    {"item": "baseline", "why_expected": "缺少对照则无法判断增益"}]
    concl = gather_text(sections, pn.CONCL_CUES, 1)
    if not concl:
        results = [s for sec in sections if sec["role"] == "results" for s in sec["sentences"]]
        concl = [results[-1]["quote"]] if results else []
    card["conclusion"] = {"text": ("作者结论：" + clip(concl[0], 200)) if concl else "所给材料未给出结论。",
                          "anchors": card["key_findings"]["anchors"][:1]}
    return card, missing


def build_answers(questions, sections, card, kps, anchor_for, notes, page_of):
    answers = []
    all_sentences = [(sec, s) for sec in sections if sec["role"] not in pn.SKIP_ROLES
                     for s in sec.get("sentences", [])]
    for idx, question in enumerate(questions, 1):
        low = question.lower()
        answer, used, atype, conf = "", [], "extractive", "medium"
        if any(k in question for k in ("章节", "section", "结构", "目的", "方法", "结果", "结论")):
            parts = []
            for note in notes:
                if note["results"]:
                    parts.append("%s（%s）：%s" % (note["title"], ROLE_ZH.get(note["role"], "正文"),
                                                  note["results"].replace("结果：", "")))
                else:
                    parts.append("%s（%s）" % (note["title"], ROLE_ZH.get(note["role"], "正文")))
            answer = "论文共 %d 个章节。%s" % (len(notes), "；".join(parts))
            for note in notes:
                used += note["anchors"][:1]
            atype, conf = "inferential", "high"
        elif any(k in question for k in ("卡片", "字段", "card")):
            answer = "研究问题：%s 数据：%s 方法：%s 主要发现：%s 条件：%s 局限：%s 结论：%s" % tuple(
                norm(card[k]["text"]) for k in CARD_KEYS)
            for k in CARD_KEYS:
                used += card[k]["anchors"][:1]
            atype, conf = "inferential", "high"
        elif any(k in question for k in ("知识", "术语", "概念", "knowledge", "term")):
            answer = "共 %d 个知识点：%s。每个条目给出规范术语、定义、同义词与页码锚点，可按术语或同义词检索。" % (
                len(kps), "、".join(k["term"] for k in kps[:12]) or "（材料中未识别到术语）")
            for kp in kps[:4]:
                used += kp["anchors"][:1]
            atype, conf = "inferential", "high"
        elif any(k in low for k in ("contribution", "贡献", "novelty", "创新")):
            cand = gather_text(sections, ("we propose", "we present", "we introduce",
                                          "outperform", "contribution"), 2)
            answer = " ".join(clip(c, 220) for c in cand) or "The supplied material does not state a contribution."
            conf = "medium" if cand else "low"
            if not cand:
                atype = "unanswerable"
        else:
            q_tokens = pn.tokens(question)
            ranked = sorted(all_sentences, key=lambda pair: -(len(q_tokens & pn.tokens(pair[1]["quote"]))
                                                              + len(pn.numbers(pair[1]["quote"]))))
            picked = [pair for pair in ranked
                      if len(q_tokens & pn.tokens(pair[1]["quote"])) > 0][:2]
            if picked:
                answer = " ".join(clip(pair[1]["quote"], 220) for pair in picked)
                for sec, sent in picked:
                    aid = anchor_for(sec, sent)
                    if aid:
                        used.append(aid)
                conf = "medium"
            else:
                answer = ("The supplied material does not answer this question directly; "
                          "the notes record only anchored statements, so this stays unresolved.")
                atype, conf = "unanswerable", "low"
        if len(norm(answer)) < 60 and len(re.findall(r"[一-鿿]", answer)) < 20:
            answer += "（依据：%s）" % ("；".join(norm(card[k]["text"])[:80] for k in
                                                ("methods", "key_findings")))
        used = list(dict.fromkeys(a for a in used if a))
        citation = "p.%d" % page_of(used[0]) if used else ""
        answers.append({"question_id": "Q%d" % idx, "question": question, "answer": norm(answer),
                        "answer_type": atype, "confidence": conf, "anchors": used[:8],
                        "citation": citation})
    return answers


def code_metrics(paths):
    out = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        metrics = {}
        for m in re.finditer(r"[\"']([A-Za-z][A-Za-z0-9_]*)[\"']\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)", text):
            metrics[m.group(1).lower()] = float(m.group(2))
        for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*(-?[0-9]+\.[0-9]+)\b", text):
            metrics.setdefault(m.group(1).lower(), float(m.group(2)))
        if metrics:
            out.append({"file": path.name, "metrics": metrics})
    return out


def paper_metrics(text):
    result = {}
    for m in re.finditer(r"([A-Za-z][A-Za-z0-9\- ]{1,30}?)\s*(?:was|is|of|=|:)?\s*[0-9]+(?:\.[0-9]+)?\s*%", text):
        label = norm(m.group(1)).lower()
        if "acc" in label:
            result["top1_accuracy"] = round(float(re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", m.group(0)).group(1)) / 100.0, 5)
    for m in re.finditer(r"(macro[\s\-]?f1|f1|bleu|precision|recall)\s*(?:was|is|of|=|:)?\s*([0-9]*\.[0-9]+)", text, re.I):
        key = norm(m.group(1)).lower().replace("-", "_").replace(" ", "_")
        result[key] = float(m.group(2))
    return result


# --------------------------------------------------------------------------
# markdown / csv output
# --------------------------------------------------------------------------
def render_notes(result):
    lines = ["# Structured notes — %s" % (result.get("case_id") or "unknown"),
             "", "status: **%s**" % result.get("status", "partial"), ""]
    card = result.get("paper_card") or {}
    lines.append("## Paper card")
    for key in CARD_KEYS:
        value = card.get(key) or {}
        refs = " ".join("[%s]" % a for a in value.get("anchors") or [])
        lines.append("- **%s**: %s %s" % (key, norm(value.get("text")), refs))
    lines += ["", "## Answers"]
    for answer in result.get("answers") or []:
        refs = " ".join("[%s]" % a for a in answer.get("anchors") or [])
        lines += ["", "### %s — %s" % (answer.get("question_id"), answer.get("question")),
                  norm(answer.get("answer")) + " " + refs]
    lines += ["", "## Section notes (paper order)"]
    for note in result.get("section_notes") or []:
        lines += ["", "### %s %s — p.%s-%s (%s)" % (note.get("section_id"), note.get("title"),
                                                    note.get("page_start"), note.get("page_end"),
                                                    note.get("role"))]
        for key in ("purpose", "methods", "results", "conclusions", "link_from_previous"):
            if note.get(key):
                lines.append("- **%s**: %s" % (key, norm(note[key])))
        lines.append("- anchors: " + " ".join("[%s]" % a for a in note.get("anchors") or []))
    lines += ["", "## Knowledge points"]
    for kp in result.get("knowledge_points") or []:
        lines.append("- %s %s — %s (synonyms: %s) %s" % (
            kp.get("kp_id"), kp.get("term"), norm(kp.get("definition")),
            ", ".join(kp.get("synonyms") or []) or "—",
            " ".join("[%s]" % a for a in kp.get("anchors") or [])))
    lines += ["", "## Gaps and uncertainties"]
    for item in result.get("uncertainties") or []:
        lines.append("- uncertainty: %s — %s" % (norm(item.get("item")), norm(item.get("why"))))
    for item in result.get("not_reported") or []:
        lines.append("- not reported: %s" % norm(item.get("item")))
    return "\n".join(lines) + "\n"


def write_anchors_csv(path, result, doc_pages):
    rows = []
    by_id = {e["anchor_id"]: e for e in result.get("evidence") or []}
    for aid in sorted(by_id):
        entry = by_id[aid]
        pages = doc_pages.get(entry.get("doc_id")) or []
        quote = entry.get("quote") or ""
        verified = bool(pages) and 0 < entry.get("page", 0) <= len(pages) and quote in pages[entry["page"] - 1]
        rows.append([aid, entry.get("doc_id"), entry.get("kind", "text"), entry.get("page"),
                     entry.get("para"), entry.get("section"), verified,
                     "ok" if verified else "quote_not_found", quote])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["anchor_id", "doc_id", "kind", "page", "para", "section",
                         "verified", "verdict", "quote_or_label"])
        writer.writerows(rows)
