"""Reference data used by the checker.

Update this file when Laravel or PHP publish new support dates.
Sources:
  * Laravel support policy: https://laravel.com/docs/master/releases
  * PHP supported versions:  https://www.php.net/supported-versions.php
"""

from __future__ import annotations

from typing import Dict, Tuple

# Date the tables below were last checked against the official pages.
DATA_LAST_VERIFIED = "2026-10-15"

UPGRADE_GUIDE_URL = "https://laravel.com/docs/{major}.x/upgrade"

# Laravel major releases.
# bugfix_until / security_until are the official end dates. Laravel 13 lists its
# bug-fix end as "Q3 2027"; 2027-09-30 is used as an approximation.
LARAVEL_RELEASES: Dict[int, Dict[str, str]] = {
    13: {"released": "2026-03-17", "bugfix_until": "2027-09-30", "security_until": "2028-03-17", "php_min": "8.3", "php_max": "8.5"},
    12: {"released": "2025-02-24", "bugfix_until": "2026-08-13", "security_until": "2027-02-24", "php_min": "8.2", "php_max": "8.5"},
    11: {"released": "2024-03-12", "bugfix_until": "2025-09-03", "security_until": "2026-03-12", "php_min": "8.2", "php_max": "8.4"},
    10: {"released": "2023-02-14", "bugfix_until": "2024-08-06", "security_until": "2025-02-04", "php_min": "8.1", "php_max": "8.3"},
    9: {"released": "2022-02-08", "bugfix_until": "2023-08-08", "security_until": "2024-02-06", "php_min": "8.0", "php_max": "8.2"},
    8: {"released": "2020-09-08", "bugfix_until": "2022-07-26", "security_until": "2023-01-24", "php_min": "7.3", "php_max": "8.1"},
}

# Last day of security support for each PHP release line.
PHP_SECURITY_EOL: Dict[Tuple[int, int], str] = {
    (7, 4): "2022-11-28",
    (8, 0): "2023-11-26",
    (8, 1): "2025-12-31",
    (8, 2): "2026-12-31",
    (8, 3): "2027-12-31",
    (8, 4): "2028-12-31",
    (8, 5): "2029-12-31",
}

# Packages that commonly show up in older Laravel projects and deserve attention.
# name -> (severity, what is wrong, what to do)
KNOWN_PACKAGE_ISSUES: Dict[str, Tuple[str, str, str]] = {
    "laravel/lumen-framework": (
        "warning",
        "Lumen is no longer actively developed by the Laravel team.",
        "Plan a migration to full Laravel (optionally with Octane for speed).",
    ),
    "fruitcake/laravel-cors": (
        "warning",
        "Abandoned. CORS handling has been built into Laravel since version 9.",
        "Remove the package and use the built-in HandleCors middleware with config/cors.php.",
    ),
    "barryvdh/laravel-cors": (
        "warning",
        "Abandoned. CORS handling is built into Laravel 9 and newer.",
        "Remove the package and use the built-in HandleCors middleware.",
    ),
    "fideloper/proxy": (
        "warning",
        "Replaced by the built-in TrustProxies middleware in Laravel 9.",
        "Remove the package and switch to Illuminate\\Http\\Middleware\\TrustProxies.",
    ),
    "facade/ignition": (
        "warning",
        "Abandoned. Replaced by spatie/laravel-ignition.",
        "Swap to spatie/laravel-ignition (required from Laravel 9).",
    ),
    "fzaninotto/faker": (
        "warning",
        "Abandoned. Replaced by fakerphp/faker.",
        "Swap to fakerphp/faker.",
    ),
    "swiftmailer/swiftmailer": (
        "warning",
        "Abandoned. Laravel 9 and newer send mail through Symfony Mailer.",
        "Remove direct SwiftMailer usage and move to Symfony Mailer / Laravel's Mail API.",
    ),
    "laravel/legacy-factories": (
        "info",
        "Compatibility layer for pre-Laravel-8 model factories.",
        "Convert factories to the class-based syntax, then remove the package.",
    ),
    "laravel/helpers": (
        "info",
        "Compatibility layer for global helpers removed in Laravel 6 (array_get, str_slug, ...).",
        "Replace helpers with Arr:: / Str:: calls, then remove the package.",
    ),
    "doctrine/dbal": (
        "info",
        "Laravel 11 and newer no longer need doctrine/dbal to modify columns.",
        "Remove it if it was only added for schema changes.",
    ),
    "laravel/breeze": (
        "info",
        "Laravel's release notes say Breeze no longer receives updates.",
        "Fine for existing apps; use the current starter kits for new projects.",
    ),
    "laravel/jetstream": (
        "info",
        "Laravel's release notes say Jetstream no longer receives updates.",
        "Fine for existing apps; use the current starter kits for new projects.",
    ),
}
