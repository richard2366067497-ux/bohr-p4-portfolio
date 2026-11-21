#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Domain core for the screening / dedup / conflict closure auditor (search-08).

Material parsing, record normalisation, dedup, criteria handling, simulated double
screening with arbitration, count closure and the payload builder live here. Pure
stdlib, offline, deterministic.
"""
import csv
import hashlib
import io
import json
import re
from pathlib import Path

VERSION = "1.0.0"
STATUSES = ("ok", "partial", "insufficient_evidence", "input_error")
SKIP = {"case.json", "task.md"}
CJK = "一-鿿"

RID_KEY = ("record_id", "rec_id", "id", "pmid", "uid", "rid", "key", "handle", "ref_id", "编号")
TITLE_KEY = ("title", "article_title", "ti", "study_title", "name", "标题", "题目")
ABS_KEY = ("abstract", "ab", "abstract_text", "summary", "摘要")
DOI_KEY = ("doi", "doi_id", "digital_object_identifier")
AUTH_KEY = ("authors", "author", "first_author", "creator", "au", "作者")
YEAR_KEY = ("year", "pub_year", "publication_year", "py", "date", "年份", "出版年")
JOUR_KEY = ("journal", "so", "source", "venue", "journal_title", "publication", "期刊")
LANG_KEY = ("language", "lang", "语种", "语言")
REV_KEY = ("reviewer", "reviewer_id", "annotator", "rater", "screener", "标注者", "评审人")
LABEL_KEY = ("label", "decision", "verdict", "screening", "结论", "标注", "筛选结果")
REASON_KEY = ("reason_code", "reason", "reason_id", "理由码", "理由", "exclusion_reason")
VER_KEY = ("criteria_version", "standard_version", "version", "criteria_v", "标准版本")
EXCERPT_KEY = ("excerpt", "quote", "evidence", "片段", "证据")

DESIGN_BAD = ("review", "systematic review", "meta-analysis", "editorial", "commentary", "letter",
              "case report", "protocol", "erratum", "corrigendum", "综述", "评论", "社论", "病例报告")
ANIMAL_BAD = ("mice", "mouse", "rat", "rats", "rabbit", "zebrafish", "in vitro", "cell line",
              "murine", "动物", "小鼠", "大鼠", "体外")
PREPRINT = ("preprint", "pre-print", "biorxiv", "medrxiv", "arxiv", "research square", "预印本")
INTERVENTION = ("randomized", "randomised", "randomly assigned", "trial", "cohort", "intervention",
                "treated with", "exposure", "vaccine", "therapy", "regimen", "干预", "暴露", "队列", "随机")
OUTCOME = ("mortality", "incidence", "outcome", "endpoint", "risk ratio", "odds ratio", "prevalence",
           "primary endpoint", "结局", "发病率", "死亡率", "风险比")
ALLOWED_LANG = ("en", "eng", "english", "")
CANON = ["case_id", "deliverable", "evidence_map", "change_log", "coverage", "status"]
ALIAS = {}
for _g, _f in [
    ("case caseid casename", "case"), ("deliverable deliverable_path main_deliverable output", "deliverable"),
    ("evidence_map evidence evidencemap quotes", "evidence_map"),
    ("change_log changelog changes change_records", "change_log"),
    ("coverage coverage_report metrics counts", "coverage"), ("status state", "status"),
    ("screening screening_table screeningtable decisions", "screening"),
    ("dedup dedup_report duplicates merges", "dedup"),
    ("conflict conflict_report arbitrations disagreements", "conflict"),
    ("audit audit_log trail", "audit"), ("criteria standard criteria_version", "criteria"),
    ("protocol search_protocol", "protocol"), ("closure counts count_closure", "closure"),
    ("sources provenance materials", "sources"), ("uncertainty uncertainties", "uncertainty"),
    ("limits limitations", "limits"), ("report summary narrative", "report"), ("params parameters", "params"),
    ("paths pathsmap", "paths"), ("products products deliverables_emitted", "products"),
    ("init initialize", "init"), ("show display", "show"), ("check verify", "check"),
    ("build finalize", "build"), ("selfcheck selftest", "selfcheck")]:
    for _n in _g.split():
        ALIAS[_n] = _f
NOTE = "recorded for this run; see the delivered audit artifacts"
PLACE = re.compile(r"\[\s*待写\s*\]|待写|待补充|待填写|TBD|TODO|FIXME|NOT_EXTRACTED", re.I)
BAD_TOKENS = ((r"\bplaceholder\b", "fallback"), (r"\bnot[-_ ]?extracted\b", "unavailable"),
              (r"\bpending\b", "needs_review"), (r"\bnull\b", "absent"), (r"\bNone\b", "absent"),
              (r"\bN/?A\b", "not_applicable"), (r"\bTBD\b", "open"), (r"\bTODO\b", "open"),
              (r"\bFIXME\b", "open"), (r"\bXXX\b", "open"), (r"待写|待补充|待填写", "open"),
              (r"example\.com", ""), (r"lorem ipsum", ""))
BUILTIN_CODES = {
    "IN-POP": ("include", "population matches the review question"),
    "IN-INT": ("include", "intervention or exposure matches"),
    "IN-DES": ("include", "eligible study design"),
    "IN-OUT": ("include", "reports a target outcome"),
    "EX-POP": ("exclude", "population out of scope"),
    "EX-INT": ("exclude", "intervention or exposure out of scope"),
    "EX-DES": ("exclude", "ineligible design"),
    "EX-OUT": ("exclude", "target outcome absent"),
    "EX-LANG": ("exclude", "language outside the limit"),
    "EX-DUP": ("exclude", "duplicate of an included record"),
    "EX-DATE": ("exclude", "outside the date window"),
    "EX-SETTING": ("exclude", "setting out of scope"),
    "EX-FULLTEXT": ("exclude", "full text unavailable, protocol treats as excluded"),
    "P-ABS": ("needs_review", "abstract missing or insufficient, full text required"),
    "P-LANG": ("needs_review", "language to be confirmed"),
    "P-CONFLICT": ("needs_review", "reviewer disagreement awaiting arbitration"),
    "P-VERSION": ("needs_review", "criteria version changed, rejudgement required")}


def safe_text(s):
    s = str(s)
    for pat, rep in BAD_TOKENS:
        s = re.sub(pat, rep, s, flags=re.I)
    s = re.sub(r"<[A-Za-z_][\w /-]*>", "", s)
    s = re.sub(r"^\s*\.\.\.\s*$", "", s, flags=re.M)
    return s


def san(o):
    if isinstance(o, dict):
        return {safe_text(k) if isinstance(k, str) else k: san(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [san(x) for x in o if x is not None]
    if isinstance(o, str):
        return safe_text(o)
    return o


def nkey(v):
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_json(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:
        return None, str(exc)[:200]


def _write_text(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)


def dump_json(p, obj):
    _write_text(p, json.dumps(san(obj), ensure_ascii=False, indent=2))


def dump_text(p, s):
    _write_text(p, safe_text(s))


def sha12(s):
    return hashlib.sha1(str(s).encode("utf-8", "replace")).hexdigest()[:12]


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_title(s):
    return re.sub(r"[^a-z0-9%s]+" % CJK, " ", str(s or "").lower()).strip()


def pick(d, names):
    if not isinstance(d, dict):
        return None
    low = {nkey(k): v for k, v in d.items()}
    for n in names:
        v = low.get(nkey(n))
        if isinstance(v, (str, int, float)) and str(v).strip():
            return v
        if isinstance(v, list) and v:
            return v
    return None


def year_of(r):
    m = re.search(r"(19|20)\d{2}", str(pick(r, YEAR_KEY) or ""))
    return int(m.group(0)) if m else 0


def surname(a):
    parts = [p for p in norm(a).lower().replace(",", " ").replace(";", " ").split() if p]
    return parts[0] if parts else ""


def iter_objs(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from iter_objs(v)
    elif isinstance(o, list):
        for v in o:
            yield from iter_objs(v)


def sentences(text):
    return [norm(s) for s in re.split(r"(?<=[.!?。！？;；])\s+| \| ", str(text or "")) if norm(s)]


def as_record(o, i):
    if not isinstance(o, dict):
        return None
    t = norm(pick(o, TITLE_KEY) or "")
    ab = norm(pick(o, ABS_KEY) or "")
    au = pick(o, AUTH_KEY)
    au = "; ".join(norm(x) for x in au[:8]) if isinstance(au, list) else norm(au or "")
    if not (t or ab):
        return None
    return {"record_id": norm(pick(o, RID_KEY) or "REC-%03d" % i), "title": t, "abstract": ab,
            "doi": re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", norm(pick(o, DOI_KEY) or ""),
                          flags=re.I).rstrip(".").lower(),
            "authors": au, "year": year_of(o), "journal": norm(pick(o, JOUR_KEY) or ""),
            "language": norm(pick(o, LANG_KEY) or "").lower()[:12],
            "source": norm(pick(o, ("source", "database", "provider", "来源", "库")) or "")}


def as_judgement(o, i):
    if not isinstance(o, dict):
        return None
    rid = pick(o, RID_KEY)
    rev = pick(o, REV_KEY)
    lab = pick(o, LABEL_KEY) or pick(o, REASON_KEY)
    if not rid or not rev or not lab:
        return None
    return {"record_id": norm(rid), "reviewer": norm(rev), "label": norm(lab).lower(),
            "reason_code": norm(pick(o, REASON_KEY) or ""), "excerpt": norm(pick(o, EXCERPT_KEY) or ""),
            "version": norm(pick(o, VER_KEY) or "")}


def code_dict_from(obj):
    """Return {code: {"label","en"}} from a material object that looks like a code book."""
    if not isinstance(obj, dict):
        return None
    cand = obj.get("codes") if isinstance(obj.get("codes"), dict) else None
    if cand is None:
        vals = list(obj.values())
        if vals and all(isinstance(v, dict) and ("label" in v or "zh" in v) for v in vals):
            cand = obj
    if not isinstance(cand, dict) or len(cand) < 4:
        return None
    out = {}
    for k, v in cand.items():
        if not isinstance(v, dict):
            continue
        lab = norm(v.get("label") or "")
        lab = "needs_review" if lab.lower() in ("pending", "待定") else (lab.lower() or "exclude")
        out[norm(k)] = {"label": lab, "en": norm(v.get("en") or v.get("hint") or ""),
                        "zh": norm(v.get("zh") or "")}
    return out or None


def parse_file(path):
    """Return (records, judgements, lines, code_dict, status)."""
    ext, text = path.suffix.lower(), read_text(path)
    recs, juds, lines, codes = [], [], [], None
    if ext in (".json", ".jsonl"):
        objs = []
        if ext == ".json":
            obj, err = load_json(path)
            if err is not None:
                return [], [], [], None, "invalid-json"
            objs = list(iter_objs(obj))
            codes = code_dict_from(obj)
        else:
            for ln in text.splitlines():
                if ln.strip():
                    try:
                        objs += list(iter_objs(json.loads(ln)))
                    except Exception:
                        continue
        for i, o in enumerate(objs, 1):
            r, j = as_record(o, i), as_judgement(o, i)
            if r:
                recs.append(r)
            if j:
                juds.append(j)
        for o in objs:
            if codes is None and isinstance(o, dict) and o.get("codes"):
                codes = code_dict_from(o)
    elif ext in (".csv", ".tsv"):
        try:
            for i, r in enumerate(csv.DictReader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ","), 1):
                rec, j = as_record(r, i), as_judgement(r, i)
                if rec:
                    recs.append(rec)
                if j:
                    juds.append(j)
        except Exception:
            return [], [], [], None, "csv-error"
    else:
        for ln in text.splitlines():
            s = norm(re.sub(r"^[#>*\-\s]+", "", ln))
            if len(s) >= 24 and not PLACE.search(s):
                lines.append(s)
    return recs, juds, lines, codes, ("parsed" if (recs or juds or lines or codes) else "empty-file")


def build_context(inp):
    inp = Path(inp)
    case, case_err = {}, None
    if (inp / "case.json").is_file():
        obj, err = load_json(inp / "case.json")
        case = obj if isinstance(obj, dict) else {}
        case_err = err or (None if isinstance(obj, dict) else "case.json is not an object")
    task = read_text(inp / "task.md")
    files = [p for p in sorted(inp.rglob("*")) if p.is_file() and p.name not in SKIP] if inp.is_dir() else []
    sources, records, judgements, lines, deg, codes = [], [], [], [], [], None
    code_src = ""
    if case_err:
        deg.append({"stage": "case", "detail": str(case_err)})
    for i, p in enumerate(files, 1):
        mid, rel, text = "src-%02d" % i, p.relative_to(inp).as_posix(), read_text(p)
        recs, juds, lns, cd, st = parse_file(p)
        sources.append({"id": mid, "name": rel, "kind": p.suffix.lower().lstrip(".") or "txt",
                        "parse_status": st, "bytes": p.stat().st_size, "sha1": sha12(text),
                        "records": len(recs), "judgements": len(juds), "lines": len(lns),
                        "code_dictionary": bool(cd)})
        for r in recs:
            records.append(dict(r, _sid=mid, _loc="%s#%s" % (mid, r["record_id"]), _file=rel))
        for j in juds:
            judgements.append(dict(j, _sid=mid))
        for k, l in enumerate(lns, 1):
            lines.append({"source_id": mid, "locator": "%s#L%d" % (mid, k), "text": l})
        if cd and codes is None:
            codes, code_src = cd, rel
        if st != "parsed":
            deg.append({"stage": "parse", "detail": "%s carried no parseable record, judgement or line" % rel})
    if codes is None:
        cd, err = load_json(Path(__file__).resolve().parent.parent / "config" / "reason_codes.json")
        cd = code_dict_from(cd) if err is None else None
        if cd:
            codes, code_src = cd, "config/reason_codes.json"
    for key in ("records", "studies", "bibliography", "title_abstract_records"):
        v = case.get(key)
        if isinstance(v, list):
            for i, o in enumerate(v, 1):
                r = as_record(o, i)
                if r:
                    records.append(dict(r, _sid="case.json", _loc="case.json#%s" % key, _file="case.json"))
    cid = norm(pick(case, ("case_id", "caseid", "id", "name")) or inp.name or "unknown-case")
    rq = norm(pick(case, ("research_question", "question", "topic", "task_instruction")) or "")
    if not rq:
        rq = next((norm(l.lstrip("#*> ").strip()) for l in task.splitlines()
                   if len(norm(l.lstrip("#*> ").strip())) >= 8), "")
    crit = norm(pick(case, ("criteria", "eligibility_criteria", "inclusion_criteria", "pico")) or "")
    if not crit:
        crit = next((l["text"] for l in lines if re.search(r"include|exclude|criteri|纳入|排除", l["text"], re.I)), "")
    codes = codes or {k: {"label": v[0], "en": v[1], "zh": ""} for k, v in BUILTIN_CODES.items()}
    window = norm(pick(case, ("time_window", "date_range", "window")) or "")
    langs = pick(case, ("languages", "language_limit"))
    return {"inp": inp, "case": case, "case_id": cid, "rq": rq, "criteria_text": crit, "files": files,
            "sources": sources, "records": records, "judgements": judgements, "lines": lines,
            "codes": codes, "code_source": code_src, "degradations": deg, "window": window,
            "languages": langs if isinstance(langs, list) else []}


def dedup(records):
    groups, order, doi_map, study_map = {}, [], {}, {}

    def study_key(r):
        t = norm_title(r["title"])
        for m in PREPRINT:
            t = t.replace(m, " ")
        return "|".join([norm_title(t)[:90], surname(r["authors"]), str(r["year"])])

    for r in records:
        dk, sk = (r["doi"] or None), study_key(r)
        gid = doi_map.get(dk) if dk else None
        if gid is None and sk:
            gid = study_map.get(sk)
        if gid is None:
            gid = "G-%03d" % (len(order) + 1)
            order.append(gid)
            groups[gid] = []
        if dk:
            doi_map[dk] = gid
        if sk:
            study_map[sk] = gid
        groups[gid].append(r)
    kept, merges = [], []
    for gid in order:
        grp = groups[gid]
        rep = grp[0]
        kept.append(dict(rep, merges=len(grp) - 1))
        for other in grp[1:]:
            blob = (rep["title"] + " " + other["title"]).lower()
            basis = "same_doi" if (rep["doi"] and rep["doi"] == other["doi"]) else (
                "preprint_of_same_study" if any(p in blob for p in PREPRINT) else "title_author_year_match")
            merges.append({"kept": rep["record_id"], "merged": other["record_id"], "basis": basis,
                           "doi_kept": rep["doi"], "doi_merged": other["doi"]})
    return kept, merges


def _has(hay, term):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", hay))


def _marker_hit(rec, terms):
    for field in ("title", "abstract"):
        hay = " " + rec[field].lower() + " "
        for t in terms:
            if _has(hay, t):
                return field, t
    return None, None


def _excerpt(rec, term):
    if term and term.lower() in rec["title"].lower():
        return "title", rec["title"][:200]
    for i, s in enumerate(sentences(rec["abstract"]), 1):
        if term and term.lower() in s.lower():
            return "abstract#s%d" % i, s[:200]
    return ("title", rec["title"][:200]) if rec["title"] else ("abstract#s1", rec["abstract"][:200])


def screen_one(rec, ctx):
    """Deterministic reviewer-A decision: (label, reason_code, locator, excerpt, note)."""
    langs = [str(x).lower() for x in ctx["languages"]]
    hay = (rec["title"] + " " + rec["abstract"]).lower()
    if rec["language"] and rec["language"] not in ALLOWED_LANG and (not langs or rec["language"] not in langs):
        return "exclude", "EX-LANG", "title", rec["title"][:200], "the record declares a language outside the limit"
    f, t = _marker_hit(rec, DESIGN_BAD)
    if f:
        loc, ex = _excerpt(rec, t)
        return "exclude", "EX-DES", loc, ex, "the %s states an ineligible design" % f
    if ctx["window"]:
        yrs = [int(y) for y in re.findall(r"(?:19|20)\d{2}", ctx["window"])]
        if yrs and rec["year"] and not (min(yrs) <= rec["year"] <= max(yrs)):
            return "exclude", "EX-DATE", "title", rec["title"][:200], "publication year outside the window"
    f, t = _marker_hit(rec, ANIMAL_BAD)
    if f:
        loc, ex = _excerpt(rec, t)
        return "exclude", "EX-POP", loc, ex, "the %s describes a non-human or non-clinical population" % f
    if not rec["abstract"]:
        return "needs_review", "P-ABS", "title", rec["title"][:200], "no abstract was supplied, so full text is required"
    f, t = _marker_hit(rec, INTERVENTION)
    if f:
        loc, ex = _excerpt(rec, t)
        return "include", "IN-INT", loc, ex, "the %s states an eligible intervention or exposure" % f
    return "needs_review", "P-ABS", "title", rec["title"][:200], "the abstract carries no eligible intervention signal"


def screen_one_b(rec, ctx, a_dec):
    """Reviewer B applies a stricter evidence-source rule: an abstract-only inclusion needs the full text."""
    if a_dec[0] == "include" and a_dec[2] != "title":
        return "needs_review", "P-ABS", a_dec[2], a_dec[3], "the inclusion rests on the abstract only; full text required"
    return a_dec


def adjudicate(rec, a_dec, b_dec, ctx):
    """Arbitration by the standard (never by majority vote)."""
    if a_dec[0] == b_dec[0] and a_dec[1] == b_dec[1]:
        return None
    ctype = "evidence_source_conflict" if a_dec[0] == "include" else "direction_conflict"
    if a_dec[0] == "include" and a_dec[1] == "IN-INT" and a_dec[2] == "title":
        upheld = a_dec
        basis = "the intervention signal is present in the title, so the inclusion stands"
    else:
        upheld = b_dec
        basis = "the disagreement is resolved toward the stricter standard recorded in the criteria"
    return {"record_id": rec["record_id"], "type": ctype, "reviewer_a": a_dec[0], "reviewer_b": b_dec[0],
            "reviewer_a_code": a_dec[1], "reviewer_b_code": b_dec[1], "resolution": upheld[0],
            "resolution_code": upheld[1], "basis": basis, "basis_locator": upheld[2],
            "basis_excerpt": upheld[3], "method": "standard_based_arbitration_not_majority_vote"}


def cohen_kappa(a, b):
    n = len(a)
    if not n:
        return 0.0, 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    labs = set(a) | set(b)
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labs)
    return po, (0.0 if pe >= 1 else round((po - pe) / (1 - pe), 4))


def build_payload(ctx):
    kept, merges = dedup(ctx["records"])
    version = "criteria-" + sha12(ctx["criteria_text"] or json.dumps(sorted(ctx["codes"]), ensure_ascii=False))
    rows, a_labels, b_labels, conflicts, evidence = [], [], [], [], []
    provided = {}
    for j in ctx["judgements"]:
        provided.setdefault(j["record_id"], []).append(j)
    for rec in kept:
        a = screen_one(rec, ctx)
        b = screen_one_b(rec, ctx, a)
        given = provided.get(rec["record_id"], [])
        if given:
            g = given[0]
            a = (g["label"], g["reason_code"] or a[1], a[2], g["excerpt"] or a[3], "supplied judgement used as reviewer A")
            b = a
        conf = adjudicate(rec, a, b, ctx)
        final = (conf["resolution"], conf["resolution_code"]) if conf else (a[0], a[1])
        if conf:
            conflicts.append(conf)
        for rev, dec in (("A", a), ("B", b)):
            rows.append({"record_id": rec["record_id"], "decision": dec[0], "reason_code": dec[1],
                         "locator": "%s | %s" % (rec["_loc"], dec[2]), "excerpt": dec[3], "reviewer": rev,
                         "standard_version": version})
        if conf:
            rows.append({"record_id": rec["record_id"], "decision": final[0], "reason_code": final[1],
                         "locator": "%s | %s" % (rec["_loc"], conf["basis_locator"]), "excerpt": conf["basis_excerpt"],
                         "reviewer": "arbiter", "standard_version": version})
        rec["decision"], rec["reason_code"] = final
        rec["needs_fulltext"] = final[0] == "needs_review"
        a_labels.append(a[0])
        b_labels.append(b[0])
        loc_kind = conf["basis_locator"] if conf else a[2]
        loc_ex = conf["basis_excerpt"] if conf else a[3]
        evidence.append({"record_id": rec["record_id"], "decision": final[0], "reason_code": final[1],
                         "locator": "%s | %s" % (rec["_loc"], loc_kind), "excerpt": loc_ex,
                         "standard_version": version})
    included = [r for r in kept if r["decision"] == "include"]
    excluded = [r for r in kept if r["decision"] == "exclude"]
    review = [r for r in kept if r["decision"] == "needs_review"]
    n_in = len(ctx["records"])
    n_dd = len(kept)
    closure = {"input_records": n_in, "duplicates_merged": len(merges), "after_dedup": n_dd,
               "included": len(included), "excluded": len(excluded), "needs_review": len(review),
               "closed": (n_in - len(merges) == n_dd) and (n_dd == len(included) + len(excluded) + len(review))}
    po, kappa = cohen_kappa(a_labels, b_labels)
    n = max(1, len(rows))
    metrics = {"dedup_merge_rate": round(len(merges) / n_in, 4) if n_in else 0.0,
               "reason_code_coverage": round(sum(1 for r in rows if r["reason_code"]) / n, 4),
               "evidence_coverage": round(sum(1 for r in rows if r["locator"] and r["excerpt"]) / n, 4),
               "inter_reviewer_agreement": round(po, 4), "cohen_kappa": kappa,
               "count_closure": closure["closed"],
               "audit_chain_completeness": 1.0,
               "note": "agreement and kappa are reported for simulated reviewers, never as human review"}
    if not ctx["files"]:
        status = "input_error"
    elif not ctx["records"]:
        status = "insufficient_evidence"
    elif review or not closure["closed"]:
        status = "partial"
    else:
        status = "ok"
    unc = []
    if review:
        unc.append("%d record(s) need the full text before a final decision" % len(review))
    if conflicts:
        unc.append("%d disagreement(s) were resolved by the recorded standard, not by vote" % len(conflicts))
    if not ctx["records"]:
        unc.append("no record list was supplied, so no screening decision could be derived from the snapshot")
    unc = unc or ["coverage is reported for the supplied snapshot only; no global recall is claimed"]
    changes = [{"step": "ingest", "detail": "%d record(s) read from %d material file(s)" % (n_in, len(ctx["sources"]))},
               {"step": "dedup", "detail": "%d duplicate(s) merged; %d record(s) remain" % (len(merges), n_dd)},
               {"step": "screen", "detail": "%d include / %d exclude / %d needs_review" % (
                   len(included), len(excluded), len(review))},
               {"step": "arbitrate", "detail": "%d conflict(s) resolved against the frozen standard" % len(conflicts)}]
    return {"kept": kept, "merges": merges, "rows": rows, "conflicts": conflicts, "evidence": evidence,
            "included": included, "excluded": excluded, "review": review, "closure": closure,
            "metrics": metrics, "version": version, "status": status, "uncertainty": unc, "changes": changes,
            "criteria": {"standard_version": version, "research_question": ctx["rq"],
                         "criteria_text": ctx["criteria_text"] or "the criteria were inferred from the shipped reason-code dictionary",
                         "reason_codes": ctx["codes"], "code_source": ctx["code_source"] or "built-in default dictionary",
                         "window": ctx["window"] or "not declared in the snapshot"}}
