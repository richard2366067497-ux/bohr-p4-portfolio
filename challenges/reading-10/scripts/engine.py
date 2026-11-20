#!/usr/bin/env python3
"""engine.py -- reproduction pipeline: input interpretation, index, reported values,
locked tolerance band, candidate discovery, real execution, comparison, attribution,
coverage, verdict, envelope. Rendering lives in build.py. Standard library only.
"""
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core as C  # noqa: E402

SENTINEL = ("case_id", "status", "sources", "uncertainty", "pending_human", "errors",
            "degradations", "changes", "runtime")
TIERS = ("reproduced", "partially_reproduced", "not_reproduced", "insufficient_evidence")
HINT = ("metric", "result", "score", "accura", "f1", "auc", "rmse", "mae", "mse", "r2",
        "error", "corr", "loss", "precision", "recall", "mape", "performance")
DEPFILES = ("requirements.txt", "environment.yml", "environment.yaml", "pipfile", "pyproject.toml",
            "setup.py", "poetry.lock", "meta.yaml", "conda.yaml")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def slug(s, n=30):
    s = re.sub(r"[^0-9A-Za-z_]+", "_", str(s or "")).strip("_")
    return (s or "m")[:n]


def rank(tier):
    return TIERS.index(tier) if tier in TIERS else 9


# ------------------------------------------------------------- input side
def load_case(inp):
    seen = []
    for cand in [inp / "case.json"] + sorted(inp.rglob("case*.json")):
        if cand.is_file() and cand not in seen:
            seen.append(cand)
            obj, err = C.load_json(cand)
            if isinstance(obj, dict):
                return obj, cand, None
            return {}, cand, err or "case_json_not_object"
    return {}, None, "case_json_not_found"


def contract_of(case):
    if not isinstance(case, dict):
        return {}
    for k in ("output_contract", "output_schema", "required_output", "deliverable_contract"):
        v = case.get(k)
        if isinstance(v, (dict, list)) and v:
            return v
    return {}


