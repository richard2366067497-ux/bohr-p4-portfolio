"""claim-preserving-polish — 输入发现、切段、术语候选与守卫判定。

这是包的"机械"半边：只做可复现的解析与比对，不做语义替代。
Agent 负责在工作稿 draft.json 里写 before/after/类型/理由；本模块判定它是否守恒。
"""
import csv
import io
import json
import os
import re
from collections import Counter

import polish_core as pc

TEXT_EXT = (".md", ".markdown", ".txt", ".tex", ".latex", ".rst", ".csv", ".json", ".bib", ".yaml", ".yml")
TEXT_KEYS = ("material", "manuscript", "materials", "source_text", "input_text", "original", "draft_text",
             "document", "paper", "text", "content", "body", "paragraphs", "sections", "full_text")
SKIP_FILES = {"case.json", "task.md", "challenge.json", "manifest.json"}
GENRES = [
    ("grant", ("基金", "申请书", "grant", "proposal", "funding")),
    ("review_response", ("审稿", "回复意见", "rebuttal", "response to review", "reviewer")),
    ("thesis", ("学位论文", "毕业论文", "thesis", "dissertation")),
    ("abstract", ("摘要", "abstract")),
    ("bilingual", ("双语", "bilingual", "中英对照")),
    ("journal", ("期刊", "投稿", "journal", "manuscript")),
]

def _is_glossary_name(name):
    low = str(name or "").lower()
    return any(k in low for k in ("glossar", "terminolog", "lexicon", "术语", "词表"))

def find_key(obj, key, depth=0):
    if depth > 3:
        return None
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        for val in obj.values():
            got = find_key(val, key, depth + 1)
            if got not in (None, "", [], {}):
                return got
    elif isinstance(obj, list):
        for val in obj[:20]:
            got = find_key(val, key, depth + 1)
            if got not in (None, "", [], {}):
                return got
    return None

def _leaf_texts(node, via, depth=0):
    out = []
    if depth > 3 or node is None:
        return out
    if isinstance(node, str):
        if node.strip():
            out.append({"text": node, "via": via})
    elif isinstance(node, list):
        for item in node:
            out.extend(_leaf_texts(item, via, depth + 1))
    elif isinstance(node, dict):
        for key, val in node.items():
            lk = str(key).lower()
            if lk in ("path", "file", "filename", "filepath") and isinstance(val, str):
                out.append({"path": val, "via": via + "." + lk})
            elif lk in TEXT_KEYS or lk in ("value", "raw"):
                out.extend(_leaf_texts(val, via + "." + lk, depth + 1))
    return out

