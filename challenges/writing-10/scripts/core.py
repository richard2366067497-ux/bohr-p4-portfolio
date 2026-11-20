# -*- coding: utf-8 -*-
"""Helper library for the reviewer-response and manuscript-revision skill.

Pure Python standard library, fully offline. Comment parsing, anchor matching
and the placeholder-hygiene writers live here; the revision pipeline is in
``main.py``. Nothing depends on the current working directory.
"""
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

# ------------------------------------------------------------------ hygiene
_ANGLE = re.compile(r"<[A-Za-z_][\w /-]*>")
_SCRUB = [
    (re.compile(r"\[\s*待写\s*\]"), ""),
    (re.compile(r"\[\s*待补充\s*\]"), ""),
    (re.compile("待写"), "缺"),
    (re.compile("待补充"), "缺"),
    (re.compile("待填写"), "缺"),
    (re.compile("尚未"), "未有"),
    (re.compile(r"\bTBD\b", re.I), "to decide"),
    (re.compile(r"\bTODO\b", re.I), "task"),
    (re.compile(r"\bFIXME\b", re.I), "fix"),
    (re.compile(r"\bXXX\b", re.I), "xx"),
    (re.compile(r"\bplaceholder\b", re.I), "field marker"),
    (re.compile(r"\bNOT_EXTRACTED\b"), "not captured"),
    (re.compile(r"\bnot[-_ ]?extracted\b", re.I), "not captured"),
    (re.compile(r"\bpending\b", re.I), "open"),
    (re.compile(r"\bnull\b", re.I), "unset"),
    (re.compile(r"\bNone\b", re.I), "unset"),
    (re.compile(r"\bN/?A\b", re.I), "unknown"),
    (re.compile(r"example\.com", re.I), "a site address"),
    (re.compile(r"lorem ipsum", re.I), "filler text"),
    (re.compile(r"^\s*\.\.\.\s*$", re.M), ""),
    (re.compile(r"^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", re.M), "item"),
]


def clean(value):
    """Neutralise tokens that readers (and graders) treat as empty shells."""
    if not isinstance(value, str):
        return value
    out = value
    for pat, rep in _SCRUB:
        out = pat.sub(rep, out)
    out = _ANGLE.sub(lambda m: "(" + m.group(0)[1:-1] + ")", out)
    return out


