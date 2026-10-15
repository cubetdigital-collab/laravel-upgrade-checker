import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from laravel_upgrade_checker import scanner  # noqa: E402
from laravel_upgrade_checker.analysis import analyze  # noqa: E402
from laravel_upgrade_checker.cli import main  # noqa: E402
from laravel_upgrade_checker.report import render_json, render_markdown, render_text  # noqa: E402

TODAY = date(2026, 10, 15)


def write(root, rel, content):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def make_legacy_project(root, lock=True):
    composer = {
        "name": "acme/shop",
        "require": {
            "php": "^8.1",
            "laravel/framework": "^10.10",
            "fruitcake/laravel-cors": "^3.0",
            "laravel/helpers": "^1.6",
        },
        "require-dev": {"fzaninotto/faker": "^1.9"},
    }
    write(root, "composer.json", json.dumps(composer))
    if lock:
        write(root, "composer.lock", json.dumps({
            "packages": [
                {"name": "laravel/framework", "version": "v10.48.4"},
                {"name": "old/thing", "version": "1.0.0", "abandoned": "new/thing"},
            ],
            "packages-dev": [],
        }))
    write(root, ".php-version", "8.1.27\n")
    write(root, "routes/web.php", "<?php\nRoute::get('/', 'HomeController@index');\n// Route::get('/x', 'OldController@skip');\n")
    write(root, "app/Models/User.php", "<?php\nclass User {\n    protected $dates = ['seen_at'];\n}\n")
    write(root, "app/Jobs/Sync.php", "<?php\nSync::dispatchNow($x);\n$y = array_get($a, 'b');\n$k = env('STRIPE_KEY');\n")
    write(root, "app/Http/Kernel.php", "<?php\nclass Kernel {\n    protected $routeMiddleware = [];\n}\n")
    write(root, "database/migrations/2022_add.php", "<?php\n$table->string('name')->nullable()->change();\n")
    write(root, "resources/views/layout.blade.php", "<link href=\"{{ mix('css/app.css') }}\">\n")
    write(root, "webpack.mix.js", "mix.js('a','b');\n")
    write(root, "tests/Feature/ExampleTest.php", "<?php\nclass ExampleTest {}\n")
    write(root, "config/app.php", "<?php\nreturn ['key' => env('APP_KEY')];\n")
    write(root, "vendor/pkg/Skip.php", "<?php\nInput::get('x');\n")


