# laravel-upgrade-checker

An offline command-line audit that tells you how ready a Laravel project is for its next upgrade.

Point it at a project folder and it reports:

- **Support status** of your Laravel version (fully supported, security-only, or end of life) against the official support policy
- **PHP compatibility**: which PHP version the project targets, whether that version is still supported, and whether it blocks the next Laravel step
- **Upgrade path**: the one-major-version-at-a-time route to the latest release, with a link to each official upgrade guide
- **Legacy code patterns** that break or change in specific Laravel versions (removed helpers, `dispatchNow()`, old factories, `->change()` migrations, `$dates`, and more)
- **Risky packages**: abandoned or superseded dependencies, including anything flagged `abandoned` in `composer.lock`
- A **modernization score** from 0 to 100

It reads files only. It never runs your code, never talks to the network, and never changes your project, so it is safe to run on client codebases.

## Install

Requires Python 3.9 or newer. There are no third-party dependencies.

```bash
git clone https://github.com/<your-org>/laravel-upgrade-checker.git
cd laravel-upgrade-checker
pip install .
```

Or run it without installing:

```bash
cd laravel-upgrade-checker
set PYTHONPATH=src            # Windows (cmd)
export PYTHONPATH=src         # macOS / Linux
python -m laravel_upgrade_checker /path/to/your-app
```

## Usage

```bash
laravel-upgrade-checker /path/to/your-app
laravel-upgrade-checker /path/to/your-app --format markdown --output report.md
laravel-upgrade-checker /path/to/your-app --format json
laravel-upgrade-checker /path/to/your-app --target 12
laravel-upgrade-checker /path/to/your-app --fail-under 70
```

| Option | What it does |
|---|---|
| `path` | Laravel project folder (default: current folder) |
| `-f, --format` | `text` (default), `markdown` (good for sharing with a client) or `json` |
| `-o, --output` | Write the report to a file |
| `-t, --target` | Laravel major version to plan for (default: latest) |
| `--fail-under N` | Exit with code 1 if the score is below N, for CI pipelines |

Exit codes: `0` success, `1` score below `--fail-under`, `2` error (not a Laravel project, folder not found, unreadable `composer.json`).

## Example output

Run against a deliberately outdated demo project (shortened):

```text
LARAVEL UPGRADE CHECKER
============================================================
MODERNIZATION SCORE: 4/100 - At risk

LARAVEL
  Version : 10.48.4 (from composer.lock)
  Status  : End of life (security fixes ended 2025-02-04)
  Latest  : 13 (3 major version(s) behind)

PHP
  8.1 - END OF LIFE (security support ends 2025-12-31) [.php-version]

UPGRADE PATH (one major version at a time)
  10 -> 11   needs PHP 8.2+ (UPGRADE PHP FIRST)
      guide: https://laravel.com/docs/11.x/upgrade
  11 -> 12   needs PHP 8.2+ (UPGRADE PHP FIRST)
  12 -> 13   needs PHP 8.3+ (UPGRADE PHP FIRST)

BLOCKERS AND RISKS BY UPGRADE STEP
  [WARNING] Column changes with ->change() in migrations  (breaks at Laravel 11, 1 hit(s))
      Laravel 11 modifies columns natively and drops any attribute you do
      not repeat (nullable, default, and so on). ...
      - database/migrations/2022_add.php:2

CODE TO CLEAN UP
  [CRITICAL] dispatchNow() / dispatch_now() removed in Laravel 9  (1 hit(s))
      Use dispatchSync() / dispatch_sync().
      - app/Jobs/Sync.php:2

PACKAGES TO REVIEW
  [WARNING] fruitcake/laravel-cors
      Abandoned. CORS handling has been built into Laravel since version 9. ...
```

## How the score works

The score starts at 100 and loses points for:

| Issue | Penalty |
|---|---|
| Each major Laravel version behind the latest | -10 (max -40) |
| Laravel version is end of life / security-only | -20 / -5 |
| PHP version is end of life / security support ends within 6 months | -20 / -5 |
| Each critical code finding | -5 (max -20) |
| Each warning code finding | -2 (max -15) |
| Each abandoned or risky package | -3 (max -15) |

Findings are counted once per rule, not once per occurrence, so one noisy pattern cannot sink a score on its own.

| Score | Rating |
|---|---|
| 90-100 | Healthy |
| 70-89 | Needs attention |
| 40-69 | Outdated |
| 0-39 | At risk |

## What it checks

**Version detection.** The installed Laravel version comes from `composer.lock`. Without a lock file it is estimated from the `composer.json` constraint, and the report says so.

**PHP detection.** In order of preference: `config.platform.php` in `composer.json`, `.php-version`, `.tool-versions`, the `FROM php:x.y` line of a root `Dockerfile`. The `require.php` constraint is only a lower bound, so on its own it is reported but not treated as the running version.

**Code rules** live in [`src/laravel_upgrade_checker/rules.py`](src/laravel_upgrade_checker/rules.py). Each rule records the Laravel version where it starts to matter, so findings are grouped by upgrade step. Rules skip `vendor/`, `node_modules/`, `storage/` and commented-out lines.

## Limits

- It is a static, regex-based scan. It points at code worth reviewing; it cannot prove that something will or will not break.
- It does not query Packagist, so it cannot tell you which packages have newer versions. It only knows the abandoned flags already stored in `composer.lock` and a small list of well-known legacy packages.
- Dynamic code (for example helper calls built from strings) is not detected.

Always read the official upgrade guide for each step and run your test suite after every upgrade.

## Keeping the data current

Support dates are in [`src/laravel_upgrade_checker/data.py`](src/laravel_upgrade_checker/data.py), with the date they were last checked against [Laravel's support policy](https://laravel.com/docs/master/releases) and [PHP's supported versions](https://www.php.net/supported-versions.php). When a new Laravel or PHP version ships, add a row there and bump `DATA_LAST_VERIFIED`. If a project is on a Laravel version newer than the tool's data, the report tells you to update the tool.

## Development

```bash
python -m unittest discover -s tests -v
```

To add a rule, append a `LineRule` or `FileRule` to `rules.py` and add a matching case to `tests/test_checker.py`.

## About

Maintained by the team at [Cubet](https://cubettech.com/). Planning a Laravel upgrade? Read the [Laravel Modernization Decision Framework](https://cubettech.com/resources/blog/laravel-modernization-decision-framework/).
