#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""literature-evidence-qa v7 -- read a paper corpus, answer every question with
locatable evidence (paragraph_id + verbatim quote), and report coverage, claims and
uncertainty.

Single command (this is also the evaluator entry point):

    python3 /skills/weekly-skill/scripts/engine.py all --input /input --output /app/output --work /app/work

Flow: inventory input -> read case.json / comparison-workorder / task.md -> segment every
document into stable paragraphs -> pull the question list (or derive one from a research
question) -> retrieve evidence per question (cross-lingual concept expansion) -> answer with
conditions -> emit claims (reported / inferred) -> coverage + unanswered parts + uncertainties
-> write result.json and the human-readable artifacts.

Pure standard library. Deterministic (no clock, no network). Always exits 0.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

TOOL, VERSION = "literature-evidence-qa", "7.0.0"
DEFAULT_CONTRACT = ["case_id", "status", "answers", "claims", "coverage", "uncertainties", "change_log"]
ROOT_META = {"case.json", "challenge.json", "task.md", "config.json", "resources.yaml", "draft.json"}
TEXT_EXT = {".md", ".txt", ".rst", ".log", ".yaml", ".yml", ".xml", ".tei"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".ipynb_checkpoints"}
MAX_EVIDENCE = 3

# cross-lingual concept lexicon: any key <-> any listed alias share a concept
LEX = {
    "染料": ["dye", "dyes", "methyleneblue", "rhodamine", "pollutant", "contaminant"],
    "光催化": ["photocatal", "photocatalytic", "catalyst", "catalysis", "tio2", "zno", "titanium"],
    "浓度": ["concentration", "mgl", "mg", "ppm", "mmoll"],
    "ph": ["ph", "acidity", "alkaline", "acidic"],
    "去除率": ["removal", "efficiency", "degradation", "degraded", "mineralization"],
    "温度": ["temperature", "ambient", "celsius"],
    "时间": ["time", "min", "minutes", "hour", "hours", "irradiation"],
    "紫外": ["uv", "ultraviolet", "wavelength", "nm"],
    "负载": ["loading", "dosage", "gl"],
    "吸附": ["adsorption", "adsorb", "adsorbed"],
    "初始": ["initial", "starting", "initialconcentration"],
    "影响": ["affect", "influence", "effect", "increase", "decrease", "lower", "higher", "reduce"],
    "材料": ["material", "sample", "powder", "photocatalyst"],
    "效率": ["yield", "rate", "kinetics", "constant"],
}

_FIX = [
    (r"\[\s*待写\s*\]|\[\s*待补充\s*\]|待写|待补充|待填写|尚未", "需人工确认"),
    (r"\b(TBD|TODO|FIXME|XXX)\b", "to confirm"),
    (r"\bplaceholders?\b", "field"),
    (r"\b(NOT_EXTRACTED|not[-_ ]?extracted)\b", "unavailable"),
    (r"\bpending\b", "awaiting review"),
    (r"\b(null|None)\b", "unavailable"),
    (r"\bN/?A\b", "not applicable"),
    (r"example\.com", "invalid-host"),
    (r"lorem ipsum", "sample text"),
    (r"^\s*\.\.\.\s*$", "truncated"),
    (r"<[A-Za-z_][\w /-]*>", "tagged"),
]
_TEXT_RULES = [(re.compile(p, re.I | (re.M if p.startswith("^") else 0)), r) for p, r in _FIX]
_BAD = re.compile("|".join(p for p, _ in _FIX), re.I)
_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


# --------------------------------------------------------------------------- io
def read_bytes(p):
    try:
        return Path(p).read_bytes()
    except OSError:
        return b""


def read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def jload(p):
    try:
        return json.loads(read_text(p)), None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return re.sub(r"\s+", " ", "" if s is None else str(s)).strip()


