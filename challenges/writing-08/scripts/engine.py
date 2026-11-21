"""engine.py — corpus ledger + bilingual section rendering.

Part 1 (ledger): material inventory, candidate extraction, verbatim quote
verification and three-source agreement. Deterministic only; every "is this
relevant / which element / is it trustworthy / is it comparable" judgement is
left to the Agent's draft.json.

Part 2 (render): turn the work draft into the section manuscript, the fact /
parameter / evidence ledgers, the gap and conflict lists and the coverage
summary. Rendering is deterministic and language-aware (zh / en): the draft
language decides the headings, labels and boilerplate, so an English case gets an
English manuscript.

Pure standard library, offline, no CWD dependency.
"""

import csv
import hashlib
import io
import json
import os
import re

MAX_FILE_BYTES = 400 * 1024
MAX_CANDIDATES = 500
MAX_PER_FILE = 70

TEXT_EXT = {
    ".yaml": "config", ".yml": "config", ".json": "config", ".toml": "config",
    ".ini": "config", ".cfg": "config", ".conf": "config", ".env": "config",
    ".log": "log", ".out": "log", ".err": "log", ".txt": "note",
    ".py": "code", ".sh": "code", ".ipynb": "code", ".js": "code", ".r": "code",
    ".md": "doc", ".rst": "doc", ".tex": "paper",
    ".csv": "table", ".tsv": "table",
}

KEY_CANON = {
    "lr": "learning_rate", "learning_rate": "learning_rate", "learningrate": "learning_rate",
    "init_lr": "learning_rate", "base_lr": "learning_rate", "peak_lr": "learning_rate",
    "bs": "batch_size", "batch": "batch_size", "batch_size": "batch_size",
    "train_batch_size": "batch_size", "micro_batch_size": "batch_size",
    "epoch": "epochs", "epochs": "epochs", "num_epochs": "epochs", "n_epochs": "epochs",
    "max_epochs": "epochs", "num_train_epochs": "epochs",
    "wd": "weight_decay", "weight_decay": "weight_decay",
    "warmup": "warmup", "warmup_ratio": "warmup", "warmup_steps": "warmup",
    "seed": "seed", "random_seed": "seed", "random_state": "seed",
    "manual_seed": "seed", "torch_seed": "seed", "global_seed": "seed",
    "optimizer": "optimizer", "optim": "optimizer", "optimizer_type": "optimizer",
    "scheduler": "scheduler", "lr_scheduler": "scheduler",
    "dataset": "dataset", "dataset_name": "dataset", "data": "dataset",
    "data_name": "dataset", "corpus": "dataset",
    "version": "dataset_version", "dataset_version": "dataset_version",
    "data_version": "dataset_version", "data_rev": "dataset_version",
    "split": "split", "split_ratio": "split", "splits": "split",
    "train_ratio": "split", "val_ratio": "split", "test_ratio": "split",
    "val_ratio_dev": "split", "eval_ratio": "split",
    "device": "device", "gpu": "device", "gpus": "device", "cuda": "device",
    "gpu_type": "device", "hardware": "device", "n_gpu": "device",
    "precision": "precision", "dtype": "precision", "amp": "precision",
    "torch": "torch_version", "torch_version": "torch_version",
    "pytorch": "torch_version", "python": "python_version",
    "python_version": "python_version",
    "commit": "code_commit", "git_commit": "code_commit", "revision": "code_commit",
    "sha": "code_commit", "code_version": "code_commit",
    "image": "container_image", "docker_image": "container_image",
    "metric": "metric", "metrics": "metric", "eval_metric": "metric",
    "baseline": "baseline", "baselines": "baseline", "baseline_name": "baseline",
    "repeat": "repeats", "repeats": "repeats", "n_runs": "repeats",
    "runs": "repeats", "num_repeats": "repeats", "n_seeds": "repeats",
    "num_layers": "num_layers", "n_layers": "num_layers", "layers": "num_layers",
    "hidden_dim": "hidden_dim", "hidden_size": "hidden_dim", "d_model": "hidden_dim",
    "dropout": "dropout", "dropout_rate": "dropout",
    "heads": "num_heads", "num_heads": "num_heads", "n_heads": "num_heads",
    "max_tokens": "max_tokens", "max_length": "max_tokens",
    "max_seq_len": "max_tokens", "seq_len": "max_tokens",
    "temperature": "temperature", "top_p": "top_p",
    "num_workers": "num_workers", "workers": "num_workers",
    "model": "model", "model_name": "model", "arch": "model",
}

