"""Static-analysis rules.

Each rule has a `since` value: the Laravel major version where the pattern
starts to cause problems (0 = general best practice). Rules are plain regexes,
so results are hints to review, not proof of breakage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class LineRule:
    id: str
    title: str
    severity: str  # "critical" | "warning" | "info"
    since: int
    advice: str
    pattern: "re.Pattern[str]"
    suffix: str = ".php"
    include: Tuple[str, ...] = ()  # only files whose relative path starts with one of these
    exclude: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FileRule:
    id: str
    title: str
    severity: str
    since: int
    advice: str
    path: str  # relative to the project root


def _re(pattern: str) -> "re.Pattern[str]":
    return re.compile(pattern)


LINE_RULES = (
    LineRule(
        id="legacy-global-helpers",
        title="Global array_*/str_* helpers removed in Laravel 6",
        severity="warning",
        since=6,
        advice="Use Illuminate\\Support\\Arr and Str (for example Arr::get, Str::slug). "
        "These calls only work while the laravel/helpers package is installed.",
        pattern=_re(
            r"(?<![\w:>$\\])(?:array_get|array_set|array_has|array_pluck|array_only|array_except|"
            r"array_dot|array_flatten|array_forget|array_pull|str_slug|str_random|str_limit|"
            r"str_plural|str_singular|snake_case|camel_case|studly_case|kebab_case)\s*\("
        ),
    ),
    LineRule(
        id="input-facade",
        title="Input facade removed in Laravel 6",
        severity="critical",
        since=6,
        advice="Use $request->input() or the Request facade instead of Input::.",
        pattern=_re(r"(?<![\w\\])Input::|Illuminate\\Support\\Facades\\Input\b"),
    ),
    LineRule(
        id="string-controller-actions",
        title="String-style controller actions in routes (Controller@method)",
        severity="warning",
        since=8,
        advice="Use [UserController::class, 'index'] so routes work without the old $namespace prefix.",
        pattern=_re(r"""['"](?:[\w\\]+\\)?\w+Controller@\w+['"]"""),
        include=("routes/",),
    ),
    LineRule(
        id="legacy-factories",
        title="Pre-Laravel-8 model factories (factory() helper / $factory->define)",
        severity="critical",
        since=8,
        advice="Convert to class-based factories (HasFactory). The old syntax needs laravel/legacy-factories.",
        pattern=_re(r"\$factory->define\(|(?<![\w:>$])factory\(\s*[\w\\]+::class"),
    ),
    LineRule(
        id="dispatch-now",
        title="dispatchNow() / dispatch_now() removed in Laravel 9",
        severity="critical",
        since=9,
        advice="Use dispatchSync() / dispatch_sync().",
        pattern=_re(r"\bdispatchNow\s*\(|(?<![\w:>$])dispatch_now\s*\("),
    ),
    LineRule(
        id="swiftmailer",
        title="SwiftMailer classes (Swift_*) removed in Laravel 9",
        severity="critical",
        since=9,
        advice="Laravel 9+ uses Symfony Mailer. Move custom mail code to the Mail facade / Symfony Mime classes.",
        pattern=_re(r"\bSwift_[A-Za-z]+"),
    ),
    LineRule(
        id="mix-helper",
        title="Laravel Mix mix() helper in Blade views",
        severity="info",
        since=9,
        advice="Laravel Mix is superseded by Vite. Replace mix() with the @vite directive when migrating.",
        pattern=_re(r"(?<![\w:>$])mix\(\s*['\"]"),
        suffix=".blade.php",
    ),
    LineRule(
        id="model-dates-property",
        title="Eloquent $dates property (deprecated in Laravel 10)",
        severity="warning",
        since=10,
        advice="Move these attributes into $casts (for example 'published_at' => 'datetime').",
        pattern=_re(r"^\s*(?:protected|public|private)\s+(?:array\s+)?\$dates\s*="),
        include=("app/",),
    ),
    LineRule(
        id="route-middleware-property",
        title="Http Kernel $routeMiddleware (renamed in Laravel 10)",
        severity="info",
        since=10,
        advice="Rename to $middlewareAliases. The old name still works but is deprecated.",
        pattern=_re(r"\$routeMiddleware\b"),
        include=("app/",),
    ),
    LineRule(
        id="migration-change",
        title="Column changes with ->change() in migrations",
        severity="warning",
        since=11,
        advice="Laravel 11 modifies columns natively and drops any attribute you do not repeat "
        "(nullable, default, and so on). Re-check every ->change() migration; doctrine/dbal is no longer needed.",
        pattern=_re(r"->change\(\)"),
        include=("database/migrations/",),
    ),
    LineRule(
        id="carbon-diff-in",
        title="Carbon diffIn*() calls (behaviour changed in Carbon 3)",
        severity="info",
        since=11,
        advice="Carbon 3 returns floats and signed values. Check code that compares or displays these numbers.",
        pattern=_re(r"->diffIn(?:Years|Months|Weeks|Days|Hours|Minutes|Seconds)\s*\("),
    ),
    LineRule(
        id="env-outside-config",
        title="env() used outside config files",
        severity="warning",
        since=0,
        advice="env() returns null once config is cached. Read the value in config/*.php and use config('...') in code.",
        pattern=_re(r"(?<![\w>:$])env\(\s*['\"]"),
        include=("app/", "routes/", "resources/"),
    ),
)


FILE_RULES = (
    FileRule(
        id="webpack-mix",
        title="webpack.mix.js found (Laravel Mix)",
        severity="warning",
        since=9,
        advice="New Laravel apps use Vite. Plan a move from Mix to Vite (laravel-vite-plugin).",
        path="webpack.mix.js",
    ),
    FileRule(
        id="http-kernel",
        title="app/Http/Kernel.php present (pre-Laravel-11 skeleton)",
        severity="info",
        since=11,
        advice="Laravel 11+ configures middleware in bootstrap/app.php. Upgraded apps may keep the Kernel; "
        "migrating gives the slimmer structure.",
        path="app/Http/Kernel.php",
    ),
    FileRule(
        id="exception-handler",
        title="app/Exceptions/Handler.php present (pre-Laravel-11 skeleton)",
        severity="info",
        since=11,
        advice="Laravel 11+ configures exception handling in bootstrap/app.php.",
        path="app/Exceptions/Handler.php",
    ),
    FileRule(
        id="console-kernel",
        title="app/Console/Kernel.php present (pre-Laravel-11 skeleton)",
        severity="info",
        since=11,
        advice="Laravel 11+ defines scheduled tasks in routes/console.php.",
        path="app/Console/Kernel.php",
    ),
    FileRule(
        id="creates-application",
        title="tests/CreatesApplication.php present (pre-Laravel-11 test skeleton)",
        severity="info",
        since=11,
        advice="Newer skeletons no longer need this trait in tests/TestCase.php.",
        path="tests/CreatesApplication.php",
    ),
)
