"""Turns raw scan results into a scored upgrade report."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from . import scanner
from .data import DATA_LAST_VERIFIED, LARAVEL_RELEASES, UPGRADE_GUIDE_URL
from .scanner import Finding, ProjectError

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Report:
    project: str
    generated: str
    data_verified: str
    laravel: Dict[str, object]
    php: Dict[str, object]
    upgrade_path: List[Dict[str, object]]
    packages: List[Dict[str, object]]
    findings: List[Finding]
    stats: Dict[str, int]
    score: int
    rating: str
    notes: List[str] = field(default_factory=list)


def laravel_status(major: int, today: date) -> Dict[str, object]:
    release = LARAVEL_RELEASES.get(major)
    latest = max(LARAVEL_RELEASES)
    if release is None:
        if major > latest:
            return {"status": "unknown", "label": "Newer than this tool's data - update the tool"}
        return {"status": "end-of-life", "label": "End of life (older than Laravel %d)" % min(LARAVEL_RELEASES)}

    bugfix_until = date.fromisoformat(release["bugfix_until"])
    security_until = date.fromisoformat(release["security_until"])
    if today <= bugfix_until:
        return {"status": "supported", "label": "Fully supported (bug fixes until %s)" % bugfix_until, **release}
    if today <= security_until:
        return {"status": "security-only", "label": "Security fixes only, until %s" % security_until, **release}
    return {"status": "end-of-life", "label": "End of life (security fixes ended %s)" % security_until, **release}


def _rating(score: int) -> str:
    if score >= 90:
        return "Healthy"
    if score >= 70:
        return "Needs attention"
    if score >= 40:
        return "Outdated"
    return "At risk"


def analyze(project_path: str, target: Optional[int] = None, today: Optional[date] = None) -> Report:
    today = today or date.today()
    root = os.path.abspath(project_path)
    if not os.path.isdir(root):
        raise ProjectError("Folder not found: %s" % project_path)

    composer = scanner.load_json(os.path.join(root, "composer.json"))
    if composer is None:
        raise ProjectError("No composer.json found in %s" % root)
    lock = scanner.load_json(os.path.join(root, "composer.lock"))

    notes: List[str] = []
    latest = max(LARAVEL_RELEASES)
    target = target or latest
    if target not in LARAVEL_RELEASES:
        raise ProjectError("Unknown target version %s. Known versions: %s" % (target, ", ".join(str(v) for v in sorted(LARAVEL_RELEASES))))

    # ---- Laravel ------------------------------------------------------------
    laravel = scanner.detect_laravel(composer, lock)
    major = int(laravel["major"])  # type: ignore[arg-type]
    laravel.update(laravel_status(major, today))
    laravel["latest_major"] = latest
    laravel["majors_behind"] = max(0, latest - major)
    if laravel["estimated"]:
        notes.append("composer.lock was not found, so the Laravel version is estimated from the composer.json constraint.")
    if major > latest:
        notes.append("This project is on a Laravel version newer than the tool's data; update laravel-upgrade-checker.")

    # ---- PHP ----------------------------------------------------------------
    signals = scanner.detect_php(root, composer, lock)
    current = scanner.effective_php(signals)
    php: Dict[str, object] = {
        "signals": [
            {"source": s["source"], "constraint": s["constraint"], "version": scanner.fmt_version(s["version"]), "kind": s["kind"]}  # type: ignore[arg-type]
            for s in signals
        ],
        "effective": None,
        "status": "unknown",
        "eol": None,
    }
    if current:
        status, eol = scanner.php_status(current["version"], today)  # type: ignore[arg-type]
        php.update({"effective": scanner.fmt_version(current["version"]), "effective_source": current["source"], "status": status, "eol": eol})  # type: ignore[arg-type]
    else:
        lowest = next((s for s in signals if s["kind"] == "constraint"), None)
        if lowest:
            status, eol = scanner.php_status(lowest["version"], today)  # type: ignore[arg-type]
            php.update({"lowest_allowed": scanner.fmt_version(lowest["version"]), "lowest_allowed_status": status})  # type: ignore[arg-type]
        notes.append("No concrete PHP version found (.php-version, Dockerfile or config.platform). Only the composer.json lower bound is known.")

    # ---- code, packages -----------------------------------------------------
    findings, stats = scanner.scan_code(root)
    if lock is None:
        findings.append(Finding(
            "no-composer-lock", "composer.lock is missing", "warning", 0,
            "Commit composer.lock so installs are reproducible and installed versions can be audited.",
            count=1, examples=[("composer.lock", 0)],
        ))
    if stats["test_files"] == 0:
        findings.append(Finding(
            "no-tests", "No automated tests found in tests/", "warning", 0,
            "Without tests, each upgrade step has to be verified by hand. Add feature tests for critical flows first.",
            count=1, examples=[("tests/", 0)],
        ))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.since, f.rule_id))
    packages = scanner.detect_packages(composer, lock)

    # ---- upgrade path -------------------------------------------------------
    php_now = None
    if current:
        php_now = tuple(int(p) for p in str(php["effective"]).split("."))[:2]
    steps: List[Dict[str, object]] = []
    for version in range(major + 1, target + 1):
        release = LARAVEL_RELEASES[version]
        needed = tuple(int(p) for p in release["php_min"].split("."))
        steps.append({
            "to": version,
            "php_min": release["php_min"],
            "php_ok": None if php_now is None else php_now >= needed,
            "released": release["released"],
            "guide": UPGRADE_GUIDE_URL.format(major=version),
            "findings": [f.rule_id for f in findings if f.since == version],
        })

    # ---- score --------------------------------------------------------------
    score = 100
    score -= min(40, 10 * int(laravel["majors_behind"]))  # type: ignore[arg-type]
    if laravel["status"] == "end-of-life":
        score -= 20
    elif laravel["status"] == "security-only":
        score -= 5
    if php["status"] == "end-of-life":
        score -= 20
    elif php["status"] == "ending-soon":
        score -= 5
    score -= min(20, 5 * sum(1 for f in findings if f.severity == "critical"))
    score -= min(15, 2 * sum(1 for f in findings if f.severity == "warning"))
    score -= min(15, 3 * sum(1 for p in packages if p["severity"] == "warning"))
    score = max(0, score)

    return Report(
        project=root,
        generated=today.isoformat(),
        data_verified=DATA_LAST_VERIFIED,
        laravel=laravel,
        php=php,
        upgrade_path=steps,
        packages=packages,
        findings=findings,
        stats=stats,
        score=score,
        rating=_rating(score),
        notes=notes,
    )