def case_id_of(case):
    for k in ("case_id", "id", "task_id", "instance_id"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def instruction(case, inp):
    parts = []
    if isinstance(case, dict):
        for k in ("task_instruction", "instruction", "task", "workorder", "organizer_workorder",
                  "scope", "requirements", "question"):
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v)
            elif isinstance(v, (dict, list)):
                parts.append(json.dumps(v, ensure_ascii=False))
    t = inp / "task.md"
    if t.is_file():
        try:
            parts.append(t.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            pass
    return "\n".join(parts)


def scope_flags(text):
    t = (text or "").casefold()
    return {"synthetic_trial": any(k in t for k in ("合成", "synthetic", "not the original author",
                                                    "替代实现", "non-original")),
            "mentions_original_repo": any(k in t for k in ("original repository", "原仓库", "原作者")),
            "text_chars": len(text or "")}


# ------------------------------------------------------------------- index
def build_index(inp, skip=()):
    mats, used = [], set()
    skip = tuple(str(Path(x).resolve()) for x in skip if x)
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name == "case.json" or "__pycache__" in p.parts:
            continue
        if skip and str(p.resolve()).startswith(skip):
            continue
        mid, k = slug(p.stem), 1
        base = mid
        while mid in used:
            k += 1
            mid = "%s%d" % (base, k)
        used.add(mid)
        rec = C.extract_material(p, str(p.relative_to(inp)), mid)
        rec["role"] = "task" if p.name.lower() == "task.md" else "material"
        mats.append(rec)
    return {"root": str(inp), "generated_at": now(), "materials": mats}


def index_of(inp, wrk, out=None):
    idx, _ = C.load_json(wrk / "index.json")
    if not isinstance(idx, dict) or "materials" not in idx:
        idx = build_index(inp, (out, wrk))
        C.dump_json(wrk / "index.json", idx)
    return idx


# --------------------------------------------------- reported and tolerance
def reported_values(case):
    out = {}

    def walk(node, path):
        if isinstance(node, dict):
            low = {str(k).casefold(): k for k in node}
            mk = next((low[k] for k in ("metric", "metric_name", "name", "indicator", "key")
                       if k in low), None)
            vk = next((low[k] for k in ("value", "reported", "expected", "target", "paper",
                                        "reference", "score") if k in low), None)
            if mk and vk:
                val = node[vk]
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    out[str(node[mk])] = {"value": float(val), "ptr": "/".join(path) or "/"}
                elif isinstance(val, str):
                    m = re.fullmatch(r"\s*(" + C.NUM + r")\s*(%|percent)?\s*", val, re.I)
                    if m:
                        v = float(m.group(1))
                        if m.group(2) and abs(v) > 1:
                            v /= 100.0
                        out[str(node[mk])] = {"value": v, "ptr": "/".join(path) or "/"}
            for k, v in node.items():
                walk(v, path + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            j = "/".join(path).casefold()
            if any(t in j for t in ("toler", "budget", "seed", "limit", "timeout", "epoch",
                                    "step", "count", "size", "version")) or \
                    not any(t in j for t in HINT):
                return
            leaf = str(path[-1]).casefold()
            name = str(path[-2]) if len(path) > 1 and (re.fullmatch(C.NUM, leaf) or
                                                      leaf in ("value", "score", "val")) else str(path[-1])
            out.setdefault(name, {"value": float(node), "ptr": "/".join(path)})

    walk(case if isinstance(case, dict) else {}, [])
    for k, v in out.items():
        v["source"] = "case.json#/" + v["ptr"]
        v["locator"] = "case.json#/" + v["ptr"]
        v.setdefault("basis", "case_declared")
    return out


def declared_tolerances(case):
    out = {}

    def walk(node, path):
        if isinstance(node, dict):
            low = {str(k).casefold(): k for k in node}
            ak = next((low[k] for k in ("abs_tol", "abs", "atol", "absolute", "abs_tolerance")
                       if k in low), None)
            rk = next((low[k] for k in ("rel_tol", "rel", "rtol", "relative", "rel_tolerance",
                                        "pct", "percent") if k in low), None)
            mk = next((low[k] for k in ("metric", "metric_name", "name", "indicator") if k in low), None)
            if ak or rk:
                ent = {}
                if ak and isinstance(node[ak], (int, float)) and not isinstance(node[ak], bool):
                    ent["abs_tol"] = float(node[ak])
                if rk and isinstance(node[rk], (int, float)) and not isinstance(node[rk], bool):
                    rel = float(node[rk])
                    ent["rel_tol"] = rel / 100.0 if rel > 1 else rel
                if ent:
                    ent["basis"] = "case_declared"
                    ent["source"] = "case.json#/" + "/".join(path + ([str(mk)] if mk else []))
                    out[str(node[mk]) if mk else "__default__"] = ent
            for k, v in node.items():
                walk(v, path + [str(k)])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])

    walk(case if isinstance(case, dict) else {}, [])
    return out


def tolerance_plan(case, rep):
    decl = declared_tolerances(case)
    entries = {}
    for name, rv in rep.items():
        ent = None
        for k, e in decl.items():
            if k != "__default__" and C.metric_match(k, name)[0]:
                ent = dict(e)
                break
        if ent is None and "__default__" in decl:
            ent = dict(decl["__default__"], basis="case_declared_default")
        if ent is None:
            ent = C.prior_entry(rv.get("value"))
            ent["source"] = "prior_default"
        entries[name] = ent
    default = dict(decl.get("__default__") or C.prior_entry(None))
    default.setdefault("basis", "prior_default")
    entries["__default__"] = default
    plan = {"declared_step": "init", "declared_at": now(), "before_any_run": True,
            "source": "case_declared+prior_default" if decl else "prior_default",
            "entries": entries}
    plan["plan_sha256"] = C.sha256_obj(entries)
    return plan


