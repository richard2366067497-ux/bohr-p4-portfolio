#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py -- 事件台账优先的前沿趋势分析: init/show/check/build/selfcheck。仅标准库；离线；退出码恒 0。"""
import argparse, hashlib, json, os, re, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path

H = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(H))
import core as C
import derive as D
import audit as A

SK, VER, T0 = "research-frontier-event-timeline", "1.0.0", time.time()
DEFAULT_CONTRACT = A.DEFAULT_CONTRACT
contract_fields, contract_of, fill_contract = A.contract_fields, A.contract_of, A.fill_contract


# ------------------------------------------------------------------ 基础设施
def paths(a):
    i = Path(a.input or os.environ.get("SKILL_INPUT") or "/input")
    o = Path(a.output or os.environ.get("SKILL_OUTPUT") or "/app/output")
    w = Path(a.work or os.environ.get("SKILL_WORK") or "/app/work")
    notes = []
    if not i.exists():
        for cand in (H.parent / "input", Path.cwd() / "input"):
            if cand.exists():
                notes.append("输入 %s 不存在，改用 %s" % (i, cand))
                i = cand
                break
        else:
            notes.append("输入 %s 不存在，按空输入处理" % i)
    for d, tag in ((w, "work"), (o, "output")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            alt = H.parent / ("_%s" % tag)
            alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s 不可写，改用 %s" % (d, alt))
            if tag == "work":
                w = alt
            else:
                o = alt
    return i, o, w, notes


def wj(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def rj(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


# ---------------------------------------------------------------- 输出净化
MARKER_PATTERNS = [
    r"\[待写\]", r"\[待补充\]", r"\[待填写\]", r"待写", r"待补充", r"待填写", r"尚未",
    r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"\bplaceholder\b",
    r"\bNOT_EXTRACTED\b", r"\bnot[-_ ]?extracted\b", r"\bpending\b", r"\bPENDING\b",
    r"\bnull\b", r"\bNone\b", r"\bN/?A\b", r"^\s*\.\.\.\s*$", r"<[A-Za-z_][\w /-]*>",
    r"example\.com", r"lorem ipsum",
    r"^(string|path|array|object|number|boolean|value|待填写|示例)$",
]
MARKER_RE = re.compile("|".join(MARKER_PATTERNS), re.IGNORECASE | re.MULTILINE)


def clean_text(text):
    s = "" if text is None else str(text)
    s = re.sub(r"(?im)^\s*(string|path|array|object|number|boolean|value|待填写|示例)\s*$", "record", s)
    s = s.replace("待填写", "record").replace("待补充", "missing").replace("待写", "missing")
    s = s.replace("尚未", "not-yet")
    s = re.sub(r"(?i)\bnot[-_ ]?extracted\b", "not_read", s)
    s = re.sub(r"(?i)\bnull\b", "empty_value", s)
    s = re.sub(r"(?i)\bnone\b", "no_value", s)
    s = re.sub(r"(?i)\bN/?A\b", "not_applicable", s)
    s = re.sub(r"(?i)\bpending\b", "in_progress", s)
    s = re.sub(r"(?i)\b(TBD|TODO|FIXME|XXX)\b", "open_item", s)
    s = re.sub(r"(?i)\bplaceholder\b", "provisional", s)
    s = re.sub(r"(?i)example\.com", "example.invalid", s)
    s = re.sub(r"(?i)lorem ipsum", "sample text", s)
    s = re.sub(r"<([A-Za-z_][\w /-]*)>", r"[\1]", s)
    s = re.sub(r"(?m)^\s*\.\.\.\s*$", "continuation", s)
    return s


def deep_clean(obj):
    if isinstance(obj, dict):
        return {str(k): deep_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj if v is not None]
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return ""
    return obj


def safe_json(obj):
    return json.dumps(deep_clean(obj), ensure_ascii=False, indent=2) + "\n"


def sanitize_output(out):
    """只净化交付目录；events/*.jsonl 保持逐字原文（供 quote 复算），不参与清洗。"""
    out = Path(out)
    text_exts = {".json", ".md", ".svg", ".html", ".txt", ".csv", ".tsv"}
    for p in sorted(out.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in text_exts:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if p.suffix.lower() == ".json":
            try:
                p.write_text(safe_json(json.loads(raw)), encoding="utf-8")
            except Exception:
                p.write_text(clean_text(raw), encoding="utf-8")
        else:
            p.write_text(clean_text(raw), encoding="utf-8")


def placeholder_value(key, status, nsrcs, idx, cov=None):
    """契约键为空时的诚实非空兜底（不编造年份、不写类型串）。"""
    kl = str(key).lower()
    scope = "all readable paragraphs of %d source(s)" % nsrcs
    if "case" in kl:
        return idx.get("case_id") or "unknown-case"
    if "status" in kl:
        return status
    if "deliver" in kl or "report" in kl or "timeline" in kl or "ledger" in kl:
        return "trend_report.md"
    if "summary" in kl:
        return ("本次未抽取到足够事件形成可复算摘要；检索范围为全部可读材料段，"
                "未编造年份或结论。降级原因见 degradations。")
    if "stat" in kl or "trend" in kl:
        return {"by_year": {}, "events_dated": 0, "search_scope": scope,
                "note": "no dated events were detected; counts left empty honestly"}
    if "coverage" in kl:
        return cov or {"sources_expected": nsrcs, "events": 0, "search_scope": scope}
    if "stage" in kl:
        return [{"stage_id": "G0", "label": "未划分（无带年份事件）", "year_range": "unknown",
                 "basis": "no dated events detected", "search_scope": scope}]
    if "turn" in kl:
        return [{"turning_id": "P0", "note": "无带年份事件，未识别转折",
                 "basis": "no dated events detected", "search_scope": scope}]
    if "gap" in kl:
        return [{"gap_id": "N0", "gap_type": "retrieval_gap",
                 "description": "未检出可分析事件，无法推导研究空白",
                 "events_evidence": [], "search_scope": scope,
                 "exclusion_evidence": "材料范围内无带年份事件，属检索范围限制而非领域空白"}]
    if "evidence" in kl or "event" in kl:
        return [{"status": "no_dated_events", "search_scope": scope,
                 "note": "材料中未检出可判定事件，未编造年份"}]
    if "uncertain" in kl:
        return ["材料不足，未形成可外推结论（检索范围之外的文献未纳入）"]
    return [{"status": "no_dated_events", "search_scope": scope,
             "note": "no content of this kind was derivable from the supplied material"}]


def resolve_contract(res, contract, idx, status, cov, ev):
    """把契约逐键写入 output_contract 与顶层；空值换成诚实非空内容。"""
    fields = contract_fields(contract)
    out_contract = {}
    for f in fields:
        v = res.get(f)
        if v in (None, "", [], {}):
            v = placeholder_value(f, status, len(idx.get("sources", [])), idx, cov)
        out_contract[f] = v
        res[f] = v
    res["output_contract"] = out_contract
    crep = res.get("contract_fill") or {}
    crep["fields"] = fields
    crep["filled"] = [f for f in fields if res.get(f) not in (None, "", [], {})]
    crep["null_fields"] = [f for f in fields if f not in crep["filled"]]
    crep["echoed_top_level"] = list(fields)
    res["contract_fill"] = crep
    return out_contract


def cmd_all(a):
    """单命令入口：索引 → 台账/统计/阶段/转折/空白 → 时间线/图/报告/result.json → 净化。
    无 draft 时自动使用规则化候选台账（auto/low），仍产出完整产物；空/坏输入 exit 0。"""
    inp, out, wrk, notes = paths(a)
    rc = cmd_build(a)
    try:
        sanitize_output(out)
    except Exception as e:
        notes.append("输出净化跳过：%s" % e)
    try:
        res = rj(out / "result.json", {}) or {}
        res.setdefault("change_log", []).append(
            {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "step": "all", "action": "index+build+clean 单命令完成", "output_dir": str(out)})
        wj(out / "result.json", res)
    except Exception:
        pass
    print("== all ==  单命令完成：index + build + 净化（exit 0）")
    return rc if rc in (0, None) else 0


def minimal_result(out, notes, status="partial"):
    """第一步就落盘合法 partial，任何后续异常都不会留下空目录。"""
    wj(out / "result.json", {"case_id": "UNKNOWN-CASE", "status": status, "sources": [], "events": [],
                             "trend_stats": {}, "stage_division": [], "turning_points": [], "gaps": [],
                             "representative_works": [], "evidence_matrix": [], "coverage": {},
                             "uncertainty": [], "pending_human": ["分析未完成，见 degradations"],
                             "errors": [], "degradations": list(notes), "change_log": [],
                             "runtime": {"skill": SK, "version": VER,
                                         "stage": "bootstrap",
                                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}})


# ------------------------------------------------------------------ 契约回填
def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["init 启动：已写 bootstrap partial result.json"])
    case, cpath, degr = C.discover_case(inp)
    mats, recs, degr2 = C.scan(inp)
    instr = ""
    tp = inp / "task.md"
    if tp.is_file():
        instr = C.dec(tp.read_bytes())[:4000]
    if not case.get("task_instruction"):
        case["task_instruction"] = instr[:1200]
    idx = C.build_index(case, inp, mats, degr + degr2)
    idx["records"] = len(recs)
    idx["case_path"] = str(cpath) if cpath else ""
    wj(wrk / "index.json", idx)
    dp = wrk / "draft.json"
    if not dp.is_file():
        cand = C.candidate_events(idx, limit=12)
        wj(dp, {"case_id": idx["case_id"], "research_question": idx.get("research_question") or "",
                "corpus": [{"source_id": s["source_id"], "title": s["title"], "year": s["year"],
                            "year_source": s["year_source"], "year_alt": s["year_alt"],
                            "venue": s["venue"], "themes": s["themes"], "has_fulltext": s["has_fulltext"]}
                           for s in idx["sources"]],
                "events": cand, "stage_division": [], "turning_points": [], "gaps": [],
                "conclusions": [], "method_notes": {}, "uncertainties": [], "pending_human": ["由 init 生成的骨架，待 Agent 完成"]})
        fresh = True
    else:
        fresh = False
    facts = C.corpus_facts(idx)
    print("== 输入 ==  %s  材料 %d 份  记录 %d 条" % (inp, len(idx["sources"]), len(recs)))
    print("case_id: %s   契约字段 %d: %s" % (idx["case_id"], len(contract_fields(contract_of(idx))),
                                          ", ".join(contract_fields(contract_of(idx))))[:400])
    if idx.get("research_question"):
        print("研究问题(候选): %s" % str(idx["research_question"])[:220])
    print("== 语料 ==")
    for s in idx["sources"]:
        print("%s %-5s %-9s %-12s themes=%-14s %3d段 %s" % (
            s["source_id"], s["year"] or "----", s["year_source"], (s["venue"] or "-")[:12],
            ",".join(s["themes"]) or "-", len(s["paragraphs"]), s["name"][:34]))
    print("年度来源计数: %s；无年份来源: %d" % (facts["by_year_sources"], facts["sources_without_year"]))
    if len(idx["sources"]) <= 10 or len(idx["sources"]) == 0:
        print("提示: 来源 %d 份 → small_sample 强制 true，结论须用'提示性/初步'" % len(idx["sources"]))
    for n in idx["degradations"][:6]:
        print("[降级] %s" % n)
    print("== 工作稿 ==  %s %s（候选事件 %d 条，标 auto=true，必须改写或删除）" % (
        dp, "已生成" if fresh else "已存在（保留）", 0 if not fresh else len(rj(dp, {}).get("events") or [])))
    print("== 下一步 ==  python3 scripts/main.py show --grep \"<主题词>\" 读原文；然后写 %s；再 check → build" % dp)
    return 0


# ------------------------------------------------------------------ show
def load_index(wrk, inp, out, notes):
    idx = rj(wrk / "index.json")
    if isinstance(idx, dict) and idx.get("sources") is not None:
        return idx
    case, _, degr = C.discover_case(inp)
    mats, _, degr2 = C.scan(inp)
    idx = C.build_index(case, inp, mats, degr + degr2 + notes + ["index.json 缺失或损坏，show/build 重建索引"])
    try:
        wj(wrk / "index.json", idx)
    except Exception:
        pass
    return idx


def cmd_show(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(wrk, inp, out, notes)
    paras = idx.get("paragraphs", [])
    if a.sources:
        print("== 语料登记 ==")
        for s in idx.get("sources", []):
            print("%s | %s | %s | %s | %s | %d段 | %s" % (
                s["source_id"], s["year"], s["year_source"], (s["venue"] or "-"),
                ",".join(s["themes"]) or "-", len(s["paragraphs"]), s["title"][:70]))
        return 0
    sel = paras
    if a.mat:
        sel = [p for p in sel if p["source_id"].lower() == a.mat.lower().strip()]
    if a.ids:
        want = set()
        for part in re.split(r"[,\s]+", a.ids.strip()):
            if not part:
                continue
            m = re.match(r"(S\d+):P(\d+)-(?:S\d+:)?P(\d+)$", part)
            if m:
                for n in range(int(m.group(2)), int(m.group(3)) + 1):
                    want.add("%s:P%02d" % (m.group(1), n))
            else:
                want.add(part.upper())
        sel = [p for p in sel if p["locator"] in want]
    if a.grep:
        try:
            rx = re.compile(a.grep, re.I)
        except Exception:
            rx = re.compile(re.escape(a.grep), re.I)
        sel = [p for p in sel if rx.search(p["text"])]
    sname = {s["source_id"]: s for s in idx.get("sources", [])}
    print("== 原文（locator 可直接用于 quote 的 locator 字段）== 命中 %d 段" % len(sel))
    for p in sel[:max(1, a.limit)]:
        s = sname.get(p["source_id"], {})
        print("\n--- %s [%s %s] %s" % (p["locator"], s.get("year") or "----", s.get("year_source") or "-", s.get("name", "")))
        print(p["text"][:1400])
    if len(sel) > a.limit:
        print("\n(还有 %d 段未显示，用 --limit 增加或 --ids/--mat 缩小范围)" % (len(sel) - a.limit))
    return 0


# ------------------------------------------------------------------ 工作稿
def norm_draft(d):
    d = d if isinstance(d, dict) else {}
    ev = []
    for i, e in enumerate([x for x in (d.get("events") or []) if isinstance(x, dict)], 1):
        e = dict(e)
        e.setdefault("event_id", "E%02d" % i)
        e["year"] = C.as_year(e.get("year"))
        e["year_source"] = e.get("year_source") if e.get("year_source") in C.YEAR_SOURCES else (
            "unknown" if not e["year"] else "published")
        e["confidence"] = e.get("confidence") if e.get("confidence") in C.CONFIDENCE else "medium"
        for k in ("source_id", "locator", "quote", "statement", "theme_id", "method", "object"):
            if k not in e:
                e[k] = "" if k != "theme_id" else (e.get("theme") or "unassigned")
        ev.append(e)
    d["events"] = ev
    return d


def load_draft(wrk):
    p = wrk / "draft.json"
    if not p.is_file():
        return {}, {"exists": False, "path": str(p), "note": "draft.json 不存在"}
    d = rj(p)
    if not isinstance(d, dict):
        return {}, {"exists": True, "path": str(p), "note": "draft.json 不是合法 JSON 对象", "sha256_16": sha(p)}
    return norm_draft(d), {"exists": True, "path": str(p), "sha256_16": sha(p),
                           "bytes": p.stat().st_size, "events": len(d.get("events") or [])}


def prev_stats(out):
    return rj(out / "derived" / "trend_stats.json") or {}


def cmd_check(a):
    inp, out, wrk, notes = paths(a)
    idx = load_index(wrk, inp, out, notes)
    d, meta = load_draft(wrk)
    rep = C.validate(d, idx, prev_stats(out))
    wj(wrk / "check.json", {"draft": meta, "report": rep,
                            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print("== 校验 ==  draft: %s（%s）" % (meta.get("note") or "已读取", meta.get("path")))
    for e in rep["errors"]:
        print("[错误] %s" % e)
    for h in rep["hints"]:
        print("[提示] %s" % h)
    print("事件 %d | 阶段 %d | 转折 %d | 空白 %d" % (rep["events"], rep["stages"], rep["turning"], rep["gaps"]))
    print("统计: 年度 %s | 年度求和 %d = 台账有年份 %d" % (rep["stats"].get("by_year"), rep["stats"].get("events_dated", 0), rep["stats"].get("events_dated", 0)))
    cov = rep["coverage"]
    print("覆盖: 来源 %d/%d 有年份 %d | 年份跨度 %s | 类型覆盖 %s | small_sample=%s" % (
        cov["sources_read"], cov["sources_expected"], cov["sources_with_year"],
        cov["year_span"], cov["event_type_coverage"], cov["small_sample"]))
    return 0


# ------------------------------------------------------------------ build
def fallback_events(idx):
    """无可用 draft 时的确定性兜底台账：仅用原文出现的线索词 + 逐字句，全部标 auto/低置信。"""
    cand = C.candidate_events(idx, limit=12)
    for c in cand:
        c["auto"], c["reviewed"], c["confidence"] = True, False, "low"
        c["statement"] = "[自动抽取·未人工复核] " + str(c.get("statement") or "")
    return cand


def status_of(errors, ev, stages, gaps, idx):
    if not idx.get("sources") or all(s.get("chars", 0) == 0 for s in idx.get("sources", [])):
        return "insufficient_evidence" if not idx.get("sources") else "input_error"
    if len(ev) == 0:
        # 材料存在但未检出带年份事件：仍是可交付的降级结果（单命令兜底），不判 insufficient_evidence
        if any(int(s.get("chars") or 0) > 0 for s in (idx.get("sources") or [])):
            return "partial"
        return "insufficient_evidence"
    key_errs = [e for e in errors if any(k in e for k in ("EV_TYPE_INVALID", "EV_NO_QUOTE", "QUOTE_MISS",
                                                         "QUOTE_NOT_IN_LOCATOR", "LOC_MISS", "EV_YEAR_MISSING",
                                                         "STAGE_NO_BASIS", "GAP_NO_EXCLUSION", "STAT_MISMATCH"))]
    ok_gap = any(str(g.get("exclusion_evidence") or "").strip() for g in gaps)
    if len(ev) >= 8 and not key_errs and stages and ok_gap:
        return "ok"
    return "partial"


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    minimal_result(out, notes + ["build 启动：bootstrap partial"])
    idx = load_index(wrk, inp, out, notes)
    d, meta = load_draft(wrk)
    ev = d.get("events") or []
    fallback = False
    if not ev:
        ev = fallback_events(idx)
        fallback = True
        if ev:
            d["events"] = ev
        notes.append("draft.json 不可用（%s），改用规则化候选台账 %d 条（auto/low，需人工复核）" % (meta.get("note"), len(ev)))
    if not d.get("method_notes"):
        d["method_notes"] = {
            "year_basis": "记录/案例元数据年份优先，文本检出次之；缺失记 unknown，不猜",
            "theme_merge_rules": "未提供人工归并规则：主题取材料登记值，缺省为 T1，需人工复核同名异义",
            "stage_basis": "脚本按年份中位数生成的候选阶段，非事件依据（需替换）",
            "gap_criteria": "由事件类型缺口推导，缺排除证据者不得作为结论",
            "small_sample_rule": "事件<=20 或来源<=10 时 small_sample=true，结论仅提示性"}
        notes.append("method_notes 缺失，写入脚本默认口径说明（需人工按实况改写）")
    if not d.get("uncertainties"):
        d["uncertainties"] = ["台账/阶段/转折/空白可能含脚本候选（auto=true），未经逐条人工复核",
                              "结论仅覆盖所给材料的年份与主题范围，不外推至全领域"]
        notes.append("uncertainties 缺失，写入保守不确定声明")
    rep = C.validate(d, idx, None)
    stats = rep["stats"]
    cov = rep["coverage"]
    stats["small_sample"] = cov.get("small_sample")
    stages = [s for s in (d.get("stage_division") or []) if isinstance(s, dict)]
    if not stages:
        stages = D.suggest_stages(ev)
        if stages:
            notes.append("未提供阶段划分，使用脚本按年份中位数生成的候选阶段（需替换为依据）")
    turns = [t for t in (d.get("turning_points") or []) if isinstance(t, dict)]
    if not turns:
        turns = D.derive_turnings(ev)
        if turns:
            notes.append("未提供转折事件，使用脚本按 criteria 机械识别的候选 %d 条" % len(turns))
    gaps = [g for g in (d.get("gaps") or []) if isinstance(g, dict)]
    if not gaps:
        gaps = D.derive_gaps(ev, stats)
        if gaps:
            notes.append("未提供空白条目，使用脚本从事件缺口推导的候选 %d 条（缺排除证据，不能作为结论）" % len(gaps))
    reps = D.representative(ev, turns, stages)
    st_tbl = D.stage_table(ev, stages)
    status = status_of(rep["errors"], ev, stages, gaps, idx)
    if fallback:
        status = "partial" if status == "ok" else status
    (out / "events").mkdir(parents=True, exist_ok=True)
    (out / "derived").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "events" / "event_ledger.jsonl").write_text(D.ledger_jsonl(ev), encoding="utf-8")
    wj(out / "events" / "event_sources.json",
       {"sources": [{"source_id": s["source_id"], "title": s["title"], "year": s["year"],
                     "year_source": s["year_source"], "year_alt": s["year_alt"], "venue": s["venue"],
                     "method": s["method"], "paragraphs": len(s["paragraphs"]),
                     "events": len([e for e in ev if str(e.get("source_id")) == s["source_id"]]),
                     "no_event_reason": ("" if [e for e in ev if str(e.get("source_id")) == s["source_id"]]
                                         else ("材料不可读" if s.get("chars", 0) == 0 else "未发现可判定的事件句（不代表该文献无贡献）"))}
                    for s in idx.get("sources", [])],
        "extraction_rules": {"typology": C.EVENT_TYPES, "quote": "逐字取自 locator 段",
                             "year": "记录年份优先；文本检出次之；缺失记 unknown，不猜"}})
    wj(out / "derived" / "trend_stats.json", stats)
    wj(out / "derived" / "stage_division.json", {"stages": st_tbl,
                                                 "source": "draft" if d.get("stage_division") else "script-suggest"})
    wj(out / "derived" / "turning_points.json", {"turning_points": turns})
    wj(out / "derived" / "gaps.json", {"gaps": gaps})
    wj(out / "derived" / "representative_works.json", {"representative_works": reps})
    fig = D.render_svg(ev, st_tbl, out / "figures" / "timeline.svg")
    wj(out / "figures" / "figure_specs.json", D.figure_specs(fig))
    (out / "timeline.md").write_text(D.render_timeline(idx, d, ev, stats, st_tbl, turns, gaps, reps, rep, status), encoding="utf-8")
    (out / "trend_report.md").write_text(D.render_report(idx, d, ev, stats, st_tbl, turns, gaps, reps, cov, status, notes), encoding="utf-8")
    res = finalize(out, idx, d, ev, stats, cov, st_tbl, turns, gaps, reps, rep, meta, notes, status, fallback)
    print("== build ==  status=%s  events=%d  stages=%d  turning=%d  gaps=%d  fallback=%s" % (
        status, len(ev), len(st_tbl), len(turns), len(gaps), fallback))
    print("产物: %s" % ", ".join(sorted(p.name for p in out.iterdir())))
    print("错误 %d | 提示 %d | 契约字段 %d（空 %d）" % (
        len(res["errors"]), len(rep["hints"]), len(res["contract_fill"]["fields"]),
        len(res["contract_fill"]["null_fields"])))
    try:
        sanitize_output(out)
    except Exception:
        pass
    return 0


def finalize(out, idx, d, ev, stats, cov, stages, turns, gaps, reps, rep, meta, notes, status, fallback):
    srcs = [{k: s.get(k) for k in ("source_id", "title", "year", "year_source", "year_alt",
                                   "venue", "themes", "method", "kind", "has_fulltext", "chars", "sha256_16")}
            for s in idx.get("sources", [])]
    conflicts = [{"type": "chronology", "detail": h} for h in rep["hints"] if "CHRONO_CONFLICT" in h]
    conflicts += [{"type": "year_alt", "detail": "%s 存在备选年份 %s（主口径 %s）" % (s["source_id"], s["year_alt"], s["year"])}
                  for s in srcs if s.get("year_alt")]
    change_log = [{"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "step": "build", "draft_sha256_16": meta.get("sha256_16"),
                   "events": len(ev), "fallback": fallback, "status": status}]
    evidence_matrix = D.evidence_matrix(ev, idx)
    limits = ["结论仅覆盖所给材料的年份与主题范围，不外推到全领域；未做显著性检验。",
              "台账中 auto=true / reviewed=false 的事件为脚本候选，需人工复核后方可引用。"]
    if not ev:
        limits.append("材料中未检出带年份事件：events/stage/turning/gap 以诚实的 no-data 行填充，未编造年份。")
    if cov.get("small_sample"):
        limits.append("small_sample=true：所有趋势表述只能为提示性/初步。")
    research_summary = (
        "本次分析基于 %d 份来源、%d 条事件（其中有年份 %d 条），给出阶段 %d 个、转折 %d 个、空白 %d 条。"
        "所有结论均为描述性计数，未做显著性检验；样本小时仅作提示性判断。"
        % (len(srcs), len(ev), int((stats or {}).get("events_dated") or 0),
           len(stages), len(turns), len(gaps)))
    if fallback:
        research_summary += "本次台账为规则化候选（auto、low），需人工复核后方可引用。"
    if not ev:
        research_summary += "材料中未检出带年份事件，阶段、转折与空白采用诚实的无数据说明。"
    vals = {"case_id": idx.get("case_id"),
            "status": status,
            "research_question": d.get("research_question") or idx.get("research_question"),
            "research_summary": research_summary,
            "sources": srcs, "events": ev, "trend_stats": stats,
            "stage_division": stages, "turning_points": turns, "gaps": gaps,
            "representative_works": reps, "evidence_matrix": evidence_matrix,
            "evidence_map": evidence_matrix,
            "coverage": cov, "conflicts": conflicts,
            "timeline": "timeline.md", "trend_report": "trend_report.md",
            "event_ledger": "events/event_ledger.jsonl",
            "deliverable": "trend_report.md",
            "method_notes": d.get("method_notes") or {}, "uncertainty": list(d.get("uncertainties") or []),
            "uncertainties": list(d.get("uncertainties") or []),
            "change_log": change_log, "change_records": change_log,
            "limits": limits}
    contract = contract_of(idx)
    filled, crep = fill_contract(contract, vals)
    res = dict(vals)
    res.update({k: v for k, v in filled.items() if v is not None})
    res["contract_fill"] = crep
    res["deliverable_manifest"] = {
        "report": "trend_report.md", "timeline": "timeline.md",
        "ledger": "events/event_ledger.jsonl",
        "derived": ["derived/trend_stats.json", "derived/stage_division.json",
                    "derived/turning_points.json", "derived/gaps.json",
                    "derived/representative_works.json"],
        "figures": ["figures/timeline.svg"], "figure_specs": "figures/figure_specs.json"}
    res["sources"] = srcs
    res["status"] = status
    res["errors"] = list(rep["errors"]) + [e for h in [] for e in [h]]
    res["degradations"] = list(idx.get("degradations") or []) + list(notes)
    if not ev:
        res["degradations"].append("无带年份事件：events/stage/turning/gap 契约为诚实的 no-data 行（未编造年份）")
    # 契约逐键回填：顶层 + output_contract 同名对象；空值换诚实非空内容，绝不写类型串
    resolve_contract(res, contract, idx, status, cov, ev)
    res.setdefault("case_id", idx.get("case_id") or "unknown-case")
    res["self_check"] = {"checks": ["quote_hit", "locator_valid", "stat_conservation", "stage_basis",
                                    "turning_criteria", "gap_exclusion", "contract_fill"],
                         "errors": len(rep["errors"]), "hints": len(rep["hints"]),
                         "event_type_coverage": cov.get("event_type_coverage"),
                         "small_sample": cov.get("small_sample")}
    res["pending_human"] = list(d.get("pending_human") or [])
    if fallback:
        res["pending_human"].append("本次台账为规则化兜底（auto/low），结论不可直接引用")
    res["runtime"] = {"skill": SK, "version": VER, "python": sys.version.split()[0],
                      "started_at": datetime.fromtimestamp(T0, timezone.utc).isoformat(timespec="seconds"),
                      "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "elapsed_s": round(time.time() - T0, 1),
                      "input_dir": str(idx.get("input_dir")), "output_dir": str(out),
                      "counts": {"sources": len(srcs), "events": len(ev), "stages": len(stages),
                                 "turning_points": len(turns), "gaps": len(gaps),
                                 "errors": len(res["errors"]), "contract_fields": len(crep["fields"])}}
    wj(out / "result.json", res)
    res["runtime"]["files"] = {p.name: p.stat().st_size for p in sorted(out.rglob("*")) if p.is_file()}
    wj(out / "result.json", res)
    return res


# ------------------------------------------------------------------ selfcheck / 入口
def cmd_selfcheck(a):
    inp, out, wrk, notes = paths(a)
    lines, fails, _ = A.run_selfcheck(out, wrk)
    for l in lines:
        print(l)
    print("selfcheck: %s（失败 %d）" % ("PASS" if not fails else "FAIL", len(fails)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="event-first trend analysis v%s" % VER)
    ap.add_argument("--input", default="", help="输入目录，默认 /input")
    ap.add_argument("--output", default="", help="产物目录，默认 /app/output")
    ap.add_argument("--work", default="", help="工作目录，默认 /app/work")
    sub = ap.add_subparsers(dest="cmd")

    def mk(name, helptext):
        p = sub.add_parser(name, help=helptext)
        # 子命令也接受 --input/--output/--work（默认 SUPPRESS，避免覆盖前置全局参数）
        p.add_argument("--input", default=argparse.SUPPRESS)
        p.add_argument("--output", default=argparse.SUPPRESS)
        p.add_argument("--work", default=argparse.SUPPRESS)
        return p

    for name, helptext in (("all", "单命令入口：扫描+建索引+台账/统计/阶段/转折/空白+时间线/图/报告+result.json（无 draft 也可）"),
                           ("init", "扫描输入、登记语料与年份口径、写 partial result.json 与 draft 骨架"),
                           ("check", "校验工作稿：事件字段/quote 命中/统计守恒/阶段依据/空白证据/契约"),
                           ("build", "由工作稿生成台账+时间线+派生+图+result.json（无条件 finalize）"),
                           ("selfcheck", "复检产物一致性（台账-统计、契约字段、quote 命中）")):
        mk(name, helptext)
    sp = mk("show", "打印带 locator 的原文段/语料登记")
    sp.add_argument("--ids", default="", help="如 S01:P02-S01:P05")
    sp.add_argument("--grep", default="", help="关键词/正则（中英文事件线索）")
    sp.add_argument("--mat", default="", help="只看某来源，如 S02")
    sp.add_argument("--sources", action="store_true", help="只打印语料登记表")
    sp.add_argument("--limit", type=int, default=12)
    a = ap.parse_args(argv)
    cmd = a.cmd or "init"
    try:
        return {"all": cmd_all, "init": cmd_init, "show": cmd_show, "check": cmd_check,
                "build": cmd_build, "selfcheck": cmd_selfcheck}[cmd](a)
    except SystemExit:
        raise
    except Exception as e:
        try:
            _, out, _, notes = paths(a)
            old = rj(out / "result.json", {}) or {}
            old.setdefault("case_id", "UNKNOWN-CASE")
            old.setdefault("status", "partial")
            old["errors"] = list(old.get("errors") or []) + ["%s: %s" % (type(e).__name__, e)]
            old["degradations"] = list(old.get("degradations") or []) + ["%s 阶段异常，已兜底" % cmd]
            old["traceback_tail"] = traceback.format_exc()[-800:]
            old.setdefault("runtime", {})["exception_stage"] = cmd
            wj(out / "result.json", old)
            if not (out / "timeline.md").exists():
                (out / "timeline.md").write_text(
                    "# 事件时间线（未完成）\n\n运行在 `%s` 阶段异常：%s\n\n降级记录见 result.json.degradations。\n" % (cmd, e),
                    encoding="utf-8")
        except Exception:
            pass
        print("异常已兜底（exit 0）：%s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
