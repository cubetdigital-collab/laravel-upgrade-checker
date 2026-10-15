"""Reads a Laravel project from disk. Offline and read-only: nothing is executed or sent anywhere."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterator, List, Optional, Tuple

from .data import KNOWN_PACKAGE_ISSUES, PHP_SECURITY_EOL
from .rules import FILE_RULES, LINE_RULES

Version = Tuple[int, ...]

SKIP_DIR_NAMES = {"vendor", "node_modules", "storage", ".git", ".idea", ".vscode"}
SKIP_REL_DIRS = {"bootstrap/cache", "public/build", "public/vendor"}
MAX_FILE_BYTES = 1_000_000
MAX_EXAMPLES = 50


class ProjectError(Exception):
    """Raised when the folder is not a readable Laravel project."""


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: str
    since: int
    advice: str
    count: int = 0
    examples: List[Tuple[str, int]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def load_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as exc:
        raise ProjectError("Could not read %s: %s" % (os.path.basename(path), exc))


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return None


_VERSION = re.compile(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    match = _VERSION.search(text or "")
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2) or 0), int(match.group(3) or 0))


def fmt_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


# --------------------------------------------------------------------------- #
# Composer version constraints
# --------------------------------------------------------------------------- #

_PART = re.compile(r"^(\^|~>|~|>=|<=|!=|==|>|<|=)?\s*v?(\d+)(?:\.(\d+|\*|x))?(?:\.(\d+|\*|x))?", re.I)


def _num(group: Optional[str]) -> Optional[int]:
    return int(group) if group and group.isdigit() else None


def _parts(group: str) -> Iterator[Tuple[str, int, Optional[int], Optional[int]]]:
    for token in re.split(r"[\s,]+", group.strip()):
        if not token:
            continue
        match = _PART.match(token)
        if match:
            yield (match.group(1) or "", int(match.group(2)), _num(match.group(3)), _num(match.group(4)))


def _or_groups(constraint: Optional[str]) -> List[str]:
    return re.split(r"\s*\|\|?\s*", constraint or "")


def constraint_major_bounds(constraint: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Lowest and highest major version a Composer constraint allows (None = unbounded)."""
    lows: List[Optional[int]] = []
    highs: List[Optional[int]] = []
    for group in _or_groups(constraint):
        lo: Optional[int] = None
        hi: Optional[int] = None
        seen = False
        for op, major, minor, patch in _parts(group):
            seen = True
            part_lo: Optional[int] = None
            part_hi: Optional[int] = None
            if op in ("^", "~", "~>", "", "=", "=="):
                part_lo = part_hi = major
            elif op in (">=", ">"):
                part_lo = major
            elif op == "<":
                part_hi = major - 1 if not minor and not patch else major
            elif op == "<=":
                part_hi = major
            else:
                continue
            if part_lo is not None:
                lo = part_lo if lo is None else max(lo, part_lo)
            if part_hi is not None:
                hi = part_hi if hi is None else min(hi, part_hi)
        if seen:
            lows.append(lo)
            highs.append(hi)
    if not lows:
        return None, None
    low = None if any(v is None for v in lows) else min(v for v in lows if v is not None)
    high = None if any(v is None for v in highs) else max(v for v in highs if v is not None)
    return low, high


def lowest_php(constraint: Optional[str]) -> Optional[Tuple[int, int]]:
    """Lowest PHP (major, minor) a constraint such as '^8.1' or '>=7.4 <8.3' allows."""
    lows: List[Tuple[int, int]] = []
    for group in _or_groups(constraint):
        best: Optional[Tuple[int, int]] = None
        for op, major, minor, _patch in _parts(group):
            if op in ("^", "~", "~>", ">=", ">", "", "=", "=="):
                candidate = (major, minor or 0)
                best = candidate if best is None else max(best, candidate)
        if best:
            lows.append(best)
    return min(lows) if lows else None


# --------------------------------------------------------------------------- #
# composer.json / composer.lock
# --------------------------------------------------------------------------- #

def find_lock_package(lock: Optional[dict], name: str) -> Optional[dict]:
    if not lock:
        return None
    for key in ("packages", "packages-dev"):
        for package in lock.get(key) or []:
            if package.get("name") == name:
                return package
    return None


def detect_laravel(composer: dict, lock: Optional[dict]) -> Dict[str, object]:
    require = composer.get("require") or {}
    constraint = require.get("laravel/framework") or (composer.get("require-dev") or {}).get("laravel/framework")
    if constraint is None:
        if "laravel/lumen-framework" in require:
            raise ProjectError(
                "This is a Lumen project. Lumen is no longer actively developed; "
                "plan a migration to full Laravel before using this tool."
            )
        raise ProjectError("laravel/framework was not found in composer.json - is this a Laravel project?")

    low, high = constraint_major_bounds(constraint)
    package = find_lock_package(lock, "laravel/framework")
    installed = parse_version(package.get("version")) if package else None

    if installed:
        return {
            "version": fmt_version(installed),
            "major": installed[0],
            "estimated": False,
            "source": "composer.lock",
            "constraint": constraint,
            "allowed_low": low,
            "allowed_high": high,
        }

    guess = high if high is not None else low
    if guess is None:
        raise ProjectError("Could not work out the Laravel version from composer.json (constraint: %s)." % constraint)
    return {
        "version": None,
        "major": guess,
        "estimated": True,
        "source": "composer.json constraint",
        "constraint": constraint,
        "allowed_low": low,
        "allowed_high": high,
    }