def tol_for(name, plan, reported):
    entries = (plan or {}).get("entries") or {}
    ent = None
    for k, e in entries.items():
        if k != "__default__" and C.metric_match(k, name)[0]:
            ent = e
            break
    if ent is None:
        ent = entries.get("__default__") or C.prior_entry(reported)
    return C.resolve_tol(ent, reported)


# -------------------------------------------------------------- candidates
def discover(inp, case, draft):
    out = []
    pools = [draft.get("candidates") if isinstance(draft, dict) else None]
    pools += [(case or {}).get(k) for k in ("candidates", "implementations", "methods", "code_variants")]
    for pool in pools:
        for i, e in enumerate(pool if isinstance(pool, list) else []):
            if not isinstance(e, dict) or not (e.get("command") or e.get("path") or e.get("file")
                                               or e.get("entry") or e.get("script")):
                continue
            raw = e.get("path") or e.get("file") or e.get("entry") or e.get("script")
            full = None
            if raw:
                cand = Path(str(raw))
                if cand.is_absolute() and cand.is_file():
                    full = cand
                elif (inp / str(raw)).is_file():
                    full = inp / str(raw)
                else:
                    hits = sorted(inp.rglob(Path(str(raw)).name))
                    full = hits[0] if hits else None
            out.append({"name": str(e.get("name") or e.get("id") or Path(str(raw or "cand")).stem),
                        "path": str(full) if full else None,
                        "rel_path": str(full.relative_to(inp)) if full and inp in full.parents else None,
                        "command": e.get("command"), "declared": True, "score": 9})
    if out:
        return out[:4]
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".py", ".sh", ".r", ".jl"):
            continue
        nm = p.stem.casefold()
        if re.match(r"^(setup|conftest|test_|__|run_all)", nm) or p.name.lower() == "main.py":
            continue
        dirs = [x.casefold() for x in p.relative_to(inp).parts[:-1]]
        s = 0.5
        if any(h in nm for h in ("cand", "method", "impl", "variant", "baseline", "solution",
                                 "model", "approach", "repro")):
            s += 3
        if any(h in d for d in dirs for h in ("candidate", "impl", "code", "src", "method", "repo")):
            s += 2
        if p.suffix.lower() == ".py":
            s += 1
        out.append({"name": p.stem, "path": str(p), "rel_path": str(p.relative_to(inp)),
                    "command": None, "declared": False, "score": s})
    out.sort(key=lambda x: (-x["score"], x["name"]))
    seen, uniq = set(), []
    for c in out:
        if c["name"] not in seen:
            seen.add(c["name"])
            uniq.append(c)
    return uniq[:3]


def env_for(draft, seed):
    env = dict(os.environ)
    env.update({"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
                "OMP_NUM_THREADS": "1", "PYTHONIOENCODING": "utf-8"})
    if seed is not None:
        env["SEED"] = str(seed)
        env["RANDOM_SEED"] = str(seed)
    extra = ((draft.get("environment") or {}).get("env") or {}) if isinstance(draft, dict) else {}
    for k, v in (extra or {}).items():
        env[str(k)] = str(v)
    return env


def _sandbox(rd, inp, out, wrk, cap=120 << 20):
    """Copy the input tree so relative data paths work and the input stays untouched.
    Never copies into itself: output/work may legitimately sit inside the input dir."""
    root = str(inp.resolve())
    skip = tuple({str(d.resolve()) for d in (out, wrk) if str(d.resolve()).startswith(root)})

    def ignore(d, names):
        bad = []
        for n in names:
            full = str(Path(d, n).resolve())
            if n.endswith(".pyc") or n in ("__pycache__", ".git", ".venv", "node_modules") \
                    or (skip and full.startswith(skip)):
                bad.append(n)
        return bad

    if sum(p.stat().st_size for p in inp.rglob("*") if p.is_file()) > cap:
        return None
    try:
        box = rd / "sandbox"
        shutil.copytree(inp, box, ignore=ignore)
        return box
    except Exception:
        return None