def discover(input_dir, case_path, task_path):
    """返回 (case, materials, task_text, errors, degradations)。缺任何东西都不抛异常。"""
    errors, degradations, materials = [], [], []
    case = {}
    if os.path.isfile(case_path):
        try:
            with open(case_path, "r", encoding="utf-8") as fh:
                case = json.load(fh)
            if not isinstance(case, dict):
                errors.append("case.json 顶层不是对象；按空案例继续")
                case = {}
        except Exception as exc:  # noqa: BLE001
            errors.append("case.json 解析失败：%s" % exc)
            degradations.append("case.json 不可解析，改为扫描目录内文本材料")
    else:
        errors.append("未找到 %s" % case_path)

    task_text = ""
    if os.path.isfile(task_path):
        task_text, _enc, warn = pc.read_text_any(task_path)
        if warn:
            degradations.append("task.md 读取告警：%s" % warn)
    else:
        errors.append("未找到 %s" % task_path)
    instruction = find_key(case, "task_instruction") or find_key(case, "instruction") or ""
    if isinstance(instruction, (dict, list)):
        instruction = json.dumps(instruction, ensure_ascii=False)
    if instruction:
        task_text = (task_text or "") + "\n\n" + str(instruction)

    seen = set()
    for key in TEXT_KEYS:
        if key not in case:
            continue
        for leaf in _leaf_texts(case[key], key):
            if "path" in leaf:
                cand = leaf["path"]
                full = cand if os.path.isabs(cand) else os.path.join(input_dir, os.path.basename(cand))
                txt, _e, warn = pc.read_text_any(full)
                if warn:
                    degradations.append("材料读取告警 %s：%s" % (os.path.basename(full), warn))
                if not txt.strip():
                    errors.append("材料路径无法读取：%s" % cand)
                    continue
                leaf = {"text": txt, "via": leaf["via"], "path": full}
            txt = leaf["text"]
            h = pc.sha256_text(pc.norm_ws(txt))
            if h in seen:
                continue
            if task_text and pc.similarity(txt[:4000], task_text[:4000]) > 0.85:
                degradations.append("字段 %s 与 task.md 高度重合，判为任务说明而非原稿" % leaf["via"])
                continue
            seen.add(h)
            leaf["role"] = "glossary" if _is_glossary_name(leaf.get("path") or leaf.get("via", "")) else "body"
            materials.append(leaf)

    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            full = os.path.join(input_dir, name)
            if not os.path.isfile(full) or name in SKIP_FILES or name.startswith("."):
                continue
            low = name.lower()
            if low.endswith((".docx", ".pdf", ".png", ".jpg", ".zip", ".xlsx", ".pptx")):
                degradations.append("跳过二进制材料 %s：本 Skill 只处理文本原稿" % name)
                continue
            if not low.endswith(TEXT_EXT):
                continue
            txt, _e, warn = pc.read_text_any(full)
            if warn:
                degradations.append("材料读取告警 %s：%s" % (name, warn))
            if not txt.strip():
                continue
            h = pc.sha256_text(pc.norm_ws(txt))
            if h in seen or (task_text and pc.similarity(txt[:4000], task_text[:4000]) > 0.85):
                continue
            seen.add(h)
            materials.append({"text": txt, "via": "dir:" + name, "path": full,
                              "role": "glossary" if _is_glossary_name(name) else "body"})

    if not materials and (task_text or "").strip():
        degradations.append("未发现原稿材料，回退以 task.md 文本作为待处理全文（可能只是任务说明）")
        materials.append({"text": task_text, "via": "task.md", "path": task_path, "role": "body"})
    return case, materials, task_text or "", errors, degradations

def build_profile(materials, task_text, case):
    text = "\n\n".join(m["text"] for m in materials)
    blob = (task_text + "\n" + pc.norm_ws(text[:2000])).lower()
    genre = "journal"
    for name, keys in GENRES:
        if any(k.lower() in blob for k in keys):
            genre = name
            break
    clean = re.sub(r"(不|无|无需|不需|不要|不做|不再|avoid|no|without)\s*(双语|中英对照|对照表|bilingual|translation|翻译)",
                   " ", blob)
    mode = "polish"
    if any(k in clean for k in ("translate", "译成", "翻译成", "target language", "英文版", "译稿")):
        mode = "translate"
    elif any(k in clean for k in ("双语", "bilingual", "中英对照")):
        mode = "bilingual"
    contract = find_key(case, "output_contract") or {}
    doc_name = "input"
    for mat in materials:
        path = mat.get("path") or ""
        if path:
            doc_name = os.path.basename(path)
            break
    return {
        "genre": genre, "language": pc.detect_language(text), "mode": mode,
        "chars": len(text), "doc_name": doc_name,
        "task_excerpt": pc.norm_ws(task_text)[:700],
        "contract_fields": [name for name, _ in pc.shape_contract(contract)],
        "material_count": len(materials),
    }

def build_segments(materials):
    text = "\n\n".join(m["text"] for m in materials)
    lex = pc.load_lexicon()
    paragraphs, offset = [], 0
    for idx, block in enumerate(pc.split_paragraphs(text), 1):
        body = block["text"]
        start = text.find(body, offset)
        if start < 0:
            start = offset
        end = start + len(body)
        offset = end
        sentences, cur = [], 0
        for s_idx, sent in enumerate(pc.split_sentences(body), 1):
            pos = body.find(sent, cur)
            if pos < 0:
                pos = cur
            sentences.append({"idx": s_idx, "start": pos, "end": pos + len(sent), "text": sent})
            cur = pos + len(sent)
        lvl, hits = pc.hedge(body, lex)
        paragraphs.append({
            "id": "P%03d" % idx, "kind": block["kind"], "text": body, "chars": len(body),
            "start": start, "end": end, "sentences": sentences,
            "hedge": {"level": lvl, "markers": hits},
            "atoms": pc.extract_spans(body, lex),
            "negation": pc.negation_count(body, lex),
        })
    return text, paragraphs

