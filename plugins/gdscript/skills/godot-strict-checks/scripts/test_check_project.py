#!/usr/bin/env python3
"""Tests for check_project.py against a real headless Godot. Run: python3 test_check_project.py"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_project  # noqa: E402

GODOT = os.environ.get("GODOT", "godot")
STRICT = """config_version=5

[debug]

gdscript/warnings/untyped_declaration=2
gdscript/warnings/unsafe_method_access=2
gdscript/warnings/unsafe_property_access=2
"""


@unittest.skipUnless(shutil.which(GODOT), "Godot not on PATH")
class CheckProjectTest(unittest.TestCase):
    def make(self, settings, files):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root))
        (root / "project.godot").write_text(settings)
        for name, source in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(source)
        return root

    FILES = {
        "enemy.gd": "class_name Enemy extends Node\nfunc die() -> void:\n\tpass\n",
        "uses_enemy.gd": "extends Node\n@export var e: Enemy\nfunc _ready() -> void:\n\te.die()\n",
        "made_up.gd": "extends Node2D\nfunc _ready() -> void:\n\tvar s: Sprite2D = $S\n\ts.velocty = 3\n",
        "addons/x/loose.gd": "extends Node\nvar untyped = 1\n",
    }

    def test_strict_project_catches_made_up_members_only(self):
        failures = check_project.check(self.make(STRICT, self.FILES), GODOT)
        self.assertEqual(list(failures), ["res://made_up.gd"])
        self.assertTrue(any("velocty" in line for line in failures["res://made_up.gd"]))

    def test_default_warnings_let_made_up_members_through(self):
        self.assertEqual(check_project.check(self.make("config_version=5\n", self.FILES), GODOT), {})


if __name__ == "__main__":
    unittest.main()
