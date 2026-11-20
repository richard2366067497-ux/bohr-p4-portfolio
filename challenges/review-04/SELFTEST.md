# Self-test — claim-graph-auditor (review-04)

Run from the skill root. `PY` is any Python 3.9+ interpreter.

## 1. Single-command smoke test

```bash
$PY scripts/main.py all --input ./input --output ./_selftest_out --work ./_selftest_work
```

Expected: exit 0; `_selftest_out/result.json` parses; `logic_report.md`,
`claim_graph.json`, `claim_evidence_matrix.csv` are non-empty; `status` is
`ok`/`partial`/`insufficient_evidence`.

## 2. Contract echo and finding traceability

```bash
$PY - <<'EOF'
import json, pathlib
out = pathlib.Path("_selftest_out")
r = json.load(open(out / "result.json", encoding="utf-8"))
echo = r["output_contract"]
assert not [k for k in echo if k not in r], "top-level echo incomplete"
sev = {"critical", "major", "minor", "suggestion"}
facet = {"fact", "citation", "method", "statistics", "argument", "structure"}
for f in r.get("findings", []):
    assert f["severity"] in sev and f["facet"] in facet
    assert f["quote"] and f["locator"] and f["recommendation"]
print("findings:", len(r.get("findings", [])), "| nodes:", len(r.get("nodes", [])),
      "| edges:", len(r.get("edges", [])))
print("OK")
EOF
```

## 3. Agent-first path

```bash
$PY scripts/main.py init  --input ./input --output ./_selftest_out --work ./_selftest_work
$PY scripts/main.py show  --input ./input
# write _selftest_work/draft.json with one verbatim quote (see SKILL.md section 0.1)
$PY scripts/main.py check --input ./input --work ./_selftest_work
$PY scripts/main.py build --input ./input --output ./_selftest_out --work ./_selftest_work
$PY scripts/main.py selfcheck --input ./input --output ./_selftest_out --work ./_selftest_work
```

Expected: all exit 0; `check.json` reports a verdict; `verify_report.json` verdict `pass`.

## 4. Empty input and broken JSON

```bash
mkdir -p _empty_in _empty_out _empty_work
$PY scripts/main.py all --input ./_empty_in --output ./_empty_out --work ./_empty_work
$PY -c "import json;r=json.load(open('_empty_out/result.json',encoding='utf-8'));print(r['status'])"
```

Expected: exit 0, `status=insufficient_evidence`, a legal contract echo, and a
`logic_report.md` that states no readable material was supplied with next steps.

## 5. Placeholder sweep

```bash
$PY - <<'EOF'
import pathlib, re
pat = re.compile(r"待写|待补充|待填写|尚未|\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|placeholder|NOT_EXTRACTED|not-extracted|\bpending\b|\bnull\b|\bNone\b|\bN/?A\b|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum", re.I)
bad = [(str(p), m.group(0)) for p in pathlib.Path("_selftest_out").rglob("*") if p.is_file()
       for m in pat.finditer(p.read_text(encoding="utf-8", errors="replace"))]
print("findings:", bad[:10])
assert not bad
print("OK")
EOF
```
