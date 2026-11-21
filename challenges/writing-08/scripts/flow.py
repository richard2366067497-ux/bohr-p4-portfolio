"""flow.py — run / check / build / selfcheck 实现（由 main.py 懒加载）。

run   = 单命令全流程：init → build → selfcheck
build = 渲染与 finalize；工作稿缺失/为空时用确定性抽取生成实质工作稿（逐字 quote +
        locator），并按检测到的语言（zh/en）渲染，始终留下合法 result.json。
"""

import json
import os
import re
import sys

import engine as ledger
import main as core
import engine as render

NUM_TABLE = re.compile(r"^[|\-\s:]+$")
HEADER_PREFIXES = ("- 案例", "- 证据来源编号", "- 标注约定",
                   "- Case:", "- Evidence source ids:", "- Conventions:")
PH_ZH = re.compile(r"〔待补：[^〕]*〕")
PH_EN = re.compile(r"\[needs input:[^\]]*\]")

def _strip_markers(line):
    line = re.sub(r"\[S\d+\]", "", line)
    line = PH_ZH.sub("", line)
    line = PH_EN.sub("", line)
    line = re.sub(r"\b[SGCPF]\d+\b", "", line)
    line = re.sub(r"[#`*|]", "", line)
    return line

def check_draft(ctx):
    """机械校验工作稿：引文逐字、行内溯源、六要素覆盖、缺口联动、冲突裁决。"""
    issues = []
    index = core.load_index(ctx) or {}
    draft, err = core.load_draft(ctx)
    if err:
        issues.append({"level": "ERROR", "code": "DRAFT_MISSING",
                       "message": "未找到工作稿 %s（%s）：先读材料写 draft.json，再 check/build"
                                  % (os.path.join(ctx["work_dir"], core.DRAFT_NAME), err)})
        return {"issues": issues, "draft": None, "verified": {}, "stats": {}}
    mat_path = {m["source_id"]: os.path.join(ctx["input_dir"], m["rel"])
                for m in index.get("materials", [])}
    verified, bad_facts, no_src = {}, [], []
    for i, f in enumerate([x for x in draft.get("facts") or [] if isinstance(x, dict)], 1):
        fid = str(f.get("fact_id") or "F%d" % i)
        sids = [s for s in (f.get("source_ids") or []) if isinstance(s, str)]
        sid = f.get("source_id") or (sids[0] if sids else "")
        if not sid:
            no_src.append(fid)
            verified[fid] = False
            issues.append({"level": "ERROR", "code": "FACT_NO_SOURCE",
                           "message": "%s 缺少 source_id，不能进入正文" % fid})
            continue
        path = mat_path.get(str(sid))
        if not path:
            verified[fid] = False
            issues.append({"level": "ERROR", "code": "SOURCE_UNKNOWN",
                           "message": "%s 引用了不存在的来源 %s" % (fid, sid)})
            continue
        ok, actual, why = ledger.verify_quote(path, f.get("quote"))
        verified[fid] = ok
        if not ok:
            bad_facts.append(fid)
            issues.append({"level": "ERROR", "code": "QUOTE_NOT_VERBATIM",
                           "message": "%s 的 quote 在 %s 中未逐字命中（%s）：%s"
                                      % (fid, sid, why, str(f.get("quote"))[:80])})
        elif f.get("locator") and actual and ("L%d" % actual) not in str(f.get("locator")):
            issues.append({"level": "WARN", "code": "LOCATOR_DRIFT",
                           "message": "%s 的 locator 写 %s，实际在第 %d 行"
                                      % (fid, f.get("locator"), actual)})
    text = render.render_manuscript(draft, index, {"case_id": ctx["case_id"],
                                                   "language": ctx.get("language")})
    cited = set(re.findall(r"\[(S\d+)\]", text))
    for fid in bad_facts:
        f = next((x for x in draft.get("facts") or []
                  if isinstance(x, dict) and str(x.get("fact_id")) == fid), {})
        sid = str(f.get("source_id") or "")
        if sid and sid in cited:
            issues.append({"level": "ERROR", "code": "UNVERIFIED_FACT_CITED",
                           "message": "未通过逐字校验的事实 %s（%s）仍被正文引用" % (fid, sid)})
    total, covered, unmarked = 0, 0, []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or NUM_TABLE.match(s):
            continue
        if s.startswith(HEADER_PREFIXES):
            continue
        if re.match(r"^\| G\d+", s):
            continue
        if not re.search(r"\d", _strip_markers(s)):
            continue
        total += 1
        if re.search(r"\[S\d+\]", s):
            covered += 1
        elif len(unmarked) < 12:
            unmarked.append(s[:110])
    if total and covered < total:
        issues.append({"level": "WARN", "code": "INLINE_CITATION_GAP",
                       "message": "%d/%d 个含数字的行带 [S#] 溯源，例如: %s"
                                  % (covered, total, " | ".join(unmarked[:5]))})
    ph_tokens = PH_ZH.findall(text) + PH_EN.findall(text)
    gap_sections = [str(g.get("section") or "") for g in draft.get("gaps") or []
                    if isinstance(g, dict)]
    if ph_tokens and not [gs for gs in gap_sections if gs]:
        issues.append({"level": "WARN", "code": "GAP_UNREGISTERED",
                       "message": "正文有 %d 处缺口标记但 gaps[].section 全为空" % len(set(ph_tokens))})
    detected = [g for g in index.get("groups", []) if g.get("status") == "conflict"]
    handled = set()
    for c in draft.get("conflicts") or []:
        if isinstance(c, dict):
            handled.add(str(c.get("item") or c.get("name") or "").lower())
    for p in draft.get("parameters") or []:
        if isinstance(p, dict) and (p.get("conflict") or str(p.get("status") or "").lower() == "conflict"):
            handled.add(str(p.get("param") or "").lower())
    silent = [g["key"] for g in detected if g.get("severity") == "high"
              and not any(g["key"] in h or h in g["key"] for h in handled if h)]
    if silent:
        issues.append({"level": "WARN", "code": "CONFLICT_SILENT",
                       "message": "以下高优先疑似冲突未在 conflicts/parameters 中裁决: %s"
                                  % ", ".join(silent[:10])})
    for p in draft.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        if p.get("status") == "gap":
            continue
        if not (p.get("source_id") or p.get("source_ids")) and str(p.get("status") or "") != "unsourced":
            issues.append({"level": "WARN", "code": "PARAM_UNSOURCED",
                           "message": "参数 %s 无来源标注（应写 source_id 或 status=unsourced）"
                                      % p.get("param")})
    for b in draft.get("baselines") or []:
        if isinstance(b, dict) and b.get("comparable") is True and b.get("budget_match") is not True:
            issues.append({"level": "WARN", "code": "BASELINE_UNFAIR",
                           "message": "基线 %s 标可比但未声明同预算" % b.get("name")})
    unfair = any(isinstance(b, dict) and b.get("comparable") is False
                 for b in draft.get("baselines") or [])
    if unfair:
        for m in re.finditer(r"(优于|超过|高于)基线|better than (?:the )?baseline|outperform",
                             text, re.I):
            head = text[max(0, m.start() - 24):m.start()]
            if not re.search(r"不|无法|不可|未|禁止|no |not ", head, re.I):
                issues.append({"level": "ERROR", "code": "BASELINE_CLAIM",
                               "message": "存在 comparable=false 的基线，正文却出现比较优势断言：%s"
                                          % text[max(0, m.start() - 30):m.end() + 10]})
                break
    cov = render.coverage(draft)
    exported = draft.get("result_fields") or {}
    planned = {key: os.path.join(ctx["output_dir"], name) for key, name in (
        ("manuscript", "manuscript.md"), ("fact_ledger", "fact_ledger.csv"),
        ("parameter_ledger", "parameter_ledger.csv"),
        ("evidence_matrix", "evidence_matrix.csv"), ("gaps", "gaps.md"),
        ("conflicts", "conflicts.md"), ("coverage", "coverage.json"))}
    missing_fields = []
    probe = {"draft": draft, "coverage": cov, "artifacts": planned,
             "case_id": ctx["case_id"], "status": "partial", "index": index}
    for name, _ in ctx["contract"]:
        if isinstance(exported, dict) and exported.get(name) is not None:
            continue
        if core.infer_value(name, probe)[0] in (None, [], {}):
            missing_fields.append(name)
    if missing_fields:
        issues.append({"level": "WARN", "code": "CONTRACT_UNMAPPED",
                       "message": "以下契约字段工作稿未提供、脚本也无法推断: %s"
                                  % ", ".join(missing_fields[:15])})
    if cov["covered"] < cov["total"]:
        issues.append({"level": "WARN", "code": "ELEMENT_GAP",
                       "message": "六类要素覆盖 %d/%d，缺: %s" % (
                           cov["covered"], cov["total"],
                           ",".join(k for k, v in cov["elements"].items() if v != "covered"))})
    errors = [i for i in issues if i["level"] == "ERROR"]
    return {"issues": issues, "draft": draft, "verified": verified,
            "stats": {"facts": len(draft.get("facts") or []), "bad_quotes": len(bad_facts),
                      "no_source": len(no_src), "inline_total": total,
                      "inline_covered": covered, "coverage": cov,
                      "errors": len(errors), "warnings": len(issues) - len(errors)},
            "text": text}