def run_one(it, inp, out, wrk, envx, timeout, plan):
    rid = slug(it["name"], 34)
    rd = wrk / "runs" / rid
    shutil.rmtree(rd, ignore_errors=True)
    rd.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": rid, "name": it["name"], "declared": bool(it.get("declared")),
           "started_at": now(), "exit_code": None, "duration_ms": None, "metrics": {},
           "metric_evidence": {}, "error": None,
           "tolerance_plan_sha256": (plan or {}).get("plan_sha256"),
           "plan_written_at": (plan or {}).get("declared_at")}
    src = Path(it["path"]) if it.get("path") else None
    rec["source_file"] = str(src) if src else None
    rec["source_sha1"] = C.sha1_file(src) if src and src.is_file() else None
    cwd = rd
    box = _sandbox(rd, inp, out, wrk)
    if box is None:
        rec["sandbox"] = None
        rec["notes"] = ["ran_in_place:no_readonly_copy"]
        cwd = src.parent if src else rd
    else:
        cwd = (box / it["rel_path"]).parent if it.get("rel_path") else box
        cwd = cwd if cwd.is_dir() else box
        rec["sandbox"] = str(box)
    rec["cwd"] = str(cwd)
    if it.get("command"):
        cmd = it["command"] if isinstance(it["command"], list) else shlex.split(str(it["command"]))
        rec["command_origin"] = "declared"
    elif src and src.suffix.lower() == ".py":
        cmd = [sys.executable, "-B", src.name]
        rec["command_origin"] = "python_file"
    elif src and src.suffix.lower() == ".sh":
        cmd = ["bash", src.name]
        rec["command_origin"] = "shell_file"
    else:
        rec["error"] = "not_executable:%s" % (src.suffix if src else "no_path")
        return rec
    rec["argv"] = [str(c) for c in cmd]
    t = time.time()
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, timeout=timeout,
                           env=envx, text=True, errors="replace")
        rec["duration_ms"] = int((time.time() - t) * 1000)
        rec["exit_code"] = r.returncode
        outtxt, errtxt = r.stdout or "", r.stderr or ""
        C.write_text(rd / "stdout.log", outtxt)
        C.write_text(rd / "stderr.log", errtxt)
        rec["stdout_tail"] = outtxt[-1600:]
        rec["stderr_tail"] = errtxt[-700:]
        rec["metrics"], rec["metric_evidence"] = C.parse_metrics(outtxt)
        rec["stdout_bytes"] = len(outtxt)
        rec["log_path"] = str(out / "runs" / (rid + ".log"))
        body = ("# run %s (%s)\n# argv: %s\n# cwd: %s\n# tolerance_plan_sha256: %s\n"
                "# exit: %s  duration_ms: %s\n\n## stdout\n%s\n\n## stderr\n%s\n") % (
            rid, it["name"], " ".join(rec["argv"]), rec.get("cwd"), rec["tolerance_plan_sha256"],
            r.returncode, rec["duration_ms"], outtxt[-12000:], errtxt[-4000:])
        C.write_text(rd / "run.log", body)
        C.write_text(out / "runs" / (rid + ".log"), body)
    except subprocess.TimeoutExpired:
        rec["error"] = "timeout_%ss" % timeout
        rec["duration_ms"] = int((time.time() - t) * 1000)
    except Exception as exc:
        rec["error"] = "%s:%s" % (type(exc).__name__, str(exc)[:140])
        rec["duration_ms"] = int((time.time() - t) * 1000)
    if rec["exit_code"] not in (0, None) and not rec.get("error"):
        rec["error"] = "exit_%s" % rec["exit_code"]
    return rec