PRIORITY_KEYS = [
    "dataset", "dataset_version", "split", "learning_rate", "batch_size", "epochs",
    "optimizer", "weight_decay", "scheduler", "warmup", "seed", "repeats",
    "device", "precision", "torch_version", "python_version", "code_commit",
    "container_image", "metric", "baseline", "model", "num_layers", "hidden_dim",
    "dropout", "num_heads", "max_tokens", "temperature", "top_p", "num_workers",
]

UNIT_PAT = re.compile(
    r"^(.*?)(?:\s*)(s|ms|us|min|h|hours?|epochs?|steps?|it(?:erations?)?|"
    r"GiB|GB|MiB|MB|TFLOPs?|GFLOPS|Mbps|%)$", re.I)

KV_LINE = re.compile(
    r"^\s*(?:[-*]\s+)?[\"']?([A-Za-z_][A-Za-z0-9_.\-]{0,48})[\"']?\s*[:=]\s*(.+?)\s*$")
KV_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_.\-]{1,40})=(?:\"([^\"]{0,80})\"|([^\s,;)\]]{1,80}))")
BARE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
SENTENCE_HINT = re.compile(
    r"(dataset|version|split|seed|epoch|batch|learning rate|baseline|metric|"
    r"GPU|CUDA|commit|reproduc|数据|划分|版本|随机|重复|基线|指标|复现|轮数|学习率)",
    re.I)

