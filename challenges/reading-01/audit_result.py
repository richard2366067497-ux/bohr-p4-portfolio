#!/usr/bin/env python3
"""Contract audit for the reader result.json.

Checks that every key required by output_contract is present and non-empty at the
top level (contract keys are shallow-copied there), that the structural sections
exist, and that status is one of the allowed values. Returns
{valid, errors, warnings, contract_keys}. Pure stdlib.

    python3 audit_result.py result.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATUSES = ("success", "partial", "cannot_determine", "failed")
REQUIRED = ["case_id", "status", "input", "result", "evidence", "uncertainty",
            "sources", "change_log", "output_contract", "runtime"]
NON_EMPTY_OK = {"case_id"}  # case_id may legitimately be null when case.json is absent


def audit(payload: dict) -> dict:
    errors, warnings = [], []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["result is not an object"], "warnings": [], "contract_keys": []}
    for key in REQUIRED:
        if key not in payload:
            errors.append("missing top-level key: %s" % key)
    if payload.get("status") not in STATUSES:
        errors.append("bad status: %r" % payload.get("status"))
    if not payload.get("uncertainty"):
        warnings.append("uncertainty is empty; state at least the extraction backend")
    if not payload.get("change_log"):
        warnings.append("change_log is empty")
    result = payload.get("result")
    if not isinstance(result, dict):
        errors.append("result must be an object")
    else:
        for key in ("answer", "structured", "claims", "relations"):
            if key not in result:
                errors.append("result missing key: %s" % key)
        if payload.get("status") in ("success", "partial") and not str(result.get("answer", "")).strip():
            errors.append("answer is empty for a non-failed status")
    if payload.get("status") in ("success", "partial") and not payload.get("evidence"):
        errors.append("evidence is empty for a non-failed status")
    contract = payload.get("output_contract")
    contract_keys = list(contract) if isinstance(contract, dict) else []
    for key in contract_keys:
        if key not in payload:
            errors.append("output_contract key not echoed at top level: %s" % key)
        else:
            value = payload[key]
            if key not in NON_EMPTY_OK and value in (None, "", [], {}):
                warnings.append("output_contract key %s echoed but empty" % key)
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "contract_keys": contract_keys}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
        out = audit(payload)
    except Exception as exc:  # noqa: BLE001
        out = {"valid": False, "errors": [str(exc)[:200]], "warnings": [], "contract_keys": []}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
