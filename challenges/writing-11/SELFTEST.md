# Self-test — manuscript-revision-desk (writing-11)

All commands are run from the skill root. `PY` is any Python 3.9+ interpreter.
Use absolute paths for the sandbox directories.

## 1. Single-command smoke test

```bash
$PY scripts/main.py all --input ./input --output ./_selftest_out --work ./_selftest_work
```

Expected: exit code 0; `_selftest_out/result.json` parses as JSON; `status` is
`ok`/`partial`/`insufficient_evidence`; `output_contract` and top-level keys agree;
`revised_manuscript.md`, `evidence_map.json`, `change_log.json` are non-empty.

## 2. Contract echo check

```bash
$PY - <<'EOF'
import json
r = json.load(open("_selftest_out/result.json", encoding="utf-8"))
echo = r["output_contract"]
missing = [k for k in echo if k not in r]
print("contract keys:", list(echo))
print("missing top-level:", missing)
assert not missing
assert r["case_id"] == echo.get("case_id", r["case_id"])
print("OK")
EOF
```

## 3. Verbatim-source and version-control check

```bash
$PY - <<'EOF'
import json, re, pathlib
out = pathlib.Path("_selftest_out")
r = json.load(open(out / "result.json", encoding="utf-8"))
man = (out / "revised_manuscript.md").read_text(encoding="utf-8")
assert "EDITORIAL-ANNOTATION" in man or r["status"] == "insufficient_evidence"
for a in r.get("annotations", []):
    assert a["source_quote"] in man
vc = r["version_control"]
assert vc["invalid_operation"]["state_unchanged"] is True
assert vc["invalid_operation"]["state_sha_before"] == vc["invalid_operation"]["state_sha_after"]
print("annotations:", len(r.get("annotations", [])), "| rollback:", vc["rollback_verified"])
print("OK")
EOF
```

## 4. Agent-first path

```bash
$PY scripts/main.py init --input ./input --output ./_selftest_out --work ./_selftest_work
$PY scripts/main.py show --input ./input
# write _selftest_work/draft.json with a verbatim quote for one target
$PY scripts/main.py check --input ./input --work ./_selftest_work
$PY scripts/main.py build --input ./input --output ./_selftest_out --work ./_selftest_work
$PY scripts/main.py selfcheck --input ./input --output ./_selftest_out --work ./_selftest_work
```

Expected: every command exits 0; `check.json` reports `verdict`; `build` finalises
the full deliverable set; `verify_report.json` verdict is `pass`.

## 5. Empty input and broken JSON

```bash
mkdir -p _empty_in _empty_out _empty_work
$PY scripts/main.py all --input ./_empty_in --output ./_empty_out --work ./_empty_work
$PY -c "import json;r=json.load(open('_empty_out/result.json',encoding='utf-8'));print(r['status'],list(r['output_contract']))"
```

Expected: exit 0, `status=insufficient_evidence`, a legal contract echo, and a
non-empty `revised_manuscript.md` that states no anchored manuscript was supplied.
Then place an invalid `case.json` (`{ "case_id": `) in an input dir and repeat:
expected exit 0 with `status=partial` and a recorded degradation.

## 6. Placeholder sweep

```bash
$PY - <<'EOF'
import pathlib, re
pat = re.compile(r"待写|待补充|待填写|尚未|TBD|TODO|FIXME|XXX|placeholder|NOT_EXTRACTED|not-extracted|pending|null|None|N/A|<[A-Za-z_][\w /-]*>|example\.com|lorem ipsum")
bad = []
for p in pathlib.Path("_selftest_out").rglob("*"):
    if p.is_file():
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(t):
            bad.append((str(p), m.group(0)))
print("findings:", bad[:10])
assert not bad
print("OK")
EOF
```
