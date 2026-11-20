#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py — 译后机械核验引擎（check / selfcheck 共用）。

只判定**可机械判定**的事实；凡需语义理解的（译文是否通顺、译名是否学术最优）不下结论，
只记 warn 并列入人审清单。检查项定义、严重度、判定口径见 references/checks_spec.md：

  sid_integrity / source_verbatim / coverage / element_coverage / glossary_quote /
  glossary_lock / glossary_drift / protected_numbers / citations / figure_table_refs /
  equation_tags / negation / hedge / placeholder_policy / target_language /
  repeated_target / contract_fields
"""
import re

VERSION = "1.0.0"
SKILL_NAME = "sci-lit-bilingual-audit"
PLACEHOLDER = "〔未译:%s〕"
ELEMENT_TYPES = ("caption_figure", "caption_table", "table_header", "table_row",
                 "formula", "reference", "heading")

NEG_EN = (r"\b(?:not|no|never|none|neither|nor|cannot|can't|without|absence|"
          r"lack(?:s|ed|ing)?|rare(?:ly)?|unable|unlikely|insignificant|fewer|below|"
          r"hardly|barely|scarcely)\b")
NEG_ZH = r"(?:不|未|无|没有|非|并非|无法|不能|不足|缺乏|罕|低于|少于|不具)"
HEDGE_EN = (r"\b(?:may|might|could|suggest(?:s|ed)?|likely|probably|possibly|possible|"
            r"appear(?:s|ed)?|approximately|about|roughly|tend(?:s|ed)?|associated with|"
            r"correlat(?:e|es|ed|ion)|potentially|presumably)\b")
HEDGE_ZH = r"(?:可能|也许|或许|似乎|大约|近似|倾向|提示|表明|相关|潜在|或可|推测)"

PH_RE = re.compile(r"〔(未译|待补|存疑):([^〕]*)〕")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
BRACKET_CITE = re.compile(r"\[\s*\d+(?:\s*[,–—-]\s*\d+)*\s*\]")
AUTHOR_CITE = re.compile(
    r"\([A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.|and\s+[A-Z][A-Za-z\-']+))?,?\s?(?:19|20)\d{2}[a-z]?\)")
FIGREF_EN = re.compile(r"(Fig(?:ure)?s?\.?|Tab(?:le)?s?\.?|Eq(?:uation)?s?\.?|Sec(?:tion)?s?\.?)\s*(\d+(?:\.\d+)*)", re.I)
FIGREF_ZH = re.compile(r"(图|表|式|章节|第)\s*(\d+(?:\.\d+)*)")
EQTAG = re.compile(r"\(\s*(\d{1,3})\s*\)")
SENT_EN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
SENT_ZH = re.compile(r"(?<=[。！？；])")


def norm_num(tok):
    t = tok.replace(" ", " ").replace("，", ",").strip()
    t = t.replace(",", "") if re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", t) else t.replace(",", ".")
    t = t.rstrip(".") if t.endswith(".") else t
    return t.split(".")[0] if re.match(r"^\d+\.0+$", t) else t


def numbers_of(text):
    out = []
    for m in NUM_RE.finditer(text):
        tok = m.group(0)
        if re.match(r"^\d{1,2}$", tok) and m.start() > 0 and text[m.start() - 1] in ".":
            continue
        out.append(norm_num(tok))
    return out


def bracket_cites(text):
    out = []
    for m in BRACKET_CITE.finditer(text):
        for p in re.split(r"[,–—-]", m.group(0).strip("[] ")):
            if p.strip().isdigit():
                out.append(p.strip())
    return out


def figrefs(text, lang):
    out = []
    if lang == "zh":
        for m in FIGREF_ZH.finditer(text):
            out.append(({"图": "fig", "表": "table", "式": "eq", "章节": "sec",
                         "第": "sec"}[m.group(1)], m.group(2)))
    for m in FIGREF_EN.finditer(text):
        w = m.group(1).lower()
        out.append(("fig" if w.startswith("fig") else "table" if w.startswith("tab")
                    else "eq" if w.startswith("eq") else "sec", m.group(2)))
    return out


def eqtags(text):
    return [m.group(1) for m in EQTAG.finditer(text) if len(m.group(1)) <= 3]


def missing_multiset(src, tgt):
    pool = {}
    for x in tgt:
        pool[x] = pool.get(x, 0) + 1
    miss = []
    for x in src:
        if pool.get(x, 0) > 0:
            pool[x] -= 1
        else:
            miss.append(x)
    return miss


def extra_multiset(src, tgt):
    return missing_multiset(tgt, src)


def split_sentences(text, lang):
    t = (text or "").strip()
    if not t:
        return []
    return [p.strip() for p in (SENT_ZH if lang == "zh" else SENT_EN).split(t) if p.strip()]


def proportional_map(ns, nt):
    if ns <= 1 or nt <= 1:
        return [0] * ns
    return [min(nt - 1, int(round(i * (nt - 1) / float(ns - 1)))) for i in range(ns)]


def _snip(text, n=90):
    """截断摘录：优先在词边界收尾，避免把 "NaCl" 截成 "Na" 这类半截词造成误判。"""
    t = (text or "").strip()
    if len(t) <= n:
        return t
    cut = t[:n]
    sp = cut.rfind(" ")
    if sp > n * 0.5:
        cut = cut[:sp]
    return cut.rstrip(" ,;:") + "…"


def _contains_term(hay, term):
    if not term:
        return False
    if re.search(r"[一-鿿]", term):
        return term in hay
    return re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", hay, re.I) is not None


def _tally(items):
    out = {}
    for c in items:
        out[c["check"]] = out.get(c["check"], 0) + 1
    return dict(sorted(out.items()))


def _find_quote(checker, sid, quote):
    """在指定段找引文；sid 缺失或无效时全篇找。返回 (found, offset, matched)。"""
    from core import quote_find
    if sid and sid in checker.by_sid:
        f, off, m = quote_find(checker.by_sid[sid]["text"], quote)
        return (True, off, m) if f else (False, -1, "")
    for s in checker.segs:
        f, off, m = quote_find(s["text"], quote)
        if f:
            return True, off, m
    return False, -1, ""


class Checker(object):
    def __init__(self, index, draft, contract_keys, target_lang="zh", derivable=None):
        self.index = index
        self.segs = index.get("segments", [])
        self.by_sid = {s["sid"]: s for s in self.segs}
        self.contract_keys = list(contract_keys or [])
        self.derivable = set(derivable or ())
        self.lang = (target_lang or "zh").lower()[:2]
        self.entries, self.raw_segments, self.checks = {}, [], []
        segs = (draft or {}).get("segments") or (draft or {}).get("items") or []
        if isinstance(segs, dict):
            segs = [dict(v, sid=k) if isinstance(v, dict) else {"sid": k, "target": v}
                    for k, v in segs.items()]
        for e in segs:
            if not isinstance(e, dict):
                continue
            sid = str(e.get("sid") or e.get("id") or "").strip()
            if sid:
                self.raw_segments.append(e)
                self.entries[sid] = e
        self.glossary = [g for g in ((draft or {}).get("glossary") or []) if isinstance(g, dict)]
        self.element_total, self.element_gaps = 0, []

    def add(self, check, status, sid=None, detail="", src="", tgt=""):
        self.checks.append({"check": check, "status": status, "sid": sid or "",
                            "detail": detail, "source_excerpt": _snip(src),
                            "target_excerpt": _snip(tgt)})

    def target_of(self, sid):
        t = (self.entries.get(sid) or {}).get("target") \
            or (self.entries.get(sid) or {}).get("translation") or ""
        return t if isinstance(t, str) else ""

    def source_of(self, sid):
        e = self.entries.get(sid) or {}
        s = e.get("source") or e.get("quote") or ""
        if isinstance(s, str) and s.strip():
            return s
        return self.by_sid.get(sid, {}).get("text", "")

    def is_uncertain(self, sid):
        return bool((self.entries.get(sid) or {}).get("uncertain"))

    # ---------------- 各项核验
    def check_sid(self):
        seen, dup, unknown = set(), [], []
        for e in self.raw_segments:
            sid = str(e.get("sid") or e.get("id") or "")
            if sid in seen:
                dup.append(sid)
            seen.add(sid)
            if sid not in self.by_sid:
                unknown.append(sid)
        if dup:
            self.add("sid_integrity", "fail", dup[0], "重复段号: %s" % ",".join(sorted(set(dup))[:8]))
        if unknown:
            self.add("sid_integrity", "fail", unknown[0],
                     "工作稿出现索引中不存在的段号: %s" % ",".join(sorted(set(unknown))[:8]))
        missing = [s["sid"] for s in self.segs if s["sid"] not in self.entries]
        if missing:
            self.add("sid_integrity", "warn", missing[0],
                     "未在工作稿中出现的段号 %d 个: %s" % (len(missing), ",".join(missing[:10])))
        if not dup and not unknown:
            self.add("sid_integrity", "pass", None,
                     "段号自洽：%d 段，工作稿提供 %d 段" % (len(self.segs), len(self.entries)))

    def check_source(self):
        bad = 0
        for sid, e in sorted(self.entries.items()):
            canon = self.by_sid.get(sid)
            got = (e.get("source") or e.get("quote") or "").strip()
            if not canon or not got:
                continue
            a, b = re.sub(r"\s+", " ", got), re.sub(r"\s+", " ", canon["text"])
            if a != b and a not in b and b not in a:
                bad += 1
                if bad <= 6:
                    self.add("source_verbatim", "fail", sid,
                             "工作稿原文与索引原文不一致（可能被回译或改写）", canon["text"], got)
        if not bad:
            self.add("source_verbatim", "pass", None, "工作稿原文逐字一致")

    def coverage(self):
        total = len(self.segs)
        translated, miss, uncertain, skipped = [], [], [], []
        for s in self.segs:
            raw = self.target_of(s["sid"])
            if not raw.strip():
                miss.append(s["sid"]); continue
            kinds = {k for k, _ in PH_RE.findall(raw)}
            if "待补" in kinds:
                miss.append(s["sid"])
            elif "未译" in kinds and len(kinds) == 1 and len(PH_RE.findall(raw)) == 1:
                skipped.append(s["sid"])
            else:
                translated.append(s["sid"])
                if self.is_uncertain(s["sid"]) or "存疑" in kinds:
                    uncertain.append(s["sid"])
        rate = round(len(translated) / float(total), 4) if total else 0.0
        any_rate = round((len(translated) + len(skipped)) / float(total), 4) if total else 0.0
        if miss:
            self.add("coverage", "fail", miss[0],
                     "未翻译 %d 段（段号=%s）" % (len(miss), ",".join(miss[:12])))
        else:
            self.add("coverage", "pass", None, "全部段落已有译文（跳过 %d 段）" % len(skipped))
        return {"total": total, "translated": len(translated), "missing": miss,
                "skipped": skipped, "uncertain": uncertain,
                "coverage_rate": rate, "coverage_rate_incl_skipped": any_rate}

    def check_elements(self):
        """图表题注/表头/表行/公式/文献等要素型段落必须覆盖，且译文对里带 type。"""
        want = [s for s in self.segs if s["type"] in ELEMENT_TYPES]
        gaps = [s["sid"] for s in want
                if not self.target_of(s["sid"]).strip() or "待补" in self.target_of(s["sid"])]
        self.element_total, self.element_gaps = len(want), gaps
        by = {}
        for s in want:
            by.setdefault(s["type"], []).append(s["sid"])
        if not want:
            self.add("element_coverage", "skip", None, "索引中未检出要素型段落")
        elif gaps:
            self.add("element_coverage", "fail", gaps[0],
                     "要素型段落未覆盖 %d/%d: %s" % (len(gaps), len(want), ",".join(gaps[:10])))
        else:
            self.add("element_coverage", "pass", None,
                     "要素型段落全部覆盖：%s" % " ".join("%s=%d" % (k, len(v))
                                                   for k, v in sorted(by.items())))
        return {"elements": len(want), "by_type": {k: len(v) for k, v in sorted(by.items())},
                "uncovered": gaps}

    def check_glossary(self):
        locked, proposed, conflicts, by_term = [], [], [], {}
        for g in self.glossary:
            term = (g.get("term") or "").strip()
            tgt = (g.get("target") or g.get("locked_target") or "").strip()
            if not term:
                continue
            by_term.setdefault(term.lower(), []).append(tgt)
            sid = str(g.get("sid") or g.get("evidence_sid") or "").strip()
            quote = (g.get("quote") or "").strip()
            if not tgt:
                proposed.append(term); continue
            if not quote:
                self.add("glossary_quote", "fail", sid,
                         "术语 `%s` 有译名但未给 quote，无法锁定" % term)
                proposed.append(term); continue
            found, off, _m = _find_quote(self, sid, quote)
            g["quote_verified"] = bool(found)
            g["quote_offset"] = off
            if found:
                locked.append(term)
            else:
                proposed.append(term)
                self.add("glossary_quote", "fail", sid,
                         "术语 `%s` 的 quote 未在原文逐字命中" % term, quote, tgt)
        for term, tgts in sorted(by_term.items()):
            uniq = sorted({t for t in tgts if t})
            if len(uniq) > 1:
                conflicts.append(term)
                self.add("glossary_drift", "warn", None,
                         "术语 `%s` 在工作稿中出现 %d 种译名: %s" % (term, len(uniq), " / ".join(uniq)))
        if locked and not any(c["check"] == "glossary_quote" and c["status"] == "fail"
                              for c in self.checks):
            self.add("glossary_quote", "pass", None, "%d 条术语 quote 全部逐字命中" % len(locked))

        occ_total, occ_hit, drift_sids = 0, 0, []
        for g in self.glossary:
            term, tgt = (g.get("term") or "").strip(), (g.get("target") or "").strip()
            if not term or not tgt or term not in locked:
                continue
            for s in self.segs:
                if not _contains_term(s["text"], term):
                    continue
                occ_total += 1
                body = self.target_of(s["sid"])
                if tgt in body:
                    occ_hit += 1
                else:
                    drift_sids.append(s["sid"])
                    if len(drift_sids) <= 8:
                        self.add("glossary_lock", "fail", s["sid"],
                                 "术语 `%s` 锁定为 `%s`，该段译文未使用锁定译名" % (term, tgt),
                                 s["text"], body)
        if not drift_sids:
            self.add("glossary_lock", "pass", None,
                     "已锁定术语全篇一致（%d 次出现）" % occ_total)
        return {"locked": sorted(set(locked)), "proposed": sorted(set(proposed)),
                "conflicts": sorted(set(conflicts)), "occurrences": occ_total, "hits": occ_hit,
                "consistency_rate": round(occ_hit / float(occ_total), 4) if occ_total else None,
                "drift_sids": sorted(set(drift_sids))}

    def check_spans(self):
        miss_num, extra_num, miss_cite, miss_fig, miss_eq = [], [], [], [], []
        for s in self.segs:
            sid, src, tgt = s["sid"], s["text"], self.target_of(s["sid"])
            if not tgt.strip():
                continue
            m = missing_multiset(numbers_of(src), numbers_of(tgt))
            if m:
                miss_num.append((sid, m))
                self.add("protected_numbers", "fail", sid,
                         "数字/单位缺失: %s" % ", ".join(m[:8]), src, tgt)
            e = extra_multiset(numbers_of(src), numbers_of(tgt))
            if e and not self.is_uncertain(sid):
                extra_num.append((sid, e))
                if len(extra_num) <= 4:
                    self.add("protected_numbers", "warn", sid,
                             "译文含原文没有的数字（可能是补的编号）: %s" % ", ".join(e[:6]), src, tgt)
            mc = missing_multiset(bracket_cites(src), bracket_cites(tgt))
            if mc:
                miss_cite.append((sid, mc))
                self.add("citations", "fail", sid,
                         "文献引用编号缺失: %s" % ", ".join(mc[:8]), src, tgt)
            if AUTHOR_CITE.findall(src) and \
                    len(AUTHOR_CITE.findall(tgt)) < len(AUTHOR_CITE.findall(src)):
                self.add("citations", "fail", sid, "作者-年份引用标记数量减少", src, tgt)
            mf = missing_multiset(figrefs(src, "en"), figrefs(tgt, self.lang))
            if mf:
                miss_fig.append((sid, ["%s %s" % x for x in mf]))
                self.add("figure_table_refs", "fail", sid,
                         "图表/章节编号不一致: %s" % "; ".join("%s %s" % x for x in mf[:6]), src, tgt)
            me = missing_multiset(eqtags(src), eqtags(tgt))
            if me:
                miss_eq.append((sid, me))
                self.add("equation_tags", "fail", sid,
                         "公式编号缺失: %s" % ", ".join(me[:6]), src, tgt)
        for name, bad in (("protected_numbers", miss_num), ("citations", miss_cite),
                          ("figure_table_refs", miss_fig), ("equation_tags", miss_eq)):
            if not bad:
                self.add(name, "pass", None, "全部段落通过")
        return {"number_gaps": [[s, v] for s, v in miss_num][:20],
                "citation_gaps": [[s, v] for s, v in miss_cite][:20],
                "figref_gaps": [[s, v] for s, v in miss_fig][:20],
                "eqtag_gaps": [[s, v] for s, v in miss_eq][:20],
                "extra_numbers": [[s, v] for s, v in extra_num][:20]}

    def check_relations(self):
        neg_total, neg_ok, hedge_total, hedge_ok = 0, 0, 0, 0
        neg_fail, hedge_fail = [], []
        for s in self.segs:
            sid, tgt = s["sid"], self.target_of(s["sid"])
            if not tgt.strip():
                continue
            src_sents = split_sentences(s["text"], "zh" if re.search(r"[一-鿿]", s["text"]) else "en")
            tgt_sents = split_sentences(tgt, self.lang)
            if not src_sents or not tgt_sents:
                continue
            amap = proportional_map(len(src_sents), len(tgt_sents))
            for i, ss in enumerate(src_sents):
                tt = tgt_sents[amap[i]]
                if re.search(NEG_EN, ss, re.I) or re.search(NEG_ZH, ss):
                    neg_total += 1
                    if re.search(NEG_ZH, tt) or re.search(NEG_EN, tt, re.I):
                        neg_ok += 1
                    else:
                        neg_fail.append(sid)
                        if len(neg_fail) <= 6:
                            self.add("negation", "fail", sid,
                                     "原文该句含否定/限制成分，对应译文未出现否定标记（第 %d 句）" % (i + 1),
                                     ss, tt)
                if re.search(HEDGE_EN, ss, re.I) or re.search(HEDGE_ZH, ss):
                    hedge_total += 1
                    if re.search(HEDGE_ZH, tt) or re.search(HEDGE_EN, tt, re.I):
                        hedge_ok += 1
                    else:
                        hedge_fail.append(sid)
                        if len(hedge_fail) <= 6:
                            self.add("hedge", "warn", sid,
                                     "原文该句含限定/可能性成分，译文可能被强化为断言（第 %d 句）" % (i + 1),
                                     ss, tt)
        if neg_total and neg_ok == neg_total:
            self.add("negation", "pass", None, "%d 个否定句全部保留" % neg_total)
        elif not neg_total:
            self.add("negation", "skip", None, "原文未检出否定成分")
        if hedge_total and hedge_ok == hedge_total:
            self.add("hedge", "pass", None, "%d 个限定句全部保留" % hedge_total)
        elif not hedge_total:
            self.add("hedge", "skip", None, "原文未检出限定成分")
        return {"negation_sentences": neg_total, "negation_kept": neg_ok,
                "negation_rate": round(neg_ok / float(neg_total), 4) if neg_total else None,
                "hedge_sentences": hedge_total, "hedge_kept": hedge_ok,
                "hedge_rate": round(hedge_ok / float(hedge_total), 4) if hedge_total else None,
                "negation_fail_sids": sorted(set(neg_fail)),
                "hedge_fail_sids": sorted(set(hedge_fail))}

    def check_language_and_placeholders(self):
        bad_lang = []
        for s in self.segs:
            tgt = self.target_of(s["sid"])
            if not tgt.strip() or PH_RE.search(tgt):
                continue
            if (self.by_sid.get(s["sid"]) or {}).get("type") in ("reference", "table_row"):
                continue
            if self.lang == "zh":
                if not re.search(r"[一-鿿]", tgt):
                    bad_lang.append(s["sid"])
            elif not re.search(r"[A-Za-z]{3,}", tgt):
                bad_lang.append(s["sid"])
        if bad_lang:
            self.add("target_language", "fail", bad_lang[0],
                     "%d 段译文缺少目标语言（%s）字符: %s"
                     % (len(bad_lang), self.lang, ",".join(bad_lang[:8])))
        else:
            self.add("target_language", "pass", None, "全部译文语言符合 %s" % self.lang)
        ph_sids = [s["sid"] for s in self.segs if PH_RE.search(self.target_of(s["sid"]))]
        for s in self.segs:
            for kind, _n in PH_RE.findall(self.target_of(s["sid"])):
                if kind == "存疑" and not self.is_uncertain(s["sid"]):
                    self.add("placeholder_policy", "warn", s["sid"],
                             "译文含〔存疑〕标记但未设 uncertain=true")
        if ph_sids:
            self.add("placeholder_policy", "warn", ph_sids[0],
                     "%d 段仍含占位符（answered 状态前必须清零）" % len(ph_sids))
        else:
            self.add("placeholder_policy", "pass", None, "无占位符")
        return ph_sids

    def check_repeats(self):
        bag = {}
        for s in self.segs:
            t = self.target_of(s["sid"]).strip()
            if len(t) > 40:
                bag.setdefault(t, []).append(s["sid"])
        dup = sorted((v for v in bag.values() if len(v) > 1), key=lambda x: x[0])
        if dup:
            self.add("repeated_target", "warn", dup[0][0],
                     "%d 组段落共用完全相同的译文（疑似复制填充）: %s"
                     % (len(dup), ",".join(dup[0][:6])))
        else:
            self.add("repeated_target", "pass", None, "无重复译文")

    def check_contract(self, draft):
        fields = (draft or {}).get("result_fields") or {}
        if not self.contract_keys:
            self.add("contract_fields", "warn", None,
                     "case.json 未提供 output_contract，将使用默认契约字段")
            return {"declared": [], "provided": sorted(fields.keys()), "missing": [],
                    "extra": [], "filled": 0, "total": 0}
        provided = [k for k in self.contract_keys if fields.get(k) not in (None, "", [], {})]
        missing = [k for k in self.contract_keys if fields.get(k) in (None, "", [], {})]
        extra = [k for k in fields if k not in self.contract_keys]
        hard = [k for k in missing if k not in self.derivable]
        if hard:
            self.add("contract_fields", "warn", None,
                     "契约字段既未在工作稿给值、也无法派生: %s" % ",".join(hard[:10]))
        elif missing:
            self.add("contract_fields", "pass", None,
                     "契约字段 %s 未在工作稿给出，由 build 按语义映射从真实产物派生回填"
                     % ",".join(missing[:10]))
        else:
            self.add("contract_fields", "pass", None, "%d 个契约字段均由工作稿提供" % len(self.contract_keys))
        if extra:
            self.add("contract_fields", "warn", None,
                     "工作稿 result_fields 含契约外字段: %s" % ",".join(extra[:8]))
        return {"declared": self.contract_keys, "provided": provided, "missing": missing,
                "extra": extra, "filled": len(provided), "total": len(self.contract_keys)}

    def run(self, draft):
        cov = self.coverage()
        self.check_elements()
        gl = self.check_glossary()
        self.check_sid()
        self.check_source()
        spans = self.check_spans()
        rel = self.check_relations()
        ph = self.check_language_and_placeholders()
        self.check_repeats()
        cf = self.check_contract(draft)
        fails = [c for c in self.checks if c["status"] == "fail"]
        warns = [c for c in self.checks if c["status"] == "warn"]
        summary = {"segments": len(self.segs), "checks": len(self.checks),
                   "pass": sum(1 for c in self.checks if c["status"] == "pass"),
                   "fail": len(fails), "warn": len(warns),
                   "skip": sum(1 for c in self.checks if c["status"] == "skip"),
                   "fail_by_check": _tally(fails), "warn_by_check": _tally(warns)}
        span_total = sum(len(s["spans"]) for s in self.segs)
        span_gap = sum(len(v) for _, v in spans["number_gaps"]) + \
            sum(len(v) for _, v in spans["citation_gaps"]) + \
            sum(len(v) for _, v in spans["figref_gaps"]) + \
            sum(len(v) for _, v in spans["eqtag_gaps"])
        rates = {"coverage_rate": cov["coverage_rate"],
                 "glossary_consistency": gl["consistency_rate"],
                 "span_retention": round(max(0.0, 1 - span_gap / float(span_total)), 4)
                 if span_total else None,
                 "negation_rate": rel["negation_rate"], "hedge_rate": rel["hedge_rate"],
                 "element_coverage": round(self.element_total and
                                           (self.element_total - len(self.element_gaps)) /
                                           float(self.element_total), 4) if self.element_total else None,
                 "quote_verbatim": round(sum(1 for g in self.glossary if g.get("quote_verified")) /
                                         float(len(self.glossary)), 4) if self.glossary else None}
        return {"checks": self.checks, "summary": summary, "rates": rates, "coverage": cov,
                "glossary": gl, "spans": spans, "relations": rel, "contract": cf,
                "elements": {"elements": self.element_total, "uncovered": self.element_gaps},
                "placeholder_sids": ph}


def derive_status(cov, fail_count, total, empty_text=False):
    if total == 0 or empty_text:
        return "insufficient_evidence"
    if fail_count == 0 and cov["coverage_rate"] >= 0.999 and not cov["missing"]:
        return "answered"
    return "partial"


RANK = {"input_error": 0, "insufficient_evidence": 1, "partial": 2, "answered": 3}


def enforce_status(requested, derived):
    """只允许更保守：requested 的等级不得高于 derived。返回 (final, note)。"""
    if not requested:
        return derived, ""
    if requested not in RANK:
        return derived, "unknown_status_ignored:%s" % requested
    if RANK[requested] > RANK[derived]:
        return derived, "status_downgraded:%s->%s" % (requested, derived)
    return requested, ""
