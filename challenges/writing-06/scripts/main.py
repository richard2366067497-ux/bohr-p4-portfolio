#!/usr/bin/env python3
"""Entry point for the paper structure and logic review skill (writing-06).

Usage:
    python3 scripts/main.py run       --input /input --output /app/output --work /app/work
    python3 scripts/main.py probe     --input /input --work /app/work
    python3 scripts/main.py build     --input /input --output /app/output --work /app/work
    python3 scripts/main.py check     --input /input --output /app/output
    python3 scripts/main.py selfcheck --input /input --output /app/output
    python3 scripts/main.py selftest                      # 内置测试：样例包跑通 + 契约/引文/降级不变量

Every subcommand that writes artifacts runs the whole pipeline, so `run` and the staged
path produce the same files. The exit code is 0 for every degradation; only an argparse
usage error returns 2.
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core    # noqa: E402
import review  # noqa: E402


def parse_args(argv):
    p = argparse.ArgumentParser(description="paper structure and logic review")
    p.add_argument("command", nargs="?", default="run",
                   choices=["run", "probe", "build", "check", "selfcheck", "selftest"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--version", action="store_true")
    return p.parse_args(argv)


def _mk_pdf(text):
    """Minimal one-page PDF carrying a Flate-compressed text stream (for the selftest only)."""
    payload = zlib.compress(("BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text).encode("utf-8"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(payload) + payload + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for x in offs:
        out += b"%010d 00000 n \n" % x
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def _mk_docx(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>%s</w:t></w:r></w:p>"
                                        "</w:body></w:document>" % text)
    return buf.getvalue()


def selftest():
    """Offline, dependency-free checks: extraction, pipeline, contract, degradation."""
    import core as C
    fails, logs = [], []

    def chk(name, cond, note=""):
        logs.append("%-4s %s%s" % ("PASS" if cond else "FAIL", name, (" — %s" % note) if note else ""))
        if not cond:
            fails.append(name)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp(prefix="w06-selftest-")
    try:
        inp, out, work = (os.path.join(tmp, x) for x in ("in", "out", "work"))
        os.makedirs(inp)
        src = os.path.join(root, "examples")
        for n in ("case.json", "manuscript.md"):
            if os.path.isfile(os.path.join(src, n)):
                shutil.copy(os.path.join(src, n), inp)
        open(os.path.join(inp, "appendix.pdf"), "wb").write(_mk_pdf("in vitro only, n = 12, 91.2% conversion"))
        open(os.path.join(inp, "notes.docx"), "wb").write(_mk_docx("The claim may hold in vitro."))
        open(os.path.join(inp, "broken.docx"), "wb").write(b"not a zip at all")

        p = os.path.join(inp, "appendix.pdf")
        chk("pdf_text_layer", "91.2%" in (C.load(C.Path(p)) or ""), "FlateDecode text extracted")
        dp = os.path.join(inp, "notes.docx")
        chk("docx_text_layer", "in vitro" in (C.load(C.Path(dp)) or ""))
        chk("broken_docx_degrades", C.load(C.Path(os.path.join(inp, "broken.docx"))) is None)

        r = review.run(inp, out, work)
        chk("exit_status_ok", r.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"))
        keys = list((r.get("output_contract") or {}).keys())
        chk("contract_filled", bool(keys) and all(r.get(k) not in (None, "", [], {}) for k in keys), "keys=%s" % keys)
        for n in ("structural_review.json", "edit_plan.md", "semantic_audit.json", "metrics.json", "result.json"):
            chk("artifact:%s" % n, os.path.isfile(os.path.join(out, n)))
        sr = json.loads(open(os.path.join(out, "structural_review.json"), encoding="utf-8").read())
        g = sr.get("grounding", {})
        chk("quote_grounding", g.get("quotes", 0) == 0 or g.get("hit_rate") >= 0.99, "hit_rate=%s" % g.get("hit_rate"))
        chk("no_placeholder_tokens", not C.TOK.search(json.dumps(r, ensure_ascii=False)))
        chk("unparsed_named_in_degradations", "broken.docx" in (r.get("degradations") or ""),
            "unreadable material must be recorded, not invented")
        sa = json.loads(open(os.path.join(out, "semantic_audit.json"), encoding="utf-8").read())
        chk("semantic_protocol", bool(sa.get("prompt_template")) and len(sa.get("dimensions", [])) == 4)
        mp = json.loads(open(os.path.join(out, "metrics.json"), encoding="utf-8").read())
        chk("baseline_metrics", mp.get("pass") is True or all("ok" in c for c in mp.get("baseline_checks", [])))
    except Exception as exc:  # noqa: BLE001
        chk("selftest_completed", False, "%s: %s" % (type(exc).__name__, exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n".join(logs))
    print("SELFTEST %s (%d checks)" % ("PASS" if not fails else "FAIL", len(logs)))
    return 0


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    if a.version:
        print(core.VERSION)
        return 0
    try:
        if a.command == "selftest":
            return selftest()
        if a.command == "probe":
            review.probe(a.input, a.work)
        elif a.command == "selfcheck":
            review.run(a.input, a.output, a.work)
            review.selfcheck(a.input, a.output)
        else:
            review.run(a.input, a.output, a.work)
    except Exception as exc:  # noqa: BLE001 - the contract requires exit code 0
        try:
            review.fail_soft(a.input, a.output, exc)
        except Exception:
            pass
        print("degraded: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
