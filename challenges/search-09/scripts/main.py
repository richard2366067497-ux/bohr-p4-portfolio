#!/usr/bin/env python3
"""search-09 单一入口。无参数 = 全流程：索引 -> 确定性推导 -> auto-draft -> 渲染 -> result.json。
init/show/check/build 仅分步调试；退出码恒 0，异常也写合法 result.json。
"""
import argparse, csv, json, re, sys, time, traceback
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402

T0 = time.time()
ART = ["appraisal.jsonl", "anchor_table.csv", "candidate_pool.csv", "grading.json"]
ACOLS = ["anchor_id", "paper_id", "checkpoint_id", "dimension", "doc_id", "locator", "section", "page",
         "quote", "match", "score", "used_for"]
PCOLS = ["candidate_id", "title", "year", "doi", "paper_type", "source_id", "source_path", "relevance_score",
         "rank", "decision", "reason_codes", "topic", "title_rel", "design", "depth", "preprint"]
ALIAS = {"candidates": "candidates", "papers": "candidates", "screening": "candidates", "search": "candidates",
         "appraisal": "appraisal", "rubric": "rubric_used", "evidence": "anchor_table", "anchors": "anchor_table",
         "gaps": "gaps", "uncertainty": "uncertainties", "grading": "grading", "method": "method_notes"}
DESIGNS = {"rct": r"rct|randomi[sz]ed|随机对照", "cohort": r"cohort|队列", "case_control": r"case-?control|病例对照",
           "sysrev": r"systematic review|meta-?analys|系统评价|荟萃", "diagnostic": r"diagnostic|诊断准确性"}
DIMK = (("DESIGN", r"设计|design|对照|control"), ("SAMPLE", r"样本|抽样|sample|招募|把握度"),
        ("MEASURE", r"测量|结局|measure|outcome|指标"), ("BIAS", r"偏倚|bias|盲|混"),
        ("STATSREP", r"统计|报告|statist|report|完整|资助|局限"))


def dirs(a):
    base = Path("/app") if Path("/app").is_dir() else Path.cwd()
    inp = Path(a.input) if a.input else Path("/input" if Path("/input").is_dir() else "input")
    out = Path(a.output) if a.output else base / "output"
    work = Path(a.work) if a.work else base / "work"
    for d in (out, work):
        d.mkdir(parents=True, exist_ok=True)
    return inp, out, work


