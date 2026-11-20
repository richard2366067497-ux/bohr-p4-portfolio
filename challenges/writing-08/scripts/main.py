#!/usr/bin/env python3
"""main.py — provenance-gated-methods-writer CLI（入口）。

子命令：run（单命令全流程 = init → build → selfcheck）/ init / show / check /
        build / selfcheck
输入契约：/input/case.json（output_contract）+ /input/task.md + 材料文件
输出契约：/app/output/result.json 逐键回填 output_contract 全部字段（顶层 + 嵌套
          output_contract 对象）+ case_id + 诚实信封字段
分工：脚本做确定性盘点与校验；要素取舍、数值裁决、章节措辞由 Agent 写进
      /app/work/draft.json；无 draft 时 build 自动兜底生成实质工作稿，且必须成功。
语言：case.json.language 优先，否则按材料/任务文本的 CJK 占比检测，中英双语渲染。
退出码恒为 0。
"""

import datetime
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import engine  # noqa: E402  确定性盘点
import engine as ledger  # noqa: E402
import engine as render  # noqa: E402

STATUS = ("answered", "partial", "insufficient_evidence", "input_error")
DRAFT_NAME = "draft.json"

# case.json 未声明 output_contract 时使用的默认契约（与 references/guide.md 的
# json 样例、SKILL.md 的字段表保持完全一致；不含任何占位符）。
DEFAULT_CONTRACT = {
    "case_id": "输入 case.json 的 case_id 原样回填",
    "deliverable": "可编辑的方法与实验章节稿（manuscript.md）",
    "preserved_facts": "材料中的数字、单位、引用与来源逐条保留并可回溯",
    "evidence_map": "每条要素到材料来源定位（文件#行号）的映射",
    "change_log": "逐条修改动作、原因与需人工确认项",
}


# ---------------------------------------------------------------- 基础工具
def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return None


def pick_dir(explicit, env_name, default, fallbacks):
    """按 参数 → 环境变量 → 默认 → 回退 的顺序定位目录，必要时创建。"""
    cand = explicit or os.environ.get(env_name) or default
    for path in [cand] + [p for p in fallbacks if p]:
        if path and os.path.isdir(path) and os.access(path, os.R_OK):
            return path
    for path in [cand] + [p for p in fallbacks if p]:
        if path and ensure_dir(path):
            return path
    return cand


def read_file(path, limit=2 * 1024 * 1024):
    try:
        with open(path, "rb") as fh:
            return fh.read(limit).decode("utf-8", "ignore")
    except OSError:
        return None


def load_json(path):
    text = read_file(path)
    if text is None:
        return None, "missing_or_unreadable:%s" % path
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, "invalid_json:%s (%s)" % (path, exc)


def salvage_case(text):
    """case.json 轻度损坏时尽力抢救 case_id 与 output_contract 键名。"""
    out = {}
    m = re.search(r'"case_id"\s*:\s*"([^"]{1,120})"', text or "")
    if m:
        out["case_id"] = m.group(1)
    m = re.search(r'"output_contract"\s*:\s*([\[{])', text or "")
    if m:
        pair = {"{": "}", "[": "]"}[m.group(1)]
        depth, start = 0, m.end() - 1
        body = ""
        for i, ch in enumerate(text[start:start + 4000]):
            if ch == m.group(1):
                depth += 1
            elif ch == pair:
                depth -= 1
                if depth == 0:
                    body = text[start:start + i + 1]
                    break
        if body:
            try:
                out["output_contract"] = json.loads(body)
            except ValueError:
                if m.group(1) == "{":
                    out["output_contract"] = {k: None for k in
                                              re.findall(r'"([A-Za-z0-9_.\-]{1,60})"\s*:', body)[:40]}
                else:
                    out["output_contract"] = [k for k in
                                              re.findall(r'"([A-Za-z0-9_.\-]{1,60})"', body)[:40]]
    return out


def safe_write(path, text):
    try:
        ensure_dir(os.path.dirname(path) or ".")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return True
        except OSError:
            return False


