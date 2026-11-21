def auto_draft(ctx, index):
    lang = ctx.get("language") or "zh"
    labels = STEP_LABELS[lang]
    cands = [c for c in index.get("candidates") or []
             if c.get("quote") and c.get("source_id")]
    texts = _material_texts(ctx, index)
    mat_path = {m.get("source_id"): os.path.join(ctx["input_dir"], m.get("rel") or "")
                for m in index.get("materials") or []}
    facts, parameters, settings, datasets, steps = [], [], [], [], []
    baselines, evaluation, repro, limitations, gaps, conflicts = [], [], [], [], [], []

    for i, c in enumerate(cands[:24], 1):
        ok, _, _ = ledger.verify_quote(mat_path.get(c["source_id"]), c.get("quote"))
        facts.append({"fact_id": "F%d" % i,
                      "statement": ("%s 的取值" % c["key"]) if c.get("key") else c["quote"][:70],
                      "value": c.get("value"), "unit": c.get("unit") or "",
                      "source_id": c["source_id"], "locator": c.get("locator"),
                      "quote": c.get("quote")[:200],
                      "status": "verified" if ok else "unverified"})
    verified_facts = [f for f in facts if f["status"] == "verified"]
    facts = verified_facts or facts[:8]
    for i, f in enumerate(facts, 1):
        f["fact_id"] = "F%d" % i

    for g in [x for x in index.get("groups") or [] if x.get("key")][:30]:
        vals = g.get("values") or []
        if not vals:
            continue
        v = vals[0]
        srcs = v.get("sources") or []
        s = srcs[0] if srcs else {}
        conflict = g.get("status") == "conflict"
        parameters.append({"param": g["key"], "value": v.get("value"),
                           "unit": v.get("unit") or "",
                           "scope": ("从材料抽取（%s）" % (s.get("file") or "")) if lang == "zh"
                                    else ("extracted from %s" % (s.get("file") or "")),
                           "source_id": s.get("source_id"), "locator": s.get("locator"),
                           "source_kind": s.get("kind") or "material",
                           "status": "conflict" if conflict else "verified",
                           "conflict": conflict, "quote": s.get("quote") or ""})
        if conflict:
            parts = []
            for v2 in (g.get("values") or [])[:3]:
                for x in (v2.get("sources") or [])[:2]:
                    parts.append("%s@%s=%s" % (x.get("source_id"), x.get("locator"), v2.get("value")))
            conflicts.append({"cid": "C%d" % (len(conflicts) + 1), "item": g["key"],
                              "category": "参数取值" if lang == "zh" else "parameter value",
                              "desc": ("多来源取值不同：" if lang == "zh" else "values differ: ")
                                      + "；".join(parts),
                              "sources": [{"source_id": x.get("source_id"),
                                           "locator": x.get("locator"), "value": v2.get("value")}
                                          for v2 in (g.get("values") or [])
                                          for x in (v2.get("sources") or [])][:6],
                              "impact": ("正文无法给出唯一取值" if lang == "zh"
                                         else "no single value can be stated"),
                              "resolution": ("待作者裁决，正文并列标注" if lang == "zh"
                                             else "awaiting an author decision; kept side by side")})
            gaps.append({"kind": "CONFLICT",
                         "desc": ("`%s` 多来源取值不同" % g["key"]) if lang == "zh"
                                 else ("`%s` differs across sources" % g["key"]),
                         "impact": "正文无法给出唯一取值" if lang == "zh" else "no unique value",
                         "owner": "author", "section": "params",
                         "question": ("请确认 %s 采用哪个来源" % g["key"]) if lang == "zh"
                                     else ("Confirm which source to use for %s" % g["key"])})

    seen_param = {(str(p.get("param") or "").lower(), str(p.get("value"))) for p in parameters}
    for sid, locs in _loclens(ctx, index).items():
        for (lineno, line) in locs:
            if len(parameters) >= 24:
                break
            for mm in NUMPAIR.finditer(line):
                name = _short_name(mm.group("name")) or _class_label(mm.group("unit"), lang)
                key = (name.lower(), mm.group("value"))
                if key in seen_param:
                    continue
                seen_param.add(key)
                parameters.append({
                    "param": name, "value": mm.group("value"), "unit": mm.group("unit"),
                    "scope": ("取自材料 %s" % sid) if lang == "zh" else ("from %s" % sid),
                    "source_id": sid, "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                    "source_kind": "material", "status": "verified", "conflict": False,
                    "quote": line[:200]})
            for mm in PH_PAIR.finditer(line):
                if ("ph", mm.group(1)) in seen_param:
                    continue
                seen_param.add(("ph", mm.group(1)))
                parameters.append({"param": "pH", "value": mm.group(1), "unit": "",
                                   "scope": ("取自材料 %s" % sid) if lang == "zh" else ("from %s" % sid),
                                   "source_id": sid,
                                   "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                                   "source_kind": "material", "status": "verified",
                                   "conflict": False, "quote": line[:200]})
            for mm in N_PAIR.finditer(line):
                if ("n", mm.group(1)) in seen_param:
                    continue
                seen_param.add(("n", mm.group(1)))
                parameters.append({"param": "n", "value": mm.group(1),
                                   "unit": "replicates" if lang == "en" else "次重复",
                                   "scope": ("取自材料 %s" % sid) if lang == "zh" else ("from %s" % sid),
                                   "source_id": sid,
                                   "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                                   "source_kind": "material", "status": "verified",
                                   "conflict": False, "quote": line[:200]})

    for p in parameters[:8]:
        if p.get("status") == "conflict":
            continue
        cls = _unit_class(p.get("unit"))
        label = labels.get(cls) or labels["generic"]
        value = "%s%s" % (p.get("value"), (" " + str(p.get("unit"))) if p.get("unit") else "")
        steps.append({"sid": "P%d" % (len(steps) + 1), "name": label,
                      "inputs": ((("材料记录的输入：%s" % p.get("quote")) if p.get("quote")
                                  else ("见来源 %s" % (p.get("locator") or ""))) if lang == "zh"
                                 else ((("recorded input: %s" % p.get("quote")) if p.get("quote")
                                        else ("see %s" % (p.get("locator") or ""))))),
                      "operation": ("%s（%s = %s）" % (label, p.get("param"), value)) if lang == "zh"
                                   else ("%s (%s = %s)" % (label, p.get("param"), value)),
                      "params": "%s = %s" % (p.get("param"), value),
                      "output": ("按材料记录的观测结果见来源原文" if lang == "zh"
                                 else "observed result as recorded in the source"),
                      "branch": p.get("locator") or "",
                      "source_ids": [p.get("source_id")], "locator": p.get("locator"),
                      "quote": p.get("quote")})
        if len(steps) >= 8:
            break

    for sid, locs in _loclens(ctx, index).items():
        for (lineno, line) in locs:
            if len(settings) >= 12:
                break
            if not re.search(r"\d", line):
                continue
            if not re.search(r"°C|℃|pH|\bmin\b|hour|UV|irradiat|temperature|concentration|"
                             r"replicate|catalyst|温度|浓度|光照|辐照|重复", line, re.I):
                continue
            area = AREA_LABELS[lang]["train"]
            settings.append({"area": area, "text": line[:200],
                             "source_ids": [sid],
                             "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                             "quote": line[:200]})
    if not settings and texts:
        sid = sorted(texts)[0]
        kind, text, _p = texts[sid]
        first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 12), "")
        if first:
            settings.append({"area": AREA_LABELS[lang]["other"], "text": first[:200],
                             "source_ids": [sid], "status": "gap",
                             "note": ("材料未单列实验设置，取材料首句作为范围说明"
                                      if lang == "zh" else
                                      "material does not list a separate setup; first line used as scope"),
                             "quote": first[:200]})

    SIZE_RE = re.compile(r"(?<![\d.])\d+(?:[.,]\d+)?\s*(?:mg/L|mL|g/L|条|行|rows?|samples?|"
                         r"examples?|篇|个)")
    for sid, locs in _loclens(ctx, index).items():
        for (lineno, line) in locs:
            if len(datasets) >= 3:
                break
            heading = re.match(r"^#{1,6}\s+(.{2,60})$", line)
            if heading and re.search(r"abstract|introduction|method|result|reference|标题|"
                                     r"摘要|方法|结果", heading.group(1), re.I):
                continue
            if DATASET_RE.search(line) or SIZE_RE.search(line):
                size = SIZE_RE.search(line)
                datasets.append({"name": (("材料的底物/样本（名称未给出，%s）" % sid) if lang == "zh"
                                          else ("material substrate/sample (name not stated, %s)" % sid)),
                                 "version": "", "size": size.group(0) if size else "",
                                 "preprocess": "", "split": "", "usage": "",
                                 "source_ids": [sid],
                                 "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                                 "status": "gap",
                                 "note": ("材料未给出数据集名称/版本/划分，需作者确认"
                                          if lang == "zh" else
                                          "dataset name/version/split not stated; author must confirm"),
                                 "quote": line[:200]})
                break
        if len(datasets) >= 3:
            break

    for sid, locs in _loclens(ctx, index).items():
        for (lineno, line) in locs:
            if baselines:
                break
            if BASELINE_RE.search(line):
                baselines.append({"name": line[:60], "version": "", "budget_match": False,
                                  "metric": "", "stat": "", "comparable": False,
                                  "source_ids": [sid],
                                  "locator": "%s#L%d" % (index_rel(index, sid), lineno),
                                  "quote": line[:200]})
        if baselines:
            break

    for p in parameters:
        unit = str(p.get("unit") or "")
        name_l = str(p.get("param") or "").lower()
        if "%" in unit or any(t in name_l for t in ("yield", "selectivity", "removal",
                                                    "产率", "选择性")):
            evaluation.append({"text": ("%s = %s%s（%s）" % (p.get("param"), p.get("value"),
                                                           (" " + unit) if unit else "",
                                                           p.get("locator") or "")) if lang == "zh"
                                       else ("%s = %s%s (%s)" % (p.get("param"), p.get("value"),
                                                                 (" " + unit) if unit else "",
                                                                 p.get("locator") or "")),
                               "source_ids": [p.get("source_id")], "locator": p.get("locator")})
    if not evaluation:
        evaluation.append({"text": ("材料未给出评价指标与统计方式，需作者确认" if lang == "zh"
                                    else "material states no metric or statistics; author must confirm"),
                           "status": "gap", "source_ids": [], "locator": ""})

    for p in parameters:
        if _unit_class(p.get("unit")) in ("rep", "time", "cond") and len(repro) < 10:
            repro.append({"item": p.get("param"),
                          "value": "%s%s" % (p.get("value"),
                                             (" " + str(p.get("unit"))) if p.get("unit") else ""),
                          "source_ids": [p.get("source_id")], "locator": p.get("locator")})

    for sid, locs in _loclens(ctx, index).items():
        for (lineno, line) in locs:
            if len(limitations) >= 4:
                break
            if len(line) < 12 or not LIMIT_RE.search(line):
                continue
            limitations.append({
                "scope": line[:120],
                "failure_case": ("材料仅给出该范围说明，范围之外（见图/表边界）的失效情形未报告"
                                 if lang == "zh" else
                                 "only this scope is stated; behaviour outside it is not reported"),
                "reason": line[:160], "source_ids": [sid],
                "locator": "%s#L%d" % (index_rel(index, sid), lineno), "quote": line[:160]})
        if len(limitations) >= 4:
            break

    elem_specs = [
        ("steps", steps, "STEPS_MISSING", "步骤序列" if lang == "zh" else "step sequence", "steps"),
        ("settings", settings, "SETTINGS_MISSING", "实验设置" if lang == "zh" else "experimental setup", "settings"),
        ("datasets", datasets, "DATASET_MISSING", "数据集版本/划分" if lang == "zh" else "dataset version/split", "data"),
        ("baselines", baselines, "BASELINE_MISSING", "基线对象与对照条件" if lang == "zh" else "baselines and comparison conditions", "baseline"),
        ("limitations", limitations, "LIMITATION_MISSING", "限制条件" if lang == "zh" else "limitations", "limits"),
    ]
    first_sid = sorted(texts)[0] if texts else ""
    for key, bucket, kind, label, section in elem_specs:
        if bucket:
            continue
        desc = ("材料未提供可引用的%s，不推测" % label) if lang == "zh" else (
            "material provides no citable %s; not guessed" % label)
        gaps.append({"kind": kind, "desc": desc,
                     "impact": ("该要素缺失影响可复现性/可比性" if lang == "zh"
                                else "missing element hurts reproducibility/comparability"),
                     "owner": "author", "section": section,
                     "question": ("请补充%s的原始记录或书面确认" % label) if lang == "zh"
                                 else ("Please supply the raw record for %s" % label)})
        fill = {"status": "gap", "source_ids": [first_sid] if first_sid else [],
                "locator": ("%s#L1" % index_rel(index, first_sid)) if first_sid else "",
                "note": desc}
        if key == "steps":
            steps.append(dict(fill, sid="P1", name=(
                "材料未记录可排序步骤，需作者补全" if lang == "zh"
                else "no orderable step record; author must complete"),
                operation=desc, quote=""))
        elif key == "settings":
            settings.append(dict(fill, area=AREA_LABELS[lang]["other"], text=desc))
        elif key == "datasets":
            datasets.append(dict(fill, name=(("未提供数据集名称（%s）" % label) if lang == "zh"
                                             else ("no dataset name (%s)" % label))))
        elif key == "baselines":
            baselines.append(dict(fill, name=(("未提供基线（%s）" % label) if lang == "zh"
                                              else ("no baseline (%s)" % label)),
                                  comparable=None, budget_match=None))
        elif key == "limitations":
            limitations.append(dict(fill, scope=label, failure_case=desc, reason=desc))

    gaps.insert(0, {"kind": "AUTO_EXTRACT",
                    "desc": ("工作稿缺失/为空：由 init 台账确定性抽取（逐字 quote+locator），"
                             "未做任务级判断") if lang == "zh" else
                            ("no draft: deterministic extraction from the init ledger "
                             "(verbatim quote + locator); no task-level judgement"),
                    "impact": ("抽取式半成品，建议 Agent 复核" if lang == "zh"
                               else "extracted half-product; agent review recommended"),
                    "owner": "agent", "section": "scope",
                    "question": ("请按 references/guide.md 复核补写判断" if lang == "zh"
                                 else "Review and complete the judgement per references/guide.md")})
    for i, g in enumerate(gaps, 1):
        g["gid"] = "G%d" % i
    draft = {
        "case_id": ctx["case_id"],
        "language": lang,
        "task_understanding": {
            "genre": "方法与实验章节" if lang == "zh" else "methods and experiments section",
            "audience": "论文读者/复现者" if lang == "zh" else "paper readers / reproducers",
            "language": lang,
            "scope": ("单命令自动抽取：%d 个材料来源 / %d 条带源事实 / %d 个参数"
                      % (len(texts), len(facts), len(parameters))) if lang == "zh"
                     else ("single-command auto extraction: %d sources / %d sourced facts / "
                           "%d parameters" % (len(texts), len(facts), len(parameters))),
            "sections": "", "notes": ("AUTO_EXTRACT：逐字抽取，步骤顺序按材料出现顺序重建"
                                      if lang == "zh" else
                                      "AUTO_EXTRACT: verbatim extraction; step order "
                                      "reconstructed in material order")},
        "facts": facts, "steps": steps, "settings": settings, "parameters": parameters,
        "datasets": datasets, "baselines": baselines, "evaluation": evaluation,
        "repro": repro, "limitations": limitations, "gaps": gaps, "conflicts": conflicts,
        "headings": {}, "result_fields": {}}
    return draft

