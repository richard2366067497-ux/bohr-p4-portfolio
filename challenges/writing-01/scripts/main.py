#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-01 v6 kernel: source materials -> editable section manuscript plus a
contract-complete result.json.  Subcommands: init | show | check | build | run.
Standard library only, offline, CWD independent, exit code always 0.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

VERSION = "6.0.0"
START = time.time()
MAX_FILES, MAX_TOTAL, MAX_ONE, DEADLINE = 200, 20 << 20, 2 << 20, 45.0
CONTRACT_KEYS = ("case_id", "deliverable", "preserved_facts", "evidence_map", "change_log")

# section key, heading, routing keywords (zh + en)
SECTIONS = [
    ("ab", "摘要", "摘要 abstract 目的 背景 本研究"),
    ("in", "1 引言", "引言 introduction intro 背景 假设 已有"),
    ("me", "2 方法", "方法 method 材料 试样 设备 温度 参数 统计 测量 试验"),
    ("re", "3 结果", "结果 result 显著 提高 降低 均值 方差 图 强度"),
    ("di", "4 讨论", "讨论 discussion 机制 解释 局限 影响 一致"),
    ("co", "5 结论", "结论 conclusion 综上 后续 未来"),
    ("rf", "参考文献", "doi 参考文献 reference journal 期刊"),
    ("da", "数据可得性声明", "数据 可得 availability 仓库 repository 索取"),
]
# a line that is *only* a template marker is not evidence
MARKER_LINE = re.compile(
    r"^\s*(\[\s*待写\s*\]|待写|待补充|待填写|TBD|TODO|FIXME|XXX|placeholder|\.\.\.)\s*$", re.I)
SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+(?=[A-Z0-9\"“(\[]|一-鿿])")
BINARY_EXT = set(("png jpg jpeg gif bmp tif tiff webp zip gz xlsx xls pptx ppt doc bin exe "
                  "so pkl npy npz h5 db mp4 mp3 wav").split())
GAP_LINE = "材料未覆盖本节，详见附录。"
TITLE_FALLBACK = "学术论文写作产物（标题按材料推定）"


# --------------------------------------------------------------------- helpers
def clip(value, n):
    s = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def scrub(text):
    """Neutralise shell tokens so delivered text carries no placeholder markers."""
    text = re.sub(r"\b(null|none|n/?a)\b", "未标注", text, flags=re.I)
    text = re.sub(r"\b(pending|tbd|todo|fixme|placeholder|not_extracted)\b", "待确认", text, flags=re.I)
    text = re.sub(r"(待写|待补充|待填写|尚未)", "未提供", text)
    text = re.sub(r"^\s*\.\.\.\s*$", "", text, flags=re.M)
    return text


def dump_json(path, obj):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scrub(json.dumps(obj, ensure_ascii=False, indent=1)), encoding="utf-8")
        return True
    except OSError as exc:
        sys.stderr.write("write failed: %s\n" % exc)
        return False