def parse_glossary_text(text):
    """解析术语表：JSON / 带表头的 CSV / 无表头的两列文本。
    关键：只把 variants 列当异写，note 之类的列不能被误认为变体。"""
    stripped = (text or "").strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
        except Exception:  # noqa: BLE001
            data = None
        rows = data if isinstance(data, list) else (data.get("terms") if isinstance(data, dict) else None)
        if isinstance(rows, list):
            return [normalize_term(r) for r in rows if isinstance(r, dict)]
    try:
        rows = [r for r in csv.reader(io.StringIO(stripped)) if any(cell.strip() for cell in r)]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        return []
    head = [c.strip().lower() for c in rows[0]]
    alias = {"term": ("term", "术语", "concept", "概念", "source"), "locked": ("locked", "锁定", "target", "译法", "写法"),
             "variants": ("variants", "variant", "变体", "异写"), "abbr": ("abbr", "缩写"),
             "note": ("note", "备注", "说明")}
    index = {}
    for key, names in alias.items():
        for pos, cell in enumerate(head):
            if any(name == cell or name in cell for name in names):
                index.setdefault(key, pos)
                break
    has_header = "term" in index or "locked" in index
    body = rows[1:] if has_header else rows
    entries = []
    for row in body:
        if len(row) < 2 and not has_header:
            continue

        def cell(key, default=""):
            pos = index.get(key)
            return row[pos].strip() if pos is not None and pos < len(row) else default

        term = cell("term") or (row[0].strip() if row else "")
        locked = cell("locked") or (row[1].strip() if len(row) > 1 else term)
        if not term or not locked:
            continue
        variants = [v.strip() for v in re.split(r"[|;、]", cell("variants")) if v.strip() and v.strip() != locked]
        if not has_header and len(row) > 2:
            variants = [v.strip() for v in row[2:] if v.strip() and v.strip() != locked]
        entries.append({"concept": term, "locked": locked, "variants": variants,
                        "abbr": cell("abbr"), "note": cell("note"), "source": "input:glossary"})
    return entries

def normalize_term(row):
    concept = row.get("concept") or row.get("term") or row.get("source") or ""
    locked = row.get("locked") or row.get("locked_form") or row.get("target") or concept
    variants = row.get("variants") or []
    if isinstance(variants, str):
        variants = [v.strip() for v in re.split(r"[|;、,]", variants) if v.strip()]
    return {"concept": concept, "locked": locked, "variants": variants,
            "abbr": row.get("abbr") or "", "note": row.get("note") or "",
            "source": "input:glossary"}

def provided_glossary(input_dir, materials):
    entries = []
    for mat in materials:
        name = (mat.get("path") or "").lower()
        if "glossar" in name or "terminolog" in name or "术语" in name:
            entries.extend(parse_glossary_text(mat["text"]))
    if os.path.isdir(input_dir):
        for fname in sorted(os.listdir(input_dir)):
            low = fname.lower()
            if "glossar" in low or "terminolog" in low or "术语" in low:
                txt, _e, _w = pc.read_text_any(os.path.join(input_dir, fname))
                entries.extend(parse_glossary_text(txt))
    uniq, seen = [], set()
    for entry in entries:
        key = pc.canon(entry.get("concept") or entry.get("locked") or "")
        if key and key not in seen:
            seen.add(key)
            uniq.append(entry)
    return uniq