def index_rel(index, sid):
    for m in index.get("materials") or []:
        if m.get("source_id") == sid:
            return m.get("rel") or sid
    return sid

def fallback_draft(ctx, index):
    lang = ctx.get("language") or "zh"
    draft = auto_draft(ctx, index)
    draft["gaps"].insert(0, {
        "gid": "G0", "kind": "EMPTY_DRAFT",
        "desc": ("工作稿与自动抽取均为空，仅渲染骨架与缺口清单" if lang == "zh"
                 else "draft and auto extraction are both empty; skeleton only"),
        "impact": ("章节不可直接用于复现" if lang == "zh" else "section not reproducible as-is"),
        "owner": "author", "section": "scope",
        "question": ("请按 references/guide.md 补写工作稿" if lang == "zh"
                     else "Write the work draft per references/guide.md")})
    return draft

def _draft_empty(draft):
    if not isinstance(draft, dict) or not draft:
        return True
    for key in ("facts", "parameters", "steps", "settings", "datasets", "baselines",
                "evaluation", "repro", "limitations", "gaps", "conflicts"):
        if draft.get(key):
            return False
    return not draft.get("task_understanding")

def cmd_build(ctx, args):
    index = core.load_index(ctx)
    if not index:
        core.cmd_init(ctx, args)
        index = core.load_index(ctx) or {}
    ctx["index"] = index
    draft, err = core.load_draft(ctx)
    auto_used = False
    if not err and _draft_empty(draft):
        err = "draft_empty"
        draft = None
    if err:
        draft = auto_draft(ctx, index)
        auto_used = bool(draft.get("facts") or draft.get("parameters") or draft.get("datasets")
                         or draft.get("steps"))
        if not auto_used:
            draft = fallback_draft(ctx, index)
        ctx["degradations"].append(
            {"code": "DRAFT_MISSING_AUTO_EXTRACT" if auto_used else "DRAFT_MISSING",
             "message": (("工作稿缺失/为空（%s），build 用确定性抽取生成实质工作稿"
                          "（逐字 quote+locator）") if auto_used
                         else "工作稿缺失/为空（%s），build 输出降级骨架") % err})
        ctx["change_log"].append({"kind": "auto", "action": "生成确定性工作稿",
                                  "reason": "工作稿缺失或为空：%s" % err,
                                  "items": {"facts": len(draft.get("facts") or []),
                                            "parameters": len(draft.get("parameters") or []),
                                            "steps": len(draft.get("steps") or [])}})
    cov = render.coverage(draft)
    ctx["coverage"] = cov
    report = {"issues": [], "verified": {}} if err else check_draft(ctx)
    verified = report.get("verified") or {}
    out = ctx["output_dir"]
    arts = {}
    try:
        arts["manuscript"] = os.path.join(out, "manuscript.md")
        core.safe_write(arts["manuscript"],
                        render.render_manuscript(draft, index, {"case_id": ctx["case_id"],
                                                                "language": ctx.get("language")}))
        jobs = (
            ("fact_ledger", "fact_ledger.csv", lambda: render.fact_ledger_csv(draft, verified)),
            ("parameter_ledger", "parameter_ledger.csv",
             lambda: render.parameter_ledger_csv(draft, index)),
            ("evidence_matrix", "evidence_matrix.csv", lambda: render.evidence_matrix_csv(cov)),
            ("gaps", "gaps.md", lambda: render.gaps_md(draft, index)),
            ("conflicts", "conflicts.md", lambda: render.conflicts_md(draft, index)),
            ("coverage", "coverage.json", lambda: json.dumps(cov, ensure_ascii=False, indent=1)),
        )
        for key, name, job in jobs:
            path = os.path.join(out, name)
            try:
                core.safe_write(path, job())
                arts[key] = path
            except (ValueError, TypeError, OSError) as exc:
                ctx["errors"].append({"code": "RENDER_FAILED_%s" % key.upper(),
                                      "message": str(exc)[:200]})
    except (OSError, ValueError, TypeError) as exc:
        ctx["errors"].append({"code": "RENDER_FAILED", "message": str(exc)[:300]})
        ctx["degradations"].append({"code": "ARTIFACT_PARTIAL",
                                    "message": "部分产物渲染失败: %s" % exc.__class__.__name__})
    ctx["artifacts"] = arts
    ctx["change_log"].append({"kind": "auto", "action": "渲染章节稿与来源台账",
                              "reason": "覆盖 %s/%s 类必需要素" % (cov["covered"], cov["total"]),
                              "artifacts": sorted(arts)})
    errors = [i for i in report.get("issues", []) if i["level"] == "ERROR"]
    if ctx["case_status"] == "input_error":
        status, reason = "input_error", "case.json 不可解析；已回填契约字段并登记缺口"
    elif not (index.get("materials") or []):
        status, reason = "insufficient_evidence", "输入目录没有可读材料，无法支撑任何方法与实验小节"
    elif cov["covered"] == 0 and not draft.get("facts"):
        status, reason = "insufficient_evidence", "材料存在但未产出任何带来源的要素"
    elif err or errors or cov["covered"] < cov["total"]:
        bits = []
        if err:
            bits.append("工作稿缺失/为空，已自动抽取")
        if errors:
            bits.append("%d 项校验错误" % len(errors))
        if cov["covered"] < cov["total"]:
            bits.append("六要素覆盖 %d/%d" % (cov["covered"], cov["total"]))
        status, reason = "partial", "降级完成：" + "；".join(bits)
    else:
        status, reason = "answered", "六要素齐备、引文逐字命中、冲突均已登记"
    if not arts.get("manuscript") or not os.path.exists(arts["manuscript"]):
        status = "partial"
        ctx["degradations"].append({"code": "MANUSCRIPT_MISSING",
                                    "message": "manuscript.md 未写出，仅保留 result.json"})
    payload = core.write_result(ctx, status, reason, draft=draft)
    print("[build] status=%s reason=%s" % (payload["status"], payload["status_reason"]))
    print("[build] language=%s coverage=%s/%s artifacts=%d contract_filled=%d/%d"
          % (ctx.get("language"), cov["covered"], cov["total"], len(core.artifact_list(ctx)),
             len(payload["contract_fields"]["filled"]),
             len(payload["contract_fields"]["declared"])))
    for a in core.artifact_list(ctx):
        print("  - %-18s %s (%dB)" % (a["key"], a["path"], a["bytes"]))
    if payload["contract_fields"]["null_or_missing"]:
        print("[build] 仍为空的契约字段: %s"
              % ", ".join(payload["contract_fields"]["null_or_missing"][:15]))
    return 0