class ConstraintTests(unittest.TestCase):
    def test_major_bounds(self):
        self.assertEqual(scanner.constraint_major_bounds("^10.0"), (10, 10))
        self.assertEqual(scanner.constraint_major_bounds("^9.19|^10.0"), (9, 10))
        self.assertEqual(scanner.constraint_major_bounds(">=9.0 <11"), (9, 10))
        self.assertEqual(scanner.constraint_major_bounds("10.*"), (10, 10))
        self.assertEqual(scanner.constraint_major_bounds("~11.0"), (11, 11))
        self.assertEqual(scanner.constraint_major_bounds(">=9.0"), (9, None))
        self.assertEqual(scanner.constraint_major_bounds("^8.0 || ^9.0"), (8, 9))

    def test_lowest_php(self):
        self.assertEqual(scanner.lowest_php("^8.1"), (8, 1))
        self.assertEqual(scanner.lowest_php("^7.3|^8.0"), (7, 3))
        self.assertEqual(scanner.lowest_php(">=8.2"), (8, 2))
        self.assertEqual(scanner.lowest_php("~8.1.0"), (8, 1))
        self.assertIsNone(scanner.lowest_php("*"))

    def test_php_status(self):
        self.assertEqual(scanner.php_status((8, 1), TODAY)[0], "end-of-life")
        self.assertEqual(scanner.php_status((8, 2), TODAY)[0], "ending-soon")
        self.assertEqual(scanner.php_status((8, 4), TODAY)[0], "supported")
        self.assertEqual(scanner.php_status((7, 2), TODAY)[0], "end-of-life")


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        make_legacy_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_laravel_and_php_detection(self):
        report = analyze(self.root, today=TODAY)
        self.assertEqual(report.laravel["version"], "10.48.4")
        self.assertFalse(report.laravel["estimated"])
        self.assertEqual(report.laravel["status"], "end-of-life")
        self.assertEqual(report.laravel["majors_behind"], 3)
        self.assertEqual(report.php["effective"], "8.1")
        self.assertEqual(report.php["status"], "end-of-life")

    def test_upgrade_path_and_php_gate(self):
        report = analyze(self.root, today=TODAY)
        self.assertEqual([s["to"] for s in report.upgrade_path], [11, 12, 13])
        self.assertFalse(report.upgrade_path[0]["php_ok"])  # Laravel 11 needs PHP 8.2
        report = analyze(self.root, target=11, today=TODAY)
        self.assertEqual([s["to"] for s in report.upgrade_path], [11])

    def test_findings(self):
        report = analyze(self.root, today=TODAY)
        ids = {f.rule_id for f in report.findings}
        for expected in (
            "string-controller-actions", "model-dates-property", "dispatch-now", "legacy-global-helpers",
            "env-outside-config", "route-middleware-property", "migration-change", "mix-helper",
            "webpack-mix", "http-kernel",
        ):
            self.assertIn(expected, ids)
        self.assertNotIn("input-facade", ids)  # only present inside vendor/, which is skipped
        by_id = {f.rule_id: f for f in report.findings}
        self.assertEqual(by_id["string-controller-actions"].count, 1)  # commented-out line ignored
        self.assertEqual(by_id["env-outside-config"].count, 1)  # config/app.php is allowed
        self.assertEqual(by_id["dispatch-now"].examples[0], ("app/Jobs/Sync.php", 2))
        self.assertNotIn("no-tests", ids)

    def test_packages(self):
        report = analyze(self.root, today=TODAY)
        names = {p["name"]: p for p in report.packages}
        self.assertIn("fruitcake/laravel-cors", names)
        self.assertIn("fzaninotto/faker", names)
        self.assertIn("laravel/helpers", names)
        self.assertIn("old/thing", names)  # abandoned flag from composer.lock
        self.assertFalse(names["old/thing"]["direct"])

    def test_score_is_bounded_and_low_for_legacy(self):
        report = analyze(self.root, today=TODAY)
        self.assertTrue(0 <= report.score <= 100)
        self.assertLess(report.score, 40)
        self.assertEqual(report.rating, "At risk")

    def test_missing_lock_estimates_version(self):
        with tempfile.TemporaryDirectory() as other:
            make_legacy_project(other, lock=False)
            report = analyze(other, today=TODAY)
            self.assertTrue(report.laravel["estimated"])
            self.assertEqual(report.laravel["major"], 10)
            self.assertIn("no-composer-lock", {f.rule_id for f in report.findings})

    def test_up_to_date_project_scores_high(self):
        with tempfile.TemporaryDirectory() as clean:
            write(clean, "composer.json", json.dumps({"require": {"php": "^8.3", "laravel/framework": "^13.0"}}))
            write(clean, "composer.lock", json.dumps({"packages": [{"name": "laravel/framework", "version": "v13.1.1"}]}))
            write(clean, ".php-version", "8.4\n")
            write(clean, "tests/Feature/ExampleTest.php", "<?php\n")
            write(clean, "app/Models/User.php", "<?php\nclass User {}\n")
            report = analyze(clean, today=TODAY)
            self.assertEqual(report.score, 100)
            self.assertEqual(report.upgrade_path, [])
            self.assertEqual(report.rating, "Healthy")

    def test_renderers(self):
        report = analyze(self.root, today=TODAY)
        text = render_text(report)
        self.assertIn("MODERNIZATION SCORE", text)
        self.assertIn("10 -> 11", text)
        text.encode("ascii")  # Windows consoles: keep output ASCII
        markdown = render_markdown(report)
        self.assertIn("# Laravel Upgrade Report", markdown)
        payload = json.loads(render_json(report))
        self.assertEqual(payload["laravel"]["major"], 10)
        self.assertTrue(payload["findings"])


class ErrorTests(unittest.TestCase):
    def test_not_a_laravel_project(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "composer.json", json.dumps({"require": {"symfony/console": "^6.0"}}))
            with self.assertRaises(scanner.ProjectError):
                analyze(root, today=TODAY)

    def test_missing_composer_json(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(scanner.ProjectError):
                analyze(root, today=TODAY)

    def test_lumen_message(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "composer.json", json.dumps({"require": {"laravel/lumen-framework": "^9.0"}}))
            with self.assertRaises(scanner.ProjectError) as ctx:
                analyze(root, today=TODAY)
            self.assertIn("Lumen", str(ctx.exception))


class CliTests(unittest.TestCase):
    def test_exit_codes_and_output_file(self):
        with tempfile.TemporaryDirectory() as root:
            make_legacy_project(root)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main([root, "--today", "2026-10-15", "--fail-under", "70"])
            self.assertEqual(code, 1)
            self.assertIn("MODERNIZATION SCORE", buffer.getvalue())

            out_file = os.path.join(root, "report.md")
            with redirect_stdout(io.StringIO()):
                code = main([root, "-f", "markdown", "-o", out_file, "--today", "2026-10-15"])
            self.assertEqual(code, 0)
            with open(out_file, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("# Laravel Upgrade Report"))

    def test_bad_path_returns_2(self):
        self.assertEqual(main(["/definitely/not/here"]), 2)


if __name__ == "__main__":
    unittest.main()