# ---------------------------------------------------- compare and attribute
def auto_reported(names, idx):
    units = C.flat_units(idx)
    out = {}
    for m in idx.get("materials", []):
        if m.get("kind") != "json":
            continue
        obj, _ = C.load_json(m["path"])
        if not isinstance(obj, dict):
            continue
        flat = {}
        C._flatten_num(obj, flat)
        for k, v in flat.items():
            leaf = k.split(".")[-1]
            for name in names:
                if name not in out and C.metric_match(leaf, name)[0]:
                    out[name] = {"value": v, "source": "material_auto:" + m["id"],
                                 "locator": "%s@j/%s" % (m["id"], k.replace(".", "/")),
                                 "quote": "%s: %s" % (leaf, v), "basis": "auto_extract_material"}
    prose = [u for u in units if u["kind"] in ("md", "pdf", "docx", "text", "xlsx", "html")
             and not u["source_id"].casefold().startswith(("method", "impl", "cand"))]
    for name in names:
        if name in out:
            continue
        toks = list(C.ALIAS.get(C.metric_group(name), ())) or [C.nk(name)]
        pat = "|".join(r"(?<![a-z])" + r"\s*".join(map(re.escape, t)) for t in toks if t)
        rx = re.compile("(?i)(?:" + pat + r")\D{0,16}(" + C.NUM + ")", re.I)
        for u in prose:
            if len(u["text"]) > 900 or "def " in u["text"] or "sum(" in u["text"]:
                continue
            m = rx.search(u["text"])
            if not m:
                continue
            val = float(m.group(1))
            if 1990 <= val <= 2035:
                continue
            out[name] = {"value": val, "source": "material_auto:" + u["source_id"],
                         "locator": u["locator"], "quote": C.snip(u["text"], 220),
                         "basis": "auto_extract_text"}
            break
    return out


def compare(runs, rep, plan, names):
    rows = []
    for name in names:
        hit = None
        for k, v in rep.items():
            ok, conf = C.metric_match(k, name)
            if ok and (hit is None or conf > hit[1]):
                hit = (k, conf, v)
        rv = hit[2] if hit else None
        reported = rv.get("value") if rv else None
        tol = tol_for(name, plan, reported)
        for r in runs:
            obs = (r.get("metrics") or {}).get(name)
            if obs is None:
                for mk, mv in (r.get("metrics") or {}).items():
                    if C.metric_match(mk, name)[0]:
                        obs = mv
                        break
            if obs is None:
                continue
            scaled, adj = float(obs), None
            if reported is not None:
                sn = C.scale_note(scaled, reported)
                if sn:
                    scaled, adj = scaled * sn["factor"], sn
            c = C.compare_values(scaled, reported, tol["abs_tol"], tol["rel_tol"]) \
                if reported is not None else {"within_tolerance": None, "abs_dev": None, "rel_dev": None}
            rows.append({
                "metric": name, "run": r["run_id"], "method": r["name"],
                "observed": round(scaled, 10), "observed_raw": obs, "reported": reported,
                "abs_tol": None if tol["abs_tol"] is None else round(tol["abs_tol"], 12),
                "rel_tol": tol["rel_tol"], "tolerance_basis": tol.get("basis"),
                "abs_dev": c.get("abs_dev"), "rel_dev": c.get("rel_dev"),
                "within_tolerance": c.get("within_tolerance"),
                "verdict": {True: "in_tolerance", False: "out_of_tolerance"}.get(
                    c.get("within_tolerance"), "no_reported_value"),
                "reported_source": (rv or {}).get("source"),
                "reported_locator": (rv or {}).get("locator") or (rv or {}).get("ptr"),
                "reported_quote": (rv or {}).get("quote"),
                "reported_basis": (rv or {}).get("basis", "case_declared"),
                "scale_adjusted": adj,
                "metric_evidence": (r.get("metric_evidence") or {}).get(name),
                "run_log": r.get("log_path")})
    return rows