def term_candidates(text, paragraphs, provided):
    lex = pc.load_lexicon()
    out, seen = [], set()
    for entry in provided:
        key = pc.canon(entry.get("concept") or entry.get("locked") or "")
        if key and key not in seen:
            seen.add(key)
            out.append(dict(entry))
    head = text[:60000]
    for m in re.finditer(r"([A-Za-z][A-Za-z\-]*(?:\s+[A-Za-z][A-Za-z\-]*){1,6})\s*\(([A-Z]{2,6})s?\)", head):
        concept, abbr = m.group(1).strip(), m.group(2)
        if pc.canon(abbr) in seen:
            continue
        seen.add(pc.canon(abbr))
        out.append({"concept": concept, "abbr": abbr, "locked": "%s (%s)" % (concept, abbr),
                    "variants": [], "source": "auto:definition"})
    abbr_all = [a for p in paragraphs for a in p["atoms"]["abbr"]]
    for abbr, count in Counter(abbr_all).most_common(8):
        if pc.canon(abbr) in seen:
            continue
        seen.add(pc.canon(abbr))
        out.append({"concept": abbr, "abbr": abbr, "locked": abbr, "variants": [],
                    "source": "auto:frequent-abbr", "count": count})
    fn_chars = set("个在的了和与并为是有该这对从到被将把由及或等也都就而但于以很更最均各每中上下其此之者所即可需能会要")
    for suffix in lex.get("term_candidate_suffixes", [])[:16]:
        for m in re.finditer(r"([\u4e00-\u9fa5]{2,8}%s)" % re.escape(suffix), head):
            term = m.group(1)
            if pc.canon(term) in seen or any(ch in fn_chars for ch in term):
                continue
            seen.add(pc.canon(term))
            out.append({"concept": term, "locked": term, "variants": [], "source": "auto:zh-suffix"})
    stop = set(("the a an of for and with to in on at by from that this these those we our is are was were "
                "be been it as which has have not than into using used can may also both such more most").split())
    tokens = [(m.group(0), m.start()) for m in re.finditer(r"[A-Za-z][A-Za-z\-]{2,}", head)]
    grams = Counter()
    for i in range(len(tokens)):
        for n in (2, 3):
            if i + n > len(tokens):
                continue
            words = [t[0] for t in tokens[i:i + n]]
            if any(w.lower() in stop for w in words):
                continue
            phrase = " ".join(words)
            if len(phrase) < 9:
                continue
            grams[phrase.lower()] += 1
    added = 0
    for phrase, count in grams.most_common(60):
        if added >= 8 or count < 2:
            continue
        if pc.canon(phrase) in seen:
            continue
        seen.add(pc.canon(phrase))
        out.append({"concept": phrase, "locked": phrase, "variants": [],
                    "source": "auto:repeated-phrase", "count": count})
        added += 1
    for entry in out:
        needle = entry.get("abbr") or entry.get("concept") or ""
        entry.setdefault("variants", [])
        if not entry.get("first_use"):
            entry["first_use"] = next((p["id"] for p in paragraphs if needle and needle in p["text"]), "")
    return out[:40]

def _changes_of(item):
    raw = item.get("changes")
    if isinstance(raw, str):
        return []
    return [c for c in (raw or []) if isinstance(c, dict)]