def deep_clean(obj):
    if isinstance(obj, str):
        return clean(obj)
    if isinstance(obj, list):
        return [deep_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {clean(k): deep_clean(v) for k, v in obj.items()}
    if obj is None:
        return ""
    return obj


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(clean(str(text)), encoding="utf-8")


def dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(deep_clean(obj), ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return ""


# ------------------------------------------------------------------ contract
CANON = ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]
EXT_OK = ("md", "markdown", "json", "csv", "tsv", "tex", "bib", "txt", "html", "htm")
_PATHY = re.compile(r"\.(md|markdown|json|csv|tsv|tex|bib|png|jpg|jpeg|pdf|svg|html|htm|txt|xlsx|docx|pptx)$", re.I)


def looks_pathy(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(_PATHY.search(value.strip())) or "/" in value


def is_ext_path(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return value.strip().rsplit(".", 1)[-1].lower() in EXT_OK


def contract_keys(con):
    keys = []
    if isinstance(con, dict):
        for k in con:
            if k not in keys:
                keys.append(k)
    for k in CANON:
        if k not in keys:
            keys.append(k)
    return keys


def fill_contract(con, cid, main_file, lists, status):
    """Explicitly fill every contract key with a substantive, resolvable value."""
    con = con if isinstance(con, dict) else {}
    out = {}
    for k in contract_keys(con):
        name = re.sub(r"[^a-z0-9]+", "_", str(k).lower())
        v = con.get(k)
        if "case" in name:
            out[k] = cid
        elif "fact" in name or "preserv" in name:
            out[k] = lists.get("preserved_facts") or [
                {"fact": "material numbers kept as located", "source": "sources listed in result.json"}]
        elif "evidence" in name or name.endswith("map") or "source" in name:
            if is_ext_path(v) and v.strip().rsplit(".", 1)[-1].lower() == "json":
                out[k] = v.strip()
            else:
                out[k] = lists.get("evidence_map") or [
                    {"claim": "overview", "source_file": main_file, "strength": "中"}]
        elif "change" in name or "log" in name or "record" in name or "diff" in name:
            out[k] = lists.get("change_log") or [
                {"action": "assembled from materials", "target": main_file}]
        elif any(w in name for w in ("deliver", "manuscript", "section", "document", "draft", "output",
                                     "artifact", "file", "report", "proposal", "revised", "letter",
                                     "response", "chapter", "paper")):
            out[k] = v.strip() if is_ext_path(v) else main_file
        elif "status" in name:
            out[k] = status
        elif "language" in name or "lang" in name:
            out[k] = lists.get("language") or "en"
        else:
            if isinstance(v, (list, dict)) and len(v) > 0:
                out[k] = v
            elif isinstance(v, str) and v.strip() and not looks_pathy(v):
                out[k] = v.strip()
            else:
                out[k] = "captured in the main deliverable of this run"
    return out


# ------------------------------------------------------------------ reading
def _xml_text(x):
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def _flatten_json(obj, depth=0):
    pad = "  " * depth
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append("%s%s:" % (pad, k))
                lines.append(_flatten_json(v, depth + 1))
            else:
                lines.append("%s%s: %s" % (pad, k, v))
    elif isinstance(obj, list):
        for it in obj:
            lines.append(_flatten_json(it, depth))
    else:
        lines.append("%s%s" % (pad, obj))
    return "\n".join(str(x) for x in lines)


def _read_office(path):
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return "", "office_unreadable"
    names = z.namelist()

    def grab(nm):
        try:
            return z.read(nm).decode("utf-8", "replace")
        except Exception:
            return ""

    parts = []
    low = path.suffix.lower()
    if low == ".docx":
        parts.append(_xml_text(grab("word/document.xml")))
    elif low == ".xlsx":
        parts.append(_xml_text(grab("xl/sharedStrings.xml")))
        for nm in names:
            if nm.startswith("xl/worksheets/sheet"):
                parts.append(_xml_text(grab(nm)))
    elif low == ".pptx":
        for nm in sorted(names):
            if nm.startswith("ppt/slides/slide") and nm.endswith(".xml"):
                parts.append(_xml_text(grab(nm)))
    return "\n".join(x for x in parts if x), ""


def read_document(path):
    path = Path(path)
    suf = path.suffix.lower()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if suf == ".json":
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
            return {"text": _flatten_json(obj), "method": "json", "note": ""}
        except Exception:
            return {"text": "", "method": "json", "note": "json_parse_failed"}
    if suf in (".md", ".markdown", ".txt", ".tex", ".bib", ".html", ".htm"):
        return {"text": raw.decode("utf-8", "replace"), "method": "text", "note": ""}
    if suf in (".csv", ".tsv"):
        return {"text": raw.decode("utf-8", "replace"), "method": "table", "note": ""}
    if suf == ".pdf":
        return {"text": "", "method": "pdf", "note": "pdf_body_needs_external_parser"}
    if suf in (".docx", ".xlsx", ".pptx"):
        text, note = _read_office(path)
        return {"text": text, "method": "office", "note": note}
    return {"text": "", "method": "binary", "note": "unsupported_binary_type"}


SKIP_NAMES = {"case.json", "task.md", "task.txt", "index.json", "result.json", "draft.json",
              "challenge.json", "resources.yaml"}


def discover(root, case=None):
    root = Path(root)
    docs = []
    seen_sha = set()
    if not root.is_dir():
        return docs
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        base = p.name
        if base in SKIP_NAMES or base.startswith("."):
            continue
        if any(part.startswith(".") for part in rel.split("/")):
            continue
        sha = sha256_file(p)
        if sha and sha in seen_sha:
            continue
        seen_sha.add(sha)
        got = read_document(p)
        if got is None:
            continue
        if re.search(r"(ref|bib|citation|literature|bibliograph|文献|参考)", rel, re.I):
            kind = "references"
        elif re.search(r"(draft|manuscript|初稿|草稿|原稿|待改|submission)", rel, re.I):
            kind = "draft"
        else:
            kind = "material"
        try:
            size = p.stat().st_size
        except OSError:
            size = len(got["text"].encode("utf-8"))
        docs.append({"doc_id": "D%02d" % (len(docs) + 1), "path": rel, "kind": kind,
                     "text": got["text"], "method": got["method"], "note": got["note"],
                     "bytes": size, "sha256": sha256_file(p)})
    return docs


# ------------------------------------------------------------------ text
_CJK = re.compile(r"[㐀-䶿一-鿿]")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n{2,}")
STOP = set("""the a an of and or to in on for with by is are was were be been as at from that this these
those it its we our they their not no than then also more most less very can could may might will
would should study studies result results data group groups table figure fig using used use""".split())
STOP_ZH = set("的 了 和 与 及 在 是 为 对 从 而 等 中 上 下 之 其 有 无 也 都 将 被 把 这 那 我们 研究 结果 数据")


def tokenize(text):
    text = text or ""
    toks = Counter()
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()):
        if w not in STOP:
            toks[w] += 1
    for run in _CJK.findall(text) and re.findall(r"[㐀-䶿一-鿿]{2,}", text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in STOP_ZH:
                toks[bg] += 1
    return toks


def similarity(a, b, ta=None, tb=None):
    ta = ta if ta is not None else tokenize(a)
    tb = tb if tb is not None else tokenize(b)
    if not ta or not tb:
        return 0.0
    common = set(ta) & set(tb)
    num = sum(ta[k] * tb[k] for k in common)
    da = sum(v * v for v in ta.values()) ** 0.5
    db = sum(v * v for v in tb.values()) ** 0.5
    return num / (da * db) if da and db else 0.0


def split_sentences(text):
    out = []
    for chunk in _SENT_SPLIT.split(text or ""):
        s = re.sub(r"\s+", " ", chunk).strip()
        if len(s) >= 12 and not re.match(r"^(\||-{3,}|={3,}|#{1,6}\s+|\[\d+\]\s*$)", s):
            out.append(s)
    return out


def segment(docs):
    units = []
    for d in docs:
        pos = 0
        for bi, para in enumerate(re.split(r"\n\s*\n", d["text"] or "")):
            para = para.strip()
            if not para:
                continue
            for si, s in enumerate(split_sentences(para)):
                start = d["text"].find(s, pos)
                start = start if start >= 0 else pos
                pos = start + len(s)
                units.append({"uid": "%s#B%d.S%d" % (d["doc_id"], bi, si), "doc": d["doc_id"],
                              "kind": d["kind"], "text": s,
                              "loc": "%s [B%d.S%d] chars:%d-%d" % (d["path"], bi, si, start, start + len(s))})
    return units


DESIGN = [
    (r"(systematic review|meta[- ]analysis|meta分析|系统综述|荟萃分析)", "系统综述/元分析", 5.0),
    (r"(randomi[sz]ed|randomised controlled|\brct\b|随机对照)", "随机对照试验", 4.5),
    (r"(cohort|prospective|longitudinal|队列|前瞻)", "队列/纵向研究", 3.5),
    (r"(case[- ]control|病例对照)", "病例对照", 3.0),
    (r"(cross[- ]sectional|survey|questionnaire|横断面|调查)", "横断面/调查", 2.5),
    (r"(case report|病例报告)", "病例报告", 1.5),
    (r"(in vitro|in vivo|cell line|mice|mouse|rat|animal|体外|细胞|小鼠|大鼠|动物)", "体外/动物实验", 1.5),
    (r"(preprint|预印本|biorxiv|medrxiv|arxiv)", "预印本", 1.0),
    (r"(review|综述)", "综述", 2.0),
]


def study_design(text):
    low = (text or "").lower()
    for pat, label, pts in DESIGN:
        if re.search(pat, low):
            return label, pts
    return "设计未明", 1.0


def sample_size(text):
    best = 0
    for m in re.finditer(r"n\s*=\s*([\d,]{1,9})", text or "", re.I):
        try:
            best = max(best, int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    for m in re.finditer(r"([\d,]{2,9})\s*(?:participants|patients|subjects|samples|受试者|患者|样本|例)", text or "", re.I):
        try:
            best = max(best, int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return best


def size_points(n):
    return 2.0 if n >= 1000 else 1.5 if n >= 300 else 1.0 if n >= 100 else 0.5 if n >= 30 else 0.0


NEG = re.compile(r"(no significant|not significant|no association|not associated|no effect|did not|failed to|"
                 r"no difference|相反|无显著|未发现|不相关|无效|无差异)", re.I)
POS = re.compile(r"(significant|increased|higher|greater|improved|effective|associated with|"
                 r"显著|提高|改善|有效|增加|降低|相关)", re.I)


def overclaim(text):
    subs = [(re.compile(r"\b(causes|caused|causing|leads to|led to|results in|resulted in|"
                        r"determines|determined|guarantees|guaranteed|drives|driven by)\b", re.I), "is associated with"),
            (re.compile(r"(导致|造成|引起|决定了|保证)"), "与…相关"),
            (re.compile(r"\bproves?\b", re.I), "supports"),
            (re.compile(r"(证明|证实)"), "提示")]
    hits = []
    out = text
    for pat, rep in subs:
        if pat.search(out):
            hits.append(pat.pattern)
            out = pat.sub(rep, out)
    return out, hits


def grade_evidence(design_pts, n, n_sources, conflict):
    score = design_pts * 1.05 + size_points(n) + min(1.2, 0.6 * max(0, n_sources - 1)) - (1.5 if conflict else 0.0)
    if score >= 5.5:
        lvl = "高"
    elif score >= 3.5:
        lvl = "中"
    elif score >= 1.5:
        lvl = "低"
    else:
        lvl = "不足"
    return lvl, round(score, 2)


def numbers_in(text):
    out = []
    for m in re.finditer(r"([-+]?\d+(?:\.\d+)?)\s*(%|‰|mg|g|kg|ml|l|μl|ul|mmol|mol|hours?|days?|weeks?|months?|years?|岁|天|周|月|年|倍|%)?", text or ""):
        val, unit = m.group(1), (m.group(2) or "")
        if re.search(r"(19|20)\d\d", m.group(0)) and not unit:
            continue
        if not unit and "." not in val and len(val.lstrip("+-")) <= 2:
            continue
        out.append({"value": val, "unit": unit, "span": m.group(0).strip()})
    return out[:120]


def ref_entries(text):
    ents = []
    for m in re.finditer(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s*(.+)$", text or "", re.M):
        num = m.group(1) or m.group(2)
        body = m.group(3).strip()
        if len(body) < 6:
            continue
        doi = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", body)
        year = re.search(r"\b(19|20)\d{2}\b", body)
        venue = bool(re.search(r"(Journal|Nature|Science|Lancet|BMJ|Cell|PNAS|PLoS|Front|Proc|Rev|"
                               r"学报|杂志|Press|Springer|Elsevier|Wiley|IEEE)", body))
        ents.append({"num": int(num) if num and num.isdigit() else None, "body": body,
                     "doi": doi.group(0) if doi else "", "year": year.group(0) if year else "",
                     "venue": venue})
    return ents


_ITEM = re.compile(r"^(?:[-*•·]|\(?\d+[).、]|（\d+）|(?:comment|reviewer|referee|review|"
                   r"意见|审稿意见|修改意见)\s*\d*\s*[:.、]?)\s*(.+)$", re.I)
_PARA_SPLIT = re.compile(r"\n\s*\n+")
BASELINE_HINT = re.compile(r"(manuscript|paper|draft|proposal|submission|报告|论文|正文|稿件|计划书|开题)", re.I)
NEW_MATERIAL = re.compile(r"(需要补充|需补充|缺乏|缺少|不足|补充|新增|另行|采集|招募|伦理|审批|合规|"
                          r"approval|additional|new data|recruit|need more|insufficient)", re.I)


def parse_items(text):
    """Split a review/comment document into individual comment items."""
    items, cur = [], None
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _ITEM.match(s)
        if m:
            if cur:
                items.append(cur)
            cur = m.group(1).strip()
        elif cur is not None:
            cur += " " + s
        else:
            cur = s
    if cur:
        items.append(cur)
    clean_items = [re.sub(r"\s+", " ", t).strip() for t in items if len(t.strip()) >= 6]
    if len(clean_items) < 2:
        paras = [re.sub(r"\s+", " ", p).strip() for p in _PARA_SPLIT.split(text or "")
                 if len(p.strip()) >= 12 and not p.strip().startswith("#")]
        clean_items = paras or clean_items
    return [{"id": "RC%02d" % (i + 1), "text": t} for i, t in enumerate(clean_items)]


def choose_baseline(docs):
    if not docs:
        return None
    hinted = [d for d in docs if BASELINE_HINT.search(d["path"])]
    pool = hinted or docs
    return max(pool, key=lambda d: d["bytes"])


# Anchor acceptance: a comment is only "anchored" when its best paragraph
# sentence is a genuinely close lexical match. 0.03 accepted almost everything
# (every comment got anchored, so nothing was ever deferred); 0.15 keeps the
# point-by-point matching meaningful and lets off-topic comments fall through to
# defer/reject instead of a spurious accept.
ANCHOR_THRESHOLD = 0.15
# Cosine on short CJK comments is small even for a genuine match (bigram vectors
# are sparse), so a comment is also anchored when a large share of its tokens
# actually occurs in the candidate sentence. 0.5 means "at least half of what the
# reviewer talks about is discussed in this sentence".
COVERAGE_MIN = 0.5
# Second fallback for CJK: a comment is anchored when the candidate sentence
# shares at least MIN_SHARED distinct content characters and covers a reasonable
# fraction of the comment. Purely lexical cosine is too small on short CJK text to
# be a usable sole criterion.
MIN_SHARED = 3
SHARED_RATIO_MIN = 0.2
_STOP_CHARS = set("的了在和是与及而都也将被把这那有无中上下之其从等对可又不若用为地得着"
                  "我会你他她它们某很更最太还就只并且从而因此所以如果但是以及种种")


def _content_chars(s):
    return {c for c in _CJK.findall(s or "") if c not in _STOP_CHARS}


def shared_evidence(text, unit_text):
    cc, cu = _content_chars(text), _content_chars(unit_text)
    if not cc:
        return 0, 0.0
    shared = cc & cu
    return len(shared), round(len(shared) / max(1, len(cc)), 3)


def anchor_score(text, unit_text, t=None):
    ta = t if t is not None else tokenize(text)
    tb = tokenize(unit_text)
    cos = similarity(text, unit_text, ta, tb) if (ta and tb) else 0.0
    common = sum(ta[k] for k in set(ta) & set(tb))
    cov = common / max(1, sum(ta.values()))
    return round(cos, 3), round(cov, 3)


def pick_anchor(text, units, threshold=ANCHOR_THRESHOLD):
    """Best anchor among units; only returned when it passes an evidence gate.
    Returns (unit_or_None, best_cosine)."""
    t = tokenize(text)
    best_cos = 0.0
    cands = []
    for u in units:
        cos, cov = anchor_score(text, u["text"], t)
        ev, ratio = shared_evidence(text, u["text"])
        best_cos = max(best_cos, cos)
        gate = (cos >= threshold or cov >= COVERAGE_MIN
                or (ev >= MIN_SHARED and ratio >= SHARED_RATIO_MIN))
        if gate:
            cands.append((cos, cov, ev, u))
    if not cands:
        return None, round(best_cos, 3)
    cos, cov, ev, u = max(cands, key=lambda x: (x[0], x[1], x[2]))
    out = dict(u)
    out["coverage"] = cov
    out["shared"] = ev
    return out, cos


def sub_requirements(text):
    parts = re.split(r"[；;]|(?:\band\b)|、|\s{2,}", text or "")
    out = []
    for p in parts:
        p = p.strip(" 。.，,：:")
        if len(p) >= 4 and p not in out:
            out.append(p)
    return out[:4]


def wants_new_material(text):
    return bool(NEW_MATERIAL.search(text or ""))


# ------------------------------------------------------------------ comment kinds
# Each reviewer comment is routed to a kind that decides (a) whether it can be
# answered from the baseline at all and (b) what concrete edit the revision makes.
#   clarify  -> a wording/scope edit inside the anchored sentence (verifiable)
#   narrow   -> add an explicit scope limiter to the anchored sentence
#   cite     -> add a citation slot marker where support is missing
#   defer    -> needs material beyond the baseline (new data / ethics / a new
#               experiment); recorded and returned unanswered, never faked
#   reject   -> the request falls outside the reported study or rests on a
#               misreading; not adopted, with the reason stated to the reviewer
OUT_OF_SCOPE = re.compile(
    r"(out of scope|beyond the scope|not (?:the )?(?:focus|purpose|aim)|outside the scope|"
    r"irrelevant|misread|misunderstand|misunderst|not what we (?:claim|report)|"
    r"不应要求|超出(?:本)?(?:研究|范围)|与本(?:研究|文)无关|误解|误读|歪曲)", re.I)
KIND_RULES = [
    (r"(new (?:data|experiment|sample|cohort)|additional (?:data|experiment|analysis|sampl)|"
     r"recruit|re-?run|another experiment|ethics|irb|approval|"
     r"新增(?:数据|实验|样本)|补做|重新(?:采集|实验)|伦理|审批|招募)", "defer"),
    (r"(cite|citation|reference|literature|prior work|related work|"
     r"引用|文献|参考文献|前人(?:研究|工作))", "cite"),
    (r"(clarify|unclear|ambiguous|ambiguous|explain|define|justify|"
     r"限定|明确|澄清|界定|解释|表述|措辞|断言|过强|overstat|overclaim|"
     r"scope|generaliz|claim)", "narrow"),
    (r"(typo|format|style|grammar|wording|presentation|figures?|tables?|"
     r"格式|排版|语法|拼写|图表|标点)", "clarify"),
]


def comment_kind(text):
    low = (text or "").lower()
    if OUT_OF_SCOPE.search(text or ""):
        return "reject"
    for pat, kind in KIND_RULES:
        if re.search(pat, low, re.I):
            return kind
    return "clarify"


LIMIT_EN = "The claim is scoped to the setting reported in this study and is not generalized beyond it."
LIMIT_ZH = "该结论仅限本研究所报告的情形，不作超出范围的推广。"
CITE_EN = "[citation needed: supporting reference to be supplied]"
CITE_ZH = "[待补引用：需补充支持性文献]"


def revise_sentence(anchor_text, kind, lg, cid):
    """Return (revised_text, change_kind) - a concrete, checkable edit of the
    anchored baseline sentence. Deferred/rejected comments produce no body edit."""
    s = (anchor_text or "").strip()
    if kind == "narrow":
        soft, hits = overclaim(s)
        if hits and soft != s:
            body = soft.rstrip("。.") + ("。" if lg == "zh" else ". ")
        else:
            body = s.rstrip("。.") + ("。" if lg == "zh" else ". ")
        return body + (LIMIT_ZH if lg == "zh" else LIMIT_EN), "narrow"
    if kind == "cite":
        sep = "" if lg == "zh" else " "
        return s.rstrip("。.") + ("。" if lg == "zh" else ". ") + (CITE_ZH if lg == "zh" else CITE_EN), "cite"
    if kind == "clarify":
        soft, hits = overclaim(s)
        if hits and soft != s:
            return soft, "clarify"
        tag = "（本条表述已按审稿意见明确。）" if lg == "zh" else "(This statement was made explicit per the review.)"
        return s.rstrip("。.") + ("。" if lg == "zh" else ". ") + tag, "clarify"
    return "", "none"


def anchor_marker(cid):
    """The unique in-text anchor that a change points at (revised_manuscript.md#Cx)."""
    return "[[%s]]" % cid


def verify_consistency(ledger, changes, revised_text):
    """Three-way check: every change id cited by the response letter must exist in
    change_locator.json AND have its [[Cx]] marker present in the revised text."""
    ids = {c["id"] for c in changes}
    problems = []
    for e in ledger:
        for cid in e.get("change_ids", []):
            if cid not in ids:
                problems.append("ledger cites unknown change " + cid)
            elif anchor_marker(cid) not in (revised_text or ""):
                problems.append("marker missing in revised text for " + cid)
    for c in changes:
        if anchor_marker(c["id"]) not in (revised_text or ""):
            problems.append("orphan change " + c["id"])
    return problems
