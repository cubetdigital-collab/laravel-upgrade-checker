"""Render a Report as plain text, Markdown or JSON (ASCII only, safe for Windows consoles)."""

from __future__ import annotations

import json
import textwrap
from typing import List

from .analysis import Report

PHP_LABELS = {
    "supported": "supported",
    "ending-soon": "security support ends soon",
    "end-of-life": "END OF LIFE",
    "unknown": "unknown",
}


def _laravel_line(report: Report) -> str:
    laravel = report.laravel
    if laravel["estimated"]:
        return "%s (estimated from %s)" % (laravel["major"], laravel["source"])
    return "%s (from %s)" % (laravel["version"], laravel["source"])


def _php_lines(report: Report) -> List[str]:
    php = report.php
    if php.get("effective"):
        eol = " (security support ends %s)" % php["eol"] if php.get("eol") else ""
        return ["%s - %s%s [%s]" % (php["effective"], PHP_LABELS[str(php["status"])], eol, php.get("effective_source"))]
    if php.get("lowest_allowed"):
        return ["not pinned; composer.json allows PHP from %s (%s)" % (php["lowest_allowed"], PHP_LABELS[str(php["lowest_allowed_status"])])]
    return ["unknown"]


def _where(finding, limit: int = 5) -> List[str]:
    out = []
    for path, line in finding.examples[:limit]:
        out.append("%s:%d" % (path, line) if line else path)
    if finding.count > limit and finding.examples:
        out.append("... and %d more" % (finding.count - limit))
    return out


def _step_php(step) -> str:
    if step["php_ok"] is None:
        return "needs PHP %s+" % step["php_min"]
    return "needs PHP %s+ (%s)" % (step["php_min"], "OK" if step["php_ok"] else "UPGRADE PHP FIRST")


def _split_findings(report: Report):
    current = int(report.laravel["major"])  # type: ignore[arg-type]
    ahead = [f for f in report.findings if f.since > current]
    behind = [f for f in report.findings if f.since <= current]
    return ahead, behind


def render_text(report: Report) -> str:
    laravel = report.laravel
    lines: List[str] = []
    add = lines.append

    add("LARAVEL UPGRADE CHECKER")
    add("=" * 60)
    add("Project : %s" % report.project)
    add("Date    : %s (support data verified %s)" % (report.generated, report.data_verified))
    add("")
    add("MODERNIZATION SCORE: %d/100 - %s" % (report.score, report.rating))
    add("")
    add("LARAVEL")
    add("  Version : %s" % _laravel_line(report))
    add("  Status  : %s" % laravel["label"])
    add("  Latest  : %s (%d major version(s) behind)" % (laravel["latest_major"], laravel["majors_behind"]))
    add("  Allowed : %s" % laravel["constraint"])
    add("")
    add("PHP")
    for line in _php_lines(report):
        add("  " + line)
    add("")

    if report.upgrade_path:
        add("UPGRADE PATH (one major version at a time)")
        start = int(laravel["major"])  # type: ignore[arg-type]
        for index, step in enumerate(report.upgrade_path):
            add("  %d -> %s   %s" % (start + index, step["to"], _step_php(step)))
            add("      guide: %s" % step["guide"])
        add("")
    else:
        add("UPGRADE PATH")
        add("  Already on the target version.")
        add("")

    ahead, behind = _split_findings(report)
    if ahead:
        add("BLOCKERS AND RISKS BY UPGRADE STEP")
        for finding in ahead:
            add("  [%s] %s  (breaks at Laravel %d, %d hit(s))" % (finding.severity.upper(), finding.title, finding.since, finding.count))
            for chunk in textwrap.wrap(finding.advice, 70, break_on_hyphens=False):
                add("      " + chunk)
            for where in _where(finding):
                add("      - " + where)
        add("")
    if behind:
        add("CODE TO CLEAN UP")
        for finding in behind:
            add("  [%s] %s  (%d hit(s))" % (finding.severity.upper(), finding.title, finding.count))
            for chunk in textwrap.wrap(finding.advice, 70, break_on_hyphens=False):
                add("      " + chunk)
            for where in _where(finding):
                add("      - " + where)
        add("")
    if not report.findings:
        add("CODE: no known legacy patterns found.")
        add("")

    if report.packages:
        add("PACKAGES TO REVIEW")
        for pkg in report.packages:
            add("  [%s] %s%s" % (str(pkg["severity"]).upper(), pkg["name"], "" if pkg["direct"] else " (indirect)"))
            for chunk in textwrap.wrap("%s %s" % (pkg["message"], pkg["advice"]), 70, break_on_hyphens=False):
                add("      " + chunk)
        add("")

    add("SCANNED: %d PHP files, %d test files" % (report.stats["php_files"], report.stats["test_files"]))
    for note in report.notes:
        add("NOTE: " + note)
    add("This is a static scan: it flags likely problems, it does not run your code.")
    return "\n".join(lines) + "\n"