def verify_item(item, base, profile):
    """单条守卫判定。返回 (record, new_base|None, hard_fail)。"""
    lex = pc.load_lexicon()
    pid = item.get("paragraph_id")
    lang = pc.detect_language(item.get("before") or base)
    rec = {"paragraph_id": pid, "codes": [], "hard": [], "soft": [], "verdict": "pass"}

    def flag(code, severity, detail):
        entry = {"code": code, "severity": severity, "detail": detail}
        rec["codes"].append(entry)
        (rec["hard"] if severity == "hard" else rec["soft"]).append(entry)

    after = item.get("after")
    if after is None:
        rec["verdict"] = "noop"
        return rec, None, False
    if not str(after).strip():
        flag("EMPTY_AFTER", "hard", "after 为空：润色不能把段落清空")
        rec["verdict"] = "rolled_back"
        return rec, None, True

    before_use = item.get("before") or base
    span = pc.find_span(base, before_use)
    if span is None:
        flag("ANCHOR_MISS", "hard", "before 无法在原文定位：必须逐字复制 show 输出的原文")
        rec["verdict"] = "rolled_back"
        return rec, None, True

    before_spans = pc.extract_spans(before_use, lex)
    after_spans = pc.extract_spans(after, lex)
    lost, added = pc.diff_atoms(before_spans, after_spans)
    if lost:
        flag("PROTECTED_ATOM_LOST", "hard", "改文丢失不可编辑原子：%s" % "、".join(
            "%s%s×%d" % (pc.ATOM_LABELS.get(x["class"], x["class"]), x["value"], x["count"]) for x in lost[:6]))
    if added:
        flag("ATOM_ADDED", "soft", "改文新增原子（可能引入材料外内容）：%s" % "、".join(
            "%s%s×%d" % (pc.ATOM_LABELS.get(x["class"], x["class"]), x["value"], x["count"]) for x in added[:4]))
    ab_lost, _ = pc.diff_atoms(before_spans, after_spans, ("abbr",))
    if ab_lost:
        flag("ABBR_CHANGED", "soft", "缩写/专名出现次数变化：%s（若为首现展开请在 changes 说明）"
             % "、".join(x["value"] for x in ab_lost[:5]))

    lvl_b, hit_b = pc.hedge(pc.mask_presentation(before_use), lex, lang)
    lvl_a, hit_a = pc.hedge(pc.mask_presentation(after), lex, lang)
    has_b, has_a = bool(hit_b), bool(hit_a)
    override = item.get("hedge_override") if isinstance(item.get("hedge_override"), dict) else {}
    override_reason = str(override.get("reason") or "").strip()
    if profile.get("mode") == "translate":
        if lvl_a != lvl_b or has_b != has_a:
            flag("HEDGE_UNCHECKED_TRANSLATE", "soft", "跨语言改写：限定强度无法词面比对（原文 %s / 改文 %s），需人工核对"
                 % ("、".join(hit_b) or "无标记", "、".join(hit_a) or "无标记"))
    elif has_b and not has_a:
        if pc.negation_count(after, lex, lang) > pc.negation_count(before_use, lex, lang):
            flag("HEDGE_DROPPED_NEGATED", "soft", "限定词消失但改文改为否定句：%s，需人工确认等价" % "、".join(hit_b[:4]))
        elif override_reason:
            flag("HEDGE_SHIFT_DECLARED", "soft", "限定词消失且已声明理由：%s" % override_reason)
        else:
            flag("HEDGE_DROPPED", "hard", "限定词 %s 在改文中消失（结论被加强）" % "、".join(hit_b[:4]))
    elif not has_b and has_a:
        flag("HEDGE_ADDED", "soft", "改文新增限定词 %s（结论被削弱）；若有意请写 hedge_override" % "、".join(hit_a[:4]))
    elif has_b and has_a and lvl_a != lvl_b:
        detail = "限定强度 %s(%s) → %s(%s)" % (lvl_b, "、".join(hit_b[:3]), lvl_a, "、".join(hit_a[:3]))
        if override_reason:
            flag("HEDGE_SHIFT_DECLARED", "soft", detail + "；已声明理由：" + override_reason)
        else:
            flag("CLAIM_STRENGTHENED" if lvl_a > lvl_b else "CLAIM_WEAKENED", "hard", detail + "；须保持原强度或写 hedge_override")

    core_b = pc.claim_core(pc.mask_presentation(before_use), lex, lang)
    core_a = pc.claim_core(pc.mask_presentation(after), lex, lang)
    cb, ca = Counter(core_b), Counter(core_a)
    dropped_core = [m for m in cb if ca.get(m, 0) < cb[m]]
    if dropped_core and profile.get("mode") != "translate" and not override_reason and lvl_a <= lvl_b:
        flag("HEDGE_MARKER_DROPPED", "hard",
             "主张内核词被删除：%s（句中其他限定词仍在，整体等级不变，但原句的限定被撤掉）"
             % "、".join(sorted(dropped_core)[:5]))

    assoc_b, causal_b = pc.association_terms(before_use, lex, lang), pc.causal_terms(before_use, lex, lang)
    assoc_a, causal_a = pc.association_terms(after, lex, lang), pc.causal_terms(after, lex, lang)
    if assoc_b and causal_a and not causal_b:
        flag("CAUSAL_UPGRADE", "hard", "相关表述（%s）被改成因果（%s）" % ("、".join(assoc_b[:3]), "、".join(causal_a[:3])))
    elif causal_b and assoc_a and not assoc_b and not causal_a:
        flag("CAUSAL_DOWNGRADE", "soft", "因果表述被降级为相关，需作者确认")

    neg_b, neg_a = pc.negation_count(before_use, lex, lang), pc.negation_count(after, lex, lang)
    if neg_b != neg_a:
        flag("NEGATION_SCOPE_CHANGED", "hard" if lang == "en" else "soft", "否定标记数 %d → %d" % (neg_b, neg_a))

    abs_b, abs_a = set(pc.absolutes(before_use, lex, lang)), set(pc.absolutes(after, lex, lang))
    if abs_a - abs_b:
        flag("ABSOLUTE_ADDED", "soft", "新增绝对化表述：%s" % "、".join(sorted(abs_a - abs_b)[:4]))

    changed = pc.norm_ws(before_use) != pc.norm_ws(after)
    ratio = pc.similarity(before_use, after)
    rec["similarity"] = round(ratio, 3)
    changes = _changes_of(item)
    if changed and profile.get("mode") != "translate":
        override_types = {str(c.get("type", "")).lower() for c in changes}
        if ratio < 0.50 and not (override_types & pc.OVERRIDE_TYPES):
            flag("REWRITE_RISK", "hard", "字符相似度 %.2f，接近整段重写；最小编辑要求句内改动，重构须标注 restructure/translate" % ratio)
        if not changes:
            flag("CHANGES_MISSING", "hard", "文本已改但未提供 changes（原文/改文/类型/理由）")
    elif not changed and changes:
        flag("NOOP_WITH_CHANGES", "soft", "before 与 after 相同却登记了 changes")

    for c_idx, ch in enumerate(changes, 1):
        ctype = str(ch.get("type") or "").strip().lower()
        reason = str(ch.get("reason") or "").strip()
        bs, as_ = str(ch.get("before_span") or ""), str(ch.get("after_span") or "")
        if ctype not in pc.EDIT_TYPES:
            flag("EDIT_TYPE_INVALID", "hard", "change#%d 类型 %r 不在编辑类型词表内" % (c_idx, ctype))
        if len(reason) < 4 or pc.canon(reason) in pc.WEAK_REASONS:
            flag("REASON_MISSING", "hard", "change#%d 缺少可判断的理由（不能只写“更学术/更好”）" % c_idx)
        if bs and as_:
            if pc.norm_ws(bs) not in pc.norm_ws(before_use):
                flag("SPAN_ANCHOR_BEFORE", "soft", "change#%d 的 before_span 未在原文逐字出现" % c_idx)
            if pc.norm_ws(as_) not in pc.norm_ws(after):
                flag("SPAN_ANCHOR_AFTER", "soft", "change#%d 的 after_span 未在改文逐字出现" % c_idx)
            if pc.norm_ws(bs) == pc.norm_ws(as_):
                flag("SPAN_NOOP", "soft", "change#%d 的原文片段与改文片段相同" % c_idx)

    s0, e0 = span
    rec["locator"] = "%s#%s[%d:%d]" % (profile.get("doc_name", "input"), pid, s0, s0 + len(before_use))
    if rec["hard"]:
        rec["verdict"] = "rolled_back"
        return rec, None, True
    rec["verdict"] = "review" if rec["soft"] else "pass"
    return rec, base[:s0] + after + base[e0:], False

