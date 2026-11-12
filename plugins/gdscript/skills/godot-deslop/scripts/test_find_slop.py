#!/usr/bin/env python3
"""Tests for find_slop.py. Run: python3 test_find_slop.py"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_slop  # noqa: E402


def rules_of(source):
    return [rule for _, rule, _ in find_slop.check_text(source)]


SLOP = '''extends Node


# Called when the node enters the scene tree for the first time.
func _ready() -> void:
	pass


# Called every frame. 'delta' is the elapsed time since the previous frame.
func _process(delta: float) -> void:
	pass


func hit(target: Node) -> void:
	if target != null and is_instance_valid(target):
		if target.has_method("take_damage"):
			target.take_damage(1)
	if is_dead == false:
		get_node("/root/Main/HUD").refresh()
	# TODO: implement knockback
	var tween := Tween.new()
'''

CLEAN = '''extends Node

@export var hud: Hud


func _ready() -> void:
	# Waits a frame so siblings exist.
	await get_tree().process_frame
	hud.refresh()


func hit(target: Hurtbox) -> void:
	if is_instance_valid(target) and not is_dead:
		target.take_damage(1)
	var color := "#ffcc00"  # TODO: move to the theme
	if node.has_method("legacy_api"):  # noslop: plugin without types
		pass
'''


class FindSlopTest(unittest.TestCase):
    def test_flags_each_rule(self):
        self.assertEqual(
            sorted(rules_of(SLOP)),
            sorted([
                "template-comment", "empty-callback",
                "template-comment", "empty-callback",
                "null-and-valid", "has-method", "bool-compare",
                "root-path", "placeholder", "tween-new",
            ]),
        )

    def test_clean_code_has_no_findings(self):
        self.assertEqual(rules_of(CLEAN), [])

    def test_empty_process_mentions_frame_cost(self):
        message = [m for _, r, m in find_slop.check_text(SLOP) if r == "empty-callback"][1]
        self.assertIn("every frame", message)

    def test_get_compared_to_false_is_kept(self):
        self.assertEqual(rules_of('if enemy.get("alive") == false:\n'), [])

    def test_tests_may_check_has_method(self):
        self.assertEqual(find_slop.check_text('expect(n.has_method("hit"))\n', is_test=True), [])

    def test_callback_with_a_body_is_kept(self):
        self.assertEqual(rules_of("func _ready() -> void:\n\tpass\n\tstart()\n"), [])

    def test_other_root_path_forms(self):
        for line in ('$"/root/Game"', "get_tree().root.get_node(\"Game\")", "get_tree().get_root().get_node(\"Game\")"):
            self.assertEqual(rules_of(f"var g := {line}\n"), ["root-path"], line)

    def test_skips_addons_and_reports_exit_code(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        (root / "addons" / "x").mkdir(parents=True)
        (root / "addons" / "x" / "a.gd").write_text(SLOP)
        (root / "ok.gd").write_text(CLEAN)
        self.assertEqual(find_slop.main([str(root)]), 0)
        (root / "bad.gd").write_text(SLOP)
        self.assertEqual(find_slop.main([str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