def attribute(rows, params, cov, runs):
    out, by = [], {}
    for r in rows:
        by.setdefault(r["metric"], []).append(r)
    for metric, rs in by.items():
        rv = next((r["reported"] for r in rs if r["reported"] is not None), None)
        ids = [r["run"] for r in rs]
        obs = [(r["observed"], r["run"]) for r in rs]
        if rv is None:
            out.append({"metric": metric, "cause": "paper_value_unavailable", "confidence": "determined",
                        "evidence": {"runs": ids}, "detail": "no reported value in case or materials"})
            continue
        bad = [r for r in rs if r["within_tolerance"] is False]
        if not bad:
            out.append({"metric": metric, "cause": "none", "confidence": "determined",
                        "evidence": {"runs": ids, "max_rel_dev": max([r["rel_dev"] or 0 for r in rs] or [0])},
                        "detail": "every observation sits inside the pre-declared band"})
            continue
        rt = max([r["rel_tol"] or 0.02 for r in rs] + [0.02])
        spread = (max(o for o, _ in obs) - min(o for o, _ in obs)) if len(obs) > 1 else 0.0
        if any(r.get("scale_adjusted") for r in rs):
            out.append({"metric": metric, "cause": "scale_mismatch", "confidence": "inferred",
                        "evidence": {"runs": ids, "note": "ratio near 1:100"},
                        "detail": "observed/reported differ by ~100x -> percent vs fraction convention"})
        elif len(obs) > 1 and spread <= abs(rv) * rt:
            out.append({"metric": metric, "cause": "shared_upstream", "confidence": "inferred",
                        "evidence": {"runs": ids, "spread": round(spread, 10), "reported": rv},
                        "detail": "both methods agree (spread %.3g <= band) yet both miss %.6g -> data "
                                  "version/split, preprocessing or restored params, not code"
                                  % (spread, rv)})
        elif len(obs) > 1:
            out.append({"metric": metric, "cause": "implementation_divergence", "confidence": "inferred",
                        "evidence": {"runs": ids, "spread": round(spread, 10)},
                        "detail": "methods disagree by %.3g (> band) -> metric code, default "
                                  "hyper-parameters or randomness" % spread})
        else:
            out.append({"metric": metric, "cause": "single_method_only", "confidence": "inferred",
                        "evidence": {"runs": ids},
                        "detail": "only one method produced a number; code vs upstream inseparable"})
    soft = [p.get("name") for p in params if p.get("class") in ("self_set", "chosen", "code_inferred")]
    if soft:
        out.append({"metric": "*", "cause": "parameter_restoration", "confidence": "inferred",
                    "evidence": {"params": soft[:8]},
                    "detail": "%d parameter(s) not stated verbatim by the paper: %s"
                              % (len(soft), ", ".join(map(str, soft[:6])))})
    lost = [r for r in runs if r.get("exit_code") not in (0,)]
    if lost:
        out.append({"metric": "*", "cause": "run_failed", "confidence": "determined",
                    "evidence": {"runs": [r["run_id"] for r in lost],
                                 "errors": [r.get("error") for r in lost]},
                    "detail": "a candidate did not finish cleanly; that run supports no agreement claim"})
    for cls, st in (cov or {}).items():
        if st.get("status") == "missing":
            out.append({"metric": "*", "cause": "material_missing", "confidence": "determined",
                        "evidence": {"object": cls}, "detail": "no %s object located in the input" % cls})
    return out


def coverage(idx, draft):
    cls = {k: [] for k in ("code", "data", "param", "dependency", "license", "eval_script")}
    req = {k: [] for k in cls}
    for m in idx.get("materials", []):
        name = Path(m["rel"]).name.casefold()
        rel = m["rel"].casefold()
        if name.startswith(("license", "licence", "copying")):
            cls["license"].append(m["id"])
        if name in DEPFILES:
            cls["dependency"].append(m["id"])
        if name.startswith(("eval", "metric", "score", "bench")) or "evaluat" in name:
            cls["eval_script"].append(m["id"])
        if m.get("kind") in ("csv", "tsv") or (m.get("kind") == "json" and m.get("units")):
            cls["data"].append(m["id"])
        if rel.endswith((".py", ".r", ".jl", ".sh")):
            cls["code"].append(m["id"])
        if m.get("kind") in ("pdf", "md", "docx", "text", "xlsx"):
            txt = " ".join(t for _, t in (m.get("units") or [])[:60]).casefold()
            if ("def " in txt or "import " in txt) and m["id"] not in cls["code"]:
                cls["code"].append(m["id"])
            if any(k in txt for k in ("hyperparameter", "learning rate", "超参", "参数设置",
                                      "configuration", "table")):
                cls["param"].append(m["id"])
    for item in (draft.get("checklist") or []) if isinstance(draft, dict) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        kind = str(item.get("kind") or "").casefold()
        for c in cls:
            if c in kind or (c == "eval_script" and "eval" in kind):
                bucket = cls[c] if item.get("status") == "available" else req[c]
                if str(item["id"]) not in bucket:
                    bucket.append(str(item["id"]))
    return {c: {"found": len(set(v)), "objects": sorted(set(v)),
                "requested": sorted(set(req[c])),
                "status": "available" if set(v) else ("needs_request" if req[c] else "missing")}
            for c, v in cls.items()}