def cmd_check(ctx, args):
    report = check_draft(ctx)
    core.safe_write(os.path.join(ctx["work_dir"], "check_report.json"),
                    json.dumps({k: v for k, v in report.items() if k != "text"},
                               ensure_ascii=False, indent=1, default=str))
    st = report.get("stats") or {}
    issues = report.get("issues", [])
    n_err = st.get("errors", len([i for i in issues if i["level"] == "ERROR"]))
    n_warn = st.get("warnings", len([i for i in issues if i["level"] != "ERROR"]))
    print("[check] ERROR=%s WARN=%s draft_ready=%s" % (n_err, n_warn, bool(report.get("draft"))))
    cov = st.get("coverage") or {}
    if cov:
        print("[check] 六要素: %s"
              % ", ".join("%s=%s" % (k, v) for k, v in cov.get("elements", {}).items()))
    if st:
        print("[check] 引文: bad_quote=%s no_source=%s inline_cited=%s/%s"
              % (st.get("bad_quotes"), st.get("no_source"),
                 st.get("inline_covered"), st.get("inline_total")))
    for issue in report.get("issues", []):
        print("  %-5s %-22s %s" % (issue["level"], issue["code"], issue["message"][:240]))
    if not report.get("issues"):
        print("[check] 未发现问题")
    print("[check] 下一步: python3 scripts/main.py build" if report.get("draft")
          else "[check] 先写工作稿再 check/build；直接 build 会自动生成确定性工作稿")
    return 0

