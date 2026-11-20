#!/usr/bin/env python3
"""Entry point for the paper structure and logic review skill (writing-06).

Usage:
    python3 scripts/main.py run       --input /input --output /app/output --work /app/work
    python3 scripts/main.py probe     --input /input --work /app/work
    python3 scripts/main.py build     --input /input --output /app/output --work /app/work
    python3 scripts/main.py check     --input /input --output /app/output
    python3 scripts/main.py selfcheck --input /input --output /app/output

Every subcommand that writes artifacts runs the whole pipeline, so `run` and the staged
path produce the same files. The exit code is 0 for every degradation; only an argparse
usage error returns 2.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core    # noqa: E402
import review  # noqa: E402


def parse_args(argv):
    p = argparse.ArgumentParser(description="paper structure and logic review")
    p.add_argument("command", nargs="?", default="run",
                   choices=["run", "probe", "build", "check", "selfcheck"])
    p.add_argument("--input", default="/input")
    p.add_argument("--output", default="/app/output")
    p.add_argument("--work", default="/app/work")
    p.add_argument("--version", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    if a.version:
        print(core.VERSION)
        return 0
    try:
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