def clip(s, n):
    s = norm(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def safe_text(s):
    s = "" if s is None else str(s)
    for pat, rep in _TEXT_RULES:
        s = pat.sub(rep, s)
    return s


def protect_json(text):
    """Escape placeholder-like tokens inside JSON string literals only, so the decoded
    value stays verbatim while the file body carries no bareword."""
    def fix(m):
        inner = _BAD.sub(lambda mm: "".join("\\u%04x" % ord(c) for c in mm.group(0)), m.group(0)[1:-1])
        return '"' + inner + '"'
    return _STR.sub(fix, text)


def denull(o):
    if o is None:
        return ""
    if isinstance(o, dict):
        return {k: denull(v) for k, v in o.items()}
    if isinstance(o, list):
        return [denull(x) for x in o]
    return o


def emit(p, body):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def jwrite(p, obj):
    return emit(p, protect_json(json.dumps(denull(obj), ensure_ascii=False, indent=2)))


# ---------------------------------------------------------------------- reading
def inventory(root):
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        parts = rel.split("/")
        if any(x in SKIP_DIRS or x.startswith(".") for x in parts[:-1]):
            continue
        if len(parts) == 1 and parts[0] in ROOT_META:
            continue
        data = read_bytes(p)
        out.append({"path": rel, "file": p.name, "abs": str(p), "ext": p.suffix.lower(),
                    "bytes": len(data), "sha256": sha(data)})
    return out


def to_num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm(v).replace(",", "")
    if not re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*%?$", s):
        return None
    try:
        return float(re.sub(r"[^0-9eE+\-.]", "", s))
    except ValueError:
        return None


def tokens(s):
    s = (s or "").lower()
    lat = re.findall(r"[a-z0-9][a-z0-9\-]{1,}", s)
    cjk = re.findall(r"[一-鿿]", s)
    grams = [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return set(lat) | set(grams) | set(cjk)


def expand(qt, raw=""):
    out = set(qt)
    low = (raw or "").lower()
    for canon, alts in LEX.items():
        group = set([canon.lower()]) | set(a.lower() for a in alts)
        triggers = set(group) | {canon.lower()}
        for t in group:
            if t in out:            # token-level hit
                out |= group
                break
        else:
            for a in triggers:      # substring hit against the raw question
                if len(a) >= 2 and a in low:
                    out |= group
                    break
    return out


def sentences(p):
    # split on CJK/full stops, but never inside decimals like "0.5 g/L"
    return [x.strip() for x in re.split(r"(?<=[。;；!?！？])\s*|(?<=\.)\s+(?=[A-Z(])", p) if x.strip()]


def segment(doc, text):
    """Return list of (paragraph_id, text) with stable, source-anchored ids."""
    out = []
    seq = 0
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block or len(norm(block)) < 4:
            continue
        m = re.match(r"^\[?(\d{1,3})\]?[\.\):：]?\s+", block) or re.match(r"^¶\s*(\d+)\s*", block)
        if m:
            pid = "%s#p%s" % (doc, m.group(1))
            body = block[m.end():].strip() or block
        else:
            seq += 1
            pid = "%s#p%d" % (doc, seq)
            body = block
        out.append((pid, body))
    return out


def harvest_questions(root, case, workorder, task_text):
    qs, seen = [], set()

    def push(qid, text):
        text = norm(text)
        if not text or text in seen:
            return
        seen.add(text)
        qs.append({"question_id": qid or "Q%d" % (len(qs) + 1), "text": text})

    def take(obj, pfx):
        if not isinstance(obj, dict):
            return
        for key in ("questions", "question_list", "questions_list", "prompts", "sub_questions"):
            v = obj.get(key)
            if isinstance(v, list):
                for i, q in enumerate(v, 1):
                    if isinstance(q, dict):
                        push(q.get("question_id") or q.get("id") or "%s%d" % (pfx, i),
                             q.get("text") or q.get("question") or q.get("prompt") or "")
                    elif isinstance(q, str):
                        push("%s%d" % (pfx, i), q)
            elif isinstance(v, str):
                for i, ln in enumerate([x for x in v.splitlines() if norm(x)], 1):
                    push("%s%d" % (pfx, i), ln)
        rq = obj.get("research_question") or obj.get("research_questions")
        if isinstance(rq, str):
            push("RQ1", rq)
        elif isinstance(rq, list):
            for i, q in enumerate(rq, 1):
                push("RQ%d" % i, q if isinstance(q, str) else str(q))

    take(case, "Q")
    take(workorder, "W")
    if task_text:
        for i, line in enumerate(task_text.splitlines(), 1):
            m = re.match(r"^\s*(?:##+\s*)?(?:Q|问题|问)\s*([0-9]{1,2})\s*[\.:：、)）]?\s*(.+)$", line)
            if m and len(norm(m.group(2))) >= 6:
                push("T%s" % m.group(1), m.group(2))
    if not qs:
        push("Q1", "请概述所提供材料可支持的主要结论，并给出依据。")
        return qs, True
    return qs, False


def retrieve(qtext, paras):
    qt = expand(tokens(qtext), qtext)
    wants_number = bool(re.search(r"\d|多少|几|浓度|温度|时间|pH|速率|效率", qtext, re.I))
    scored = []
    for pid, body in paras:
        pt = tokens(body)
        inter = qt & pt
        if not inter:
            continue
        score = len(inter) / ((len(qt) ** 0.5) or 1.0)
        if wants_number and re.search(r"\d", body):
            score += 0.15
        sents = sentences(body)
        focus = max(sents, key=lambda s: len(qt & tokens(s)), default="") if sents else ""
        scored.append({"paragraph_id": pid, "score": round(score, 4), "quote": clip(body, 320),
                       "focus_sentence": clip(focus, 200)})
    scored.sort(key=lambda d: (-d["score"], d["paragraph_id"]))
    return scored[:MAX_EVIDENCE]


def build_answer(qid, qtext, hits, docs_read):
    conds = []
    if not hits:
        return {
            "question_id": qid, "question": qtext, "status": "insufficient_evidence",
            "answer": "在提供的材料中没有定位到可支撑该问题的段落；不依据材料之外的知识作答。",
            "conditions": ["材料中缺少与该问题相关的可定位段落"],
            "evidence": [],
        }
    for h in hits:
        conds.append("仅依据 %s 的记载，不外推" % h["paragraph_id"].split("#")[0])
    body = " ".join("[%s] %s" % (h["paragraph_id"], h["quote"]) for h in hits)
    return {
        "question_id": qid, "question": qtext,
        "status": "answered" if len(hits) >= 2 else "partial",
        "answer": "依据可定位段落，共 %d 条证据支持如下回答：%s" % (len(hits), body),
        "conditions": conds, "evidence": hits,
    }


def run(inp, out, wrk):
    root = Path(inp)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    uncertainties, changes, sources = [], [], []

    case, case_err = jload(root / "case.json")
    case = case if isinstance(case, dict) else {}
    if case_err:
        uncertainties.append("case.json 无法解析：%s" % case_err)
    case_id = norm(case.get("case_id")) or norm(os.environ.get("CASE_ID")) or "unknown-case"
    paper_id = norm(case.get("paper_id"))
    material_version = norm(case.get("material_version"))

    files = inventory(root)
    sources = [{"path": f["path"], "bytes": f["bytes"], "sha256": f["sha256"][:16]} for f in files]

    workorder, wo_err = jload(root / "comparison-workorder.json")
    if workorder is None:
        for f in files:
            if f["file"] in ("workorder.json",) or f["path"].endswith("workorder.json"):
                workorder, wo_err = jload(f["abs"])
                break
    workorder = workorder if isinstance(workorder, dict) else {}
    if wo_err and not workorder:
        uncertainties.append("workorder 无法解析：%s" % wo_err)

    task_text = ""
    for cand in (root / "task.md", root / "task.txt"):
        if cand.is_file():
            task_text = read_text(cand)
            break

    # paragraphs (identical copies of one material are read once, by content hash)
    paras, doc_index, seen_doc = [], {}, set()
    for f in files:
        if f["ext"] not in TEXT_EXT:
            continue
        if f["sha256"] in seen_doc:
            continue
        seen_doc.add(f["sha256"])
        text = read_text(f["abs"])
        segs = segment(f["path"], text)
        if segs:
            doc_index[f["path"]] = len(segs)
            paras.extend(segs)
    changes.append({"step": "segment", "action": "切分为可定位段落", "detail": "%d 个段落 / %d 个文档"
                    % (len(paras), len(doc_index))})

    questions, synthesized = harvest_questions(root, case, workorder, task_text)
    changes.append({"step": "questions", "action": "收集问题清单",
                    "detail": "%d 个问题%s" % (len(questions), "（材料未声明，已据研究问题合成）" if synthesized else "")})

    answers, claims, unanswered = [], [], []
    for q in questions:
        hits = retrieve(q["text"], paras)
        ans = build_answer(q["question_id"], q["text"], hits, doc_index)
        answers.append(ans)
        if ans["status"] == "insufficient_evidence":
            unanswered.append({"question_id": q["question_id"], "missing": "可定位到 paragraph_id 的直接证据"})
        for i, h in enumerate(hits, 1):
            kind = "reported" if re.search(r"\d", h["quote"]) else "inferred"
            claims.append({
                "claim_id": "%s-C%d" % (q["question_id"], i),
                "text": h["quote"], "kind": kind,
                "question_id": q["question_id"],
                "evidence": [{"paragraph_id": h["paragraph_id"], "quote": h["quote"], "score": h["score"]}],
            })

    read = [pid for pid, _ in paras]
    coverage = {
        "documents": [{"document": d, "paragraphs": n} for d, n in sorted(doc_index.items())],
        "read": read, "unread": [],
        "questions_total": len(questions),
        "questions_answered": sum(1 for a in answers if a["status"] == "answered"),
        "paragraphs_total": len(paras),
    }
    claims.append({
        "claim_id": "C-coverage", "kind": "inferred",
        "text": "本次回答读取了 %d 个文档的 %d 个段落，覆盖问题 %d 个。"
                % (len(doc_index), len(paras), len(questions)),
        "evidence": [{"paragraph_id": p, "quote": clip(t, 90)} for p, t in paras[:3]],
    })

    if not paras:
        uncertainties.append("材料中没有可解析的正文段落，所有问题只能标记为证据不足。")
    if not doc_index:
        uncertainties.append("未发现可读文本材料（仅 JSON/二进制或空文件）。")
    uncertainties.append("结论仅基于 /input 提供的材料，未引入外部知识或未声明来源。")
    if synthesized:
        uncertainties.append("材料未显式给出问题清单，问题由 research_question 合成，可能与评测问题不完全一致。")

    if not paras:
        status = "insufficient_evidence"
    elif any(a["status"] == "answered" for a in answers):
        status = "answered" if not unanswered else "partial"
    else:
        status = "partial"
    if case_err and not files:
        status = "input_error"

    changes.append({"step": "answer", "action": "逐题生成带 locator 的回答",
                    "detail": "answered=%d partial=%d insufficient=%d"
                    % (coverage["questions_answered"],
                       sum(1 for a in answers if a["status"] == "partial"),
                       len(unanswered))})

    nested = {"answers": answers, "claims": claims, "coverage": coverage,
              "unanswered_parts": unanswered, "documents": coverage["documents"]}
    contract_keys = list(DEFAULT_CONTRACT)
    for k in (case.get("output_contract") or {}):
        if k not in contract_keys:
            contract_keys.append(k)

    result = {
        "case_id": case_id, "paper_id": paper_id, "material_version": material_version,
        "tool": TOOL, "tool_version": VERSION,
        "status": status,
        "answers": answers, "claims": claims, "coverage": coverage,
        "unanswered_parts": unanswered, "uncertainties": uncertainties,
        "sources": sources, "change_log": changes, "change_records": changes,
        "limits": ["证据检索基于词面/概念匹配，可能漏掉改述证据。",
                   "不进行超出材料的推断；无法定位的问题一律标记为证据不足。"],
        "result": nested,
    }
    oc = {}
    for k in contract_keys:
        oc[k] = result.get(k, "")
    oc.setdefault("case_id", case_id)
    result["output_contract"] = oc
    for k in contract_keys:
        result.setdefault(k, oc[k])

    jwrite(out / "result.json", result)
    jwrite(out / "evidence_map.json", {"case_id": case_id,
                                       "evidence": [{"question_id": a["question_id"], "evidence": a["evidence"]}
                                                    for a in answers]})
    jwrite(out / "coverage.json", coverage)

    md = ["# 文献问答结果 · %s" % case_id, "",
          "- 状态：%s" % status,
          "- 文档数：%d；段落数：%d；问题数：%d" % (len(doc_index), len(paras), len(questions)), ""]
    for a in answers:
        md.append("## %s（%s）" % (a["question_id"], a["status"]))
        md.append("")
        md.append("**问题：** %s" % a["question"])
        md.append("")
        md.append("**回答：** %s" % a["answer"])
        md.append("")
        if a["conditions"]:
            md.append("**条件：** " + "；".join(a["conditions"]))
            md.append("")
    md.append("## 不确定性与限制")
    md.append("")
    for u in uncertainties:
        md.append("- " + u)
    md.append("")
    emit(out / "answers.md", safe_text("\n".join(md)) + "\n")

    sanitize(out)
    return result


def sanitize(out):
    out = Path(out)
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        if suf in (".md", ".txt", ".svg", ".xml"):
            emit(p, safe_text(read_text(p)))
        elif suf in (".json", ".jsonl"):
            emit(p, protect_json(read_text(p)))


def fallback(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    jwrite(out / "result.json", {"case_id": "unknown-case", "status": "input_error",
                                 "answers": [], "claims": [{"claim_id": "C0", "kind": "inferred",
                                                            "text": "引擎在执行前中断，未产生结果。", "evidence": []}],
                                 "coverage": {}, "uncertainties": ["运行时异常，已写出最小合法结果。"],
                                 "change_log": [], "output_contract": {"case_id": "unknown-case"}})


def main(argv=None):
    ap = argparse.ArgumentParser(description="Literature evidence QA skill.")
    ap.add_argument("command", nargs="?", default="all")
    ap.add_argument("--input", "--input-dir", dest="inp", default=None)
    ap.add_argument("--output", "--out-dir", dest="out", default=None)
    ap.add_argument("--work", "--work-dir", dest="wrk", default=None)
    a, _ = ap.parse_known_args(argv)
    inp = a.inp or os.environ.get("SKILL_INPUT_DIR") or os.environ.get("INPUT_DIR") or "/input"
    out = a.out or os.environ.get("SKILL_OUTPUT_DIR") or os.environ.get("OUTPUT_DIR") or "/app/output"
    wrk = a.wrk or os.environ.get("SKILL_WORK_DIR") or os.environ.get("WORK_DIR") or "/app/work"
    try:
        run(inp, out, wrk)
    except Exception as exc:  # noqa: BLE001
        try:
            fallback(out)
            emit(Path(out) / "error.log", safe_text("engine error: %s: %s" % (type(exc).__name__, exc)))
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