def detect_php(root: str, composer: dict, lock: Optional[dict]) -> List[Dict[str, object]]:
    """Collect every hint about the PHP version the project targets or runs on."""
    signals: List[Dict[str, object]] = []

    required = (composer.get("require") or {}).get("php")
    if required:
        low = lowest_php(required)
        if low:
            signals.append({"source": "composer.json require.php", "constraint": required, "version": low, "kind": "constraint"})

    platform = ((composer.get("config") or {}).get("platform") or {}).get("php")
    if platform:
        parsed = parse_version(platform)
        if parsed:
            signals.append({"source": "composer.json config.platform.php", "constraint": platform, "version": parsed[:2], "kind": "platform"})

    text = read_text(os.path.join(root, ".php-version"))
    if text:
        parsed = parse_version(text.strip())
        if parsed:
            signals.append({"source": ".php-version", "constraint": text.strip(), "version": parsed[:2], "kind": "runtime"})

    text = read_text(os.path.join(root, ".tool-versions"))
    if text:
        match = re.search(r"(?im)^\s*php\s+(\S+)", text)
        parsed = parse_version(match.group(1)) if match else None
        if parsed:
            signals.append({"source": ".tool-versions", "constraint": match.group(1), "version": parsed[:2], "kind": "runtime"})

    text = read_text(os.path.join(root, "Dockerfile"))
    if text:
        match = re.search(r"(?im)^\s*FROM\s+(?:[\w.\-]+/)*php:(\d+\.\d+)", text)
        if match:
            parsed = parse_version(match.group(1))
            signals.append({"source": "Dockerfile", "constraint": match.group(1), "version": parsed[:2], "kind": "runtime"})

    return signals


def effective_php(signals: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    """Prefer a platform/runtime signal; fall back to nothing (a constraint is only a lower bound)."""
    for kind in ("platform", "runtime"):
        for signal in signals:
            if signal["kind"] == kind:
                return signal
    return None


def php_status(version: Tuple[int, ...], today: date) -> Tuple[str, Optional[str]]:
    key = (version[0], version[1] if len(version) > 1 else 0)
    if key < (7, 4):
        return "end-of-life", None
    eol = PHP_SECURITY_EOL.get(key)
    if eol is None:
        return "unknown", None
    end = date.fromisoformat(eol)
    if today > end:
        return "end-of-life", eol
    if (end - today).days <= 180:
        return "ending-soon", eol
    return "supported", eol


def detect_packages(composer: dict, lock: Optional[dict]) -> List[Dict[str, object]]:
    direct = dict(composer.get("require") or {})
    direct.update(composer.get("require-dev") or {})

    results: List[Dict[str, object]] = []
    seen = set()
    for name in sorted(direct):
        if name in KNOWN_PACKAGE_ISSUES:
            severity, message, advice = KNOWN_PACKAGE_ISSUES[name]
            results.append({"name": name, "severity": severity, "message": message, "advice": advice, "direct": True})
            seen.add(name)

    if lock:
        for key in ("packages", "packages-dev"):
            for package in lock.get(key) or []:
                name = package.get("name")
                abandoned = package.get("abandoned")
                if not name or not abandoned or name in seen:
                    continue
                replacement = abandoned if isinstance(abandoned, str) else None
                results.append({
                    "name": name,
                    "severity": "warning",
                    "message": "Marked abandoned on Packagist" + (" (suggested replacement: %s)." % replacement if replacement else "."),
                    "advice": "Replace it with %s." % replacement if replacement else "Find a maintained alternative.",
                    "direct": name in direct,
                })
                seen.add(name)
    return results


# --------------------------------------------------------------------------- #
# source code scan
# --------------------------------------------------------------------------- #

def _iter_php_files(root: str) -> Iterator[Tuple[str, str]]:
    for dirpath, dirnames, filenames in os.walk(root):
        kept = []
        for name in dirnames:
            rel_dir = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if name in SKIP_DIR_NAMES or rel_dir in SKIP_REL_DIRS:
                continue
            kept.append(name)
        dirnames[:] = kept
        for filename in filenames:
            if filename.endswith(".php"):
                absolute = os.path.join(dirpath, filename)
                yield absolute, os.path.relpath(absolute, root).replace(os.sep, "/")


_COMMENT_PREFIXES = ("//", "#", "*", "/*")
_NOT_TESTS = {"TestCase.php", "CreatesApplication.php", "Pest.php"}


def scan_code(root: str) -> Tuple[List[Finding], Dict[str, int]]:
    findings: Dict[str, Finding] = {}
    stats = {"php_files": 0, "test_files": 0}

    for absolute, rel in _iter_php_files(root):
        stats["php_files"] += 1
        if rel.startswith("tests/") and os.path.basename(rel) not in _NOT_TESTS:
            stats["test_files"] += 1

        rules = [
            rule for rule in LINE_RULES
            if rel.endswith(rule.suffix)
            and (not rule.include or rel.startswith(rule.include))
            and not (rule.exclude and rel.startswith(rule.exclude))
        ]
        if not rules:
            continue
        try:
            if os.path.getsize(absolute) > MAX_FILE_BYTES:
                continue
            with open(absolute, encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError:
            continue

        for number, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(_COMMENT_PREFIXES):
                continue
            for rule in rules:
                if rule.pattern.search(line):
                    finding = findings.setdefault(
                        rule.id, Finding(rule.id, rule.title, rule.severity, rule.since, rule.advice)
                    )
                    finding.count += 1
                    if len(finding.examples) < MAX_EXAMPLES:
                        finding.examples.append((rel, number))

    for file_rule in FILE_RULES:
        if os.path.isfile(os.path.join(root, file_rule.path)):
            findings[file_rule.id] = Finding(
                file_rule.id, file_rule.title, file_rule.severity, file_rule.since, file_rule.advice,
                count=1, examples=[(file_rule.path, 0)],
            )

    return list(findings.values()), stats
