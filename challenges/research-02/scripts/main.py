#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""outline-slot-review 命令行：init / show / check / build / selfcheck。

输入 /input（回退 ./input），工作稿 /app/work，产物 /app/output；
纯标准库、离线、不依赖 CWD；任何分支退出码恒 0，且磁盘上始终存在合法 result.json。
"""
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit
import rules
from kit import SKILL, V, blank_result, prepare, read_json, resolve, write_json, write_jsonl, write_text


# ------------------------------------------------------------------ init
def cmd_init(a):
    ctx = prepare(a)
    work, out = ctx["work"], ctx["out"]
    write_json(out / "result.json", blank_result(ctx))
    write_json(work / "index.json", {
        "case_id": ctx["cid"], "input_dir": str(ctx["ind"]), "language": ctx["lg"], "research_question": ctx["rq"],
        "contract_fields": list(ctx["con"]), "task_instruction": ctx["instr"][:1200], "docs": ctx["sources"],
        "records": ctx["records"], "locator_format": "<相对输入根的路径>#B<块号>S<句号>@<起始字符>-<结束字符>"})
    write_jsonl(work / "records.jsonl", ctx["records"])
    dp = work / "draft.json"
    made = "已存在，未覆盖"
    if not dp.exists():
        write_json(dp, kit.scaffold(ctx))
        made = "已生成脚手架"
    print("init: case=%s 材料 %d 个（source %d / records %d / protocol %d）语言=%s"
          % (ctx["cid"], len(ctx["docs"]), sum(1 for d in ctx["docs"] if d["kind"] == "source"),
             len(ctx["records"]), sum(1 for d in ctx["docs"] if d["kind"] == "protocol"), ctx["lg"]))
    print("      产物 %s；工作 %s；draft.json %s" % (out, work, made))
    print("      契约字段 %d 个：%s" % (len(ctx["con"]), ", ".join(list(ctx["con"])[:12])))
    if ctx["records"]:
        print("      题录 %d 条（重复 %d）：%s" % (len(ctx["records"]),
                                                 sum(1 for r in ctx["records"] if r["duplicate_of"]),
                                                 ", ".join(r["record_id"] for r in ctx["records"][:10])))
    print("下一步：python3 scripts/main.py show   # 用 locator 读材料，然后你亲自写 draft.json")
    return 0


# ------------------------------------------------------------------ show
def cmd_show(a):
    ctx = prepare(a)
    if a.task:
        print("== task.md ==")
        print((ctx["task"] or "（无 task.md）")[:a.max * 120])
        print("\n== case 指令 ==")
        print(ctx["instr"][:3000] or "（case 未给指令）")
        return 0
    if a.records:
        print("record_id | source_id | year | doi | title | 备注")
        for r in ctx["records"]:
            print("%s | %s | %s | %s | %s | %s" % (r["record_id"], r["source_id"] or "—", r["year"] or "—",
                                                  r["doi"] or "—", (r["title"] or "—")[:90], r["note"] or ""))
        if not ctx["records"]:
            print("（输入未提供题录；按材料文件逐篇筛选）")
        return 0
    if a.grep:
        hit = 0
        for u in ctx["units"]:
            if re.search(a.grep, u["text"], re.I):
                print("[%s] %s\n    %s" % (u["sid"], u["loc"], u["text"][:400]))
                hit += 1
                if hit >= a.max:
                    break
        print("\n-- 命中 %d 句（上限 %d）--" % (hit, a.max))
        return 0
    if a.source:
        d = ctx["dmap"].get(a.source) or next((x for x in ctx["docs"] if x["path"] == a.source), None)
        if not d:
            print("未找到来源 %s；可用：%s" % (a.source, ", ".join(sorted(k for k in ctx["dmap"]))))
            return 0
        print("%s | %s | kind=%s method=%s abstract_only=%s chars=%d sentences=%d"
              % (d["sid"], d["path"], d["kind"], d["method"], d["abstract_only"],
                 len(d["text"] or ""), len(d["units"])))
        print("meta: title=%s year=%s doi=%s" % ((d["meta"].get("title") or "—")[:120],
                                                 d["meta"].get("year") or "—", d["meta"].get("doi") or "—"))
        for n, u in enumerate(d["units"], 1):
            if n > a.max:
                print("... 余下 %d 句未显示，用 --max 放大" % (len(d["units"]) - a.max))
                break
            print("%s%s\n      %s" % ("## " if u["heading"] else "  ", u["loc"], u["text"][:600]))
        if not d["units"]:
            print("（无可切分文本；见 init 输出的 degradations）")
        return 0
    print("case_id=%s 语言=%s 材料 %d 个；locator：<path>#B<块>S<句>@<start>-<end>"
          % (ctx["cid"], ctx["lg"], len(ctx["docs"])))
    for d in ctx["docs"]:
        print("%-4s %-38s kind=%-8s %-10s %6dB %4d句 abs=%-3s %s"
              % (d["sid"], d["path"][:38], d["kind"], d["method"], d["bytes"], len(d["units"]),
                 "yes" if d["abstract_only"] else "no", (d["meta"].get("title") or "")[:56]))
    print("\n用法：show --source S01 [--max 200] | show --grep <正则> | show --records | show --task")
    return 0


# ------------------------------------------------------------------ check
def cmd_check(a):
    ctx = prepare(a)
    dp = ctx["work"] / "draft.json"
    issues, raw = [], None
    if not dp.exists():
        issues.append({"code": "C101", "level": "FIX", "name": "draft_json_missing", "target": str(dp),
                       "message": "工作稿不存在", "hint": "先 show 读材料，再写 draft.json（SKILL.md 第 5 节）"})
    else:
        raw = read_json(dp, "__bad__")
        if raw == "__bad__":
            issues.append({"code": "C102", "level": "FIX", "name": "json_invalid", "target": str(dp),
                           "message": "draft.json 不是合法 JSON", "hint": "修语法后重跑 check"})
            raw = {}
    m = rules.norm(raw or {}, ctx)
    if raw and m["authored"]:
        issues += rules.validate(m, ctx)
        if str(m["case_id"]) != str(ctx["cid"]):
            issues.append({"code": "C103", "level": "WARN", "name": "case_id_mismatch", "target": "case_id",
                           "message": "draft %s vs case %s" % (m["case_id"], ctx["cid"]), "hint": "与输入对齐"})
    elif raw:
        issues.append({"code": "C101", "level": "FIX", "name": "scaffold_only", "target": str(dp),
                       "message": "工作稿仍为 init 脚手架（_scaffold=true）", "hint": "按第 5 节填写后保存"})
    fix = [i for i in issues if i["level"] == "FIX"]
    rep = {"case_id": ctx["cid"], "ready_to_build": not fix, "fix": len(fix), "warn": len(issues) - len(fix),
           "checks": issues, "counts": {"criteria": len(m["criteria"]), "screening": len(m["screening"]),
                                        "sections": len(m["outline"]), "slots": len(m["slots"])}}
    write_json(ctx["work"] / "check_report.json", rep)
    print("check: %d FIX / %d WARN -> %s" % (rep["fix"], rep["warn"],
                                             "就绪，可 build" if rep["ready_to_build"] else "未就绪，先修 FIX"))
    print("      当前工作稿：条款 %d，筛选行 %d，章节 %d，槽位 %d"
          % (len(m["criteria"]), len(m["screening"]), len(m["outline"]), len(m["slots"])))
    for i in sorted(issues, key=lambda x: (0 if x["level"] == "FIX" else 1, x["code"]))[:40]:
        print("  [%s] %s %s: %s -> %s" % (i["level"], i["code"], i["target"], i["message"], i["hint"]))
    if len(issues) > 40:
        print("  ... 共 %d 条，完整见 %s" % (len(issues), ctx["work"] / "check_report.json"))
    print("记录：%s" % (ctx["work"] / "check_report.json"))
    return 0


# ------------------------------------------------------------------ build
def cmd_build(a):
    ctx = prepare(a)
    out, work = ctx["out"], ctx["work"]
    write_json(out / "result.json", blank_result(ctx))          # 先落合法 partial，再 finalize
    changes, errs, degs = [], list(ctx["errs"]), list(ctx["degs"])
    raw = read_json(work / "draft.json", "__bad__")
    why = None
    if raw == "__bad__":
        m, why = rules.fallback(ctx, "draft.json 缺失或不是合法 JSON"), "draft.json 缺失或非法"
    elif not raw:
        m, why = rules.fallback(ctx, "未找到工作稿 draft.json"), "未找到工作稿"
    elif raw.get("_scaffold") and not (raw.get("criteria") or raw.get("outline") or raw.get("slots")):
        m, why = rules.fallback(ctx, "工作稿仍是 init 脚手架"), "工作稿未填写（脚手架）"
    else:
        m = rules.norm(raw, ctx)
        if not (m["criteria"] or m["outline"] or m["slots"]):
            m, why = rules.fallback(ctx, "工作稿无 criteria/outline/slots"), "工作稿为空"
    if why:
        degs.append({"stage": "build", "type": "work_draft_missing", "detail": why + "：已产出降级最小交付"})
    fixed = rules.repair(m, ctx, changes, degs)
    issues = [] if why else rules.validate(m, ctx)
    fix = [i for i in issues if i["level"] == "FIX"]
    cov = rules.coverage(m, ctx)
    draft, gr, unc = rules.render_draft(m, ctx, cov), rules.gap_report(m, ctx, cov), rules.uncertainty(m, ctx, cov)
    key = lambda x: (len(x), x)
    filled = [m["slots"][k] for k in sorted(m["slots"], key=key) if m["slots"][k]["state"] == "filled"]
    gaps = [m["slots"][k] for k in sorted(m["slots"], key=key) if m["slots"][k]["state"] == "gap"]
    label = {s["slot_id"]: sec["heading"] for sec in m["outline"] for s in sec["slots"]}
    slot_rows = [{"slot_id": s["slot_id"], "section": label.get(s["slot_id"], ""), "claim": s["claim"],
                  "strength": s["strength"], "polarity": s["polarity"], "conflicts_with": s["conflicts_with"],
                  "evidence_refs": s["evidence_refs"], "verified": bool(s["evidence_refs"])} for s in filled]
    gap_rows = [{"slot_id": s["slot_id"], "section": label.get(s["slot_id"], ""), "gap_type": s["gap_type"],
                 "gap_reason": s["gap_reason"], "search_scope": s["search_scope"],
                 "missing_evidence": s["missing_evidence"]} for s in gaps]
    status = ("input_error" if not [d for d in ctx["docs"] if d["kind"] == "source"]
              else "partial" if (why or fix or fixed["dropped"] or cov["filled_ratio"] < 0.5 or errs) else "ok")
    write_json(out / "screening" / "criteria.json", {"case_id": ctx["cid"], "protocol": m["protocol"],
                                                     "criterion_count": len(m["criteria"]), "criteria": m["criteria"]})
    write_jsonl(out / "screening" / "screening_log.jsonl", m["screening"])
    write_json(out / "outline" / "skeleton.json", {
        "case_id": ctx["cid"], "research_question": m["rq"], "outline_basis": m["outline_basis"],
        "sections": [{"sec_id": s["sec_id"], "heading": s["heading"], "purpose": s["purpose"], "lead": s["lead"],
                      "lead_slot_ids": s["lead_slot_ids"], "slots": s["slots"]} for s in m["outline"]]})
    write_jsonl(out / "slots" / "filled.jsonl", slot_rows)
    write_jsonl(out / "slots" / "gaps.jsonl", gap_rows)
    write_text(out / "draft.md", draft)
    write_json(out / "gap_report.json", gr)
    write_json(out / "coverage.json", dict(cov, case_id=ctx["cid"], quotes_verified=cov["evidence_refs"],
                                           check={"fix": len(fix), "warn": len(issues) - len(fix)}))
    write_json(out / "changes.json", {"case_id": ctx["cid"], "count": len(changes), "repairs": fixed,
                                      "changes": changes})
    write_json(out / "screening" / "check_report.json", {"case_id": ctx["cid"], "checks": issues, "fix": len(fix)})
    prods = {"draft_text": draft, "slot_rows": slot_rows, "gap_rows": gap_rows, "coverage": cov,
             "uncertainty": unc, "changes": changes, "status": status}
    res, cmap = {}, {}
    for k in ctx["con"]:
        v, art = rules.value_for(k, prods, m, ctx)
        res[k] = v
        if art:
            cmap[k] = art
        if v is None:
            degs.append({"stage": "contract", "type": "unmapped_field",
                         "detail": "字段 %s 无对应产物，按 null 回填" % k})
    env = {"case_id": ctx["cid"], "status": status, "skill": SKILL, "skill_version": V, "contract_map": cmap,
           "artifacts": {"draft": "draft.md", "outline": "outline/skeleton.json",
                         "criteria": "screening/criteria.json", "screening": "screening/screening_log.jsonl",
                         "slots_filled": "slots/filled.jsonl", "slots_gaps": "slots/gaps.jsonl",
                         "gap_report": "gap_report.json", "coverage": "coverage.json", "changes": "changes.json"},
           "sources": ctx["sources"], "metrics": cov, "uncertainty": unc, "changes": changes,
           "degradations": degs, "errors": errs,
           "runtime": {"script": "main.py", "version": V, "python": sys.version.split()[0],
                       "seconds": round(time.time() - ctx["t0"], 2), "network": "disabled",
                       "commands": ["init", "show", "check", "build", "selfcheck"]}}
    for k, v in env.items():
        res.setdefault(k, v)
    write_json(out / "result.json", res)
    print("build: status=%s 章节=%d 槽位=%d 已填=%d 缺口=%d 覆盖率=%.0f%% 引文=%d"
          % (status, cov["sections"], cov["slots_total"], cov["filled"], cov["gaps"],
             100 * cov["filled_ratio"], cov["evidence_refs"]))
    print("       修补：引文纠正 %d，丢弃 %d，强度下调 %d，槽位转缺口 %d，冲突对称 %d"
          % (fixed["quote"], fixed["dropped"], fixed["strength"], fixed["gap"], fixed["sym"]))
    print("       产物：%s/draft.md（%d 字）与 result.json（契约 %d/%d）"
          % (out, len(draft), len([k for k in ctx["con"] if k in res]), len(ctx["con"])))
    if why:
        print("       兜底模式：%s；逐条缺口见 slots/gaps.jsonl 与 gap_report.json" % why)
    elif fix:
        print("       注意：仍有 %d 个 FIX 级问题（见 screening/check_report.json），status 记为 %s" % (len(fix), status))
    return 0


# ------------------------------------------------------------------ selfcheck
def cmd_selfcheck(a):
    ctx = prepare(a)
    out = ctx["out"]
    chk = []

    def c(name, ok, detail=""):
        chk.append({"check": name, "pass": bool(ok), "detail": detail})

    rj = read_json(out / "result.json")
    c("result_json_parses", isinstance(rj, dict), "缺失或非法" if not isinstance(rj, dict) else "ok")
    rj = rj if isinstance(rj, dict) else {}
    miss = [k for k in ctx["con"] if k not in rj]
    c("contract_fields", not miss, "缺 %s" % miss if miss else "回填 %d/%d" % (len(ctx["con"]), len(ctx["con"])))
    c("case_id_echo", str(rj.get("case_id")) == str(ctx["cid"]), str(rj.get("case_id")))
    c("envelope", all(k in rj for k in ("status", "errors", "degradations", "sources")), "status/errors/degradations/sources")
    arts = ("draft.md", "outline/skeleton.json", "screening/criteria.json", "screening/screening_log.jsonl",
            "slots/filled.jsonl", "slots/gaps.jsonl", "gap_report.json", "coverage.json")
    c("artifacts_present", all((out / f).exists() for f in arts),
      "缺 %s" % [f for f in arts if not (out / f).exists()])
    rows, bad, tot = [], [], 0
    p = out / "slots" / "filled.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                if line.strip():
                    bad.append("jsonl")
    for r in rows:
        for e in r.get("evidence_refs") or []:
            tot += 1
            d = ctx["dmap"].get(e.get("source_id") or "")
            if not d or kit.find_quote(e.get("quote"), d)[0] not in ("exact", "normalized"):
                bad.append("%s/%s" % (r.get("slot_id"), e.get("source_id")))
    c("quotes_reverbatim", (tot > 0 or not rows) and not bad,
      "命中 %d/%d%s" % (tot - len(bad), tot, "" if not bad else " 失败:" + ",".join(bad[:6])))
    sk = read_json(out / "outline" / "skeleton.json", {}) or {}
    sids = {s["slot_id"] for sec in sk.get("sections", []) for s in sec.get("slots", [])}
    gp = []
    p2 = out / "slots" / "gaps.jsonl"
    if p2.exists():
        gp = [json.loads(l) for l in p2.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    got = {r["slot_id"] for r in rows} | {g["slot_id"] for g in gp}
    c("slots_cover_outline", bool(sids) and sids == got,
      "outline %d / 产物 %d；差 %s" % (len(sids), len(got), sorted(sids ^ got)[:6] or "无"))
    draft = (out / "draft.md").read_text(encoding="utf-8", errors="replace") if (out / "draft.md").exists() else ""
    tags = {t for grp in re.findall(r"\[((?:SL\d+)(?:,SL\d+)*)\]", draft) for t in grp.split(",")}
    c("draft_backlinks", tags <= sids and (bool(tags) or not rows),
      "段落标记 %d 个，未声明 %s" % (len(tags), sorted(tags - sids)[:4] or "无"))
    marks = set(re.findall(r"\[(S\d+)\]", draft))
    c("citations_resolvable", all(mk in ctx["dmap"] for mk in marks), "引文标记 %s" % (", ".join(sorted(marks)) or "无"))
    c("gap_fields", all(g.get("gap_type") in kit.GAP_TYPES and g.get("search_scope") for g in gp),
      "%d 个缺口" % len(gp))
    ch = kit.cliche_hits(json.dumps(read_json(out / "gap_report.json", {}) or {}, ensure_ascii=False))
    c("no_cliche_in_gaps", not ch, "命中套话 %s" % ch if ch else "未命中")
    cov = read_json(out / "coverage.json", {}) or {}
    c("coverage_consistent", cov.get("filled") == len(rows) and cov.get("gaps") == len(gp),
      "filled_ratio=%s（filled %s / gaps %s / 文件 %s,%s）"
      % (cov.get("filled_ratio"), cov.get("filled"), cov.get("gaps"), len(rows), len(gp)))
    passed = all(x["pass"] for x in chk)
    write_json(out / "selfcheck.json", {"case_id": ctx["cid"], "passed": passed, "checks": chk,
                                        "limits": ["未联网核验文献真实性与 DOI（离线）",
                                                   "PDF 若走 std-miniz 近似抽取，版式与连字不可靠，引文需回原文复核"]})
    print("selfcheck %s  %d/%d 项通过" % ("PASS" if passed else "FAIL", sum(1 for x in chk if x["pass"]), len(chk)))
    for x in chk:
        if not x["pass"]:
            print("  [FAIL] %s: %s" % (x["check"], x["detail"]))
    print("记录：%s" % (out / "selfcheck.json"))
    if not passed:
        print("提示：若失败项与内容有关，回到 show -> 改 draft.json -> check -> build，再 selfcheck")
    return 0


# ------------------------------------------------------------------ 入口
def main(argv=None):
    try:
        return _main(argv)
    except SystemExit:
        return 0
    except Exception as e:
        try:
            kit.fail_result(resolve(argparse.Namespace(input=None, output=None, work=None))[1], e)
        except Exception:
            pass
        import traceback
        traceback.print_exc()
        return 0


def _main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="outline-slot-review：提纲驱动的文献综述（筛选 → 提纲槽位 → 逐字引文填充 → 渲染草稿）。"
                    "纯标准库、离线、先写 partial result.json 再 finalize、退出码恒 0。",
        epilog="主路径：init → show → 写 draft.json → check → build → selfcheck")
    ap.add_argument("--version", action="version", version="outline-slot-review " + V)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", help="输入目录（默认 /input，回退 ./input）")
    common.add_argument("--output", help="产物目录（默认 /app/output）")
    common.add_argument("--work", help="工作目录（默认 /app/work）")
    for p in (ap, common):
        pass
    sub = ap.add_subparsers(dest="cmd")
    helps = {"init": "建索引与工作稿脚手架，并先写 partial result.json",
             "show": "打印带 locator 的材料/题录/检索命中，供逐字引用",
             "check": "机械校验工作稿（标准先行/引文逐字/槽位覆盖/契约/冲突）",
             "build": "由工作稿生成全部产物并 finalize result.json（含缺稿兜底）",
             "selfcheck": "独立复检产物与契约回填"}
    for name, fn in (("init", cmd_init), ("show", cmd_show), ("check", cmd_check),
                     ("build", cmd_build), ("selfcheck", cmd_selfcheck)):
        sp = sub.add_parser(name, help=helps[name], parents=[common])
        sp.add_argument("--source", help="show：只看某个来源，如 S01")
        sp.add_argument("--grep", help="show：在全材料中检索（正则）")
        sp.add_argument("--max", type=int, default=60, help="show：最大输出条数（默认 60）")
        sp.add_argument("--records", action="store_true", help="show：打印题录表")
        sp.add_argument("--task", action="store_true", help="show：打印 task.md 与 case 指令")
        sp.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 0
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