def read_text(path):
    """Best-effort text read; binary or oversized returns (None, reason)."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return None, "stat_failed:%s" % exc.__class__.__name__
    if size > MAX_FILE_BYTES:
        try:
            with open(path, "rb") as fh:
                raw = fh.read(MAX_FILE_BYTES)
        except OSError as exc:
            return None, "read_failed:%s" % exc.__class__.__name__
        note = "truncated_at_%d" % MAX_FILE_BYTES
    else:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            return None, "read_failed:%s" % exc.__class__.__name__
        note = ""
    if b"\x00" in raw[:4096]:
        return None, "binary"
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            return text, note
        except UnicodeDecodeError:
            continue
    return None, "undecodable"

def classify(rel, text):
    ext = os.path.splitext(rel)[1].lower()
    kind = TEXT_EXT.get(ext)
    if kind:
        return kind
    if text is None:
        return "unreadable"
    head = text[:4000]
    ts = len(re.findall(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", head))
    kv = len(KV_LINE.findall(head))
    if ts >= 3:
        return "log"
    if kv >= 4:
        return "config"
    if re.search(r"(def |import |class )", head):
        return "code"
    return "doc"

def scan(input_dir):
    """Walk the material directory; return (materials, unreadable)."""
    materials, unreadable = [], []
    if not os.path.isdir(input_dir):
        return materials, unreadable
    for root, dirs, files in os.walk(input_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            if name.startswith("."):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, input_dir)
            if rel.replace(os.sep, "/") in ("case.json", "task.md", "challenge.json"):
                continue
            if os.path.islink(path):
                continue
            text, note = read_text(path)
            kind = classify(rel, text)
            entry = {
                "source_id": "",
                "rel": rel.replace(os.sep, "/"),
                "path": path,
                "kind": kind,
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
                "lines": (text.count("\n") + 1) if text else 0,
                "readable": text is not None,
                "note": note,
                "sha1": hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()[:12],
            }
            if text is None:
                unreadable.append(entry)
                materials.append(entry)
                continue
            materials.append(entry)
    for i, m in enumerate(materials, 1):
        m["source_id"] = "S%d" % i
    return materials, unreadable

def canon_key(raw):
    k = re.sub(r"[^a-z0-9_]", "_", str(raw).strip().lower())
    k = re.sub(r"_+", "_", k).strip("_")
    tail = k.split(".")[-1]
    return KEY_CANON.get(k) or KEY_CANON.get(tail) or k

def split_value_unit(value):
    v = (value or "").strip().strip("\"'").rstrip(",;:")
    v = re.sub(r"\s+#.*$", "", v).strip()
    while v.endswith(")") and v.count("(") < v.count(")"):
        v = v[:-1].rstrip(",;")
    m = UNIT_PAT.match(v)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2)
    return v, ""

def norm_value(value):
    """Numeric/string normalisation for three-source comparison only."""
    v = (value or "").strip().strip("\"'").lower()
    v = v.rstrip(",;")
    v = v.replace("_", "")
    try:
        return "num:%.10g" % float(v)
    except (TypeError, ValueError):
        return "str:" + re.sub(r"\s+", " ", v)

def _candidates_from_json(text, rel):
    out = []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return out
    stack = [(k, data[k]) for k in data] if isinstance(data, dict) else []
    while stack and len(out) < MAX_PER_FILE:
        key, val = stack.pop(0)
        if isinstance(val, dict):
            for k2 in list(val)[:40]:
                stack.append(("%s.%s" % (key, k2), val[k2]))
        elif isinstance(val, list):
            if len(val) <= 6:
                out.append((key, json.dumps(val, ensure_ascii=False)))
        else:
            out.append((key, str(val)))
    return out

def extract_candidates(materials, input_dir):
    """Extract candidate elements; each carries source_id + locator + verbatim quote."""
    cands = []
    for m in materials:
        if not m.get("readable"):
            continue
        text, _ = read_text(m["path"])
        if text is None:
            continue
        rel = m["rel"]
        rows = []
        if rel.endswith(".json"):
            for key, val in _candidates_from_json(text, rel):
                rows.append((key, val, None, "%s: %s" % (key, val)))
        for idx, line in enumerate(text.splitlines(), 1):
            if len(cands) + len(rows) >= MAX_CANDIDATES or len(rows) >= MAX_PER_FILE:
                break
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*", ">")):
                continue
            pairs = KV_PAIR.findall(stripped)
            if m["kind"] in ("log", "code") and len(pairs) >= 2:
                for raw_k, q_v, b_v in pairs:
                    rows.append((raw_k, q_v or b_v, idx, stripped))
                continue
            mm = KV_LINE.match(stripped)
            if mm and len(mm.group(2)) <= 160:
                rows.append((mm.group(1), mm.group(2), idx, stripped))
                continue
            if SENTENCE_HINT.search(stripped) and re.search(r"\d", stripped):
                rows.append(("", stripped, idx, stripped))
        seen = set()
        for raw_k, val, line_no, quote in rows:
            value, unit = split_value_unit(val)
            if m["kind"] == "code" and BARE_IDENT.match(value or "") \
                    and value.lower() not in ("true", "false", "none", "null"):
                continue
            key = canon_key(raw_k) if raw_k else ""
            if m["kind"] == "log" and str(raw_k).strip().lower() in ("epoch", "epochs", "step"):
                key = "epoch_index"
            sig = (key, norm_value(value), line_no if line_no is not None else quote[:40])
            if sig in seen:
                continue
            seen.add(sig)
            if line_no is None:
                loc = "%s#json:%s" % (rel, raw_k)
                line_no = _find_line(text, quote)
                if line_no:
                    loc = "%s#L%d" % (rel, line_no)
            else:
                loc = "%s#L%d" % (rel, line_no)
            cands.append({
                "key": key,
                "raw_key": raw_k or "(sentence)",
                "value": value,
                "unit": unit,
                "norm": norm_value(value),
                "quote": quote.strip()[:300],
                "source_id": m["source_id"],
                "file": rel,
                "locator": loc,
                "line": line_no,
                "kind": m["kind"],
                "priority": 0 if key in PRIORITY_KEYS else 1,
            })
            if len(cands) >= MAX_CANDIDATES:
                return cands
    return cands

def _find_line(text, needle):
    needle = (needle or "").strip()
    if not needle:
        return None
    for i, line in enumerate(text.splitlines(), 1):
        if needle[:60] in line:
            return i
    return None

def _norm_ws(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def verify_quote(path, quote):
    """Verbatim check: the whitespace-normalised quote must occur in the file."""
    if not quote:
        return False, None, "empty_quote"
    text, note = read_text(path)
    if text is None:
        return False, None, "source_unreadable:%s" % note
    if _norm_ws(quote) in _norm_ws(text):
        return True, _find_line(text, quote), "verbatim"
    return False, None, "quote_not_found"

def three_source(cands):
    """Group by canonical key, compare values across sources: conflicts + agreement."""
    groups = {}
    for c in cands:
        if not c["key"]:
            continue
        groups.setdefault(c["key"], []).append(c)
    out = []
    for key, items in groups.items():
        distinct = {}
        for c in items:
            distinct.setdefault(c["norm"], []).append(c)
        srcs = {c["source_id"] for c in items}
        entry = {
            "key": key,
            "num_sources": len(srcs),
            "distinct_values": len(distinct),
            "values": [
                {
                    "value": vals[0]["value"],
                    "unit": vals[0]["unit"],
                    "sources": [
                        {"source_id": v["source_id"], "file": v["file"],
                         "locator": v["locator"], "kind": v["kind"],
                         "quote": v["quote"][:160]}
                        for v in vals[:4]
                    ],
                }
                for vals in distinct.values()
            ],
            "status": "conflict" if len(distinct) > 1 and len(srcs) > 1
                      else ("agree" if len(distinct) == 1 and len(srcs) > 1 else "single"),
        }
        if entry["status"] == "conflict":
            entry["severity"] = "high" if key in PRIORITY_KEYS else "low"
        out.append(entry)
    out.sort(key=lambda e: (0 if e["status"] == "conflict" and e.get("severity") == "high" else
                            1 if e["status"] == "conflict" else 2,
                            PRIORITY_KEYS.index(e["key"]) if e["key"] in PRIORITY_KEYS else 99))
    return out

def excerpt(material, max_lines=12):
    text, _ = read_text(material["path"])
    if text is None:
        return ["[unreadable: %s]" % material.get("note", "")]
    lines = [ln for ln in text.splitlines() if ln.strip()][:max_lines]
    return ["%s#L%d | %s" % (material["rel"], i + 1, ln.strip()[:200])
            for i, ln in enumerate(lines)]

SECTIONS = {
    "zh": [
        ("scope", "1 任务与范围"),
        ("data", "2 数据与预处理"),
        ("steps", "3 方法步骤"),
        ("settings", "4 实验设置"),
        ("params", "5 参数与来源"),
        ("baseline", "6 基线对照与可比性"),
        ("metric", "7 评价指标与统计方式"),
        ("repro", "8 复现清单"),
        ("limits", "9 限制条件与失效场景"),
        ("gaps", "10 缺口与待作者确认项"),
    ],
    "en": [
        ("scope", "1 Task and scope"),
        ("data", "2 Data and preprocessing"),
        ("steps", "3 Method steps"),
        ("settings", "4 Experimental setup"),
        ("params", "5 Parameters and provenance"),
        ("baseline", "6 Baselines and comparability"),
        ("metric", "7 Metrics and statistics"),
        ("repro", "8 Reproduction checklist"),
        ("limits", "9 Limitations and failure cases"),
        ("gaps", "10 Open items for the author"),
    ],
}

ELEMENTS = {
    "zh": [
        ("steps", "方法步骤"),
        ("settings", "实验设置（训练/验证/评测、硬件、环境、种子、重复）"),
        ("parameters", "参数与取值"),
        ("datasets", "数据集与划分"),
        ("baselines", "基线与比较条件"),
        ("repro_limits", "复现清单与限制条件"),
    ],
    "en": [
        ("steps", "Method steps"),
        ("settings", "Experimental setup (train/val/test, hardware, environment, seeds, repeats)"),
        ("parameters", "Parameters and values"),
        ("datasets", "Datasets and splits"),
        ("baselines", "Baselines and comparison conditions"),
        ("repro_limits", "Reproduction checklist and limitations"),
    ],
}

ELEMENT_KEYS = {
    "steps": ["steps"],
    "settings": ["settings"],
    "parameters": ["parameters"],
    "datasets": ["datasets"],
    "baselines": ["baselines"],
    "repro_limits": ["repro", "limitations"],
}

GAP_PH = "〔待补：%s〕"
GAP_PH_EN = "[needs input: %s]"

T = {
    "zh": {
        "title": "方法与实验",
        "case": "- 案例：`%s`",
        "sources": "- 证据来源编号：%s（逐条定位见 `fact_ledger.csv`）",
        "convention": "- 标注约定：数字后 `[S#]` 指向来源编号；`%s` 表示材料未给出、需作者确认。",
        "field": "字段",
        "scope_fallback": "本章覆盖方法与实验设置，写作约束%s。",
        "genre": "体裁", "audience": "受众", "language": "语言", "scope": "范围",
        "structure": "结构要求", "note": "说明",
        "data_none": "数据集名称、版本、规模与划分%s，本稿不推测；该要素缺失会使复现不可行。",
        "version": "版本", "size": "规模", "preprocess": "预处理", "split_l": "划分",
        "usage": "用途", "dataset_name": "数据集名称",
        "dataset_tbl": "| 数据集 | 版本 | 规模 | 划分 | 用途 | 来源 |",
        "steps_none": "材料未提供可排序的操作记录，操作序列%s（缺失使他人无法按步骤复做）。",
        "step": "步骤", "inputs": "输入", "operation": "操作", "params": "参数",
        "output": "输出", "branch": "分支/判断",
        "settings_none": "训练、验证与评测流程未分开记录，硬件、软件版本、随机种子与重复次数%s；条件串台会使结果不可复现。",
        "other": "其他设置",
        "params_none": "参数表%s：材料中未出现可引用的参数取值。",
        "param_tbl": "| 参数 | 取值 | 单位 | 作用对象 | 来源 | 状态 |",
        "param_name": "参数名", "value": "取值", "taken_from": "取自材料",
        "conflict_state": "冲突待确认", "conflict_head": "### 材料间不一致（未统一，交作者确认）",
        "conflict_line": "- `%s`：%s；结论：材料间不一致，需作者确认%s。",
        "conflict_plain": "多来源取值不同",
        "baseline_none": "基线对象、版本与对照条件%s；缺此要素时“与基线比较”只能是断言而非结论。",
        "baseline_tbl": "| 基线 | 版本 | 同预算 | 指标口径 | 统计方式 | 可比性 | 来源 |",
        "baseline_name": "基线名称", "budget": "同预算", "comparable": "可比",
        "not_comparable": "不可直接比较", "to_confirm": "待确认",
        "baseline_warn": "上述基线与本方法在预算、指标口径或统计方式上不一致，因此不给出“相对基线的性能优势”一类断言；如需比较，先对齐条件（同预算、同指标、同重复次数）。",
        "metric_none": "评价指标与统计方式（重复次数、聚合方式、显著性）%s。",
        "metric_desc": "指标说明",
        "metric_from_baseline": "- %s：指标口径 %s；统计方式 %s%s",
        "repro_none": "复现清单（代码版本、环境、种子、命令、数据获取方式）%s。",
        "repro_missing": "- 复现清单缺项：%s。",
        "repro_item": "项目",
        "limits_none": "限制条件%s：需写清“当 X 时不适用，因为材料中 Y”，不接受笼统表述。",
        "limit_scope": "适用范围", "limit_fail": "失效场景", "limit_reason": "材料依据",
        "gaps_none": "本轮未登记缺口；若上文章节出现 `%s` 标记，说明缺口登记缺失，需补登。",
        "gap_tbl": "| 缺口 | 类型 | 描述 | 影响 | 需谁确认 | 涉及小节 |",
        "section_confirm": "本节待确认：",
        "pending": "缺口",
        "gaps_title": "# 缺口与待作者确认清单",
        "gaps_none2": "本轮工作稿未登记缺口。若章节中出现 `%s` 标记，请补登对应条目。",
        "what_missing": "- 缺什么：%s", "impact": "- 影响：%s",
        "who": "- 需谁确认：%s", "which": "- 涉及小节：%s",
        "ask": "- 追问：%s", "ask_default": "（请作者提供上述材料的准确取值/来源）",
        "auto_unreadable": "## 自动检测：不可读材料",
        "conflicts_title": "# 材料间冲突登记表（并列保留，不做静默统一）",
        "conflicts_none": "工作稿未登记冲突项。",
        "src": "来源", "locator": "定位", "val": "取值",
        "impact_default": "正文数值不确定，需作者裁决",
        "disposal": "- 处置：%s",
        "disposal_default": "待作者裁决（正文并列标注，不择一取整）",
        "detected_head": "## 自动检测到的疑似冲突（供核对，未必全部成立）",
    },
    "en": {
        "title": "Methods and Experiments",
        "case": "- Case: `%s`",
        "sources": "- Evidence source ids: %s (per-item locators in `fact_ledger.csv`)",
        "convention": "- Conventions: a number followed by `[S#]` points at a source id; `%s` means the material does not state it and the author must confirm.",
        "field": "field",
        "scope_fallback": "This chapter covers the method and the experimental setup; the writing constraints are %s.",
        "genre": "Genre", "audience": "Audience", "language": "Language", "scope": "Scope",
        "structure": "Required structure", "note": "Notes",
        "data_none": "Dataset name, version, size and split are %s; this draft does not guess. Without them the work cannot be reproduced.",
        "version": "version", "size": "size", "preprocess": "preprocessing", "split_l": "split",
        "usage": "usage", "dataset_name": "dataset",
        "dataset_tbl": "| Dataset | Version | Size | Split | Use | Source |",
        "steps_none": "The material provides no orderable operation record, so the step sequence is %s (without it nobody can redo the work step by step).",
        "step": "Step", "inputs": "inputs", "operation": "operation", "params": "params",
        "output": "output", "branch": "branch/decision",
        "settings_none": "Training, validation and test procedures are not recorded separately; hardware, software versions, random seeds and repeat counts are %s. Mixed conditions make results irreproducible.",
        "other": "Other settings",
        "params_none": "Parameter table is %s: the material contains no citable parameter value.",
        "param_tbl": "| Parameter | Value | Unit | Applies to | Source | Status |",
        "param_name": "parameter", "value": "value", "taken_from": "from material",
        "conflict_state": "conflict, to confirm", "conflict_head": "### Inconsistencies across materials (not unified; for the author)",
        "conflict_line": "- `%s`: %s; verdict: the materials disagree and the author must confirm%s.",
        "conflict_plain": "values differ across sources",
        "baseline_none": "Baseline objects, versions and comparison conditions are %s; without them \"better than baseline\" is an assertion, not a result.",
        "baseline_tbl": "| Baseline | Version | Same budget | Metric | Statistics | Comparable | Source |",
        "baseline_name": "baseline", "budget": "same budget", "comparable": "comparable",
        "not_comparable": "not directly comparable", "to_confirm": "to confirm",
        "baseline_warn": "The baselines above differ from this method in budget, metric or statistics, so no \"performance advantage over baseline\" claim is made; align the conditions first (same budget, same metric, same repeats).",
        "metric_none": "Metrics and statistics (repeat count, aggregation, significance) are %s.",
        "metric_desc": "metric note",
        "metric_from_baseline": "- %s: metric %s; statistics %s%s",
        "repro_none": "Reproduction checklist (code version, environment, seed, command, data access) is %s.",
        "repro_missing": "- Missing checklist items: %s.",
        "repro_item": "item",
        "limits_none": "Limitations are %s: state plainly \"when X it does not hold, because the material shows Y\" instead of generic wording.",
        "limit_scope": "scope", "limit_fail": "failure case", "limit_reason": "material basis",
        "gaps_none": "No gap was registered this round; if `%s` markers appear above, the gap list is incomplete and must be extended.",
        "gap_tbl": "| Gap | Type | Description | Impact | Owner | Section |",
        "section_confirm": "Open in this section: ",
        "pending": "Gaps",
        "gaps_title": "# Gaps and items for the author",
        "gaps_none2": "The draft registered no gap. If `%s` markers appear in the manuscript, register the matching items.",
        "what_missing": "- Missing: %s", "impact": "- Impact: %s",
        "who": "- Owner: %s", "which": "- Section: %s",
        "ask": "- Follow-up: %s", "ask_default": "(please supply the exact value/source for the items above)",
        "auto_unreadable": "## Auto-detected: unreadable materials",
        "conflicts_title": "# Cross-material conflict register (kept side by side, never silently unified)",
        "conflicts_none": "The draft registered no conflict.",
        "src": "Source", "locator": "Locator", "val": "Value",
        "impact_default": "the value in the text is uncertain and needs an author decision",
        "disposal": "- Disposition: %s",
        "disposal_default": "awaiting an author decision (kept side by side, no silent choice)",
        "detected_head": "## Auto-detected candidate conflicts (for review, not all necessarily real)",
    },
}

def _lang_of(draft, meta=None):
    meta = meta or {}
    for src in (draft.get("language") if isinstance(draft, dict) else None,
                (draft.get("task_understanding") or {}).get("language") if isinstance(draft, dict) else None,
                meta.get("language")):
        if src in ("zh", "en"):
            return src
    return "zh"

def _list(draft, key):
    val = draft.get(key)
    if isinstance(val, list):
        return [v for v in val if isinstance(v, dict) or isinstance(v, str)]
    return []

def _text(val, default=""):
    if val is None:
        return default
    if isinstance(val, (list, tuple)):
        return "；".join(str(v) for v in val if v not in (None, "")) or default
    return str(val).strip() or default

def cite(source_ids):
    ids = []
    for s in source_ids or []:
        s = str(s).strip()
        if s and s not in ids:
            ids.append(s)
    return "".join(" [%s]" % s for s in ids)

def cite_cell(source_ids):
    return cite(source_ids).strip() or "—"

def _sids(item):
    out = []
    for key in ("source_ids", "source_id", "sources"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            out.extend([p for p in val.replace(",", " ").split() if p])
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                elif isinstance(v, dict) and v.get("source_id"):
                    out.append(str(v["source_id"]))
    return out

def _field(item, key, label, ph=GAP_PH):
    val = _text(item.get(key))
    return val if val else ph % label

def _gaps(draft, section=None):
    out = []
    for g in _list(draft, "gaps"):
        if isinstance(g, dict):
            if section is None or _text(g.get("section")).lower().find(section) >= 0:
                out.append(g)
    return out

def _gap_lines(draft, section, t):
    picked = _gaps(draft, section)
    if not picked:
        return []
    return ["", "> " + t["section_confirm"] + "；".join(
        "%s %s" % (_text(g.get("gid"), "G?"), _text(g.get("desc"), "")) for g in picked)]

def _conflict_map(draft):
    out = {}
    for c in _list(draft, "conflicts"):
        if not isinstance(c, dict):
            continue
        item = _text(c.get("item") or c.get("name")).lower()
        if item:
            out[item] = c
    return out

_TAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine_tail.py")
with open(_TAIL, "r", encoding="utf-8") as _tail_fh:
    exec(compile(_tail_fh.read(), _TAIL, "exec"), globals())