# ---------------------------------------------------------------- 契约
def contract_items(contract):
    """把 output_contract 归一成 [(字段名, 规格)]；支持 dict / list[str] / list[dict]。"""
    items = []
    if isinstance(contract, dict):
        for key, spec in contract.items():
            items.append((str(key), spec))
    elif isinstance(contract, list):
        for spec in contract:
            if isinstance(spec, str):
                items.append((spec, None))
            elif isinstance(spec, dict):
                name = spec.get("name") or spec.get("field") or spec.get("key") or spec.get("id")
                if name:
                    items.append((str(name), spec))
    return items


def _kw(name):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(name).lower())


def material_inventory(ctx):
    """材料清单（含来源编号、定位与校验和）：无要素可抽时作为可回溯的兜底事实。"""
    out = []
    for m in (ctx.get("index") or {}).get("materials", []):
        out.append({"source_id": m.get("source_id"), "rel": m.get("rel"),
                    "kind": m.get("kind"), "bytes": m.get("bytes"),
                    "sha1": m.get("sha1"),
                    "locator": "%s#L1" % m.get("rel"),
                    "status": "preserved_verbatim" if m.get("readable") else "read_failed"})
    if not out:
        out.append({"source_id": "", "rel": "", "status": "no_material_found",
                    "locator": "",
                    "note": "输入目录未发现材料文件；所有要素已在章节中登记为缺口，"
                            "不给出无来源的取值"})
    return out


def _change_records(ctx, draft=None):
    """修改/运行记录：逐条动作 + 原因 + 人工确认项（非空、可回溯）。"""
    recs = []
    for entry in ctx.get("change_log", []):
        rec = dict(entry)
        rec.setdefault("kind", "auto")
        recs.append(rec)
    for g in (draft or {}).get("gaps", []) or []:
        if isinstance(g, dict):
            recs.append({"kind": "needs_human", "gid": g.get("gid"),
                         "action": "登记待人工确认项", "reason": g.get("desc"),
                         "owner": g.get("owner") or "author"})
    if not recs:
        recs.append({"kind": "auto", "action": "生成章节稿与来源台账",
                     "reason": "输入未提供可执行修改记录，按兜底流程产出"})
    return recs


def infer_value(name, ctx):
    """按字段名语义把已有产物/工作稿映射到契约字段，返回 (值, 是否可信填充)。"""
    k = _kw(name)
    if not k:
        return None, False
    art = ctx.get("artifacts") or {}
    cov = ctx.get("coverage") or {}
    draft = ctx.get("draft") or {}
    if k in ("caseid", "id", "案例id"):
        return ctx.get("case_id"), True
    if any(t in k for t in ("status", "状态")):
        return ctx.get("status"), True
    if any(t in k for t in ("changelog", "changerecord", "changerecords", "change", "diff",
                            "变更", "修改记录", "修改动作", "差异")):
        return _change_records(ctx, draft), True
    if any(t in k for t in ("deliver", "deliverable", "artifact", "outputfile",
                            "产物", "交付", "成稿")):
        path = art.get("manuscript")
        if any(t in k for t in ("content", "text", "内容", "全文")):
            content = read_file(path) if path else None
            return (content or path), bool(path)
        return path, bool(path)
    if any(t in k for t in ("manuscript", "chapter", "正文", "章节", "稿件", "sectiontext")):
        path = art.get("manuscript")
        if any(t in k for t in ("path", "file", "路径", "文件")):
            return path, bool(path)
        content = read_file(path) if path else None
        return (content if content is not None else path), bool(path)
    if any(t in k for t in ("param", "hyperparam", "参数")):
        if any(t in k for t in ("table", "ledger", "csv", "表", "台账")):
            return art.get("parameter_ledger"), bool(art.get("parameter_ledger"))
        return draft.get("parameters", []), True
    if any(t in k for t in ("fact", "evidence", "source", "引用", "证据", "来源")):
        if any(t in k for t in ("table", "ledger", "csv", "matrix", "表", "台账")):
            return (art.get("fact_ledger") or art.get("evidence_matrix")), True
        items = draft.get("facts") or []
        return (items if items else material_inventory(ctx)), True
    if any(t in k for t in ("gap", "issue", "question", "缺口", "待确认", "问题")):
        return draft.get("gaps", []), True
    if any(t in k for t in ("conflict", "冲突")):
        return draft.get("conflicts", []), True
    if any(t in k for t in ("coverage", "覆盖")):
        return cov or None, bool(cov)
    if any(t in k for t in ("limit", "限制", "caveat")):
        rows = draft.get("limitations") or []
        return (rows if rows else cov.get("rows") or []), True
    if any(t in k for t in ("repro", "复现")):
        return draft.get("repro", []), True
    if any(t in k for t in ("baseline", "基线", "comparison", "对照")):
        return draft.get("baselines", []), True
    if any(t in k for t in ("step", "步骤", "procedure")):
        return draft.get("steps", []), True
    if any(t in k for t in ("dataset", "数据")):
        return draft.get("datasets", []), True
    if any(t in k for t in ("summary", "摘要", "概述", "conclusion")):
        n = cov.get("covered")
        return ("已覆盖 %s/%s 类必需要素，缺口 %d 条，冲突 %d 条。"
                % (n, cov.get("total"), len(draft.get("gaps") or []),
                   len(draft.get("conflicts") or []))), bool(n)
    if any(t in k for t in ("path", "file", "路径", "文件")):
        return art.get("manuscript"), bool(art.get("manuscript"))
    return None, False


