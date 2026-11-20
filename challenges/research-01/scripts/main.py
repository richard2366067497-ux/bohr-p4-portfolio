#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - research-01 investigation notebook CLI.

Commands: init | show | check | build | selfcheck.  Exit code is always 0; a legal
partial result.json is written first and finalised unconditionally.
"""

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # keep the installed skill dir free of __pycache__

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import parse as P          # noqa: E402
import check as C          # noqa: E402
import render as R         # noqa: E402
import contract as X       # noqa: E402
from render import cut     # noqa: E402

SKILL_ROOT = HERE.parent
T0 = time.time()


# --------------------------------------------------------------------------- io
def jwrite(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False), "utf-8")
    tmp.replace(p)


def jline(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    p.write_text(body + ("\n" if body else ""), "utf-8")


def jdump(obj):
    return json.dumps(obj, ensure_ascii=False)


def load_json(path):
    return json.loads(Path(path).read_text("utf-8", errors="replace"))


def cut(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# --------------------------------------------------------------------------- derive
def _p(args):
    return P.resolve_paths(getattr(args, "input", None), getattr(args, "work", None),
                           getattr(args, "output", None))


def _slim(idx):
    return {"input_dir": idx["input_dir"], "case_path": idx["case_path"],
            "task_path": idx["task_path"], "stats": idx["stats"],
            "contract": idx["contract"],
            "materials": [{"source_id": m["id"], "path": m["rel"], "kind": m["kind"],
                           "read_method": m["read_method"], "chars": m["chars"],
                           "blocks": len(m.get("blocks") or [])} for m in idx["materials"]],
            "records": idx["records"][:200],
            "degradations": idx["degradations"], "errors": idx["errors"]}


def cmd_init(args):
    inp, work, out = _p(args)
    idx = P.build_index(inp)
    jwrite(work / "index.json", _slim(idx))
    data = {"case_id": (idx["case"] or {}).get("case_id"), "question": P.question_of(idx),
            "sqs": [], "search_steps": [], "findings": [], "conflicts": [],
            "conflict_hints": [], "synthesis": [], "evidence": [], "open_questions": [],
            "uncertainties": [], "sources": [], "coverage": {}}
    chk = {"issues": [], "repairs": [], "stats": {"fix": 0, "warn": 0, "quotes_verified": 0,
                                                  "quotes_failed": 0, "locators_repaired": 0,
                                                  "uncovered_sub_questions": []}}
    deg = list(idx["degradations"]) + [{"code": "init_partial",
                                        "detail": "init 阶段仅建立索引；待 Agent 写工作稿后 build 生成正式产物"}]
    res = X.build_result((idx["case"] or {}).get("case_id") or "unknown", "partial", data, chk, idx,
                       deg, idx["errors"], [{"change_id": "C1", "kind": "partial_written",
                                             "detail": "init 写出合法 partial result.json"}],
                       {"phase": "init", "seconds": round(time.time() - T0, 2)})
    jwrite(out / "result.json", res)
    print("[init] input=%s work=%s output=%s" % (inp, work, out))
    print("[init] materials=%d readable=%d records=%d contract_keys=%d chars=%d" % (
        idx["stats"]["materials"], idx["stats"]["readable_materials"], idx["stats"]["records"],
        idx["stats"]["contract_keys"], idx["stats"]["chars"]))
    print("[init] question: %s" % cut(data["question"], 160))
    print("[init] contract keys: %s" % ", ".join(f["key"] for f in idx["contract"]))
    for d in idx["degradations"]:
        print("[init] degraded: %s %s" % (d.get("code"), d.get("path") or d.get("detail") or ""))
    print("[init] partial result.json -> %s" % (out / "result.json"))
    print("[init] NEXT: python3 scripts/main.py show  → read sentences → write %s/draft.json "
          "→ check → build" % work)


def cmd_show(args):
    inp, work, out = _p(args)
    idx = P.build_index(inp)
    g = args.grep
    if args.max_sents == 0:
        args.max_sents = 10 ** 6
    print("== CASE ==")
    print("case_id: %s" % ((idx["case"] or {}).get("case_id") or "(none)"))
    print("question: %s" % cut(P.question_of(idx), 400))
    print("contract keys (%d): %s" % (len(idx["contract"]), " | ".join(f["key"] for f in idx["contract"])))
    for k in ("constraints", "search_protocol", "protocol", "time_range", "inclusion", "exclusion"):
        v = (idx["case"] or {}).get(k)
        if v:
            print("%s: %s" % (k, cut(jdump(v) if not isinstance(v, str) else v, 300)))
    if args.brief:
        tm = (idx.get("task_md") or "").strip()
        print("\n== TASK.MD (%d chars) ==\n%s" % (len(tm), tm[:3000]))
    print("\n== MATERIALS (%d) ==" % idx["stats"]["materials"])
    for m in idx["materials"]:
        print("[%s] kind=%s read=%s chars=%d blocks=%d  %s" % (
            m["id"], m["kind"], m["read_method"], m["chars"], len(m.get("blocks") or []), m["rel"]))
    if idx["records"]:
        print("\n== RECORDS (%d) ==" % len(idx["records"]))
        for r in idx["records"][: args.max_records]:
            print("[%s] %s | %s | %s" % (r["rec_id"], cut(r.get("title"), 80),
                                          r.get("year") or "-", r["locator"]))
    mats = idx["materials"]
    if args.source:
        mats = [m for m in mats if m["id"] == args.source or m["rel"] == args.source]
        if not mats:
            print("\n!! source %s not found" % args.source)
    print("\n== EXCERPTS (verbatim; copy quote text exactly) ==")
    for m in mats:
        if m.get("kind") == "table" and not args.source:
            continue
        blocks = m.get("blocks") or []
        show = blocks if args.max_blocks == 0 else blocks[: args.max_blocks]
        print("\n--- [%s] %s (%d blocks, showing %d) ---" % (m["id"], m["rel"], len(blocks), len(show)))
        n = 0
        for b in show:
            if not b["sents"]:
                continue
            print("  %s %s" % (b["bid"], cut(b["text"], 90)))
            for s in b["sents"]:
                if g and g not in s["text"]:
                    continue
                if n >= args.max_sents:
                    break
                print("  [%s] %s" % (m["id"], P.locator_for(m, s["start"], s["end"])))
                print("  > %s" % cut(s["text"], args.max_chars))
                n += 1
        if n >= args.max_sents:
            print("  (capped at %d sentences; use --max-sents 0 for all)" % args.max_sents)
        if g:
            print("  (grep '%s': %d sentences)" % (g, n))
    print("\n== NEXT ==")
    print("write %s/draft.json (schema: references/draft_schema.md) then run: check → build" % work)


def _draft_path(args):
    _, work, _ = _p(args)
    return work / "draft.json"


def cmd_check(args):
    inp, work, out = _p(args)
    idx = P.build_index(inp)
    dp = _draft_path(args)
    info = {"path": str(dp), "status": "missing"}
    draft = None
    try:
        draft = C.normalize_draft(load_json(dp))
        info["status"] = "loaded"
    except FileNotFoundError:
        info["status"] = "missing"
    except Exception as e:
        info["status"] = "invalid"
        info["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    if draft is None:
        print("[check] draft %s (%s) -> nothing to validate; build will use fallback" % (info["status"], dp))
        jwrite(work / "check-report.json", {"draft": info, "issues": [], "repairs": [],
                                            "stats": {"fix": 0, "warn": 0}})
        return
    chk = C.check_draft(draft, idx)
    jwrite(work / "check-report.json", {"draft": info, "issues": chk["issues"],
                                        "repairs": chk["repairs"], "stats": chk["stats"]})
    st = chk["stats"]
    print("[check] draft=%s sub_questions=%d findings=%d synthesis=%d open=%d steps=%d" % (
        dp, st["sub_questions"], st["findings"], st["synthesis_paragraphs"],
        st["open_questions"], st["search_steps"]))
    print("[check] quotes %d/%d hits, locator repairs=%d, fix=%d warn=%d" % (
        st["quotes_verified"], st["quotes_verified"] + st["quotes_failed"],
        st["locators_repaired"], st["fix"], st["warn"]))
    for r in chk["repairs"]:
        print("  [REPAIR %s] %s %s → %s" % (r["code"], r["where"], r["detail"], r["to"]))
    for i in chk["issues"]:
        print("  [%s %s] %s: %s%s" % (i["severity"], i["code"], i["where"], i["message"],
                                      (" | %s" % i["fix_hint"]) if i["fix_hint"] else ""))
    if st["fix"] == 0:
        print("[check] OK: no FIX. run build.")
    else:
        print("[check] %d FIX must be resolved before build (build still runs and degrades)." % st["fix"])


def _finalize(args, phase):
    inp, work, out = _p(args)
    idx = P.build_index(inp)
    degradations = list(idx["degradations"])
    errors = list(idx["errors"])
    changes = []
    dp = work / "draft.json"
    draft, dstat = None, "missing"
    try:
        draft = C.normalize_draft(load_json(dp))
        dstat = "loaded"
    except FileNotFoundError:
        dstat = "missing"
    except Exception as e:
        dstat = "invalid"
        errors.append({"code": "draft_invalid", "detail": "%s: %s" % (type(e).__name__, str(e)[:200])})
    if draft is None or not (draft["findings"] or draft["sub_questions"]):
        if dstat == "loaded":
            degradations.append({"code": "draft_incomplete",
                                 "detail": "draft.json 有结构但缺 findings/sub_questions"})
        else:
            degradations.append({"code": "draft_%s" % dstat,
                                 "detail": "未找到可用工作稿 %s：走确定性兜底推导" % dp})
        draft = C.normalize_draft(X.derive_draft(idx))
        draft["derived"] = True
        changes.append({"change_id": "C%d" % (len(changes) + 1), "kind": "derived_fallback",
                        "detail": "无工作稿：子问题由任务句拆出、发现卡由材料句机械抽取，未经 Agent 复核，结论只能作线索"})
    chk = C.check_draft(draft, idx)
    for r in chk["repairs"]:
        changes.append({"change_id": "C%d" % (len(changes) + 1), "kind": "locator_repaired",
                        "detail": "%s %s → %s" % (r["where"], r["detail"], r["to"])})
    status = "ok"
    if idx["stats"]["readable_materials"] == 0:
        status = "insufficient_evidence"
        if any(e.get("code") == "case_json_invalid" for e in errors):
            status = "input_error"
    if draft.get("derived") or chk["stats"]["fix"] > 0:
        status = "partial" if status == "ok" else status
    data = R.assemble(draft, idx, chk)
    if not data.get("case_id"):
        data["case_id"] = (idx["case"] or {}).get("case_id") or ("case-%s" % (
            Path(idx["input_dir"]).name or "unknown"))
    files = R.render_all(draft, idx, data, chk)
    for rel, content in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, "utf-8")
    for o in data["open_questions"]:
        pass
    if any(e.get("code") == "case_json_invalid" for e in errors):
        degradations.append({"code": "case_json_invalid", "detail": "case.json 坏 JSON，按 task.md 与材料兜底"})
    if data["conflict_hints"] and not data["conflicts"]:
        degradations.append({"code": "conflict_hint_unadjudicated",
                             "detail": "脚本提示 %d 处方向相反的候选句，但工作稿未登记反证" % len(data["conflict_hints"])})
    if data["coverage"]["quotes_failed"]:
        degradations.append({"code": "quote_unverified",
                             "detail": "%d 条引文未逐字命中，相关卡片已降为 provisional/low" %
                                       data["coverage"]["quotes_failed"]})
    if data["coverage"]["sub_questions_covered"] < data["coverage"]["sub_questions"]:
        degradations.append({"code": "sub_question_uncovered",
                             "detail": "%d 个子问题无发现卡" % (
                                 data["coverage"]["sub_questions"] - data["coverage"]["sub_questions_covered"])})
    changes.append({"change_id": "C%d" % (len(changes) + 1), "kind": "finalize",
                    "detail": "build 无条件 finalize：%d 章 + 契约 %d 键" % (
                        len(files), len(idx["contract"]))})
    extra = {"phase": phase, "seconds": round(time.time() - T0, 2), "draft_status": dstat,
             "derived": bool(draft.get("derived")),
             "python": sys.version.split()[0], "skill": "research-investigation-notebook/1.0.0"}
    res = X.build_result(data["case_id"], status, data, chk, idx, degradations, errors, changes, extra, out=out)
    jwrite(out / "result.json", res)
    print("[build] status=%s derived=%s draft=%s" % (status, extra["derived"], dstat))
    print("[build] chapters=%d findings=%d evidence=%d quotes=%d/%d fix=%d warn=%d" % (
        len(files), len(data["findings"]), len(data["evidence"]),
        chk["stats"]["quotes_verified"], chk["stats"]["quotes_verified"] + chk["stats"]["quotes_failed"],
        chk["stats"]["fix"], chk["stats"]["warn"]))
    filled = sum(1 for a in res["contract_audit"] if a["filled"])
    print("[build] contract keys filled %d/%d (empty: %s)" % (
        filled, len(res["contract_audit"]),
        ", ".join(a["key"] for a in res["contract_audit"] if not a["filled"]) or "none"))
    print("[build] notebook -> %s   result -> %s" % (out / "notebook", out / "result.json"))
    if extra["derived"]:
        print("[build] WARNING: no usable draft.json — degraded fallback. Read materials, write the "
              "draft, then re-run check/build.")
    return res


def cmd_build(args):
    _finalize(args, "build")


def cmd_selfcheck(args):
    inp, work, out = _p(args)
    idx = P.build_index(inp)
    rep = {"checked_at_phase": "selfcheck", "pass": True, "items": []}

    def add(name, ok, detail):
        rep["items"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            rep["pass"] = False

    rp = out / "result.json"
    try:
        res = load_json(rp)
        add("result_json_readable", True, str(rp))
    except Exception as e:
        add("result_json_readable", False, "%s: %s" % (type(e).__name__, e))
        res = {}
    keys = [f["key"] for f in idx["contract"]]
    missing = [k for k in keys if k not in res]
    add("contract_keys_present", not missing, "missing=%s" % (missing or "none"))
    empty = [a["key"] for a in res.get("contract_audit", []) if not a["filled"]]
    add("contract_keys_filled", not empty, "empty=%s" % (empty or "none"))
    need = ["notebook/00-README.md", "notebook/01-brief.md", "notebook/02-search-log.jsonl",
            "notebook/03-findings/finding-cards.jsonl", "notebook/04-synthesis.md",
            "notebook/05-open-questions.md", "appendix/evidence-register.jsonl"]
    empt = []
    for rel in need:
        p = out / rel
        if not p.is_file() or p.stat().st_size == 0:
            empt.append(rel)
    add("chapters_present_nonempty", not empt, "empty=%s" % (empt or "none"))
    cards = 0
    cp = out / "notebook/03-findings/finding-cards.jsonl"
    if cp.is_file():
        cards = sum(1 for ln in cp.read_text("utf-8").splitlines() if ln.strip())
    add("cards_match_result", cards == len(res.get("findings") or []),
        "cards=%d result.findings=%d" % (cards, len(res.get("findings") or [])))
    qv = qf = 0
    for f in res.get("findings") or []:
        for it in (f.get("support") or []) + (f.get("counter") or []):
            loc = C.quote_locate(idx, it.get("quote") or "", it.get("source_id"))
            if loc["ok"]:
                qv += 1
            else:
                qf += 1
    add("quotes_reverified", qf == 0, "verified=%d failed=%d" % (qv, qf))
    reg = {f.get("finding_id") for f in res.get("findings") or []}
    bad = [i for f in res.get("findings") or [] for i in
           [x for x in (f.get("sub_question_id"),) if x] if i not in
           {s.get("sq_id") for s in res.get("sub_questions") or []}]
    add("findings_point_to_registered_sq", not bad, "bad=%s" % (bad or "none"))
    draft, dstat = None, "missing"
    try:
        draft = C.normalize_draft(load_json(work / "draft.json"))
        dstat = "loaded"
    except FileNotFoundError:
        pass
    except Exception:
        dstat = "invalid"
    if draft is None or not (draft["findings"] or draft["sub_questions"]):
        draft = C.normalize_draft(X.derive_draft(idx))
    chk = C.check_draft(draft, idx)
    data = R.assemble(draft, idx, chk)
    a = "".join("%s:%s" % (k, v) for k, v in sorted(R.render_all(draft, idx, data, chk).items()))
    b = "".join("%s:%s" % (k, v) for k, v in sorted(R.render_all(draft, idx, data, chk).items()))
    add("deterministic_render", a == b, "two renders identical=%s" % (a == b))
    degs = [d.get("code") for d in res.get("degradations") or []]
    add("draft_present", "draft_missing" not in degs and "draft_invalid" not in degs,
        "draft_status=%s" % dstat)
    rep["degradations"] = degs
    rep["counts"] = {"findings": len(res.get("findings") or []), "quotes_verified": qv,
                     "quotes_failed": qf, "chapters": len(need)}
    jwrite(out / "selfcheck.json", rep)
    print("[selfcheck] pass=%s" % rep["pass"])
    for it in rep["items"]:
        print("  [%s] %s — %s" % ("OK" if it["ok"] else "FAIL", it["check"], it["detail"]))
    print("[selfcheck] report -> %s" % (out / "selfcheck.json"))


# --------------------------------------------------------------------------- main
def _fallback(args, exc):
    try:
        _, _, out = _p(args)
        res = {"case_id": "unknown", "status": "partial",
               "degradations": [{"code": "unexpected_error", "detail": "%s: %s" % (
                   type(exc).__name__, str(exc)[:300])}],
               "errors": [{"code": "unexpected_error", "trace": traceback.format_exc()[-1200:]}],
               "runtime": {"phase": getattr(args, "command", "unknown"),
                           "seconds": round(time.time() - T0, 2)}}
        idx = P.build_index(out / "_none")
        res = X.attach_output_contract(res, P.DEFAULT_CONTRACT, out=out)
        jwrite(out / "result.json", res)
        print("[fatal] %s: %s" % (type(exc).__name__, exc))
        print("[fatal] wrote minimal legal result.json -> %s" % (out / "result.json"))
    except Exception:
        print("[fatal] could not write fallback result.json")
        traceback.print_exc()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="research-01 investigation notebook: init | show | check | build | selfcheck")
    ap.add_argument("--input", help="input dir (default: /input)")
    ap.add_argument("--work", help="work dir (default: /app/work)")
    ap.add_argument("--output", help="output dir (default: /app/output)")
    sub = ap.add_subparsers(dest="command")
    s = sub.add_parser("init", help="index inputs, write legal partial result.json")
    for p in (s,):
        pass
    show = sub.add_parser("show", help="print locator-tagged verbatim excerpts")
    show.add_argument("--source")
    show.add_argument("--grep")
    show.add_argument("--max-blocks", type=int, default=12)
    show.add_argument("--max-chars", type=int, default=240)
    show.add_argument("--max-sents", type=int, default=60)
    show.add_argument("--max-records", type=int, default=20)
    show.add_argument("--records", action="store_true")
    show.add_argument("--brief", action="store_true")
    sub.add_parser("check", help="validate work draft against materials")
    sub.add_parser("build", help="render notebook + final result.json (always finalises)")
    sub.add_parser("selfcheck", help="re-verify written artifacts")
    for p in (s, show, sub.choices["check"], sub.choices["build"], sub.choices["selfcheck"]):
        p.add_argument("--input", dest="input2", help=argparse.SUPPRESS)
        p.add_argument("--work", dest="work2", help=argparse.SUPPRESS)
        p.add_argument("--output", dest="output2", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    for a in ("input", "work", "output"):
        alt = getattr(args, "%s2" % a, None)
        if getattr(args, a, None) is None and alt:
            setattr(args, a, alt)
    cmd = args.command or "init"
    fn = {"init": cmd_init, "show": cmd_show, "check": cmd_check,
          "build": cmd_build, "selfcheck": cmd_selfcheck}.get(cmd, cmd_init)
    try:
        fn(args)
    except SystemExit:
        pass
    except Exception as e:
        _fallback(args, e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
