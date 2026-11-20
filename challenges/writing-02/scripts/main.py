#!/usr/bin/env python3
"""claim-preserving-polish — CLI: init / show / check / build / selfcheck.

主路径：
  init  建索引 + 合法 partial result.json
  show  打印带 locator 的原文、保护性原子、限定强度与术语候选
  (Agent 亲自润色，写 /app/work/draft.json)
  check 机械校验：原子守恒、限定强度、否定、最小编辑、修改记录五要素
  build 生成 polished.md / changes.csv / glossary.csv / verification.json / result.json
  selfcheck 复检产物

脚本不代替阅读与判断；异常一律捕获、result.json 一定合法、退出码恒 0。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polish_core as pc  # noqa: E402
import pipeline as pl  # noqa: E402
import render as rd  # noqa: E402
from contract import postprocess  # noqa: E402

DEFAULT_INPUT = "/input"
DEFAULT_WORK = "/app/work"
DEFAULT_OUT = "/app/output"
MAIN_FILE = "polished.md"

def append_cmd_log(work, cmd):
    path = os.path.join(work, "cmd_log.json")
    rows = pc.jload(path, []) or []
    rows.append({"cmd": cmd, "at": pc.now_iso()})
    pc.jdump(path, rows[-40:])

def load_state(a):
    case, materials, task_text, errors, degradations = pl.discover(a.input, a.case, a.task)
    body = [m for m in materials if m.get("role") != "glossary"] or materials
    gloss_files = [m for m in materials if m.get("role") == "glossary"]
    if gloss_files:
        degradations.append("术语表文件 %d 份按锁定式摄取，不计入正文" % len(gloss_files))
    profile = pl.build_profile(body, task_text, case)
    doc_text, paragraphs = pl.build_segments(body)
    provided = pl.provided_glossary(a.input, materials)
    candidates = pl.term_candidates(doc_text, paragraphs, provided)
    contract = pl.find_key(case, "output_contract") or {}
    raw_id = pl.find_key(case, "case_id") or pl.find_key(case, "id")
    if not raw_id:
        raw_id = os.path.basename(body[0]["path"]) if body[0].get("path") else "unknown-case"
    sources = [{"kind": "material", "via": m.get("via", ""), "path": m.get("path") or "(inline)",
                "chars": len(m["text"]), "sha256": pc.sha256_text(m["text"]),
                "used_for": "唯一事实来源：润色不新增材料外事实"} for m in body]
    sources += [{"kind": "glossary", "via": m.get("via", ""), "path": m.get("path") or "(inline)",
                 "chars": len(m["text"]), "sha256": pc.sha256_text(m["text"]),
                 "used_for": "术语锁定式，优先于 Agent 判断"} for m in gloss_files]
    return {
        "case": case, "case_id": str(raw_id), "materials": materials, "task_text": task_text,
        "errors": errors, "degradations": degradations, "profile": profile, "doc_text": doc_text,
        "segments": {"paragraphs": paragraphs,
                     "doc": {"chars": len(doc_text), "sha256": pc.sha256_text(doc_text),
                             "materials": len(materials)}},
        "provided": provided, "candidates": candidates, "contract": contract, "sources": sources,
        "glossary_files": gloss_files,
        "material_fallback": bool(body) and body[0].get("via") == "task.md",
    }

def load_draft(work):
    for name in ("draft.json", "plan.json"):
        path = os.path.join(work, name)
        data = pc.jload(path)
        if isinstance(data, dict):
            return data, path
    return None, ""

def usable(draft):
    return bool(draft and (draft.get("items") or draft.get("untouched") or draft.get("glossary")))

_EDIT_RULES = [
    (r"\bIn this paper, we\b", "We", "concision", "摘要/正文默认指本文工作，In this paper 属冗余框架语", "en"),
    (r"\bIn this work, we\b", "We", "concision", "In this work 与主语重复，删去不损失信息", "en"),
    (r"\ba total of (?=\d)", "", "concision", "数字前 a total of 属冗余量词，删去不改变数值", "en"),
    (r"\bin order to\b", "to", "concision", "in order to 可压缩为 to，语义不变", "en"),
    (r"\bdue to the fact that\b", "because", "concision", "due to the fact that 冗长，because 更直接", "en"),
    (r"\butilizes\b", "uses", "word_choice", "utilize 与 use 同义，学术语域下 use 更直接", "en"),
    (r"\butilized\b", "used", "word_choice", "utilize 与 use 同义，学术语域下 use 更直接", "en"),
    (r"\butilizing\b", "using", "word_choice", "utilize 与 use 同义，学术语域下 use 更直接", "en"),
    (r"\butilize\b", "use", "word_choice", "utilize 与 use 同义，学术语域下 use 更直接", "en"),
    (r"\bet al\b(?!\.)", "et al.", "punctuation", "et al. 的缩写点缺失，补齐不改变引用对象", "en"),
    (r"(?<=\S) {2,}", " ", "punctuation", "句中连续空格合并为一个，版式规范", "any"),
    (r" +([,.;:!?])(?!\d)", r"\1", "punctuation", "标点前不应有空格", "en"),
    (r",(?=[A-Za-z])", ", ", "punctuation", "英文逗号后缺空格（数字千分位不受影响）", "en"),
    (r"([a-z])(?=\((?:[A-Z][a-z]|\d))", r"\1 ", "punctuation", "括号前补空格，避免单词与括号粘连", "en"),
    (r" +([，。；：、？！）】」])", r"\1", "punctuation", "中文标点前不应有空格", "zh"),
    (r"([（【「]) +", r"\1", "punctuation", "中文左括号后不应有空格", "zh"),
]

_FROZEN_RE = re.compile(r"\\(documentclass|usepackage|begin|end|section|subsection|cite|citep|ref|label|"
                        r"frac|mathrm|textbf|emph|setmainfont|setCJKmainfont|bibliographystyle|"
                        r"bibliography|onehalfspacing|captionsetup|includegraphics)|```|\$\$")

def _apply_rules(text, lang):
    """返回 (after_text, changes)。changes 只登记真正命中的规则；规则按段落语言过滤。"""
    cur, changes = text, []
    for pat, repl, typ, reason, scope in _EDIT_RULES:
        if scope != "any" and scope != lang:
            continue
        hits = list(re.finditer(pat, cur))
        if not hits:
            continue
        for m in hits:
            before_span = m.group(0)
            after_span = m.expand(repl)
            if before_span == after_span:
                continue
            changes.append({"before_span": before_span, "after_span": after_span,
                            "type": typ, "reason": reason})
        cur = re.sub(pat, repl, cur)
    return cur, changes

def autodraft(a, state):
    """在 /app/work/draft.json 不存在时，自动写一份保守的最小编辑工作稿。"""
    draft, path = load_draft(a.work)
    if usable(draft):
        return draft, path, False
    items, untouched = [], []
    for para in state["segments"]["paragraphs"]:
        if para.get("kind") not in ("body", "heading"):
            continue
        before = para["text"]
        if _FROZEN_RE.search(before):
            untouched.append({"paragraph_id": para["id"],
                              "reason": "LaTeX/代码段整体冻结：自动规则不改命令、参数与环境体"})
            continue
        after, changes = _apply_rules(before, pc.detect_language(before))
        if changes and pc.norm_ws(after) != pc.norm_ws(before):
            items.append({"paragraph_id": para["id"], "before": before, "after": after,
                          "changes": changes, "hedge_override": None})
        else:
            untouched.append({"paragraph_id": para["id"],
                              "reason": "自动守卫未发现高置信度机械问题；语义层修改留给 Agent 复核"})
    draft = {"case_id": state["case_id"],
             "task_understanding": {"genre": state["profile"].get("genre"),
                                    "target_language": state["profile"].get("language"),
                                    "audience": "按 task.md 声明",
                                    "must_do": ["只改语言层", "逐处留痕", "数字/单位/引用/图表指向逐字保留"],
                                    "must_protect": ["protected atoms (numbers, units, citations, pointers, equations)"]},
             "glossary": [], "items": items, "untouched": untouched,
             "uncertainties": [{"paragraph_id": None, "issue": "自动工作稿只含机械修正，语义级改写需人工确认",
                                "options": ["接受机械修正", "由 Agent 补写语义层编辑"], "severity": "low"}],
             "result_fields": {}}
    draft["uncertainties"][0].pop("paragraph_id")
    path = os.path.join(a.work, "draft.json")
    pc.jdump(path, draft)
    pc.log("== auto-draft ==（无工作稿 → 自动生成保守最小编辑稿：%d 段有改动，%d 段声明无需改）"
           % (len(items), len(untouched)))
    return draft, path, True

def write_work_files(a, state):
    pc.ensure(a.work)
    pc.jdump(os.path.join(a.work, "case_profile.json"), {
        "case_id": state["case_id"], "profile": state["profile"], "contract": state["contract"],
        "errors": state["errors"], "degradations": state["degradations"], "sources": state["sources"],
        "generated_at": pc.now_iso()})
    pc.jdump(os.path.join(a.work, "segments.json"), state["segments"])
    pc.jdump(os.path.join(a.work, "glossary_candidates.json"), state["candidates"])
    template = os.path.join(a.work, "draft.template.json")
    if not os.path.exists(template):
        pc.jdump(template, {
            "_howto": ("复制本文件为 /app/work/draft.json 后逐段填写。before 必须逐字复制 show 输出的原文；"
                       "after 是改后文本（确实无需改的段落放进 untouched 并写理由）；changes 每项写 "
                       "before_span/after_span/type/reason；hedge_override 仅在你**有意**改变结论强度时填写。"
                       "填完先跑 check，再跑 build。"),
            "case_id": state["case_id"],
            "task_understanding": {"genre": state["profile"]["genre"],
                                   "target_language": state["profile"]["language"],
                                   "audience": "", "must_do": [], "must_protect": []},
            "glossary": [], "items": [], "untouched": [], "uncertainties": [], "result_fields": {},
        })

def cmd_init(a):
    state = load_state(a)
    pc.ensure(a.work)
    pc.ensure(a.out)
    write_work_files(a, state)
    out = rd.finalize(a, state, None, "init", False)
    pc.log("== init ==")
    pc.log("case_id       : %s" % state["case_id"])
    pc.log("材料          : %d 份 / %d 字符（%s）" % (len(state["materials"]), state["profile"]["chars"],
                                                ", ".join(m.get("via", "?") for m in state["materials"][:4]) or "-"))
    if state.get("glossary_files"):
        pc.log("术语表文件    : %s" % ", ".join(g.get("path") or g.get("via", "?") for g in state["glossary_files"]))
    pc.log("文体/语言/模式: %s / %s / %s" % (state["profile"]["genre"], state["profile"]["language"],
                                          state["profile"]["mode"]))
    pc.log("段落          : %d 段（冻结块 %d，标题 %d）"
           % (len(state["segments"]["paragraphs"]),
              sum(1 for p in state["segments"]["paragraphs"] if p["kind"] == "frozen"),
              sum(1 for p in state["segments"]["paragraphs"] if p["kind"] == "heading")))
    pc.log("契约字段      : %s" % (", ".join(state["profile"]["contract_fields"]) or "(未声明，使用默认集)"))
    pc.log("已写          : %s（合法 partial）" % out["result_path"])
    pc.log("                %s" % os.path.join(a.work, "segments.json"))
    pc.log("                %s" % os.path.join(a.work, "draft.template.json"))
    if state["errors"]:
        pc.log("errors        : %s" % "; ".join(state["errors"]))
    for item in state["degradations"][:6]:
        pc.log("degradation   : %s" % item)
    pc.log("下一步        : python3 scripts/main.py show")
    return 0

def cmd_show(a):
    state = load_state(a)
    pc.ensure(a.work)
    if not os.path.exists(os.path.join(a.work, "segments.json")):
        write_work_files(a, state)
    L = []
    L.append("== 案例概览 ==")
    L.append("case_id: %s | 文体: %s | 语言: %s | 模式: %s | 文档: %s | 段落: %d"
             % (state["case_id"], state["profile"]["genre"], state["profile"]["language"], state["profile"]["mode"],
                state["profile"]["doc_name"], len(state["segments"]["paragraphs"])))
    L.append("契约字段: %s" % (", ".join(state["profile"]["contract_fields"]) or "(未声明)"))
    L.append("任务约束摘录: %s" % (state["profile"]["task_excerpt"][:400] or "-"))
    L.append("")
    L.append("== 待处理段落（before 必须逐字复制下方原文；locator 可直接引用）==")
    for para in state["segments"]["paragraphs"]:
        atoms = para["atoms"]
        atom_txt = " ".join("%s:%s" % (pc.ATOM_LABELS.get(cls, cls).replace("数字+单位", "数量"),
                                       "/".join(sorted(set(atoms.get(cls, [])))[:6]))
                            for cls in pc.HARD_ATOM_CLASSES if atoms.get(cls))
        L.append("--- [%s] %s | %d 字符 | hedge L%d%s | 否定 %d | locator %s#%s[%d:%d]"
                 % (para["id"], para["kind"], para["chars"], para["hedge"]["level"],
                    ("(" + "、".join(para["hedge"]["markers"][:4]) + ")") if para["hedge"]["markers"] else "",
                    para["negation"], state["profile"]["doc_name"], para["id"], para["start"], para["end"]))
        if atom_txt:
            L.append("原子(不可改): %s" % atom_txt)
        body = para["text"]
        if len(body) > 1200:
            body = body[:1200] + "\n…（超长段落截断，完整原文见 %s）" % os.path.join(a.work, "segments.json")
        L += ["<<<", body, ">>>"]
        if len(para["sentences"]) > 1:
            L.append("句: " + " | ".join("S%d(%d-%d)" % (s["idx"], s["start"], s["end"])
                                        for s in para["sentences"][:12]))
        L.append("")
    if state["provided"]:
        L.append("== 输入术语表（权威锁定，优先于你的判断）==")
        for entry in state["provided"]:
            L.append("- %s => %s %s" % (entry.get("concept"), entry.get("locked"),
                                        ("变体:" + "|".join(entry.get("variants") or [])) if entry.get("variants") else ""))
        L.append("")
    L.append("== 术语候选（脚本抽取，是否锁定由你判断）==")
    for entry in state["candidates"][:25]:
        L.append("- [%s] concept=%s locked=%s abbr=%s first_use=%s"
                 % (entry.get("source", "?"), entry.get("concept"), entry.get("locked"),
                    entry.get("abbr") or "-", entry.get("first_use") or "-"))
    L += ["", "== 下一步 ==",
          "把逐段结果写进 %s（可从 %s 复制），然后跑 check 与 build。"
          % (os.path.join(a.work, "draft.json"), os.path.join(a.work, "draft.template.json"))]
    text = "\n".join(L)
    pc.write_text(os.path.join(a.work, "show.md"), text + "\n")
    pc.log(text)
    return 0

def cmd_check(a):
    state = load_state(a)
    pc.ensure(a.work)
    draft, path = load_draft(a.work)
    if not usable(draft):
        pc.log("== check ==")
        pc.log("未找到可用工作稿（%s/draft.json 或 plan.json）。" % a.work)
        pc.log("请先读 show 输出、逐段润色并写工作稿，再跑 check —— 脚本不会代替这一步。")
        pc.jdump(os.path.join(a.work, "check_report.json"),
                 {"draft": None, "ok": False, "reason": "draft_missing", "records": []})
        return 0
    report = pl.verify_draft(draft, state["segments"], state["profile"])
    rows = rd.change_rows(draft, report)
    grows = rd.glossary_rows(draft, state)
    issues = rd.term_sweep(grows, [p["id"] for p in state["segments"]["paragraphs"]], report["working"])
    counts = report["counts"]
    pc.log("== check ==")
    pc.log("工作稿: %s（items %d，术语 %d，untouched %d）"
           % (path, counts["items"], len(draft.get("glossary") or []), len(draft.get("untouched") or [])))
    pc.log("覆盖: %d/%d 段 | 已改 %d 段 | 修改 %d 处 | 硬失败 %d | 回退段 %d | 软提示 %d"
           % (counts["covered"], counts["editable"], counts["changed"], len(rows), report["hard_count"],
              len(report["rolled_back"]), len(report["pending"]) - report["hard_count"]))
    for rec in report["records"]:
        for code in rec.get("hard") or []:
            pc.log("[HARD] %s %s %s" % (rec.get("paragraph_id"), code["code"], code.get("detail", "")[:200]))
        for code in rec.get("soft") or []:
            pc.log("[SOFT] %s %s %s" % (rec.get("paragraph_id"), code["code"], code.get("detail", "")[:160]))
    for issue in issues:
        pc.log("[TERM] %s %s %s" % (issue.get("paragraph_id"), issue["code"], issue.get("detail", "")[:160]))
    if report["missing_coverage"]:
        pc.log("[COVERAGE] 未处理段落: %s" % "、".join(report["missing_coverage"]))
    pc.jdump(os.path.join(a.work, "check_report.json"), {
        "draft": path, "ok": report["hard_count"] == 0 and not report["missing_coverage"],
        "counts": counts, "records": report["records"], "missing_coverage": report["missing_coverage"],
        "terminology_sweep": issues, "checked_at": pc.now_iso()})
    if report["hard_count"] or report["missing_coverage"]:
        pc.log("下一步: 修正 [HARD]/[COVERAGE] 后重跑 check；确认无误再跑 build")
    else:
        pc.log("下一步: python3 scripts/main.py build")
    return 0

def cmd_build(a):
    state = load_state(a)
    draft, path = load_draft(a.work)
    if not usable(draft):
        draft, path, _made = autodraft(a, state)   # 兜底：无工作稿时自动生成保守最小编辑稿
    has_draft = usable(draft)
    out = rd.finalize(a, state, draft if has_draft else None, "build", has_draft)
    pc.log("== build ==")
    pc.log("工作稿: %s" % (path if has_draft else "(缺失 → 兜底：按原文保守交付，status=partial)"))
    pc.log("状态: %s（%s）" % (out["status"], out["result"].get("status_reason", "")))
    cov = out["result"]["coverage"]
    pc.log("覆盖: %d/%d 段 | 已改 %d 段 | 修改 %d 处 | 回退 %d | 术语 %d 条 | 守卫提示 %d"
           % (cov["covered"], cov["editable"], cov["changed"], len(out["rows"]),
              cov["rolled_back_items"], len(out["glossary"]), len(out["issues"])))
    pc.log("产物:")
    for key, meta in out["result"]["deliverables"].items():
        pc.log("  %-24s %s (%d bytes)" % (key, meta["path"], meta["bytes"]))
    pc.log("契约字段: " + ", ".join("%s=%s" % (r["field"], "ok" if r["filled"] else "null")
                                 for r in out["result"]["_contract_report"]))
    return 0

def cmd_selfcheck(a):
    result = pc.jload(os.path.join(a.out, "result.json"))
    checks = []
    if not isinstance(result, dict):
        checks.append({"check": "result_json_exists", "ok": False, "detail": "result.json 缺失或不可解析"})
        pc.log("[FAIL] result.json 缺失或不可解析")
        pc.jdump(os.path.join(a.out, "audit.json"), {"ok": False, "checks": checks, "at": pc.now_iso()})
        return 0
    checks.append({"check": "result_json_exists", "ok": True})
    contract = result.get("_contract_report") or []
    missing = [c["field"] for c in contract if c.get("field") not in result or result.get(c.get("field")) is None]
    checks.append({"check": "contract_fields_present", "ok": not missing,
                   "detail": ("未回填: " + ", ".join(missing)) if missing else "全部字段已回填"})
    for key in ("case_id", "status", "errors", "degradations", "pending_human", "sources"):
        checks.append({"check": "envelope_%s" % key, "ok": key in result})
    for key, meta in (result.get("deliverables") or {}).items():
        checks.append({"check": "deliverable_%s" % key, "ok": os.path.exists(meta.get("path", "")),
                       "detail": meta.get("path")})
    polished = ""
    p_path = os.path.join(a.out, "polished.md")
    if os.path.exists(p_path):
        polished, _e, _w = pc.read_text_any(p_path)
    checks.append({"check": "polished_non_empty",
                   "ok": bool(pc.norm_ws(polished)) or result.get("status") == "input_error",
                   "detail": "%d chars" % len(polished)})
    bad = [r for r in (result.get("edit_log") or []) if isinstance(r, dict) and (not r.get("reason") or not r.get("type"))]
    checks.append({"check": "change_records_have_type_reason", "ok": not bad, "detail": "%d 条缺字段" % len(bad)})
    checks.append({"check": "coverage_reported",
                   "ok": (result.get("verification") or {}).get("coverage_ratio") is not None})
    failed = [c for c in checks if not c["ok"]]
    for check in checks:
        pc.log("[%s] %s %s" % ("PASS" if check["ok"] else "WARN", check["check"], check.get("detail", "")))
    pc.log("== selfcheck: %d 项检查，%d 项待解释 ==" % (len(checks), len(failed)))
    pc.jdump(os.path.join(a.out, "audit.json"),
             {"ok": not failed, "checks": checks, "status": result.get("status"), "at": pc.now_iso()})
    return 0

def parse_args(argv):
    parser = argparse.ArgumentParser(prog="main.py", description="claim-preserving-polish 五命令入口")
    parser.add_argument("command", choices=["init", "show", "check", "build", "selfcheck", "all"])
    parser.add_argument("--input", default=os.environ.get("POLISH_INPUT", DEFAULT_INPUT))
    parser.add_argument("--work", default=os.environ.get("POLISH_WORK", DEFAULT_WORK))
    parser.add_argument("--out", default=os.environ.get("POLISH_OUT", DEFAULT_OUT))
    parser.add_argument("--case", default=None, help="默认 <input>/case.json")
    parser.add_argument("--task", default=None, help="默认 <input>/task.md")
    args = parser.parse_args(argv)
    args.case = args.case or os.path.join(args.input, "case.json")
    args.task = args.task or os.path.join(args.input, "task.md")
    return args

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parse_args(argv)
    except SystemExit:
        return 0
    pc.ensure(args.work)
    pc.ensure(args.out)
    append_cmd_log(args.work, args.command)
    handlers = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
                "selfcheck": cmd_selfcheck}
    try:
        if args.command == "all":
            handlers["init"](args)
            autodraft(args, load_state(args))   # 无工作稿时自动生成保守最小编辑稿
            for name in ("show", "check", "build"):
                handlers[name](args)
            postprocess(args)            # 先回填契约，再让 selfcheck 看到完整字段
            handlers["selfcheck"](args)
            postprocess(args)            # 再扫一遍 selfcheck 写出的 JSON 产物
            return 0
        rc = handlers[args.command](args) or 0
        postprocess(args)
        return rc
    except Exception as exc:  # noqa: BLE001 - 任何异常都降级为合法交付
        rd.emergency(args, exc)
        try:
            postprocess(args)
        except Exception:  # noqa: BLE001
            pass
        return 0

if __name__ == "__main__":
    sys.exit(main())
