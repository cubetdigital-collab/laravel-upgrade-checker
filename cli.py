"""Command-line interface."""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from typing import List, Optional

from . import __version__
from .analysis import analyze
from .report import RENDERERS
from .scanner import ProjectError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="laravel-upgrade-checker",
        description="Offline audit of a Laravel project: version support status, PHP compatibility, "
        "legacy code patterns, risky packages and an upgrade path.",
    )
    parser.add_argument("path", nargs="?", default=".", help="path to the Laravel project (default: current folder)")
    parser.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text", help="report format (default: text)")
    parser.add_argument("-o", "--output", help="write the report to this file instead of the screen")
    parser.add_argument("-t", "--target", type=int, help="Laravel major version to plan for (default: latest known)")
    parser.add_argument("--fail-under", type=int, metavar="SCORE", help="exit with code 1 if the score is below SCORE (for CI)")
    parser.add_argument("--today", help=argparse.SUPPRESS)  # YYYY-MM-DD, used by the tests
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        today = date.fromisoformat(args.today) if args.today else None
        report = analyze(args.path, target=args.target, today=today)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except ProjectError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    rendered = RENDERERS[args.format](report)
    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        print("Report written to %s (score %d/100, %s)" % (args.output, report.score, report.rating))
    else:
        sys.stdout.write(rendered)

    if args.fail_under is not None and report.score < args.fail_under:
        return 1
    return 0