UNIT_WORDS = (r"(?:mg/L|g/L|µg/L|ug/L|mmol/L|mg|kg|g|%|°C|℃|min|mins|h|hr|hours?|"
              r"days?|s|sec|mL|L|mM|µM|μM|nM|kV|W|nm|rpm|pH|"
              r"replicates?|times?|runs?|epochs?)")
NUMPAIR = re.compile(
    r"\b(?P<name>[A-Za-z][A-Za-z\- ]{2,28}?)\s*"
    r"(?:=|:|was|were|is|are|reached|reaches|at|of|with|to|for)?\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>" + UNIT_WORDS + r")(?![A-Za-z])", re.I)
PH_PAIR = re.compile(r"\bpH\s*=?\s*(\d+(?:\.\d+)?)")
N_PAIR = re.compile(r"\bn\s*=\s*(\d+)\b")
SENT_SPLIT = re.compile(r"(?<=[.!?;。；！？])\s+|\n+")
STOP_NAME = {"the", "a", "an", "of", "in", "on", "at", "with", "and", "or", "was",
             "were", "is", "are", "to", "for", "within", "after", "before", "under",
             "reached", "reaches", "using", "by", "as", "it", "this", "that",
             "reused", "recorded", "shown", "obtained", "given", "was", "then"}

