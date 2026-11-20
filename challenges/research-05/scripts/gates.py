#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""research-topic-gatekeeper 规则层：工作稿解析、逐条证据定位校验、五门 gate 判据、兜底工作稿。
纯标准库、离线、不依赖 CWD。所有判断基于 index.json 中真实抽取的文本，不做任何案例硬编码。"""
import json, os, re
from pathlib import Path

OVERLAP = ("method", "data", "scenario", "conclusion", "none")
CSTATUS = ("comparable", "not_comparable")
NTYPE = ("method", "data", "scenario_transfer", "conclusion_correction")
NVERD = ("covered", "novel", "undetermined")
ASTATE = ("source", "assumed", "unsupported")
ACAT = ("data", "compute", "experiment", "time", "people", "ethics")
VERDICT = ("go", "conditional", "no_go")

GATES = (("G1", "worth_doing", "值得做吗：研究问题是否被拆成可检验的表述"),
         ("G2", "nobody_done", "别人做到哪一步：最近的同类工作是否已覆盖设想"),
         ("G3", "can_do", "做得出来吗：数据/算力/实验/时间/人员/伦理前提是否成立"),
         ("G4", "not_old_wine", "不是旧方案吗：每条创新陈述与最近工作是否逐条划清边界"),
         ("G5", "downside", "失败会怎样：kill criteria、残余风险与退出成本"))

# 模糊措辞（出现即要求给可测量替换或标 untestable）
VAGUE = re.compile(r"(显著提升|大幅提升|明显改善|性能更好|效果更好|更有优势|国际领先|填补空白|首创|"
                   r"有效解决|较好效果|较高精度|大幅降低|state[- ]of[- ]the[- ]art|significantly better|"
                   r"novel and effective|填补了空白)", re.I)
# 把"检索不到"当"新颖"的禁用表述
FALSE_NOVEL = re.compile(r"(检索不到|未检索到|检索无结果|没有检索到|无人研究|尚无人研究|尚无人做过|无人做过|"
                         r"未见报道|没有任何研究|没有相关研究|no (?:existing|prior) work|nothing has been done|"
                         r"first to (?:study|propose))", re.I)
NEG_CTX = re.compile(r"(不代表|不等同|不等于|并非|不是|不得|不能|避免|禁止|而非|no claim)")
NEGATE = re.compile(r"(相反|不一致|相矛盾|未能复现|无法复现|不成立|然而.*(?:未能|没有)|no significant|"
                    r"contradict|inconsistent|failed to reproduce|did not (?:improve|outperform)|"
                    r"no improvement|contrary to)", re.I)
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|个月|月|年|周|天|小时|h|例|名|人|次|万|亿|GB|TB|GPU|核|token|s|min)")


def norm(s):
    s = str(s if s is not None else "").replace("\ufeff", "").replace("\r\n", "\n")
    return re.sub(r"[\s\u3000]+", " ", s).strip()


def al(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def dicts(v):
    return [x for x in al(v) if isinstance(x, dict)]


def strs(v):
    return [norm(x) for x in al(v) if norm(x)]


def paras(text, cap=1600):
    out = []
    for b in [x.strip() for x in re.split(r"\n\s*\n", str(text or ""))]:
        while len(b) > cap:
            cut = b.rfind("\n", 0, cap)
            cut = cut if cut > 200 else cap
            out.append(b[:cut].strip())
            b = b[cut:].strip()
        if b:
            out.append(b)
    return out or ([norm(text)] if norm(text) else [])


def load_json(p):
    p = Path(p)
    if not p.is_file():
        return None, "not_found"
    err = "unreadable"
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(p.read_text(encoding=enc).lstrip("\ufeff")), None
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
    return None, err


def dump_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(t, p)


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


# ---------------- 证据语料与逐条定位校验 ----------------
def corpus(index):
    """返回 [(id, locator, normtext_lower)]：材料段落 + 材料全文 + 对象内联文本。"""
    rows = []
    for m in index.get("materials", []):
        for pa in m.get("paras", []):
            t = norm(pa.get("text")).lower()
            if t:
                rows.append((m["id"], pa["loc"], t))
        body = norm(m.get("text")).lower()
        if body:
            rows.append((m["id"], "body", body))
    for o in index.get("object_texts", []):
        t = norm(o.get("text")).lower()
        if t:
            rows.append((o["id"], o.get("locator") or "inline", t))
    return rows


def _ordered(rows, sid):
    sid = norm(sid)
    first = [r for r in rows if r[0] == sid] if sid else []
    return first + [r for r in rows if not sid or r[0] != sid]


def find_quote(rows, sid, quote):
    q = norm(quote).lower()
    if len(q) < 6:
        return None
    for r in _ordered(rows, sid):
        if q in r[2]:
            return r[0], r[1], "exact"
    segs = [norm(s).lower() for s in re.split(r"…|\.\.\.|⋯|\.\.\.\.", str(quote)) if len(norm(s)) >= 6]
    if len(segs) > 1:
        for r in _ordered(rows, sid):
            if all(s in r[2] for s in segs):
                return r[0], r[1], "segments"
    qs = re.sub(r"\s+", "", q)
    if len(qs) >= 6:
        for r in _ordered(rows, sid):
            if qs in re.sub(r"\s+", "", r[2]):
                return r[0], r[1], "despaced"
    return None


def gather_evidence(draft):
    """收集工作稿里所有证据三元组，保留其归属引用 ref。"""
    out = []
    for d in walk(draft):
        ev = d.get("evidence")
        if isinstance(ev, list):
            ref = str(d.get("claim_id") or d.get("id") or d.get("topic") or d.get("name") or "")
            for e in ev:
                if isinstance(e, dict) and norm(e.get("quote")):
                    out.append({"ref": ref, "claim_id": d.get("claim_id"), "source_id": e.get("source_id"),
                                "locator": e.get("locator"), "quote": norm(e.get("quote")),
                                "polarity": norm(e.get("polarity")).lower() or "support"})
    return out


def verify(rows, corpus_rows):
    res, bad = [], []
    for r in rows:
        hit = find_quote(corpus_rows, r.get("source_id"), r.get("quote"))
        row = dict(r)
        if hit:
            row.update(status="verified", found_source=hit[0], found_locator=hit[1], match=hit[2])
        else:
            row.update(status="quote_not_found")
            bad.append(row)
        res.append(row)
    return res, bad


def claim_index(draft, ev_rows):
    """claim_id -> 已验证证据条数 / 关联 source。"""
    m = {}
    for e in ev_rows:
        if e.get("claim_id"):
            d = m.setdefault(norm(e["claim_id"]), {"verified": 0, "total": 0, "sources": []})
            d["total"] += 1
            if e.get("status") == "verified":
                d["verified"] += 1
                if e.get("found_source"):
                    d["sources"].append(e["found_source"])
    return m


# ---------------- 五门 gate 判据 ----------------
def false_novel(text):
    """只在“把检索不到当新颖”的肯定用法上命中；带否定/免责语境的表述不算。"""
    t = norm(text)
    for m in FALSE_NOVEL.finditer(t):
        if NEG_CTX.search(t[max(0, m.start() - 14):m.start()]):
            continue
        return m.group(0)
    return ""


def question_split(q):
    return [k for k in ("object", "variables", "baseline", "expected") if norm(q.get(k))]


def check(draft, index):
    E, W, G = [], [], []
    err = lambda c, m: E.append({"code": c, "msg": m})
    warn = lambda c, m: W.append({"code": c, "msg": m})
    gap = lambda item, why: G.append({"item": item, "why": why, "needed_by": "定稿前"})
    corpus_rows = corpus(index)
    ev_rows, bad = verify(gather_evidence(draft), corpus_rows)
    ci = claim_index(draft, ev_rows)
    hit = sum(1 for e in ev_rows if e.get("status") == "verified")
    ratio = (hit / len(ev_rows)) if ev_rows else 0.0
    for b in bad[:8]:
        warn("W_QUOTE", "引文未逐字命中 %s @%s: %s" % (b.get("source_id") or "?", b.get("locator") or "?",
                                                  b.get("quote")[:46]))
    if bad:
        gap("%d 条引文未命中" % len(bad), "quote 改写/跨段/来源编号错；仅命中条目可作证据")

    # ---- G1 问题可检验
    q = draft.get("question") or {}
    split = question_split(q)
    if not norm(q.get("problem_statement")):
        err("E_G1_STATEMENT", "question.problem_statement 缺失：需要一句可检验的问题陈述")
    if len(split) < 4:
        err("E_G1_SPLIT", "问题拆解不全，缺 %s" % "、".join(
            k for k in ("object", "variables", "baseline", "expected") if k not in split))
    if not strs(q.get("falsification")):
        err("E_G1_FALSIFY", "question.falsification 为空：必须写清何种观测会否定该设想")
    vm = VAGUE.findall(norm(q.get("problem_statement")))
    rep = strs([(x.get("vague") if isinstance(x, dict) else x) for x in al(q.get("vague_replaced"))])
    if vm and not rep:
        warn("W_G1_VAGUE", "问题陈述含模糊措辞（%s）但未登记 vague_replaced" % "、".join(sorted(set(vm))[:3]))

    # ---- G2 已有工作比较
    mat = dicts(draft.get("matrix"))
    src_ids = {norm(s.get("sid")) for s in index.get("objects", {}).get("sources", []) if s.get("sid")}
    src_ids |= {norm(m["id"]) for m in index.get("materials", [])}
    if not mat:
        err("E_G2_MATRIX", "matrix 为空：至少为每条创新陈述填 1 行最近工作对照")
    for i, r in enumerate(mat, 1):
        rid = norm(r.get("claim_id")) or "row%d" % i
        if norm(r.get("overlap")).lower() not in OVERLAP:
            err("E_G2_OVERLAP", "%s overlap=%r 不在 %s" % (rid, r.get("overlap"), "/".join(OVERLAP)))
        st = norm(r.get("comparison_status")).lower()
        if st not in CSTATUS:
            err("E_G2_STATUS", "%s comparison_status=%r 不在 comparable/not_comparable" % (rid, r.get("comparison_status")))
        if st == "not_comparable" and not norm(r.get("cannot_compare_reason")):
            err("E_G2_REASON", "%s 标为 not_comparable 但未写 cannot_compare_reason" % rid)
        sid = norm(r.get("source_id"))
        if sid and sid not in src_ids:
            err("E_G2_FAKE", "%s source_id=%s 不在输入对象表内（疑似编造文献）" % (rid, sid))
        if not norm(r.get("boundary_note")):
            warn("W_G2_BOUNDARY", "%s 缺 boundary_note：没有说明与设想的边界差别" % rid)
    per_claim = {}
    for r in mat:
        per_claim[norm(r.get("claim_id"))] = per_claim.get(norm(r.get("claim_id")), 0) + 1

    # ---- G3 可行性前提
    asm = dicts(draft.get("assumptions"))
    if len(asm) < 3:
        err("E_G3_ASSUMPTIONS", "assumptions 少于 3 条：数据/算力/实验/时间/人员/伦理至少覆盖 3 类")
    cats = {norm(a.get("category")).lower() for a in asm if norm(a.get("category")).lower() in ACAT}
    if asm and len(cats) < 3:
        warn("W_G3_CATS", "前提类别只覆盖 %d 类（%s）" % (len(cats), "、".join(sorted(cats)) or "—"))
    for a in asm:
        aid = norm(a.get("id")) or "A?"
        st = norm(a.get("state")).lower()
        if st not in ASTATE:
            err("E_G3_STATE", "%s state=%r 不在 source/assumed/unsupported" % (aid, a.get("state")))
        if not norm(a.get("kill_criteria")):
            err("E_G3_KILL", "%s 缺 kill_criteria：无法判定何时放弃" % aid)
        if st == "source":
            ok = any(e.get("status") == "verified" and (e.get("ref") == aid or norm(a.get("source_locator"))
                     and norm(a.get("source_locator")) in (e.get("found_locator") or "")) for e in ev_rows)
            if not ok:
                err("E_G3_UNSOURCED", "%s 标为 source 但无可核验的逐字证据/定位" % aid)
        if not norm(a.get("validation_experiment")):
            warn("W_G3_VALID", "%s 缺 validation_experiment：看不出用什么最小实验把 assumed 变成 source" % aid)

    # ---- G4 创新判定
    nov = dicts(draft.get("novelty"))
    if not nov:
        err("E_G4_NOVELTY", "novelty 为空：每条创新陈述必须给类型与覆盖判定")
    for n in nov:
        cid = norm(n.get("claim_id")) or "C?"
        t = norm(n.get("type")).lower()
        v = norm(n.get("verdict")).lower()
        if t not in NTYPE:
            err("E_G4_TYPE", "%s type=%r 不在 method/data/scenario_transfer/conclusion_correction" % (cid, n.get("type")))
        if v not in NVERD:
            err("E_G4_VERDICT_ENUM", "%s verdict=%r 不在 covered/novel/undetermined" % (cid, n.get("verdict")))
        if v == "covered" and not strs(n.get("covered_by")):
            err("E_G4_COVERED_BY", "%s 判为 covered 但未给 covered_by" % cid)
        if v == "novel" and not norm(n.get("boundary")):
            err("E_G4_BOUNDARY", "%s 判为 novel 但未写 boundary（与最近工作的差别）" % cid)
        blob = norm(n.get("boundary")) + " " + norm(n.get("rationale"))
        if v == "novel" and false_novel(blob) and per_claim.get(cid, 0) < 2:
            err("E_G4_FALSE_NOVEL", "%s 用“检索不到/无人研究”支撑新颖性且对照行不足 2 条" % cid)
        if per_claim.get(cid, 0) < 1:
            warn("W_G4_NOMATRIX", "%s 没有任何对照行" % cid)

    # ---- G5 反证与退出
    conf = dicts(draft.get("conflicts"))
    contradict = [e for e in ev_rows if norm(e.get("polarity")).lower() == "contradict"]
    if contradict and not conf:
        err("E_CONFLICT_UNLOGGED", "存在 %d 条 polarity=contradict 的证据但 conflicts 为空" % len(contradict))
    if not conf and not norm(draft.get("no_contrary_found")):
        err("E_CONFLICT_SILENT", "既无 conflicts 也无 no_contrary_found 说明：不允许只报支持性证据")
    for c in conf:
        if not (al(c.get("support")) and al(c.get("contradict"))):
            warn("W_CONFLICT_PAIR", "冲突条目 %r 缺 support/contradict 一侧的原话" % norm(c.get("topic"))[:24])
        if not norm(c.get("resolution")):
            warn("W_CONFLICT_RES", "冲突条目 %r 未写取舍理由" % norm(c.get("topic"))[:24])

    # ---- 研究空白（禁止全局断言）
    gp = draft.get("research_gap") or {}
    if not norm(gp.get("statement")):
        err("E_GAP_STATEMENT", "research_gap.statement 缺失：需说明材料范围内的空白")
    if gp.get("global_claim") in (True, "true", "True", 1):
        err("E_GAP_GLOBAL", "research_gap.global_claim=true：不得断言全局无人研究")
    if norm(gp.get("statement")) and (false_novel(norm(gp.get("statement"))) or not norm(gp.get("scope"))):
        warn("W_GAP_SCOPE", "空白陈述应限定 scope（本材料/本时间窗范围内）")
    if not al(gp.get("basis")):
        warn("W_GAP_BASIS", "空白陈述无 basis 证据")

    # ---- 五门 gate 卡片
    gd = {}
    for g in dicts(draft.get("gates")):
        gd[norm(g.get("gate_id")).upper()] = g
    for gid, name, qs in GATES:
        g = gd.get(gid)
        if not g:
            err("E_GATE_MISSING", "缺 %s（%s）" % (gid, name))
            continue
        v = norm(g.get("verdict")).lower()
        if v not in VERDICT:
            err("E_GATE_VERDICT", "%s verdict=%r 不在 go/conditional/no_go" % (gid, g.get("verdict")))
        if v in ("conditional", "no_go"):
            if not strs(g.get("conditions")):
                err("E_G5_COND", "%s 判为 %s 但未写 conditions" % (gid, v))
            if not norm(g.get("pivot_if_no_go")):
                err("E_G5_PIVOT", "%s 判为 %s 但未给 pivot_if_no_go" % (gid, v))
        eids = strs(g.get("evidence_ids"))
        if not eids:
            err("E_GATE_NOEVID", "%s 无 evidence_ids：判定必须能回到具体证据" % gid)
        else:
            miss = [x for x in eids if x not in ci or not ci[x]["verified"]]
            if miss:
                err("E_GATE_BADEVID", "%s evidence_ids 未解析到已验证证据：%s" % (gid, "、".join(miss[:4])))
        if v == "go" and gid == "G1" and (len(split) < 4 or not strs(q.get("falsification"))):
            err("E_G1_GO", "G1 判 go 但问题未拆全/无判伪条件")
        if v == "go" and gid == "G3" and any(norm(a.get("state")).lower() == "unsupported" for a in asm):
            err("E_G3_GO", "G3 判 go 但存在 unsupported 前提")
        if v == "go" and gid == "G4" and any(norm(n.get("verdict")).lower() == "undetermined" for n in nov):
            warn("W_G4_GO", "G4 判 go 但存在 undetermined 的创新判定")

    # ---- 综合结论一致性
    dec = draft.get("decision") or {}
    overall = norm(dec.get("overall")).lower()
    if overall not in VERDICT:
        err("E_DECISION", "decision.overall=%r 不在 go/conditional/no_go" % dec.get("overall"))
    if overall == "go" and any(norm(g.get("verdict")).lower() == "no_go" for g in gd.values()):
        err("E_DECISION_INCONSISTENT", "总判定 go 但存在 no_go 的 gate")
    if overall == "go" and any(norm(g.get("verdict")).lower() == "conditional" for g in gd.values()):
        err("E_DECISION_INCONSISTENT", "总判定 go 但存在 conditional 的 gate：应降为 conditional 并给条件")
    if not norm(dec.get("summary")):
        err("E_DECISION_SUMMARY", "decision.summary 缺失")
    if overall in ("go", "conditional") and not dicts(dec.get("next_validation")):
        warn("W_DECISION_NEXT", "缺 next_validation：没写什么证据能把结论推进到下一步")

    # ---- 检索协议与覆盖
    sp = draft.get("search_protocol") or {}
    if not strs(sp.get("queries")):
        warn("W_SEARCH_QUERIES", "search_protocol.queries 为空：检索式无法复核")
    if not norm(sp.get("windows") or sp.get("date_window")):
        warn("W_SEARCH_WINDOW", "search_protocol 未给时间窗")
    if not nums(sp.get("screened")):
        warn("W_SEARCH_SCREENED", "search_protocol.screened 未给筛选条数")

    # ---- 数字溯源
    blob = json.dumps(draft, ensure_ascii=False)
    alltext = " ".join(r[2] for r in corpus_rows)
    stray = []
    for m in NUM.finditer(blob):
        v = norm(m.group(0))
        if v.lower() not in alltext and v not in stray:
            stray.append(v)
    if stray:
        warn("W_NUMBER", "数字在材料中无同形文本（须标计划值或补依据）：" + "、".join(stray[:8]))

    six = {
        "problem_decomposition": bool(len(split) == 4 and strs(q.get("falsification"))),
        "search_coverage": bool(strs(sp.get("queries")) and norm(sp.get("windows") or sp.get("date_window")) and nums(sp.get("screened"))),
        "evidence_backlink": bool(ev_rows) and ratio >= 0.8,
        "conflict_evidence": bool(conf) or bool(norm(draft.get("no_contrary_found"))),
        "synthesis": bool(norm(dec.get("summary"))) and len(gd) >= 5,
        "research_gap": bool(norm(gp.get("statement"))) and bool(al(gp.get("basis"))),
    }
    cov = {"six_checks": six, "six_passed": sum(1 for v in six.values() if v),
           "question_fields": split, "gates": len(gd), "matrix_rows": len(mat),
           "novelty_claims": len(nov), "assumptions": len(asm),
           "assumption_states": _tally(asm, "state"), "conflicts": len(conf),
           "evidence_total": len(ev_rows), "evidence_verified": hit,
           "evidence_hit_rate": round(ratio, 3), "contradicting_evidence": len(contradict),
           "readable_materials": sum(1 for m in index.get("materials", []) if m.get("chars")),
           "materials": len(index.get("materials", []))}
    counts = {"gates_present": len(gd), "gates_total": 5, "matrix_rows": len(mat),
              "novelty": len(nov), "assumptions": len(asm), "conflicts": len(conf),
              "evidence_total": len(ev_rows), "evidence_verified": hit,
              "six_passed": cov["six_passed"], "errors": len(E), "warnings": len(W)}
    return {"errors": E, "warnings": W, "gaps": G, "coverage": cov, "evidence": ev_rows,
            "claim_index": ci, "counts": counts}


def nums(v):
    try:
        return int(str(v).strip().split(".")[0]) if str(v).strip() else 0
    except Exception:
        return len(re.findall(r"\d+", str(v))) and 1 or 0


def _tally(rows, k):
    out = {}
    for r in rows:
        v = norm(r.get(k)).lower() or "unset"
        out[v] = out.get(v, 0) + 1
    return out


# ---------------- 工作稿加载 ----------------
def load_draft(work):
    for name in ("draft.json", "gate_draft.json", "draft.md"):
        p = Path(work) / name
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            return {}, str(p), "unreadable: %s" % e
        if name.endswith(".md"):
            return md_draft(txt), str(p), "draft.md 仅为叙事稿，结构化字段使用兜底"
        try:
            obj = json.loads(txt.lstrip("\ufeff"))
        except Exception as e:
            return {}, str(p), "json_invalid: %s" % e
        return (obj, str(p), None) if isinstance(obj, dict) else ({}, str(p), "draft.json 非对象")
    return {}, None, "无工作稿（%s/draft.json）" % work


MD_HINT = (("G1", ("问题", "可检验", "question")), ("G2", ("比较", "已有工作", "prior")),
           ("G3", ("可行", "前提", "feasib")), ("G4", ("创新", "novel")), ("G5", ("风险", "kill", "失败")))


def md_draft(text):
    """极简 md 兜底：只抽出段落归到 gate，其余字段留给兜底模板；status 必为 partial。"""
    cur, buf = None, {}
    for line in str(text).split("\n"):
        h = re.match(r"^\s{0,3}#{1,4}\s*(.+?)\s*$", line)
        if h:
            low = h.group(1).lower()
            cur = next((g for g, kws in MD_HINT if any(k in low for k in kws)), None)
            continue
        if cur and norm(line):
            buf.setdefault(cur, []).append(norm(line))
    return {"_md_sections": {k: " ".join(v)[:1200] for k, v in buf.items()}, "_from_md": True}


def seeds(index, limit=8):
    rows = [(m["id"], pa["loc"], norm(pa.get("text"))) for m in index.get("materials", [])
            for pa in m.get("paras", []) if len(norm(pa.get("text"))) >= 60
            and not re.match(r"^[#>|*\-{]", norm(pa.get("text")))]
    for o in index.get("object_texts", []):
        if len(norm(o.get("text"))) >= 60:
            rows.append((o["id"], o.get("locator") or "inline", norm(o.get("text"))))
    rows.sort(key=lambda r: -min(len(r[2]), 700))
    return [{"source_id": r[0], "locator": r[1], "text": r[2]} for r in rows[:limit]]


def fallback_draft(index, case_id, why="无可用工作稿"):
    """兜底：只用索引里真实存在的文本，判据一律 conditional，绝不编造文献/结论。"""
    smap = {s.get("material"): s.get("sid") for s in index.get("objects", {}).get("sources", []) if s.get("material")}
    sd = seeds(index, 8)
    for r in sd:
        r["sid"] = smap.get(r["source_id"], r["source_id"])
    ev = lambda rs: [{"source_id": r["sid"], "locator": r["locator"],
                      "quote": r["text"][:200], "polarity": "support"} for r in rs]
    srcs = [s for s in index.get("objects", {}).get("sources", []) if s.get("sid")][:12]
    if not srcs:
        srcs = [{"sid": m["id"], "title": m.get("rel")} for m in index.get("materials", [])[:8]]
    claims = []
    for i, s in enumerate(srcs[:6], 1):
        pool = [r for r in sd if r["sid"] == s.get("sid")] or sd[:1]
        claims.append({"claim_id": "C%d" % i,
                       "text": "输入材料 %s 与当前设想的关系尚需人工确认（%s）"
                               % (s.get("sid"), norm(s.get("title"))[:60] or "题录缺标题"),
                       "evidence": ev(pool[:1])})
    if not claims:
        claims = [{"claim_id": "C1", "text": "输入材料不足以支撑具体判断", "evidence": []}]
    matrix = [{"claim_id": c["claim_id"], "source_id": s.get("sid"),
               "task": "待确认", "method": "待确认", "data": "待确认", "evaluation": "待确认",
               "overlap": "none", "comparison_status": "not_comparable",
               "cannot_compare_reason": "兜底模式未做逐格比对：工作稿缺失（%s）" % why,
               "boundary_note": "未经阅读判断，不得作为划界结论", "locator": "—"}
              for c in claims[:3] for s in srcs[:1]]
    gates = []
    for gi, (gid, name, qs) in enumerate(GATES):
        gates.append({"gate_id": gid, "name": name, "question": qs, "verdict": "conditional",
                      "conditions": ["补齐工作稿中本门所需的材料阅读与逐条证据后才能判定"],
                      "evidence_ids": [claims[min(gi, len(claims) - 1)]["claim_id"]],
                      "residual_risks": ["兜底模式未做实质判断"],
                      "pivot_if_no_go": "改做同一材料范围内的可行性/覆盖复核", "rationale": "兜底：%s" % why})
    return {
        "case_id": case_id, "_fallback": True,
        "question": {"problem_statement": "（待补）输入材料中的研究设想尚未被拆成可检验表述；请依据 case.json 的 task_instruction 与材料补全。",
                     "object": "", "variables": [], "baseline": "", "expected": "",
                     "falsification": [], "vague_replaced": [],
                     "untestable": ["兜底模式未做判断"]},
        "search_protocol": {"queries": [], "windows": "", "inclusion": [], "exclusion": [], "screened": 0},
        "gates": gates,
        "matrix": matrix,
        "novelty": [{"claim_id": c["claim_id"], "type": "method", "verdict": "undetermined",
                     "covered_by": [], "boundary": "",
                     "rationale": "兜底模式不做新颖性判定"} for c in claims[:3]],
        "assumptions": [{"id": "A1", "statement": "研究所需数据/算力/时间前提未知", "category": "data",
                         "state": "unsupported", "source_locator": "", "kill_criteria": "在预定决策窗口内仍拿不到可用数据则停止",
                         "validation_experiment": "先做 1 个最小样本的可用性检查"},
                        {"id": "A2", "statement": "人员能力与实验条件未知", "category": "people", "state": "unsupported",
                         "source_locator": "", "kill_criteria": "若关键角色缺位则改做文献型研究",
                         "validation_experiment": "列出角色与工时，确认可投入"},
                        {"id": "A3", "statement": "时间窗与算力预算未知", "category": "time", "state": "unsupported",
                         "source_locator": "", "kill_criteria": "若算力排期晚于决策窗口则降级为小样本",
                         "validation_experiment": "试跑一次最小任务测实际耗时"}],
        "claims": claims,
        "conflicts": [],
        "no_contrary_found": "兜底模式未做系统检索：材料范围内未登记相反结论，但不等于不存在相反证据",
        "research_gap": {"statement": "材料范围内未见直接覆盖该设想的记录（限本材料与本次筛选，不代表全局无人研究）",
                         "scope": "本材料范围", "basis": ev(sd[:2]), "global_claim": False},
        "decision": {"overall": "conditional",
                     "summary": "兜底交付：已建索引与对象表，但缺少 Agent 工作稿（%s），五门判定均为 conditional。" % why,
                     "conditions": ["需按 SKILL.md 第 3 节补写 draft.json 后重跑 check/build"],
                     "next_validation": [{"step": "阅读材料并填写 draft.json", "evidence_needed": "每门 1 条逐字证据",
                                          "gate": "G1"}]},
        "change_log": [{"action": "脚本兜底生成", "target": "decision_brief.md",
                        "reason": why, "before": "—", "after": "五门 conditional 骨架"}],
    }


def merge(draft, fb):
    """用兜底补齐缺失/空字段，并返回补齐清单（不覆盖 Agent 已写内容）。"""
    fixed = []
    for k, v in fb.items():
        if k.startswith("_"):
            continue
        if k == "no_contrary_found" and draft.get("conflicts"):
            continue          # 已登记冲突时不需要“未见相反结论”声明
        cur = draft.get(k)
        empty = cur is None or cur == "" or cur == [] or cur == {}
        if empty and v not in (None, "", [], {}):
            draft[k] = v
            fixed.append(k)
    return draft, fixed