def wcsv(path, head, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        w.writerow(head)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def jload(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_case(inp, errs, degr):
    case, task, q = {}, "", ""
    for n in ("case.json", "task.json", "challenge.json"):
        if (inp / n).is_file():
            obj, err = jload(inp / n)
            if err:
                errs.append({"stage": "case", "detail": "%s 解析失败：%s" % (n, err)})
                degr.append("case 不可解析：契约键按空处理，case_id=null")
            elif isinstance(obj, dict):
                case = obj
            break
    else:
        degr.append("无 case.json：case_id=null")
    if (inp / "task.md").is_file():
        try:
            task = (inp / "task.md").read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            errs.append({"stage": "task.md", "detail": str(e)})
    q = str(case.get("task_instruction") or case.get("task") or case.get("question") or "")
    if not q and task:
        q = next((l.strip("# ").strip() for l in task.splitlines()
                  if len(l.strip("# ").strip()) > 40 and not l.strip().startswith(("|", "-", ">"))), "")
    return case, task, q[:400]


def ckeys(case):
    raw = case.get("output_contract") or case.get("outputContract") or case.get("required_outputs") or []
    out = []
    for v in ([raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else []):
        out += list(v) if isinstance(v, dict) else ([v] if isinstance(v, str) else [])
    return [str(k) for k in out]


def fill(keys, payload):
    res, low = {}, {k.lower(): k for k in payload}
    for key in keys:
        k = key.lower().strip()
        hit = k if k in payload else (ALIAS.get(k) if ALIAS.get(k) in payload else None)
        if not hit:
            hit = next((v for kk, v in low.items() if len(kk) >= 4 and (kk in k or k in kk)), None)
        res[key] = payload.get(hit) if hit else None
    return res


def declared(task, case):
    """case.json / task.md 里声明过的维度或检查点 -> 追加为附加检查点（无则用内置 5 维）。"""
    items = []
    for k in ("rubric", "dimensions", "checkpoints", "criteria", "appraisal_scheme"):
        v = case.get(k)
        if isinstance(v, list):
            items += [x if isinstance(x, str) else str(x.get("name") or x.get("text") or "") for x in v]
        elif isinstance(v, dict):
            items += list(v)
        elif isinstance(v, str):
            items.append(v)
    items += [m.group(2) for m in (re.match(r"^\s*[-*•]?\s*(维度|检查点|dimension|checkpoint)\s*[:：]\s*(.+)$",
                                             l, re.I) for l in (task or "").splitlines()) if m]
    out = []
    for x in items:
        s = re.sub(r"\s+", " ", re.sub(r"[*`#>]", "", str(x))).strip(" ：:-")
        if 3 <= len(s) <= 40:
            out.append(s)
    return out[:8]


def add_declared(items, log):
    for i, text in enumerate(items, 1):
        cid, pat = "DECL%d" % i, "|".join(re.escape(t) for t in (E.toks(text)[:3] or [text]))
        if any(c["checkpoint_id"] == cid for c in E.CP_ALL):
            continue
        E.CP_ALL.append({"checkpoint_id": cid, "kw": pat, "neg": None, "question": text[:40], "floor": "low",
                         "dimension": next((d for d, p in DIMK if re.search(p, text.lower())), "STATSREP"),
                         "sections": ["Methods", "Results", "Abstract", "Body"], "type": ""})
        log.append("声明维度 `%s` -> %s" % (text, cid))


def screen(papers, terms, designs):
    """确定性筛选+排序：0.40 topic + 0.25 title + 0.20 design + 0.15 depth。"""
    rows = []
    for p in papers:
        title = p["title"]
        body = title + " " + " ".join(b["text"] for b in p["blocks"] if b["section"] in ("Title", "Abstract"))[:4000]
        cover = E.overlap(" ".join(terms), body) if terms else 0.0
        tc = E.overlap(" ".join(terms), title) if terms else 0.0
        subs = {"topic": 2 if cover >= .6 else (1 if cover >= .3 else 0),
                "title": 2 if tc >= .5 else (1 if tc >= .25 else 0),
                "design": ((2 if p["paper_type"] != "unknown" else 1) if not designs else
                           (2 if p["paper_type"] in designs else (1 if p["paper_type"] == "unknown" else 0))),
                "depth": 2 if p["scope"] == "full_text" else (1 if p["scope"] == "abstract" else 0)}
        score = round(sum(round(E.W[k] * v, 3) for k, v in subs.items()), 3)
        if subs["depth"] == 0:
            dec, codes = "exclude", ["R_NOFT"]
        elif score >= .55:
            dec, codes = "include", ["I_TOPIC", "I_FULLTEXT"] + (["I_DESIGN"] if subs["design"] == 2 else [])
        elif score < .30:
            dec, codes = "exclude", (["R_OFFTOPIC"] if subs["topic"] == 0 else ["R_DESIGN"])
        else:
            dec, codes = "unclear", ["R_UNCLEAR"]
        rows.append({"candidate_id": p["paper_id"], "title": title, "year": p["year"], "doi": p["doi"],
                     "authors": (p["authors"] or "")[:120], "venue": p["venue"], "source_id": p["source_id"],
                     "source_path": p["source_path"], "paper_type": p["paper_type"],
                     "preprint": p.get("preprint", False), "relevance": subs, "relevance_score": score,
                     "decision": dec, "reason_codes": codes,
                     "decision_basis": "; ".join(E.CODES.get(c, c) for c in codes),
                     "type_anchor": p.get("type_anchor")})
    rows.sort(key=lambda r: (-r["relevance_score"], -int(r["year"] or 0), r["candidate_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def draft_merge(draft, papers, rows, anchors, log):
    """Agent 工作稿：quote 先逐字核验，通过才覆盖该检查点；失败只记录，保留确定性结论。"""
    if not isinstance(draft, dict):
        return 0
    by_id, ov = {p["paper_id"]: p for p in papers}, 0
    for dp in draft.get("papers") or []:
        p = by_id.get(str(dp.get("paper_id")))
        if not p:
            log.append("draft 未匹配文献 %s" % dp.get("paper_id"))
            continue
        if dp.get("paper_type") and dp["paper_type"] != p["paper_type"]:
            log.append("%s 类型 %s -> %s" % (p["paper_id"], p["paper_type"], dp["paper_type"]))
            p["paper_type"] = dp["paper_type"]
        for dc in dp.get("checkpoints") or []:
            row = next((r for r in rows if r["paper_id"] == p["paper_id"]
                        and r["checkpoint_id"] == str(dc.get("checkpoint_id"))), None)
            q = str(((dc.get("anchors") or [{}])[0]).get("quote") or "")
            blk = next((b for b in p["blocks"] if q and q in b["text"]), None) if row else None
            if not blk:
                log.append("%s/%s draft 锚点未命中，弃用" % (p["paper_id"], dc.get("checkpoint_id")))
                continue
            aid = "A%03d" % (len(anchors) + 1)
            anchors.append({"anchor_id": aid, "paper_id": p["paper_id"], "checkpoint_id": row["checkpoint_id"],
                            "dimension": row["dimension"], "doc_id": blk["locator"].split("#")[0],
                            "locator": blk["locator"], "section": blk["section"], "page": blk.get("page"),
                            "quote": q, "match": E.verify(q, blk["text"])[0], "score": 1.0,
                            "used_for": row["checkpoint_id"]})
            row["anchor_ids"].append(aid)
            row.update(judgment=dc.get("judgment") or row["judgment"], risk=dc.get("risk") or row["risk"],
                       rule_id="R_AGENT_DRAFT", rationale=str(dc.get("rationale") or "Agent 工作稿，quote 已核验")[:300],
                       evidence={"doc_id": blk["locator"].split("#")[0], "locator": blk["locator"],
                                 "section": blk["section"], "page": blk.get("page"), "quote": q, "match": "verified"})
            ov += 1
    return ov


def assemble(inp, errs, degr, log):
    case, task, question = load_case(inp, errs, degr)
    extra = declared(task or question, case)
    add_declared(extra, log)
    if not extra:
        log.append("未解析到声明维度：用内置量表")
    docs, problems = E.discover(inp)
    degr += ["%s: %s" % (p.get("kind"), p.get("path") or p.get("detail")) for p in problems]
    papers = [E.route_type(p) for p in E.build_papers(docs)]
    ds = {k for k, pat in DESIGNS.items() if re.search(pat, (question or "").lower())}
    cands = screen(papers, E.toks(question)[:30], ds if 0 < len(ds) <= 3 else set())
    rows, anchors = [], []
    for p in papers:
        if p["scope"] == "metadata":
            degr.append("%s 仅题录元数据，不评价" % p["paper_id"])
            continue
        r, a = E.appraise(p)
        rows += r
        anchors += a
    gaps = [{"kind": "access_error", "subject": d["doc_id"],
             "detail": "%s 文本层不可用（%s）" % (d["rel"], d["meta"]["quality"]),
             "action": "记 access_error；OCR 后重跑，不据此推断未报告"}
            for d in docs if d["meta"].get("quality") in ("no_text_layer", "encrypted", "unreadable")]
    gaps += [{"kind": "abstain", "subject": "%s/%s" % (r["paper_id"], r["checkpoint_id"]),
              "detail": "弃权（%s）`%s` 无命中，检索 %d 块" % (r.get("abstain_reason"),
                                                          r["searched_scope"]["keyword_family"],
                                                          r["searched_scope"]["blocks"]),
              "action": "人工补检后可解除"} for r in rows if r["judgment"] == "not_assessable"]
    gaps += [{"kind": "out_of_scope", "subject": c["candidate_id"],
              "detail": "相关度 %s 落在 unclear：%s" % (c["relevance_score"], c["decision_basis"]),
              "action": "人工判断后再评价"} for c in cands if c["decision"] == "unclear"]
    if not papers:
        gaps.append({"kind": "empty_result", "subject": "candidate_pool", "detail": "材料中未识别出可用文献",
                     "action": "不补造文献；检查 /input"})
    fixtures = [{"doc_id": d["doc_id"], "path": d["rel"], "issue": "fixture/duplicate/conflict",
                 "handling": "仅登记，不作任何判断的证据"} for d in docs if d.get("fixture")]
    grades = {}
    for p in papers:
        rs = [r for r in rows if r["paper_id"] == p["paper_id"]]
        if rs:
            grades[p["paper_id"]] = dict(E.grade(rs, p["paper_type"]), type=p["paper_type"])
    return {"cid": case.get("case_id") or case.get("caseId") or case.get("id"), "keys": ckeys(case),
            "question": question, "docs": docs, "papers": papers, "cands": cands, "rows": rows,
            "anchors": anchors, "gaps": gaps, "fixtures": fixtures, "grades": grades, "extra": extra}


def payload_of(st, errs, degr, log, mode, merged, phase="run"):
    j = {k: sum(1 for r in st["rows"] if r["judgment"] == k) for k in E.JUDG}
    c = {"materials": len([d for d in st["docs"] if d.get("role") == "material"]), "documents": len(st["docs"]),
         "blocks": sum(len(d["blocks"]) for d in st["docs"]), "papers": len(st["papers"]),
         "candidates": len(st["cands"]), "anchors": len(st["anchors"]),
         "verified_anchors": sum(1 for a in st["anchors"] if a["match"] in ("exact", "normalized")),
         "checkpoints": len(st["rows"]), "dimensions_covered": len({r["dimension"] for r in st["rows"]}),
         "gaps": len(st["gaps"]), "fixtures": len(st["fixtures"]), "met": j["met"], "partial": j["partial"],
         "not_met": j["not_met"], "not_assessable": j["not_assessable"]}
    for k, v in (("included", "include"), ("excluded", "exclude"), ("unclear", "unclear")):
        c[k] = sum(1 for x in st["cands"] if x["decision"] == v)
    judged = j["met"] + j["partial"] + j["not_met"]
    status = ("input_error" if not st["papers"] else
              "answered" if st["rows"] and judged and not degr and not errs and phase == "run" else "partial")
    p = {"case_id": st["cid"], "status": status, "research_question": st["question"] or None,
         "summary": "%d 材料/%d 篇/候选 %d(纳入 %d)/检查点 %d(met %d,partial %d,not_met %d,弃权 %d)/锚点 %d(核验 %d)"
                    % (c["materials"], c["papers"], c["candidates"], c["included"], c["checkpoints"], j["met"],
                       j["partial"], j["not_met"], j["not_assessable"], c["anchors"], c["verified_anchors"]),
         "paper_type": {x["paper_id"]: x["paper_type"] for x in st["papers"]},
         "candidates": st["cands"], "appraisal": st["rows"], "anchor_table": st["anchors"],
         "robs": {k: v["overall"] for k, v in st["grades"].items()},
         "grading": st["grades"],
         "rubric_used": {"skill": "%s/%s" % (E.NAME, E.VERSION), "source": "references/appraisal_rules.md",
                         "dimensions": [d for d, _ in E.DIMS],
                         "declared": st["extra"], "rules_fallback": E.RULES_ERR or None},
         "review_log": log, "fixtures": st["fixtures"], "gaps": st["gaps"], "counts": c,
         "degradations": degr, "errors": errs,
         "method_notes": ["block->题录->论文->类型->检查点->锚点->判定->分级，确定性可复算",
                          "判断带 source_id+locator+逐字 quote，脚本内包含校验，失败即弃权",
                          "Agent draft 覆盖已核验检查点 %d 条" % merged],
         "assumptions": ["材料文本即事实依据；不联网、不补造、不做事实核验",
                         "类型=标题+前 6 块首个命中；abstract 弱于全文"],
         "uncertainties": [g["detail"][:120] for g in st["gaps"] if g["kind"] in ("access_error", "out_of_scope")][:8],
         "sources": [{"source_id": d["doc_id"], "path": d["rel"], "kind": d["kind"], "role": d.get("role"),
                      "blocks": len(d["blocks"]), "quality": d["meta"].get("quality")} for d in st["docs"]],
         "artifacts": ART,
         "runtime": {"seconds": round(time.time() - T0, 2), "python": sys.version.split()[0],
                     "skill": "%s/%s" % (E.NAME, E.VERSION), "mode": mode}}
    out = fill(st["keys"], p)
    out.update(p)
    out["contract_filled"] = {"declared": len(st["keys"]),
                              "filled": sum(1 for k in st["keys"] if out.get(k) is not None)}
    return out


def write_all(out, payload, st):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    empty = {"paper_id": None, "dimension": None, "checkpoint_id": "N/A", "judgment": "not_assessable",
             "risk": "insufficient", "rule_id": "R_J1_ABSTAIN", "anchor_ids": [], "evidence": {},
             "abstain_reason": "not_parsable", "rationale": "无可评读材料：见 result.json.gaps"}
    (out / "appraisal.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                  for r in st["rows"] or [empty]), encoding="utf-8")
    wcsv(out / "anchor_table.csv", ACOLS, [[a.get(k, "") for k in ACOLS] for a in st["anchors"]])
    wcsv(out / "candidate_pool.csv", PCOLS,
           [[c["candidate_id"], c["title"], c["year"], c["doi"], c["paper_type"], c["source_id"], c["source_path"],
             c["relevance_score"], c["rank"], c["decision"], ";".join(c["reason_codes"]), c["relevance"]["topic"],
             c["relevance"]["title"], c["relevance"]["design"], c["relevance"]["depth"], c["preprint"]]
            for c in st["cands"]] or [["-", "（无候选）"] + [""] * (len(PCOLS) - 2)])
    jdump(out / "grading.json", {"schema": "search-09/grading@1", "case_id": st["cid"],
                                 "thresholds": {"dimension": "维度取最严重者 major>some>low；无有效判断=insufficient",
                                                "design_floor": E.FLOOR,
                                                "overall": "弃权≥50%->insufficient_evidence；DESIGN/SAMPLE/BIAS 有 major->high_risk；some≥2->some_concerns；否则 low_risk"},
                                 "papers": st["grades"]})
    jdump(out / "result.json", payload)


def cmd_run(a):
    inp, out, work = dirs(a)
    errs, degr, log = [], [], []
    if E.RULES_ERR:
        degr.append("规则块不可用（%s）：退到内置最小量表" % E.RULES_ERR)
    print("== %s %s input=%s" % (E.NAME, E.VERSION, inp))
    try:
        st = assemble(inp, errs, degr, log)
        draft, merged = None, 0
        for n in ("draft.json", "plan.json"):
            if (Path(work) / n).is_file():
                draft, err = jload(Path(work) / n)
                degr += ["%s 解析失败：%s（忽略）" % (n, err)] if err else []
                log += ["读取工作稿 %s（Agent 可选增强）" % n] if not err else []
                break
        if draft:
            merged = draft_merge(draft, st["papers"], st["rows"], st["anchors"], log)
        else:
            log.append("无 work/draft.json：纯确定性推导（全流程已完成，非降级）")
        payload = payload_of(st, errs, degr, log, "agent_augmented" if merged else "deterministic", merged)
        write_all(out, payload, st)
        print("status=%s | %s" % (payload["status"], payload["summary"]))
        print("contract %d/%d | %s" % (payload["contract_filled"]["filled"], payload["contract_filled"]["declared"],
                                       " ".join("%s(%dB)" % (f, (out / f).stat().st_size) for f in ART + ["result.json"])))
    except Exception as e:
        errs.append({"stage": "run", "detail": "%s: %s" % (type(e).__name__, e),
                     "trace": traceback.format_exc()[-600:]})
        print("! recoverable failure: %s" % e)
        try:
            out.mkdir(parents=True, exist_ok=True)
            for f in ART:
                if not (out / f).is_file():
                    (out / f).write_text("" if f.endswith((".csv", ".jsonl")) else "{}", encoding="utf-8")
            jdump(out / "result.json", {"case_id": None, "status": "partial", "errors": errs, "appraisal": [],
                                        "candidates": [], "anchor_table": [], "counts": {}, "artifacts": ART,
                                        "degradations": degr + ["异常兜底：仍写出合法 partial"], "gaps": []})
        except Exception:
            pass
    print("done in %.2fs" % (time.time() - T0))
    return 0


def cmd_init(a):
    inp, out, work = dirs(a)
    errs, degr, log = [], [], []
    st = assemble(inp, errs, degr, log)
    jdump(Path(work) / "index.json", {"case_id": st["cid"], "contract": st["keys"], "rules_error": E.RULES_ERR,
                                      "docs": [{"doc_id": d["doc_id"], "path": d["rel"], "role": d.get("role"),
                                                "blocks": len(d["blocks"]), "quality": d["meta"].get("quality")}
                                               for d in st["docs"]],
                                      "papers": [{"paper_id": p["paper_id"], "type": p["paper_type"],
                                                  "scope": p["scope"], "title": p["title"][:120]}
                                                 for p in st["papers"]]})
    jdump(Path(out) / "result.json",
          payload_of(st, errs, degr + ["init 只建索引，未渲染主产物"], log, "init", 0, "init"))
    print("init: %d 文件 / %d 篇 / 键 %d" % (len(st["docs"]), len(st["papers"]), len(st["keys"])))
    return 0


def cmd_show(a):
    inp, out, work = dirs(a)
    st = assemble(inp, [], [], [])
    if a.checkpoints:
        print("\n".join("%-6s %-9s %s" % (c["checkpoint_id"], c["dimension"], c["question"])
                        for c in E.plan(a.checkpoints)))
        return 0
    print("case_id=%r 契约键=%s" % (st["cid"], ",".join(st["keys"]) or "无"))
    for d in st["docs"]:
        print("%s %-28s %-8s blocks=%-3d %s%s" % (d["doc_id"], d["rel"][:28], d.get("role"), len(d["blocks"]),
                                                  d["meta"].get("quality", "-"), " FIXTURE" if d.get("fixture") else ""))
    for p in st["papers"]:
        print("%s %-11s %-9s %s" % (p["paper_id"], p["paper_type"], p["scope"], p["title"][:78]))
    print("候选 %d / 检查点 %d / 锚点 %d" % (len(st["cands"]), len(st["rows"]), len(st["anchors"])))
    return 0


def cmd_check(a):
    inp, out, work = dirs(a)
    st = assemble(inp, [], [], [])
    bad = sum(1 for x in st["anchors"] if x["match"] == "mismatch")
    noev = sum(1 for r in st["rows"] if r["judgment"] != "not_assessable" and not (r.get("evidence") or {}).get("quote"))
    ok = all(E.grade([r for r in st["rows"] if r["paper_id"] == p["paper_id"]], p["paper_type"])["overall"]
             == g["overall"] for p in st["papers"] for g in [st["grades"].get(p["paper_id"])] if g)
    issues = [x for x in ("%d 条锚点未命中" % bad if bad else "", "无检查点判断" if not st["rows"] else "",
                          "分级不可复算" if not ok else "") if x]
    jdump(Path(work) / "check_report.json", {"anchors": len(st["anchors"]), "mismatch": bad, "rows": len(st["rows"]),
                                             "no_evidence": noev, "grade_recompute": ok,
                                             "contract_keys": len(st["keys"]), "issues": issues})
    print("check: 锚点 %d（mismatch %d）/ 判断 %d / 无证据 %d / 契约键 %d"
          % (len(st["anchors"]), bad, len(st["rows"]), noev, len(st["keys"])))
    for x in issues:
        print("  - " + x)
    print("RESULT: %s" % ("PASS" if not issues else "ATTENTION"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="search-09 文献质量评价（无参数=全流程）")
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "init", "show", "check", "build"])
    ap.add_argument("--input"), ap.add_argument("--output"), ap.add_argument("--work")
    ap.add_argument("--checkpoints", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd in ("run", "build"):
        return cmd_run(a)
    return {"init": cmd_init, "show": cmd_show, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception as e:
        print("soft failure: %s" % e)
    sys.exit(0)