def render_markdown(report: Report) -> str:
    laravel = report.laravel
    out: List[str] = []
    add = out.append

    add("# Laravel Upgrade Report")
    add("")
    add("- **Project:** `%s`" % report.project)
    add("- **Date:** %s (support data verified %s)" % (report.generated, report.data_verified))
    add("- **Modernization score:** **%d/100** - %s" % (report.score, report.rating))
    add("")
    add("## Current stack")
    add("")
    add("| | |")
    add("|---|---|")
    add("| Laravel | %s |" % _laravel_line(report))
    add("| Support status | %s |" % laravel["label"])
    add("| Latest Laravel | %s (%d major version(s) behind) |" % (laravel["latest_major"], laravel["majors_behind"]))
    add("| PHP | %s |" % _php_lines(report)[0])
    add("")

    add("## Upgrade path")
    add("")
    if report.upgrade_path:
        add("| Step | PHP requirement | Guide |")
        add("|---|---|---|")
        start = int(laravel["major"])  # type: ignore[arg-type]
        for index, step in enumerate(report.upgrade_path):
            add("| %d -> %s | %s | [Upgrade guide](%s) |" % (start + index, step["to"], _step_php(step), step["guide"]))
    else:
        add("Already on the target version.")
    add("")

    ahead, behind = _split_findings(report)
    for heading, items in (("Blockers and risks by upgrade step", ahead), ("Code to clean up", behind)):
        if not items:
            continue
        add("## " + heading)
        add("")
        for finding in items:
            add("### %s: %s" % (finding.severity.capitalize(), finding.title))
            add("")
            add("%d occurrence(s). %s" % (finding.count, finding.advice))
            add("")
            for where in _where(finding):
                add("- `%s`" % where if "..." not in where else "- %s" % where)
            add("")

    if report.packages:
        add("## Packages to review")
        add("")
        add("| Package | Severity | Notes |")
        add("|---|---|---|")
        for pkg in report.packages:
            add("| `%s`%s | %s | %s %s |" % (pkg["name"], "" if pkg["direct"] else " (indirect)", pkg["severity"], pkg["message"], pkg["advice"]))
        add("")

    add("---")
    add("Scanned %d PHP files and %d test files. This is a static scan; it flags likely problems and does not run your code." % (report.stats["php_files"], report.stats["test_files"]))
    for note in report.notes:
        add("")
        add("> Note: " + note)
    return "\n".join(out) + "\n"


def render_json(report: Report) -> str:
    payload = {
        "project": report.project,
        "generated": report.generated,
        "data_verified": report.data_verified,
        "score": report.score,
        "rating": report.rating,
        "laravel": report.laravel,
        "php": report.php,
        "upgrade_path": report.upgrade_path,
        "packages": report.packages,
        "findings": [
            {
                "id": f.rule_id,
                "title": f.title,
                "severity": f.severity,
                "since": f.since,
                "count": f.count,
                "advice": f.advice,
                "examples": ["%s:%d" % (p, n) if n else p for p, n in f.examples],
            }
            for f in report.findings
        ],
        "stats": report.stats,
        "notes": report.notes,
    }
    return json.dumps(payload, indent=2, default=str) + "\n"


RENDERERS = {"text": render_text, "markdown": render_markdown, "json": render_json}