UNIT_CLASS_LABEL = {
    "conc": ("concentration", "浓度"),
    "cond": ("temperature / condition", "温度 / 条件"),
    "time": ("reaction duration", "反应时长"),
    "resp": ("response metric", "响应指标"),
    "rep": ("repeat count", "重复次数"),
    "generic": ("recorded quantity", "记录量"),
}

STEP_LABELS = {
    "zh": {"conc": "配制/设定底物浓度", "cond": "设定温度与 pH 条件",
           "time": "设定反应时长并辐照", "resp": "测定响应/降解指标",
           "rep": "重复实验并记录波动", "reuse": "催化剂重复使用测试",
           "generic": "按材料记录执行该操作"},
    "en": {"conc": "Prepare the substrate at the stated concentration",
           "cond": "Set the temperature and pH conditions",
           "time": "Run the reaction for the stated duration and irradiate",
           "resp": "Measure the response / degradation metric",
           "rep": "Repeat the run and record the spread",
           "reuse": "Reuse test for the catalyst",
           "generic": "Execute the operation as recorded in the material"},
}
AREA_LABELS = {"zh": {"hw": "硬件与环境", "rand": "随机性与重复", "metric": "指标",
                      "train": "训练/反应条件", "other": "其他设置"},
               "en": {"hw": "Hardware and environment", "rand": "Randomness and repeats",
                      "metric": "Metrics", "train": "Training / reaction conditions",
                      "other": "Other settings"}}
LIMIT_RE = re.compile(r"(限制|局限|limitation|不适用|仅适用|只能|only when|only for|"
                      r"subject to|without activity loss|not applicable)", re.I)
DATASET_RE = re.compile(r"(数据集|数据|dataset|corpus|语料|split|划分|version|版本|"
                        r"substrate|sample|底物|样本)", re.I)
BASELINE_RE = re.compile(r"(baseline|基线|对照|control group|compared with|versus|vs\.|"
                         r"对比方法|BM25)", re.I)

def _material_texts(ctx, index):
    """{source_id: (kind, text, path)} — 只含可读材料。"""
    texts = {}
    for m in index.get("materials") or []:
        if m.get("readable") is False:
            continue
        path = os.path.join(ctx["input_dir"], m.get("rel") or "")
        try:
            text, _ = ledger.read_text(path)
        except Exception:
            text = None
        if text and text.strip():
            texts[m["source_id"]] = (m.get("kind") or "doc", text, path)
    return texts

def _loclens(ctx, index):
    """{source_id: [(lineno, line)]}"""
    out = {}
    for sid, (_kind, text, _path) in _material_texts(ctx, index).items():
        out[sid] = [(i, ln.strip()) for i, ln in enumerate(text.splitlines(), 1) if ln.strip()]
    return out

def _short_name(raw):
    words = [w for w in re.split(r"[^A-Za-z0-9/°%]+", raw or "") if w]
    words = [w for w in words if w.lower() not in STOP_NAME]
    if not words:
        return ""
    return " ".join(words[-3:])[:40]

def _class_label(unit, lang):
    label = UNIT_CLASS_LABEL.get(_unit_class(unit)) or UNIT_CLASS_LABEL["generic"]
    return label[0] if lang == "en" else label[1]

def _unit_class(unit):
    u = (unit or "").lower()
    if any(t in u for t in ("mg/l", "g/l", "mg", "kg", "mm", "µm", "µm", "mM", "nm", "g")):
        return "conc"
    if u in ("°c", "℃", "ph"):
        return "cond"
    if any(t in u for t in ("min", "h", "hr", "sec", "s", "day")):
        return "time"
    if "%" in u:
        return "resp"
    if any(t in u for t in ("replicate", "time", "run")):
        return "rep"
    return "generic"

_TAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow_tail.py")
with open(_TAIL, "r", encoding="utf-8") as _tail_fh:
    exec(compile(_tail_fh.read(), _TAIL, "exec"), globals())