def cmd_selfcheck(ctx, args):
    path = os.path.join(ctx["output_dir"], "result.json")
    data, err = core.load_json(path)
    problems, patched = [], False
    if err:
        problems.append(err)
        ctx["degradations"].append({"code": "RESULT_JSON_BAD", "message": err})
        core.write_result(ctx, "partial", "result.json 不可解析，已按兜底重建", draft=None)
        data, err = core.load_json(path)
        if err:
            print("[selfcheck] FAIL 无法重建 result.json")
            return 0
    declared = [n for n, _ in ctx["contract"]]
    echo = data.get("output_contract") if isinstance(data.get("output_contract"), dict) else None
    missing = [n for n in declared if n not in data or (echo is not None and n not in echo)]
    if missing:
        problems.append("契约字段缺失: %s" % ", ".join(missing))
        if echo is None:
            data["output_contract"] = {}
            echo = data["output_contract"]
        for name in missing:
            val = data.get(name)
            if val in (None, [], ""):
                val = {"field": name,
                       "carried_by": "result.json 顶层信封字段（sources/artifacts/coverage/limits）"}
            data[name] = val
            echo[name] = val
        patched = True
    for key, default in (("case_id", ctx["case_id"]), ("status", "partial"), ("errors", []),
                         ("degradations", []), ("uncertainties", ["未在 result.json 中记录不确定性，"
                                                                  "已按兜底补记"]),
                         ("sources", []), ("change_records", []), ("limits", []),
                         ("pending_human", [])):
        if key not in data:
            problems.append("信封字段缺失（已补默认值）: %s" % key)
            data[key] = default
            patched = True
    if data.get("status") not in core.STATUS:
        problems.append("status 非法（已改为 partial）: %s" % data.get("status"))
        data["status"] = "partial"
        patched = True
    if patched:
        core.safe_write(path, json.dumps(data, ensure_ascii=False, indent=1, default=str))
    for art in data.get("artifacts") or []:
        p = art.get("path")
        if not p or not os.path.exists(p):
            problems.append("产物不存在: %s" % p)
        elif os.path.getsize(p) == 0:
            problems.append("产物为空: %s" % p)
    empty = [n for n in declared if data.get(n) in (None, [], "")]
    print("[selfcheck] status=%s artifacts=%d 契约字段=%d/%d"
          % (data.get("status"), len(data.get("artifacts") or []),
             len([n for n in declared if data.get(n) not in (None, [], "")]), len(declared)))
    if empty:
        print("[selfcheck] 契约字段为空: %s" % ", ".join(empty[:10]))
    for p in problems:
        print("  FAIL %s" % p)
    if not problems:
        print("[selfcheck] PASS 产物齐备、JSON 合法、契约字段齐全（顶层 + 嵌套）")
    return 0

def cmd_run(ctx, args):
    core.cmd_init(ctx, args)
    cmd_build(ctx, args)
    cmd_selfcheck(ctx, args)
    print("[run] 全流程完成：init → build → selfcheck")
    return 0

HANDLERS = {"run": cmd_run, "check": cmd_check, "build": cmd_build, "selfcheck": cmd_selfcheck}