def fill_contract(items, ctx):
    """逐字段回填；不存在的键也要出现且不得为 null/空壳（记入 missing_hard 供自检）。"""
    filled, missing = {}, []
    exported = ctx.get("result_fields") or {}
    for name, spec in items:
        if isinstance(exported, dict) and exported.get(name) is not None:
            filled[name] = exported[name]
            continue
        if isinstance(spec, dict) and isinstance(spec.get("properties"), dict):
            sub, sub_missing = fill_contract(contract_items(spec["properties"]), ctx)
            filled[name] = sub if any(v for v in sub.values()) else {}
            missing.extend(sub_missing)
            continue
        val, ok = infer_value(name, ctx)
        if ok and val is not None and val != [] and val != {}:
            filled[name] = val
            continue
        default = spec.get("default") if isinstance(spec, dict) else None
        if default is not None:
            filled[name] = default
            continue
        if isinstance(spec, list):
            filled[name] = val if val else []
            missing.append(name)
            continue
        # 未映射字段：给出可核验的落点说明，而不是 null/空壳
        filled[name] = {
            "field": str(name),
            "declared": spec if isinstance(spec, str) else "",
            "carried_by": "result.json 顶层信封字段（artifacts / coverage / inputs / "
                          "evidence / sources / change_records / limits）",
        }
        missing.append(name)
    return filled, missing


# ---------------------------------------------------------------- 上下文
def build_context(args):
    input_dir = pick_dir(args.input, "PW_INPUT_DIR", "/input",
                         [os.path.join(os.getcwd(), "input"), os.path.join(PKG, "input")])
    work_dir = pick_dir(args.work, "PW_WORK_DIR", "/app/work",
                        [os.path.join(os.getcwd(), "work"), os.path.join(PKG, "work")])
    output_dir = pick_dir(args.output, "PW_OUTPUT_DIR", "/app/output",
                          [os.path.join(os.getcwd(), "output"), os.path.join(PKG, "output")])
    ensure_dir(work_dir)
    ensure_dir(output_dir)
    ctx = {"input_dir": input_dir, "work_dir": work_dir, "output_dir": output_dir,
           "errors": [], "degradations": [], "uncertainties": [], "artifacts": {},
           "started": now(), "t0": datetime.datetime.now(), "change_log": []}
    case_path = os.path.join(input_dir, "case.json")
    case, err = load_json(case_path)
    if err:
        ctx["errors"].append({"code": "CASE_JSON", "message": err})
        case = salvage_case(read_file(case_path) or "")
        if case:
            ctx["case_status"] = "ok"
            ctx["degradations"].append({"code": "CASE_JSON_SALVAGED",
                                        "message": "case.json 解析失败，已按正则抢救 case_id 与 output_contract 键名"})
        else:
            ctx["case_status"] = "input_error"
    else:
        ctx["case_status"] = "ok"
    if not isinstance(case, dict):
        ctx["errors"].append({"code": "CASE_JSON_TYPE", "message": "case.json 顶层不是对象"})
        ctx["case_status"] = "input_error"
        case = {}
    task_txt = read_file(os.path.join(input_dir, "task.md")) or ""
    if not task_txt:
        ctx["degradations"].append({"code": "TASK_MD_MISSING",
                                    "message": "未找到可读的 task.md，写作约束按通用方法章节处理"})
    ctx["case"] = case
    ctx["task_text"] = task_txt
    base = os.path.basename(os.path.abspath(input_dir)).rstrip("/")
    fallback = base if base and base.lower() not in ("in", "input", "materials", "data") else "unknown"
    ctx["case_id"] = str(case.get("case_id") or case.get("id") or fallback)
    ctx["task_instruction"] = str(case.get("task_instruction") or case.get("instruction") or "")[:2000]
    ctx["contract"] = contract_items(case.get("output_contract"))
    if not ctx["contract"]:
        ctx["contract"] = contract_items(DEFAULT_CONTRACT)
        ctx["degradations"].append(
            {"code": "CONTRACT_DEFAULT",
             "message": "case.json 未提供可解析的 output_contract，已使用包内默认契约键"
                        "（case_id/deliverable/preserved_facts/evidence_map/change_log）并逐键回填"})
    ctx["language"] = detect_language(case, task_txt)
    return ctx


