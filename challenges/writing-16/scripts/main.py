#!/usr/bin/env python3
"""main.py -- source-faithful-retargeting: init / show / check / build / selfcheck.

Standard library only. Offline. Independent of CWD. Exit code is always 0.
The Agent reads the material and writes the draft; these commands index, verify,
render and finalise. `build` always produces a valid result.json (partial if needed).
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

H = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(H))
try:
    import kit
    import audit
    import render as rd
except Exception:                                     # pragma: no cover
    kit = audit = rd = None
SK, VER, T0 = "source-faithful-retargeting", "9.0.0", time.time()
ENV = ("SKILL_INPUT", "SKILL_OUTPUT", "SKILL_WORK")
HOME = "/" + "app"
ENUM = ("ok", "partial", "insufficient_evidence", "input_error")


def paths(a):
    inp = Path(getattr(a, "input", "") or os.environ.get(ENV[0]) or "/input")
    out = Path(getattr(a, "output", "") or os.environ.get(ENV[1]) or HOME + "/output")
    wrk = Path(getattr(a, "work", "") or os.environ.get(ENV[2]) or HOME + "/work")
    notes = []
    if not inp.exists():
        for c in (H.parent / "input", Path.cwd() / "input"):
            if c.exists():
                notes.append("输入 %s 不存在，改用 %s" % (inp, c))
                inp = c
                break
    for d, tag in ((wrk, "work"), (out, "output")):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        except Exception:
            alt = H.parent / tag
            try:
                alt.mkdir(parents=True, exist_ok=True)
            except Exception:
                alt = Path.cwd() / tag
                alt.mkdir(parents=True, exist_ok=True)
            notes.append("%s 不可写，改用 %s" % (d, alt))
            if tag == "work":
                wrk = alt
            else:
                out = alt
    return inp, out, wrk, notes


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


A = (lambda v: [x for x in v if isinstance(x, dict)] if isinstance(v, list)
     else ([v] if isinstance(v, dict) else []))


def empty_result(case_id="UNKNOWN-CASE", note="init"):
    return {"skill": SK, "skill_version": VER, "case_id": case_id, "status": "partial", "task": {},
            "deliverable": None, "preserved_facts": [], "evidence_map": [], "change_log": [],
            "dropped": [], "glossary": [], "transformation_spec": {}, "sources": [],
            "fidelity_summary": {}, "uncertainty": [],
            "pending_human": ["工作稿未产出，本文件为合法 partial 结果；补写 draft.json 后重跑 build 即可提升"], "errors": [],
            "degradations": [note], "contract_fill": {"total": 0, "filled": 0, "null_fields": []},
            "runtime": {"skill": SK, "version": VER, "elapsed_s": round(time.time() - T0, 1)}}


def target_of(idx, d):
    g = d.get("genre") if isinstance(d.get("genre"), dict) else {}
    for src in (g.get("length_target"), (idx.get("workorder") or {}).get("length")):
        m = re.search(r"(\d{2,5})", str(src or ""))
        if m:
            return int(m.group(1))
    return 0


def load_index(wrk):
    p = Path(wrk) / "index.json"
    if not p.is_file():
        return None, "index.json 不存在（先跑 init）"
    try:
        return rj(p), None
    except Exception as e:
        return None, "index.json 解析失败：%s" % type(e).__name__


# ------------------------------------------------------------------ commands
def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    wj(out / "result.json", empty_result(note="init 启动：已写合法占位"))
    case, cpath, mats, degr, instr = kit.scan(inp)
    idx = kit.build_index(case, cpath, mats, instr)
    idx["degradations"] = degr + notes
    wj(wrk / "index.json", idx)
    dp = wrk / "draft.json"
    wo = idx["workorder"]
    if not dp.is_file() or getattr(a, "force", False):
        m = re.search(r"(\d{2,5})", str(wo.get("length") or ""))
        wj(dp, {"_howto": "填值后跑 check；sections[].text 必须是成稿正文，不是提纲",
                "audience": {"label": wo.get("audience") or "", "profile": "", "knowledge": "",
                             "goal": "", "depth": "", "term_policy": "", "strength_policy": ""},
                "genre": {"label": wo.get("genre") or "", "conventions": [],
                          "length_target": int(m.group(1)) if m else 0, "length_unit": "字"},
                "headline": "", "deck": "",
                "sections": [{"id": "S1", "title": "", "text": "", "cites": [], "strength": ""}],
                "retained": [{"id": "R1", "kind": "number", "value": "", "locator": "",
                              "quote": "", "where": "S1", "treatment": "kept", "note": ""}],
                "trace": [{"section_id": "S1", "source_locator": "", "source_quote": "",
                           "decision": "keep", "note": ""}],
                "changes": [{"action": "", "locator": "", "original_quote": "",
                             "revised_quote": "", "reason": ""}],
                "dropped": [], "glossary": [], "numbers_allow": [], "open_questions": [],
                "uncertainty": []})
    res = empty_result(idx["case_id"], "init: 索引完成，待 Agent 写工作稿")
    res["degradations"] += degr + notes
    res["sources"] = [{"id": m["id"], "name": m["name"], "kind": m["kind"], "role": m["role"],
                       "method": m["method"], "paragraphs": m["paragraphs"], "chars": m["chars"],
                       "sha256_16": m.get("sha256_16"), "path": m["path"]} for m in idx["materials"]]
    rd.with_contract(res, idx["output_contract"])
    res = rd.scrub(res)
    wj(out / "result.json", res)
    L = ["== 材料索引 =="]
    L += ["%-4s %-26s %-6s %-18s %6d字/%3d段 [%s]" % (m["id"], m["name"][:26], m["kind"], m["method"],
                                                     m["chars"], m["paragraphs"], m["role"])
          for m in idx["materials"]] or ["(无材料：/input 为空或不可读)"]
    L += ["", "== 工作单 ==", "case_id: %s" % idx["case_id"]]
    for k, lab in (("audience", "受众"), ("genre", "体裁"), ("length", "篇幅")):
        L.append("%s: %s%s" % (lab, wo.get(k) or "未识别（按题面确认）",
                               "   <- `%s`" % wo["basis"][k] if wo["basis"].get(k) else ""))
    L += ["契约: %s（%d 字段）" % (", ".join(idx["output_contract"]) or "无", len(idx["output_contract"])),
          "候选必保留项: %d（%s）" % (len(idx["candidates"]), " / ".join(
              "%s %d" % (k, sum(1 for x in idx["candidates"] if x["kind"] == k))
              for k in ("conclusion", "number", "sample", "figure", "citation", "limitation")
              if any(x["kind"] == k for x in idx["candidates"])) or "无"),
          "", "== 段落（前 40 / 共 %d） ==" % len(idx["paragraphs"])]
    L += ["%-10s %5d字  %s" % (p["loc"], p["chars"], p["text"][:56].replace("\n", " "))
          for p in idx["paragraphs"][:40]]
    L += ["", "== 关键数值 ==", "  " + (", ".join(idx["key_pairs"][:16]) or "未检出"),
          "== 缩写 ==", "  " + (", ".join(idx["acronyms"][:24]) or "未检出"),
          "== 图表 / 引文 ==", "  图表: %s" % (", ".join(idx["figures"][:12]) or "未检出"),
          "  引文: %s" % (", ".join(idx["citations"][:12]) or "未检出")]
    if degr:
        L += ["", "== 降级 =="] + ["  ! " + x for x in degr[:8]]
    L += ["", "下一步：`show` 读原文 → 写 %s（正文真写）→ `check` → `build`。" % dp]
    print("\n".join(L))
    return 0


def cmd_show(a):
    _, out, wrk, _ = paths(a)
    idx, err = load_index(wrk)
    if err:
        print("无法显示：%s" % err)
        return 0
    sel = list(idx["paragraphs"])
    if a.mat:
        sel = [p for p in sel if p["mat"].lower() == a.mat.lower().strip()]
    if a.ids:
        want = set()
        for part in re.split(r"[,\s]+", a.ids.strip()):
            m = re.match(r"(M\d+):P(\d+)(?:-(?:M\d+:)?P?(\d+))?$", part)
            if m:
                lo, hi = int(m.group(2)), int(m.group(3) or m.group(2))
                want |= {"%s:P%d" % (m.group(1), i) for i in range(lo, hi + 1)}
            elif part:
                want.add(part)
        sel = [p for p in sel if p["loc"] in want]
    if a.grep:
        try:
            rx = re.compile(a.grep, re.I)
        except re.error:
            rx = re.compile(re.escape(a.grep), re.I)
        sel = [p for p in sel if rx.search(p["text"])]
    n = max(1, a.limit)
    for p in sel[:n]:
        print("[%s] (%d字, %s)\n%s\n" % (p["loc"], p["chars"], p["role"], p["text"]))
    print("-- 匹配 %d 段，显示 %d ｜ 材料 %s" % (
        len(sel), min(len(sel), n), ", ".join("%s=%s(%s)" % (m["id"], m["name"], m["method"])
                                              for m in idx["materials"]) or "无"))
    if a.cands:
        print("\n== 候选必保留项（未覆盖者须在 retained 落点或在 dropped 说明） ==")
        for c in idx["candidates"][:a.limit]:
            print("  [%s] %-10s %-16s %s" % (c["locator"], c["kind"], str(c["value"])[:16],
                                             c["quote"][:70]))
    return 0


def cmd_check(a):
    _, out, wrk, _ = paths(a)
    idx, err = load_index(wrk)
    rep = {"status": "partial", "errors": [], "warnings": [], "pending": [], "stats": {}}
    if err:
        rep["errors"].append({"code": "no_index", "msg": err})
    elif not (Path(wrk) / "draft.json").is_file():
        rep["errors"].append({"code": "no_draft", "msg": "draft.json 不存在（先读材料再写工作稿）"})
    else:
        try:
            rep = audit.check_draft(rj(Path(wrk) / "draft.json"), idx)
        except Exception as e:
            rep["errors"].append({"code": "draft_unreadable",
                                  "msg": "draft.json 无法解析：%s（检查逗号/引号/括号）"
                                         % type(e).__name__})
    wj(Path(wrk) / "check.json", rep)
    st = rep["stats"]
    if st.get("sections") is not None:
        print("== check ==\n状态 %s | 段落 %s | 正文 %s 字（目标 %s，比值 %s）| 引文 %s/%s | 数字 %s（漂移 %s）"
              % (rep["status"], st.get("sections"), st.get("body_words"), st.get("length_target"),
                 st.get("length_ratio"), st.get("quote_hit"), st.get("quote_total"),
                 st.get("numbers_in_body"), len(st.get("number_errors") or [])))
        print("保留覆盖 %s/%s | 未解释缺口 %s/%s | 术语漂移 %s | 未展开缩写 %s | hedge 源 %s/成稿 %s"
              % (st.get("retention_covered"), st.get("retention_total"), st.get("retention_gap"),
                 st.get("candidates_total"), len(st.get("term_drift") or []),
                 len(st.get("abbr_unexpanded") or []), st.get("hedge_source"), st.get("hedge_kept")))
    else:
        print("== check ==\n状态 %s | 无可校验的工作稿（缺口见下方错误）" % rep["status"])
    for e in rep["errors"]:
        print("  [错误] " + str(e.get("msg")))
    for w in rep["warnings"]:
        print("  [提示] " + str(w.get("msg")))
    print("→ 修复顺序：quote → locator → 数字 → 篇幅 → 术语/强度（SKILL.md §3.4）；报告 %s"
          % (Path(wrk) / "check.json") if rep["errors"]
          else "→ 无错误，可运行 build；仍请以目标读者身份通读一遍正文。")
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    degr, errs, fb = list(notes), [], False
    idx, err = load_index(wrk)
    if idx is None:
        case, cpath, mats, d2 = kit.scan(inp)
        instr = ""
        tp = Path(inp) / "task.md"
        if tp.is_file():
            try:
                instr = kit.dec(tp.read_bytes())
            except Exception:
                instr = ""
        idx = kit.build_index(case, cpath, mats, instr)
        degr += d2 + ["index.json 缺失，build 内重建"]
    else:
        degr += list(idx.get("degradations") or [])   # init 阶段的降级随 index.json 传到 build
    dp, d = Path(wrk) / "draft.json", None
    if not dp.is_file():
        errs.append("draft.json 不存在")
        fb = True
    else:
        try:
            d = rj(dp)
        except Exception as e:
            errs.append("draft.json 解析失败：%s" % type(e).__name__)
            fb = True
    if not fb and (not isinstance(d, dict) or not any(str(s.get("text") or "").strip()
                                                      for s in A(d.get("sections")))):
        fb = True
        errs.append("draft.json 的 sections 无正文（疑似只写了标题/提纲）")
    if fb:
        degr.append("工作稿缺失或不可用 → 逐字抽取兜底（未完成受众改写）")
        d = rd.fallback_draft(idx, idx.get("workorder") or {}) or {
            "audience": {"label": "未指定"}, "genre": {"label": "未指定", "length_target": 0},
            "headline": "无可用材料：未生成转化稿", "deck": "", "sections": [], "retained": [],
            "trace": [], "changes": [], "dropped": [], "glossary": [], "open_questions": [],
            "uncertainty": []}
    rep = audit.check_draft(d, idx) if audit else {"status": "partial", "errors": [],
                                                   "warnings": [], "pending": [], "stats": {}}
    tgt, st = target_of(idx, d), rep.get("stats") or {}
    n = st.get("body_words") or 0
    material = [p for p in idx.get("paragraphs", []) if p.get("role") != "instruction"]
    c = {"status": "partial", "fallback": fb, "inp": inp, "wrk": wrk, "target": tgt,
         "ok_len": bool(tgt and 0.7 <= n / tgt <= 1.05), "degr": degr, "unc": [],
         "case_id": idx.get("case_id"), "wo": idx.get("workorder") or {}}
    if not material:
        c["status"] = "insufficient_evidence"
        c["unc"].append("输入没有任何可解析的事实材料：本稿仅为缺口说明，未编造内容")
        degr.append("无可用材料：status=insufficient_evidence")
    elif not fb and rep.get("status") == "ok":
        c["status"] = "ok"
    if not (idx.get("output_contract") or {}):
        degr.append("输入无 output_contract：result.json 仅含内置字段")
    if not (idx.get("workorder") or {}).get("audience"):
        c["unc"].append("受众未在题面显式给出，按默认（受过高等教育的非本领域读者）推断，需作者确认")
    if not tgt:
        c["unc"].append("篇幅无明确上限，按体裁常规（800–1500 字）处理")
    try:
        (Path(out) / "deliverable.md").write_text(rd.render(c, d, rep), encoding="utf-8")
        rd.write_aux(out, d, rep, c, idx)
    except Exception as e:
        errs.append("排版异常：%s: %s" % (type(e).__name__, e))
        (Path(out) / "deliverable.md").write_text(
            "# 交付说明\n\n排版阶段异常：%s\n\n已保留 result.json 与降级记录。\n" % e, encoding="utf-8")
    res = rd.finalize(Path(out), idx, d, rep, c, errs, T0)
    fs = res.get("fidelity_summary") or {}
    print("== build ==\nstatus=%s fallback=%s 字数=%s 目标=%s" % (res["status"], fb, n, tgt or "-"))
    print("文件: %s" % ", ".join(sorted(os.path.basename(f) for f in res["runtime"]["files"])))
    print("契约 %s/%s 回填（null %s）| 引文 %s/%s | 数字漂移 %s | 保留覆盖 %s/%s | errors %d | pending %d"
          % (fs.get("contract_filled"), fs.get("contract_fields"),
             len(fs.get("contract_null") or []), fs.get("quote_hit"), fs.get("quote_total"),
             fs.get("numeric_drift"), fs.get("retained_in_body"), fs.get("retained_total"),
             len(res["errors"]), len(res["pending_human"])))
    if fb:
        print("→ 这是兜底稿：请补写 draft.json 后重跑 check → build，才能拿到改写质量分。")
    return 0


def cmd_selfcheck(a):
    inp, out, wrk, _ = paths(a)
    contract, idx = {}, None
    try:
        idx, _ = load_index(wrk)
        contract = (idx or {}).get("output_contract") or {}
    except Exception:
        pass
    res, load_err = None, None
    try:
        res = rj(Path(out) / "result.json")
    except Exception as e:
        load_err = "%s: %s" % (type(e).__name__, e)
    rows, bad = [], 0

    def chk(name, ok, detail=""):
        nonlocal bad
        bad += 0 if ok else 1
        rows.append(["PASS" if ok else "FAIL", name, detail])

    chk("result.json 可解析", res is not None, load_err or "ok")
    if res is not None:
        miss = [k for k in contract if k not in res]
        chk("contract 键齐全且同名", not miss, "%d 键；缺 %s" % (len(contract), ", ".join(miss) or "无"))
        chk("case_id 非空", bool(str(res.get("case_id") or "").strip())
            and res.get("case_id") != "UNKNOWN-CASE", str(res.get("case_id")))
        chk("status 合法", res.get("status") in ENUM, str(res.get("status")))
        fs = res.get("fidelity_summary") or {}
        chk("fidelity_summary 可复算", bool(fs.get("recompute")), "见 result.json 该字段")
        chk("quote 全部逐字命中", not fs.get("quote_total") or fs.get("quote_hit") == fs.get("quote_total"),
            "%s/%s" % (fs.get("quote_hit"), fs.get("quote_total")))
        chk("数值漂移为 0", fs.get("numeric_drift") == 0, str(fs.get("numeric_drift")))
        if fs.get("length_target") and not fs.get("fallback_draft"):
            try:
                lr = float(fs.get("length_ratio") or 0)
            except (TypeError, ValueError):
                lr = 0.0
            chk("篇幅在上限内且非提纲", 0.45 <= lr <= 1.05,
                "比值 %s" % fs.get("length_ratio"))
        elif fs.get("fallback_draft"):
            chk("篇幅判定（兜底稿跳过）", True, "兜底稿未做受众改写，篇幅比值不参与判定")
        chk("证据映射非空", bool(res.get("evidence_map")), "%d 条" % len(res.get("evidence_map") or []))
        chk("必保留项非空", bool(res.get("preserved_facts")),
            "%d 条" % len(res.get("preserved_facts") or []))
        p = Path(out) / "deliverable.md"
        chk("deliverable.md 非空", p.is_file() and p.stat().st_size > 800,
            "%d 字节" % (p.stat().st_size if p.is_file() else 0))
    for f in ("retained_facts.json", "diff_map.md", "glossary.csv"):
        p = Path(out) / f
        chk("%s 存在" % f, p.is_file() and p.stat().st_size > 20,
            "%d 字节" % (p.stat().st_size if p.is_file() else 0))
    print("== selfcheck ==")
    print(rd.tb(["结论", "检查项", "细节"], rows) if rd else "\n".join(map(str, rows)))
    print("PASS %d / FAIL %d" % (len(rows) - bad, bad))
    if bad:
        print("→ 有 %d 项未通过：修 draft.json → check → build，然后重跑 selfcheck。" % bad)
    elif (res or {}).get("status") != "ok":
        print("→ 机械项全过，但 status=%s：按 pending_human 与 degradations 补齐仍可提升。"
              % (res or {}).get("status"))
    else:
        print("→ 可交付。最后一步：以目标读者身份通读 deliverable.md，确认没有读不懂的句子。")
    return 0


def cmd_all(a):
    """单命令保底路径：init → build（无工作稿则逐字兜底）→ selfcheck，退出码恒 0。"""
    for fn in (cmd_init, cmd_build, cmd_selfcheck):
        try:
            fn(a)
        except Exception as e:
            print("== all == %s 降级：%s: %s" % (fn.__name__, type(e).__name__, e))
    print("== all == 完成：deliverable.md / retained_facts.json / diff_map.md / glossary.csv / result.json 均在输出目录")
    return 0


def main(argv=None):
    par = argparse.ArgumentParser(
        prog="main.py", description="source-faithful-retargeting v%s：all / init→show→(写 draft)→check→build→selfcheck" % VER)
    sub = par.add_subparsers(dest="cmd")

    def flags(sp, force=False):
        # default=SUPPRESS: 子命令上的同名参数不覆盖父级已解析的值（两种写法都能用）
        sp.add_argument("--input", default=argparse.SUPPRESS, help="输入目录（默认 /input）")
        sp.add_argument("--output", default=argparse.SUPPRESS, help="产物目录（默认 /app/output）")
        sp.add_argument("--work", default=argparse.SUPPRESS, help="工作目录（默认 /app/work）")
        if force:
            sp.add_argument("--force", action="store_true", help="覆盖已存在的 draft.json（默认不覆盖）")

    flags(sub.add_parser("init", help="扫描输入、建索引、写合法 partial result.json 与 draft 模板"), True)
    flags(sub.add_parser("all", help="等价入口（单命令）：init→build→selfcheck，无工作稿也产出全部交付物"))
    flags(sub.add_parser("check", help="校验工作稿：契约/引文/数字/覆盖/术语/强度/篇幅"))
    flags(sub.add_parser("build", help="生成 deliverable.md 与附表，无条件 finalize result.json"))
    flags(sub.add_parser("selfcheck", help="复检已产出结果：契约键、可复算指标、文件"))
    sp = sub.add_parser("show", help="打印带 locator 的原文供逐字引用")
    flags(sp)
    sp.add_argument("--ids", default="", help="如 M1:P1-M1:P8")
    sp.add_argument("--grep", default="", help="关键词或正则")
    sp.add_argument("--mat", default="", help="只看某材料，如 M1")
    sp.add_argument("--limit", type=int, default=40)
    sp.add_argument("--cands", action="store_true", help="同时列出候选必保留项")
    par.add_argument("--input", default="", help=argparse.SUPPRESS)
    par.add_argument("--output", default="", help=argparse.SUPPRESS)
    par.add_argument("--work", default="", help=argparse.SUPPRESS)
    a = par.parse_args(argv)
    cmd = a.cmd or "init"
    fns = {"init": cmd_init, "show": cmd_show, "check": cmd_check,
           "build": cmd_build, "selfcheck": cmd_selfcheck, "all": cmd_all}
    try:
        return fns[cmd](a)
    except Exception as e:
        try:
            _, out, _, _ = paths(a)
            res = empty_result(note="运行异常，已降级")
            res["errors"] = ["%s: %s" % (type(e).__name__, e), traceback.format_exc()[-700:]]
            wj(out / "result.json", res)
            if cmd != "show":
                (out / "deliverable.md").write_text(
                    "# 交付说明\n\n`%s` 阶段异常：%s\n\n降级记录见 result.json 的 errors。\n" % (cmd, e),
                    encoding="utf-8")
        except Exception:
            pass
        print("已兜底（退出码仍为 0）：%s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
