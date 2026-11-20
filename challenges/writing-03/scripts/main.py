#!/usr/bin/env python3
"""Entry point for the academic format and template adapter (writing-03).

Subcommands:
  run        full pipeline: inventory, specification, re-typeset, verify, write artifacts
  probe      inventory only, written to <work>/inventory.json
  build      identical to run, used as the agent-first build step
  check      identical to run, used as the pass/fail gate
  selfcheck  run, then validate the contract echo and the artifact set

The exit code is 0 for every degraded path; only argparse usage errors return 2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import core     # noqa: E402
import adapter  # noqa: E402


def build_parser():
    ap = argparse.ArgumentParser(description="Adapt an academic manuscript to a format or template specification.")
    ap.add_argument("command", nargs="?", default="run",
                    choices=["run", "probe", "build", "check", "selfcheck"])
    ap.add_argument("--input", default="/input", help="input case directory")
    ap.add_argument("--output", default="/app/output", help="output directory for the artifacts")
    ap.add_argument("--work", default="/app/work", help="scratch directory for the build records")
    ap.add_argument("--no-preview", action="store_true", help="skip the optional rendered preview")
    ap.add_argument("--version", action="store_true", help="print the package version and stop")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.version:
        print(core.VERSION)
        return 0
    try:
        if args.command == "probe":
            adapter.probe(args.input, args.work)
        elif args.command == "selfcheck":
            adapter.run_pipeline(args.input, args.output, args.work)
            adapter.selfcheck(args.input, args.output)
        else:
            adapter.run_pipeline(args.input, args.output, args.work)
    except Exception as exc:  # every failure still leaves a readable result.json
        adapter.fail_soft(args.input, args.output, exc)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("unexpected failure: %s" % exc, file=sys.stderr)
        raise SystemExit(0)