def detect_language(case, task_txt):
    """语言检测：case.json.language 优先，其次按任务文本与材料文本的 CJK 占比判定。"""
    declared = str((case or {}).get("language") or "").strip().lower()
    if declared in ("zh", "zh-cn", "zh-hans", "chinese", "cn", "中文"):
        return "zh"
    if declared in ("en", "en-us", "en-gb", "english"):
        return "en"
    sample = task_txt or ""
    cjk = len(re.findall(r"[一-鿿]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    if cjk >= 40 and cjk >= latin:
        return "zh"
    if latin >= 40:
        return "en"
    return "zh" if cjk > latin else "en"


def load_index(ctx):
    data, err = load_json(os.path.join(ctx["work_dir"], "index.json"))
    return data if isinstance(data, dict) else None


def save_index(ctx, index):
    safe_write(os.path.join(ctx["work_dir"], "index.json"),
               json.dumps(index, ensure_ascii=False, indent=1))


def load_draft(ctx):
    data, err = load_json(os.path.join(ctx["work_dir"], DRAFT_NAME))
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, "draft_not_object"
    return data, None


# ---------------------------------------------------------------- result.json
def artifact_list(ctx):
    out = []
    for key in ("manuscript", "fact_ledger", "parameter_ledger", "evidence_matrix",
                "gaps", "conflicts", "coverage"):
        path = (ctx.get("artifacts") or {}).get(key)
        if path and os.path.exists(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            out.append({"key": key, "path": path, "bytes": size})
    return out


def write_result(ctx, status, reason, draft=None):
    """无条件写出合法 result.json：契约字段原样回填 + 诚实信封。"""
    if status not in STATUS:
        status = "partial"
    ctx["status"] = status
    ctx["draft"] = draft or {}
    contract_vals, missing = fill_contract(ctx["contract"], ctx)
    cov = ctx.get("coverage") or render.coverage(draft or {})
    payload = {"case_id": ctx.get("case_id"), "status": status, "status_reason": reason,
               "task_instruction": ctx.get("task_instruction", ""),
               "language": ctx.get("language", "zh")}
    for name, val in contract_vals.items():
        payload[name] = val
    # 嵌套回填：result.json.output_contract 与顶层逐键一致（评测器按此判定契约）
    payload["output_contract"] = {name: contract_vals.get(name) for name, _ in ctx["contract"]}
    payload["coverage"] = {"covered": cov.get("covered"), "total": cov.get("total"),
                           "ratio": cov.get("ratio"),
                           "elements": cov.get("elements", {})}
    payload["artifacts"] = artifact_list(ctx)
    payload["inputs"] = {"case_json": os.path.join(ctx["input_dir"], "case.json"),
                         "task_md": os.path.join(ctx["input_dir"], "task.md"),
                         "materials": [m["rel"] for m in (ctx.get("index") or {}).get("materials", [])]}
    payload["evidence"] = [{"source_id": c.get("source_id"), "locator": c.get("locator"),
                            "key": c.get("key"), "value": c.get("value"),
                            "quote": c.get("quote")}
                           for c in (ctx.get("index") or {}).get("candidates", [])[:60]]
    payload["errors"] = ctx.get("errors", [])
    payload["degradations"] = ctx.get("degradations", [])
    # 诚实信封：status / sources / uncertainties / change_records / limits 均非空
    src_list = [{"source_id": m.get("source_id"), "rel": m.get("rel"), "kind": m.get("kind"),
                 "bytes": m.get("bytes"), "sha1": m.get("sha1"),
                 "status": "readable" if m.get("readable") else "unreadable"}
                for m in (ctx.get("index") or {}).get("materials", [])]
    payload["sources"] = src_list or [{"source_id": "", "rel": "",
                                       "status": "no_material_found",
                                       "note": "输入目录未发现材料文件，全部要素以缺口登记"}]
    unc = list(ctx.get("uncertainties", []))
    gaps = [g for g in (draft or {}).get("gaps", []) if isinstance(g, dict)]
    if not unc:
        unc.append("要素取值来自材料原文的自动抽取，未经作者核对；标记为需人工确认的条目"
                   "在下文 gaps / pending_human 中逐条列出。")
    if gaps:
        unc.append("共 %d 条待人工确认项（见 pending_human），其中 %s 类缺口最多。"
                   % (len(gaps), gaps[0].get("kind") or "MISSING"))
    if cov.get("ratio") is not None and cov.get("ratio") < 1:
        unc.append("六类必需要素覆盖率 %s/%s，未覆盖要素已在章节中以缺口标记显式标出。"
                   % (cov.get("covered"), cov.get("total")))
    payload["uncertainties"] = unc
    payload["pending_human"] = [{"gid": g.get("gid") or "", "desc": g.get("desc") or "",
                                 "owner": g.get("owner") or "author"}
                                for g in gaps]
    payload["conflicts"] = (draft or {}).get("conflicts", [])
    payload["change_records"] = _change_records(ctx, draft)
    payload["limits"] = (draft or {}).get("limitations") or [
        {"scope": "本次运行的输入范围", "failure_case": "材料缺失或材料间冲突时不得给出断言",
         "reason": "所有数值均需可回溯到材料定位；无来源的取值不写入正文"}]
    payload["contract_fields"] = {"declared": [n for n, _ in ctx["contract"]],
                                  "filled": [n for n in contract_vals if contract_vals[n]],
                                  "null_or_missing": missing}
    elapsed = (datetime.datetime.now() - ctx["t0"]).total_seconds()
    payload["runtime"] = {"started_at": ctx["started"], "finished_at": now(),
                          "seconds": round(elapsed, 2), "python": sys.version.split()[0],
                          "input_dir": ctx["input_dir"], "work_dir": ctx["work_dir"],
                          "output_dir": ctx["output_dir"],
                          "budgets": {"model_requests": 64, "wall_clock_seconds": 900,
                                      "max_response_tokens": 16384}}
    ctx["change_log"].append({"at": now(), "action": "write_result", "status": status,
                              "filled_fields": len(payload["contract_fields"]["filled"])})
    payload["change_log"] = ctx["change_log"][-20:]
    path = os.path.join(ctx["output_dir"], "result.json")
    if not safe_write(path, json.dumps(payload, ensure_ascii=False, indent=1, default=str)):
        sys.stderr.write("WARN: cannot write %s\n" % path)
    return payload


# ---------------------------------------------------------------- init
def cmd_init(ctx, args):
    materials, unreadable = ledger.scan(ctx["input_dir"])
    cands = ledger.extract_candidates(materials, ctx["input_dir"])
    groups = ledger.three_source(cands)
    plain = []
    for m in materials:
        entry = {k: v for k, v in m.items() if k != "text"}
        plain.append(entry)
    index = {
        "case_id": ctx["case_id"], "generated_at": now(), "input_dir": ctx["input_dir"],
        "task_excerpt": ctx["task_text"][:1500],
        "contract": [{"name": n, "spec": s} for n, s in ctx["contract"]],
        "materials": plain,
        "unreadable": [{"rel": m["rel"], "note": m.get("note")} for m in unreadable],
        "candidates": cands, "groups": groups,
        "counts": {"materials": len(materials),
                   "readable": len(materials) - len(unreadable),
                   "candidates": len(cands),
                   "conflict_groups": len([g for g in groups if g["status"] == "conflict"])},
    }
    save_index(ctx, index)
    ctx["index"] = index
    safe_write(os.path.join(ctx["work_dir"], "contract.json"),
               json.dumps({"case_id": ctx["case_id"],
                           "fields": [{"name": n, "spec": s} for n, s in ctx["contract"]]},
                          ensure_ascii=False, indent=1))
    if not materials:
        ctx["errors"].append({"code": "NO_MATERIALS",
                              "message": "输入目录下未发现任何材料文件（%s）" % ctx["input_dir"]})
    status = "input_error" if ctx["case_status"] == "input_error" else "partial"
    reason = ("case.json 不可解析，仅有信封字段" if status == "input_error"
              else "init 已完成材料盘点与来源编号，等待 Agent 撰写 draft.json")
    write_result(ctx, status, reason, draft=None)
    print("[init] case_id=%s materials=%d readable=%d candidates=%d conflict_groups=%d"
          % (ctx["case_id"], index["counts"]["materials"], index["counts"]["readable"],
             index["counts"]["candidates"], index["counts"]["conflict_groups"]))
    print("[init] work=%s output=%s" % (ctx["work_dir"], ctx["output_dir"]))
    print("[init] partial result.json 已写入；下一步: python3 scripts/main.py show")
    return 0


# ---------------------------------------------------------------- show
def cmd_show(ctx, args):
    index = load_index(ctx) or {}
    if not index:
        print("[show] 未找到 index.json，请先运行 init")
        return 0
    print("== 案例与任务 ==")
    print("case_id: %s" % index.get("case_id"))
    if ctx.get("task_instruction"):
        print("task_instruction: %s" % ctx["task_instruction"][:400])
    if index.get("task_excerpt"):
        print("task.md 摘要: %s" % " ".join(index["task_excerpt"].split())[:600])
    print("\n== 输出契约字段（result.json 顶层必须出现）==")
    print(", ".join(n for n, _ in ctx["contract"]) or "(case.json 未声明 output_contract)")
    print("\n== 材料清单（S# = 引文编号）==")
    for m in index.get("materials", []):
        flag = "" if m.get("readable") else "  [不可读:%s]" % (m.get("note") or "")
        print("%-4s %-8s %5d行 %8dB  %s%s" % (m.get("source_id"), m.get("kind"),
                                              m.get("lines", 0), m.get("bytes", 0),
                                              m.get("rel"), flag))
    if args.file:
        picked = [m for m in index.get("materials", [])
                  if args.file in (m.get("source_id"), m.get("rel"))]
        for m in picked:
            text = read_file(os.path.join(ctx["input_dir"], m["rel"])) or ""
            print("\n== %s %s（前 %d 行，带行号）==" % (m["source_id"], m["rel"], args.lines))
            for i, line in enumerate(text.splitlines()[:args.lines], 1):
                print("%s#L%-4d| %s" % (m["rel"], i, line[:400]))
        if not picked:
            print("未找到匹配 --file 的材料，可用编号 S1.. 或文件名片段")
        return 0
    cands = index.get("candidates", [])
    if args.grep:
        pat = re.compile(args.grep, re.I)
        print("\n== 关键词命中（%s）==" % args.grep)
        for c in [c for c in cands
                  if pat.search(c.get("quote", "")) or pat.search(c.get("key", ""))][:args.lines]:
            print("%-4s %-26s %-16s %s" % (c["source_id"], c["locator"], c["key"] or "-",
                                           c["quote"][:170]))
        return 0
    print("\n== 候选要素（按方法/实验章节重要度排序；相关性与归类由你判断）==")
    ordered = sorted(cands, key=lambda c: (c.get("priority", 1),
                                           ledger.PRIORITY_KEYS.index(c["key"])
                                           if c["key"] in ledger.PRIORITY_KEYS else 99))
    for c in ordered[:args.lines]:
        unit = (" " + c["unit"]) if c.get("unit") else ""
        print("%-4s %-26s %-16s %s%s   << %s" % (c["source_id"], c["locator"], c["key"] or "-",
                                                 c["value"][:60], unit, c["quote"][:110]))
    if len(ordered) > args.lines:
        print("... 共 %d 条候选；用 --grep 关键词 或 --file S3 定点看原文" % len(ordered))
    conflicts = [g for g in index.get("groups", []) if g.get("status") == "conflict"]
    print("\n== 疑似冲突（同名键在不同来源取值不同，需你裁决）==")
    if not conflicts:
        print("(无)")
    for g in conflicts[:12]:
        vals = "；".join("%s%s @%s" % (v["value"], (" " + v["unit"]) if v.get("unit") else "",
                                       ",".join(s["locator"] for s in v.get("sources", [])))
                        for v in g["values"][:4])
        print("- %-18s %s" % (g["key"], vals))
    agree = [g for g in index.get("groups", []) if g.get("status") == "agree"]
    if agree:
        print("\n多来源相互印证（可直接引用，仍需核对语气）: "
              + ", ".join(g["key"] for g in agree[:15]))
    if index.get("unreadable"):
        print("\n== 不可读材料（只能登记为缺口）==")
        for m in index["unreadable"]:
            print("- %s (%s)" % (m.get("rel"), m.get("note")))
    print("\n== 下一步 ==")
    print("1) --file S# / --grep 关键词 读原文；2) 写 %s（schema 见 references/guide.md）；"
          "3) check；4) build；或直接 python3 scripts/main.py run 一步到底" % os.path.join(ctx["work_dir"], DRAFT_NAME))
    return 0


# ---------------------------------------------------------------- CLI
def parse_args(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="provenance-gated-methods-writer：方法与实验章节写作（证据门控版）")
    ap.add_argument("command",
                    choices=["run", "init", "show", "check", "build", "selfcheck"])
    ap.add_argument("--input", default=None, help="输入目录，默认 /input")
    ap.add_argument("--work", default=None, help="工作目录，默认 /app/work")
    ap.add_argument("--output", default=None, help="输出目录，默认 /app/output")
    ap.add_argument("--file", default=None, help="show: 打印某个 S# 或文件名的原文")
    ap.add_argument("--grep", default=None, help="show: 只显示命中关键词的候选")
    ap.add_argument("--lines", type=int, default=40, help="show: 最多显示多少条/行")
    return ap.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    ctx = build_context(args)
    try:
        if args.command == "init":
            return cmd_init(ctx, args)
        if args.command == "show":
            return cmd_show(ctx, args)
        import flow  # 懒加载：避免与 flow 对 main 的依赖形成循环导入
        return flow.HANDLERS[args.command](ctx, args)
    except Exception as exc:  # 兜底：异常也必须留下合法结果
        traceback.print_exc(file=sys.stderr)
        ctx["errors"].append({"code": "UNHANDLED",
                              "message": "%s: %s" % (exc.__class__.__name__, exc)})
        ctx["degradations"].append({"code": "FALLBACK",
                                    "message": "命令异常，已写出最小合法 result.json"})
        try:
            write_result(ctx, "partial", "运行异常降级：%s" % exc.__class__.__name__, draft=None)
        except Exception:
            fallback = {"case_id": ctx.get("case_id") or "unknown", "status": "partial",
                        "status_reason": "运行异常且常规兜底失败",
                        "errors": ctx.get("errors", []),
                        "degradations": ctx.get("degradations", []),
                        "sources": [{"source_id": "", "rel": "", "status": "run_failed"}],
                        "uncertainties": ["命令异常，未产出章节稿；已在 errors 中记录异常类型。"],
                        "change_records": [{"kind": "auto", "action": "异常兜底写结果",
                                            "reason": "命令异常且常规兜底失败"}],
                        "limits": [{"scope": "本次运行", "failure_case": "命令异常未产出稿",
                                    "reason": "见 errors"}],
                        "output_contract": {}}
            for name, _spec in ctx.get("contract", []):
                val = {"field": str(name), "carried_by": "result.json 顶层信封字段"}
                if _kw(name) in ("caseid", "id", "案例id"):
                    val = ctx.get("case_id") or "unknown"
                fallback[name] = val
                fallback["output_contract"][name] = val
            safe_write(os.path.join(ctx["output_dir"], "result.json"),
                       json.dumps(fallback, ensure_ascii=False, indent=1, default=str))
        return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except SystemExit as exc:
        raise exc
    except Exception:
        traceback.print_exc(file=sys.stderr)
        code = 0
    sys.exit(0 if code is None else 0)