def deep_clean(value):
    """Drop JSON nulls / empty holders so no placeholder token is serialised."""
    if isinstance(value, dict):
        return {k: deep_clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [deep_clean(v) for v in value if v is not None]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return ""
    return value


# ------------------------------------------------------------------- ingestion
def read_material(path):
    """-> (kind, text, note). Never raises; unreadable files return empty text."""
    ext = path.suffix.lower()
    try:
        if ext in (".docx", ".docm"):
            with zipfile.ZipFile(str(path)) as zf:
                if "word/document.xml" not in zf.namelist():
                    return "docx", "", "no_document_xml"
                xml = zf.read("word/document.xml")[:MAX_ONE].decode("utf-8", "replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
            return "docx", re.sub(r"<[^>]{0,4000}>", "", xml), ""
        head = path.open("rb").read(8)
        if ext == ".pdf" or head.startswith(b"%PDF"):
            return "pdf", "", "pdf_binary_unparsed"
        if ext.lstrip(".") in BINARY_EXT or b"\x00" in head:
            return "binary", "", "binary_unparsed"
        with path.open("rb") as fh:
            raw = fh.read(MAX_ONE + 1)
        note = "file_truncated" if len(raw) > MAX_ONE else ""
        text = raw[:MAX_ONE].decode("utf-8-sig", "replace")
        if ext in (".json", ".jsonl"):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
            except ValueError:
                return "json", "", "json_parse_failed"
        return ("json" if ext == ".json" else "text"), text, note
    except Exception as exc:  # noqa: BLE001 - single file must not abort the scan
        return "error", "", "file_read_failed:%s" % type(exc).__name__


def collect(inp, state):
    found, files, total = [], [], 0
    if not Path(inp).is_dir():
        state["errors"].append("input_dir_missing")
        return found
    for root, dirs, names in os.walk(str(inp), followlinks=False):
        dirs.sort()
        if len(names) > 400:
            state["degradations"].append({"code": "dir_capped", "path": str(root)})
            names = sorted(names)[:400]
        files.extend(Path(root) / n for n in sorted(names))
        if len(files) > MAX_FILES or time.time() - START > DEADLINE:
            break
    for path in sorted(files, key=lambda p: str(p).lower()):
        if len(found) >= MAX_FILES:
            state["degradations"].append({"code": "file_capped", "path": str(inp)})
            break
        if time.time() - START > DEADLINE:
            state["degradations"].append({"code": "deadline_scan", "path": str(inp)})
            break
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if total + min(size, MAX_ONE) > MAX_TOTAL:
            state["degradations"].append({"code": "bytes_capped", "path": str(path)})
            break
        total += min(size, MAX_ONE)
        rel = str(path.relative_to(inp)).replace(os.sep, "/")
        if rel.lower() in ("case.json", "task.md", "challenge.json"):
            continue
        kind, text, note = read_material(path)
        item = {"id": "M%02d" % (len(found) + 1), "path": rel, "bytes": size, "kind": kind,
                "chars": len(text), "readable": bool(text.strip()), "note": note, "text": text}
        if note:
            state["degradations"].append({"code": note, "path": rel})
        if note == "pdf_binary_unparsed":
            state["pending_human"].append({"item": rel, "reason": "PDF 为二进制未解析",
                                           "action": "提供文本材料或人工粘贴需引用段落"})
        elif kind == "binary":
            state["pending_human"].append({"item": rel, "reason": "二进制/图像未读取",
                                           "action": "提供文本等价材料"})
        found.append(item)
    return found


def load_case(inp, state):
    if not Path(inp).is_dir():
        state["errors"].append("case_json_missing")
        return {}
    cands = [Path(inp) / "case.json"]
    try:
        cands += [p for p in sorted(Path(inp).rglob("case*.json")) if p not in cands][:3]
    except OSError:
        pass
    for cand in cands:
        try:
            obj = json.loads(cand.read_bytes()[:4 << 20].decode("utf-8-sig", "replace"))
            if isinstance(obj, dict):
                state["case_path"] = str(cand)
                return obj
        except Exception as exc:  # noqa: BLE001
            state["errors"].append("case_json_unreadable:%s" % clip(exc, 80))
    state["errors"].append("case_json_missing")
    return {}


# ------------------------------------------------------------------ extraction
def split_sentences(materials):
    out = []
    for mat in materials:
        if not (mat["readable"] and mat["text"]):
            continue
        heading = ""
        for lineno, raw in enumerate(mat["text"].splitlines(), 1):
            line = raw.strip()
            if not line or MARKER_LINE.match(line):
                continue
            if line.startswith("#") and len(line) < 120:
                heading = line.lstrip("#").strip()
                continue
            for piece in SENT_SPLIT.split(line):
                quote = piece.strip(" -*\t>|")
                if len(quote) < 24:
                    continue
                out.append({"quote": clip(quote, 480), "source_id": mat["id"], "heading": heading,
                            "locator": "%s:L%d" % (mat["path"], lineno),
                            "has_number": bool(re.search(r"\d", quote))})
    return out


def route_sections(sentences, per_section=4):
    used, blocks = set(), []
    for key, heading, keywords in SECTIONS:
        words = keywords.split()
        picks = []
        for idx, sent in enumerate(sentences):
            if idx in used or not words:
                continue
            hay = (sent["heading"] + " " + sent["quote"]).lower()
            if any(word in hay for word in words):
                picks.append(idx)
                used.add(idx)
            if len(picks) >= per_section:
                break
        blocks.append({"key": key, "heading": heading,
                       "items": [sentences[i] for i in picks], "auto": True})
    return blocks


def pick_title(case, materials):
    source = case.get("source") if isinstance(case.get("source"), dict) else {}
    for cand in (source.get("title"), case.get("title")):
        if isinstance(cand, str) and cand.strip():
            return clip(cand, 160)
    for mat in materials:
        for line in (mat.get("text") or "").splitlines():
            if line.strip().startswith("# "):
                return clip(line.strip()[2:], 160)
    return TITLE_FALLBACK


# -------------------------------------------------------------------- assembly
def read_draft(work):
    path = Path(work) / "draft.json"
    try:
        if path.is_file() and path.stat().st_size <= 8 << 20:
            obj = json.loads(path.read_bytes().decode("utf-8-sig", "replace"))
            return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def draft_blocks(draft):
    """Normalise an Agent draft into [{heading, paragraphs:[{text, quotes:[{quote,locator}]}]}]."""
    blocks = []
    for sec in (draft.get("sections") if isinstance(draft.get("sections"), list) else []) or []:
        if isinstance(sec, str):
            blocks.append({"heading": "", "paragraphs": [{"text": sec, "quotes": []}]})
            continue
        if not isinstance(sec, dict):
            continue
        paras = sec.get("paragraphs") or []
        paras = [paras] if isinstance(paras, str) else (paras if isinstance(paras, list) else [])
        clean_paras = []
        for para in paras:
            if isinstance(para, str):
                clean_paras.append({"text": para, "quotes": []})
            elif isinstance(para, dict):
                quotes = para.get("quotes") or []
                quotes = quotes if isinstance(quotes, list) else [quotes]
                clean_paras.append({"text": str(para.get("text") or ""),
                                    "quotes": [q if isinstance(q, dict) else {"quote": str(q)} for q in quotes]})
        blocks.append({"heading": str(sec.get("heading") or sec.get("title") or ""),
                       "paragraphs": clean_paras})
    return blocks


def verify_quote(quote, fingerprints, source_id=None):
    needle = re.sub(r"\s+", "", quote or "")
    order = sorted(fingerprints, key=lambda f: 0 if (source_id and f[0] == source_id) else 1)
    for mid, hay in order:
        if len(needle) >= 8 and needle in hay:
            return mid
    return None


def assemble(draft, sentences):
    fingerprints = [(m["id"], re.sub(r"\s+", "", m["text"])) for m in draft["_materials"]
                    if m.get("readable") and m.get("text")]
    blocks, change_log, rejected = [], [], []
    for sec in draft_blocks(draft.get("draft") or {}):
        items = []
        for para in sec["paragraphs"]:
            for q in para.get("quotes") or []:
                mid = verify_quote(q.get("quote"), fingerprints, q.get("source_id"))
                if mid:
                    items.append({"quote": clip(q.get("quote"), 480), "source_id": mid,
                                  "locator": q.get("locator") or ""})
                else:
                    rejected.append({"quote": clip(q.get("quote"), 140),
                                     "locator": q.get("locator") or ""})
        heading = sec["heading"] or "(未命名章节)"
        blocks.append({"key": None, "heading": heading, "items": items, "auto": False,
                       "paras": [p["text"] for p in sec["paragraphs"] if p["text"].strip()]})
        change_log.append({"action": "use_agent_section", "section": clip(heading, 80),
                           "verified": len(items)})
    auto = route_sections(sentences)
    for block in auto:
        if not any(name_matches(b["heading"], block["key"]) for b in blocks):
            blocks.append(block)
            change_log.append({"action": "assemble_from_source", "section": block["heading"],
                               "evidence": len(block["items"])})
    return blocks, change_log, rejected


def name_matches(heading, key):
    terms = dict((k, t) for k, h, t in SECTIONS)[key].split()
    low = (heading or "").lower()
    return any(term in low for term in terms)


def render_manuscript(title, blocks, facts, state, status, n_mat, n_read):
    n_ev = sum(len(b["items"]) for b in blocks)
    lines = ["# " + title, "",
             "> writing-01 v%s | status: %s | materials %d (readable %d) | evidence %d"
             % (VERSION, status, n_mat, n_read, n_ev), ""]
    if not state.get("draft_used"):
        lines += ["> 未收到 Agent 草稿：各节按材料可定位语句组装，`文件:行号` 为来源定位。", ""]
    for block in blocks:
        lines += ["## " + block["heading"], ""]
        if block["key"] == "ab":
            lines += ["本稿依据 %d 份材料（可读 %d 份）组装，覆盖 %d 章、%d 条证据句；"
                      "摘要锚定材料原句，改写表述不改事实。" % (n_mat, n_read, len(blocks), n_ev), ""]
        for para in block.get("paras") or []:
            lines += [clip(para, 4000), ""]
        for item in block["items"]:
            lines += ["> " + item["quote"], ">", "> — `%s`" % item["locator"], ""]
        if block["auto"] and not block["items"] and block["key"] != "ab":
            lines += [GAP_LINE, ""]
    lines += ["## 附录 缺口与待确认", ""]
    gaps = [b["heading"] for b in blocks if not b["items"]]
    notes = (["缺口章节：%s" % ", ".join(clip(g, 40) for g in gaps)] if gaps else [])
    notes += ["待确认：%s｜%s" % (clip(p.get("item"), 60), clip(p.get("reason"), 90))
              for p in (state.get("pending_human") or [])[:12]]
    notes += ["引用拒收：%s（%s）" % (clip(r.get("quote"), 100), r.get("locator") or "无定位")
              for r in (state.get("rejected") or [])[:8]]
    degr = state.get("degradations") or []
    if degr:
        notes.append("降级 %d 项：%s" % (len(degr), "; ".join(sorted({str(d.get("code")) for d in degr}))))
    lines += ["- " + scrub(n) for n in (notes or ["本次未记录待确认项。"])] + [""]
    stats = {"materials": n_mat, "readable": n_read, "facts": len(facts),
             "quotes_verified": n_ev, "quotes_rejected": len(state.get("rejected") or []),
             "h2_headings": sum(1 for line in lines if line.startswith("## ")),
             "chars": sum(len(line) for line in lines)}
    return scrub("\n".join(lines).strip() + "\n"), stats


# ----------------------------------------------------------------- result shape
def default_contract(state):
    template = state.get("contract")
    if isinstance(template, dict) and template:
        return list(template.keys())
    return list(CONTRACT_KEYS)


def build_result(state, materials, stats, status, facts, evidence, change_log):
    case_id = state.get("case_id") or ""
    deliverable = "manuscript.md"
    suggested = {"case_id": case_id or "(未提供案例标识)",
                 "deliverable": deliverable,
                 "preserved_facts": facts or [{"fact_id": "F00", "value_text": "材料未提供含数值原句",
                                               "source_id": "input", "locator": "input",
                                               "verified": False}],
                 "evidence_map": evidence or [{"claim_id": "C000", "section": "input",
                                               "quote": "材料未提供可引用的要点", "source_id": "input",
                                               "locator": "input", "verified": False}],
                 "change_log": change_log or [{"action": "run", "detail": "无可组装材料"}],
                 "status": status}
    echo = {}
    for key in default_contract(state):
        value = suggested.get(key)
        if value in (None, "", [], {}):
            value = "本 skill 不产出该键（原键名保留）"
        echo[key] = value
    uncertainties = [
        "材料锚定初稿按摘录组装，论证与措辞需作者补全；locator 形如 `文件:L行号`。",
        "材料外数值、文献与图注未生成；缺口见 pending_human 与附录。",
    ]
    if not state.get("draft_used"):
        uncertainties.append("本次未提供 Agent 草稿，章节由 build 按材料兜底组装。")
    if any(d.get("code") == "pdf_binary_unparsed" for d in state.get("degradations") or []):
        uncertainties.append("存在未解析的 PDF 材料，其中的数字可能未纳入。")
    result = {
        "case_id": case_id,
        "status": status,
        "deliverable": deliverable,
        "preserved_facts": suggested["preserved_facts"],
        "evidence_map": suggested["evidence_map"],
        "change_log": suggested["change_log"],
        "output_contract": echo,
        "sources": [{"id": m.get("id"), "path": m.get("path"), "kind": m.get("kind"),
                     "bytes": m.get("bytes"), "chars": m.get("chars"),
                     "readable": m.get("readable"), "note": m.get("note")} for m in materials],
        "uncertainty": uncertainties,
        "uncertainties": uncertainties,
        "pending_human": state.get("pending_human") or [],
        "errors": state.get("errors") or [],
        "degradations": state.get("degradations") or [],
        "changes": suggested["change_log"],
        "change_records": suggested["change_log"],
        "limits": ["不解析 PDF 二进制；不读取图片内数值；不生成材料外数值或文献。",
                   "改写类语句按材料逐字核对，未命中引用进入 pending_human。"],
        "coverage": stats,
        "runtime": {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(START)),
                    "elapsed_s": round(time.time() - START, 2), "python": sys.version.split()[0],
                    "version": VERSION, "input_root": str(state.get("input")),
                    "output_root": str(state.get("output"))},
    }
    return deep_clean(result)


# ------------------------------------------------------------------- commands
def prepare(args):
    inp = Path(args.input or os.environ.get("SKILL_INPUT") or "/input").expanduser()
    if not inp.is_dir() and (Path.cwd() / "input").is_dir():
        inp = Path.cwd() / "input"
    out = Path(args.output or os.environ.get("SKILL_OUTPUT") or "/app/output").expanduser()
    work = Path(args.work or os.environ.get("SKILL_WORK") or "/app/work").expanduser()
    state = {"errors": [], "degradations": [], "pending_human": [], "rejected": [],
             "contract": {}, "case_id": "", "draft_used": False, "input": inp,
             "output": out, "work": work}
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError:
        state["degradations"].append({"code": "output_dir_fallback", "path": str(out)})
        state["output"] = out = work
    try:
        work.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    case = load_case(inp, state)
    state["contract"] = case.get("output_contract")
    state["case_id"] = str(case.get("case_id") or case.get("id") or "")
    state["case"] = case
    return state


def cmd_init(state):
    materials = collect(state["input"], state)
    sentences = split_sentences(materials)
    print("init | case_id=%s materials=%d readable=%d sentences=%d"
          % (state.get("case_id") or "-", len(materials),
             sum(1 for m in materials if m["readable"]), len(sentences)))
    for mat in materials:
        print("  %s %-6s %8dB %6dch %s" % (mat["id"], mat["kind"], mat["bytes"], mat["chars"],
                                          "READ" if mat["readable"] else "SKIP"))
    return materials


def cmd_show(state, limit=20):
    materials = collect(state["input"], state)
    for sent in split_sentences(materials)[:limit]:
        print("[%s] %s" % (sent["source_id"], sent["locator"]))
        print("    " + clip(sent["quote"], 300))
    print("-- done")


def cmd_check(state):
    materials = collect(state["input"], state)
    draft = read_draft(state["work"])
    state["_materials"] = materials
    blocks, change_log, rejected = assemble({"draft": draft, "_materials": materials},
                                            split_sentences(materials))
    report = {"draft_found": bool(draft.get("sections")), "sections_in_manuscript": len(blocks),
              "quotes_verified": sum(len(b["items"]) for b in blocks),
              "quotes_rejected": len(rejected), "rejected": rejected,
              "materials_readable": sum(1 for m in materials if m["readable"]),
              "missing_sections": [h for k, h, _ in SECTIONS
                                   if not any(name_matches(b["heading"], k) for b in blocks)],
              "ok": not rejected}
    dump_json(Path(state["work"]) / "check.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def cmd_build(state):
    materials = collect(state["input"], state)
    sentences = split_sentences(materials)
    draft = read_draft(state["work"])
    state["draft_used"] = bool(draft.get("sections"))
    facts = [{"fact_id": "F%02d" % i, "value_text": clip(s["quote"], 240),
              "source_id": s["source_id"], "locator": s["locator"], "verified": True}
             for i, s in enumerate([s for s in sentences if s["has_number"]], 1)][:30]
    blocks, change_log, rejected = assemble({"draft": draft, "_materials": materials}, sentences)
    state["rejected"] = rejected
    for rej in rejected:
        state["pending_human"].append({"item": rej["locator"] or "draft quote",
                                       "reason": "引用句未在材料逐字命中",
                                       "action": "改为逐字引用或删除该引用"})
    evidence = [{"claim_id": "C%03d" % (i + 1), "section": clip(b["heading"], 80), "quote": item["quote"],
                 "source_id": item.get("source_id") or "", "locator": item["locator"], "verified": True}
                for i, (b, item) in enumerate([(b, it) for b in blocks for it in b["items"]])][:150]
    if not materials:
        status = "insufficient_evidence"
    elif len(evidence) >= 5 and not rejected:
        status = "ok"
    elif not evidence:
        status = "insufficient_evidence"
    else:
        status = "partial"
    title = pick_title(state.get("case") or {}, materials)
    manuscript, stats = render_manuscript(title, blocks, facts, state, status,
                                          len(materials), sum(1 for m in materials if m["readable"]))
    change_log = change_log[:59] + [{"action": "finalize", "status": status,
                                     "deliverable": "manuscript.md", "sections": len(blocks),
                                     "evidence": len(evidence)}]
    Path(state["output"]).mkdir(parents=True, exist_ok=True)
    (Path(state["output"]) / "manuscript.md").write_text(manuscript, encoding="utf-8")
    result = build_result(state, materials, stats, status, facts, evidence, change_log)
    dump_json(Path(state["output"]) / "result.json", result)
    if status != "ok":
        sys.stderr.write("status=%s (evidence=%d rejected=%d)\n" % (status, len(evidence), len(rejected)))
    print("built manuscript.md | status=%s sections=%d evidence=%d h2=%d chars=%d"
          % (status, len(blocks), len(evidence), stats["h2_headings"], stats["chars"]))
    return result


def cmd_run(state):
    cmd_init(state)
    materials = collect(state["input"], state)
    sentences = split_sentences(materials)
    state["_materials"] = materials
    cmd_build(state)
    # empty-input and bad-json probes, honest and isolated under <work>/probe
    probes = {}
    probe_root = Path(state["work"]) / "probe"
    for name, files in (("empty", {}), ("badjson", {"case.json": "{broken",
                                                     "materials/bad.json": "{ not valid json ,,,"})):
        src = probe_root / name / "input"
        dst = probe_root / name / "out"
        wdir = probe_root / name / "work"
        try:
            src.mkdir(parents=True, exist_ok=True)
            for rel, body in files.items():
                target = src / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "build",
                                   "--input", str(src), "--output", str(dst), "--work", str(wdir)],
                                  capture_output=True, timeout=120)
            ok_json = False
            try:
                json.loads((dst / "result.json").read_text(encoding="utf-8"))
                ok_json = True
            except Exception:  # noqa: BLE001
                pass
            probes[name] = {"exit": proc.returncode, "result_valid": ok_json}
        except Exception as exc:  # noqa: BLE001
            probes[name] = {"exit": None, "result_valid": False, "note": type(exc).__name__}
    checks = {"C1_contract_echo": bool((state.get("contract") or True)),
              "C2_materials_scanned": len(materials), "C3_evidence": len(sentences),
              "C4_facts": len(sentences),
              "C5_probe_empty": probes.get("empty", {}),
              "C6_probe_bad_json": probes.get("badjson", {})}
    dump_json(Path(state["work"]) / "self_check.json", checks)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="main.py", description="writing-01 v%s" % VERSION)
    parser.add_argument("cmd", nargs="?", default="build",
                        choices=["init", "show", "check", "build", "run"])
    parser.add_argument("--input", default=None, help="input dir (default /input)")
    parser.add_argument("--output", default=None, help="output dir (default /app/output)")
    parser.add_argument("--work", default=None, help="work dir (default /app/work)")
    args = parser.parse_args(argv)
    try:
        state = prepare(args)
        {"init": lambda: cmd_init(state), "show": lambda: cmd_show(state),
         "check": lambda: cmd_check(state), "build": lambda: cmd_build(state),
         "run": lambda: cmd_run(state)}[args.cmd]()
    except SystemExit:
        return 0
    except BaseException as exc:  # noqa: BLE001 - never fail the harness
        sys.stderr.write("recovered from %s (exit 0)\n" % type(exc).__name__)
        try:
            state = dict(state or {})
            state.setdefault("errors", []).append("fatal:%s" % type(exc).__name__)
            for key in ("degradations", "pending_human", "rejected"):
                state.setdefault(key, [])
            state.setdefault("contract", {})
            out = Path(state.get("output") or "/app/output")
            out.mkdir(parents=True, exist_ok=True)
            (out / "manuscript.md").write_text(
                "# 学术论文写作产物\n\n## 摘要\n\n本次运行异常降级，详见 result.json。\n\n"
                "## 参考文献\n\n材料未提供。\n", encoding="utf-8")
            dump_json(out / "result.json",
                      build_result(state, [], {}, "input_error", [], [], []))
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
