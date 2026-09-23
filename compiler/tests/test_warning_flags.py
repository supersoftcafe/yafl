"""-W flag resolution: the pure name-list -> enabled-category-set logic
shared by main.py's CLI and (mirrored) bootstrap/frontend/warnings.yafl."""
from __future__ import annotations

import warning_flags as wf
from tests.testutil import TimedTestCase as TestCase


class TestResolveEnabledWarnings(TestCase):
    def test_default_set_is_everything_but_unused_parameter(self):
        self.assertEqual(
            {"unused-variable", "discarded-value", "fragile-base"},
            set(wf.resolve_enabled_warnings([])))

    def test_wname_enables_one(self):
        enabled = wf.resolve_enabled_warnings(["unused-parameter"])
        self.assertIn("unused-parameter", enabled)

    def test_wall_enables_every_known_warning(self):
        self.assertEqual(set(wf.KNOWN_WARNINGS), set(wf.resolve_enabled_warnings(["all"])))

    def test_wno_disables_a_default_on_warning(self):
        enabled = wf.resolve_enabled_warnings(["no-fragile-base"])
        self.assertNotIn("fragile-base", enabled)
        self.assertIn("unused-variable", enabled)

    def test_flags_apply_left_to_right(self):
        # -Wall then -Wno-X: X ends up off, matching GCC's left-to-right rule.
        enabled = wf.resolve_enabled_warnings(["all", "no-unused-parameter"])
        self.assertNotIn("unused-parameter", enabled)
        self.assertIn("fragile-base", enabled)
        # Reversed order: -Wno-X then -Wall re-enables X.
        enabled = wf.resolve_enabled_warnings(["no-unused-variable", "all"])
        self.assertIn("unused-variable", enabled)

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            wf.resolve_enabled_warnings(["not-a-real-warning"])
        with self.assertRaises(ValueError):
            wf.resolve_enabled_warnings(["no-not-a-real-warning"])
