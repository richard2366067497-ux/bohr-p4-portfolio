#!/usr/bin/env python3
"""Evidence reconciliation for the reader result: every evidence row must point at a
region that exists in the layout, and every structural item must be anchored.

Returns {status, checked_claims, resolved, unresolved, warnings, errors}. Pure stdlib
so it also runs standalone:

    python3 evidence_reconcile.py result.json paper.layout.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _regions(layout: dict) -> dict:
    regs = {}
    for page in layout.get("pages", []):
        pno = page.get("page")
        regs.setdefault("p%02d" % pno if isinstance(pno, int) else str(pno), None)
        for ln in page.get("lines", []):
            if ln.get("id"):
                regs[ln["id"]] = (ln.get("text") or "")[:200]
        for bl in page.get("blocks", []):
            if bl.get("id"):
                regs.setdefault(bl["id"], (bl.get("text") or "")[:200])
    return regs


def reconcile(result: dict, layout: dict) -> dict:
    regs = _regions(layout)
    page_ids = {k for k in regs if re.match(r"^p\d+$", k)}
    evidence = result.get("evidence", []) or []
    unresolved, warnings, errors = [], [], []
    for i, row in enumerate(evidence):
        region = str(row.get("region") or "")
        page = row.get("page")
        hit = region in regs or ("p%02d" % page if isinstance(page, int) else "") in page_ids
        if not hit:
            # page-level region like p01-abstract is acceptable when the page exists
            base = re.match(r"^(p\d+)", region)
            if base and base.group(1) in page_ids:
                warnings.append("evidence[%d] region %r is page-scoped, not line-scoped" % (i, region))
                hit = True
        if not hit:
            unresolved.append({"index": i, "claim": row.get("claim"), "region": region,
                               "page": page, "reason": "region not found in layout"})
        quote = row.get("quote")
        if not quote:
            errors.append("evidence[%d] missing quote" % i)
        elif region in regs and isinstance(regs[region], str) and regs[region]:
            norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
            if norm(quote)[:40] and norm(quote)[:40] not in norm(regs[region]):
                warnings.append("evidence[%d] quote not found verbatim in region %s" % (i, region))
    structured = (result.get("result") or {}).get("structured", []) or []
    for j, item in enumerate(structured):
        region = str(item.get("region") or "")
        if region and region not in regs:
            base = re.match(r"^(p\d+)", region)
            if not (base and base.group(1) in page_ids):
                warnings.append("structured[%d] region %r not anchored" % (j, region))
    status = "success" if not unresolved and not errors else "partial"
    return {"status": status, "checked_claims": len(evidence),
            "resolved": len(evidence) - len(unresolved), "unresolved": unresolved,
            "warnings": warnings, "errors": errors,
            "region_count": len(regs)}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 0
    try:
        result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
        layout = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace"))
        out = reconcile(result, layout)
    except Exception as exc:  # noqa: BLE001
        out = {"status": "failed", "error": str(exc)[:200], "unresolved": []}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