def empty_report(segments):
    paragraphs = {}
    for para in segments["paragraphs"]:
        lvl, hit = pc.hedge(para["text"])
        paragraphs[para["id"]] = {
            "changed": False, "similarity": 1.0, "atoms_lost": [], "atoms_added": [],
            "hedge_before": {"level": lvl, "markers": hit}, "hedge_after": {"level": lvl, "markers": hit},
            "negation_before": para["negation"], "negation_after": para["negation"],
            "final_text": para["text"],
        }
    editable = [p["id"] for p in segments["paragraphs"] if p["kind"] in ("body", "heading")]
    return {
        "records": [], "working": {p["id"]: p["text"] for p in segments["paragraphs"]},
        "paragraphs": paragraphs, "pending": [], "hard_count": 0, "rolled_back": [],
        "untouched": {}, "missing_coverage": editable,
        "counts": {"paragraphs_total": len(segments["paragraphs"]), "editable": len(editable),
                   "covered": 0, "changed": 0, "unchanged": len(editable),
                   "needs_human": 0, "items": 0, "rolled_back_items": 0},
    }

def verify_draft(draft, segments, profile):
    paras = {p["id"]: p for p in segments["paragraphs"]}
    working = {pid: p["text"] for pid, p in paras.items()}
    records, pending, hard_count = [], [], 0
    items = [i for i in (draft.get("items") or []) if isinstance(i, dict)]
    for item in items:
        pid = item.get("paragraph_id")
        if pid not in paras:
            rec = {"paragraph_id": pid, "codes": [{"code": "ANCHOR_UNKNOWN_PID", "severity": "hard",
                                                   "detail": "段落 id 不存在于本案例"}],
                   "hard": [{"code": "ANCHOR_UNKNOWN_PID", "detail": "段落 id 不存在"}], "soft": [],
                   "verdict": "rolled_back"}
            records.append(rec)
            hard_count += 1
            continue
        rec, new_base, failed = verify_item(item, working[pid], profile)
        rec["item"] = item.get("segment_id") or pid
        records.append(rec)
        if failed:
            hard_count += 1
            pending.append({
                "id": "H%03d" % len(pending), "paragraph_id": pid,
                "issue": "；".join("%s：%s" % (c["code"], c.get("detail", "")) for c in rec["hard"])[:400],
                "need": "确认此处是否必须修改；当前已回退原文",
                "options": ["接受回退（保留原文）", "按最小编辑重写该处后复跑 check", "人工润色并更新 changes"],
                "severity": "high",
            })
        else:
            working[pid] = new_base
            for soft in rec["soft"]:
                pending.append({
                    "id": "S%03d" % len(pending), "paragraph_id": pid,
                    "issue": "%s：%s" % (soft["code"], soft.get("detail", ""))[:400],
                    "need": "人工确认该处是否仍表达作者主张",
                    "options": ["保持改文", "恢复原文", "调整措辞后复跑 check"],
                    "severity": "medium",
                })

    para_report = {}
    for pid, para in paras.items():
        final = working[pid]
        lost, added = pc.diff_atoms(pc.extract_spans(para["text"]), pc.extract_spans(final))
        lvl0, hit0 = pc.hedge(para["text"])
        lvl1, hit1 = pc.hedge(final)
        para_report[pid] = {
            "changed": pc.norm_ws(final) != pc.norm_ws(para["text"]),
            "similarity": round(pc.similarity(para["text"], final), 3),
            "atoms_lost": lost, "atoms_added": added,
            "hedge_before": {"level": lvl0, "markers": hit0},
            "hedge_after": {"level": lvl1, "markers": hit1},
            "negation_before": pc.negation_count(para["text"]),
            "negation_after": pc.negation_count(final),
            "final_text": final,
        }
        if lost:
            hard_count += 1
            working[pid] = para["text"]
            para_report[pid].update({"reverted": True, "final_text": para["text"]})
            pending.append({
                "id": "H%03d" % len(pending), "paragraph_id": pid,
                "issue": "段落级守恒复核失败，整段回退原文：%s" % "、".join(
                    "%s%s" % (pc.ATOM_LABELS.get(x["class"], x["class"]), x["value"]) for x in lost[:6]),
                "need": "确认数字/单位/引用/图表指向是否应保持一致",
                "options": ["保持原文", "修正改文后复跑 check"],
                "severity": "high",
            })

    declared = {u.get("paragraph_id"): str(u.get("reason") or "")
                for u in (draft.get("untouched") or []) if isinstance(u, dict)}
    covered = set(declared)
    for item in items:
        if item.get("paragraph_id") in paras:
            covered.add(item.get("paragraph_id"))
    editable = [p["id"] for p in segments["paragraphs"] if p["kind"] in ("body", "heading")]
    rolled = sorted({p["paragraph_id"] for p in pending if p["severity"] == "high"})
    return {
        "records": records, "working": working, "paragraphs": para_report,
        "pending": pending, "hard_count": hard_count, "rolled_back": rolled,
        "untouched": declared, "missing_coverage": [pid for pid in editable if pid not in covered],
        "counts": {
            "paragraphs_total": len(segments["paragraphs"]), "editable": len(editable),
            "covered": len([p for p in editable if p in covered]),
            "changed": len([1 for p in para_report.values() if p["changed"]]),
            "unchanged": len([pid for pid in editable if not para_report[pid]["changed"]]),
            "needs_human": len(rolled), "items": len(items),
            "rolled_back_items": sum(1 for r in records if r.get("verdict") == "rolled_back"),
        },
    }