def verdict_for(rows, runs, cov, scope, draft):
    graded = [r for r in rows if r["within_tolerance"] is not None]
    good = [r for r in graded if r["within_tolerance"]]
    if not runs or not graded:
        tier, why = "insufficient_evidence", "no candidate produced a number comparable to a reported value"
    elif len(good) == len(graded):
        tier, why = "reproduced", "all %d comparable observations inside the pre-declared band" % len(graded)
    elif good:
        tier, why = "partially_reproduced", "%d/%d observations inside the band; the rest are attributed" % (
            len(good), len(graded))
    else:
        tier, why = "not_reproduced", "all %d observations outside the band" % len(graded)
    missing = sorted([k for k, v in (cov or {}).items() if v.get("status") != "available"])
    caps = []
    if tier == "reproduced":
        if missing:
            caps.append("missing_materials:" + ",".join(missing))
        if scope.get("synthetic_trial"):
            caps.append("synthetic_trial_scope")
        if caps:
            tier = "partially_reproduced"
            why += " | capped: " + "; ".join(caps)
    agent = (draft.get("verdict") or {}) if isinstance(draft, dict) else {}
    atier = agent.get("tier") or agent.get("verdict")
    conflict = None
    if atier in TIERS:
        if rank(atier) < rank(tier):
            conflict = "agent=%s looser than computed=%s; computed kept" % (atier, tier)
        elif rank(atier) > rank(tier):
            tier = atier
            why += " | tightened by agent: " + str(agent.get("rationale") or "")[:200]
    return {"tier": tier, "rationale": why, "caps": caps, "missing_objects": missing,
            "agent_tier": atier, "verdict_conflict": conflict,
            "rule": "all in band=reproduced; some=partially_reproduced; none=not_reproduced; nothing "
                    "run or nothing reported=insufficient_evidence; missing materials or a synthetic "
                    "trial cap a would-be 'reproduced' at 'partially_reproduced'"}


# ------------------------------------------------------------- envelope
def emit(out, res):
    for k in SENTINEL:
        res.setdefault(k, None if k in ("case_id", "status", "runtime") else [])
    base = res.get("runtime") or {}
    res["runtime"] = dict(base, **{"finished_at": now(),
                                   "python": platform.python_version(),
                                   "platform": platform.platform()})
    C.dump_json(out / "result.json", res, indent=2)
    return res


def shell(case, cid, status="partial", t0=None):
    con = contract_of(case)
    un = []
    base = {"case_id": cid, "status": status, "summary": "", "sources": [], "uncertainty": [],
            "pending_human": [], "errors": [], "degradations": [], "changes": [],
            "runtime": {"started_at": now() if t0 is None else t0}}
    if con:
        filled = C.echo_contract(con, {}, un)
        if isinstance(filled, dict):
            base = dict(filled, **base)
        else:
            base["_contract_shape"] = filled
    if un:
        base["degradations"] = sorted(set(base["degradations"]) |
                                      {"contract_field_unmapped:" + ",".join(sorted(set(un)))})
    return base
