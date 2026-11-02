#!/usr/bin/env python3
"""Tests for check_gdextension.py. Run: python3 test_check_gdextension.py"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_gdextension as cg  # noqa: E402


def problems_of(*args, **kwargs):
    return cg.check(*args, **kwargs)[0]

GOOD = """[configuration]
entry_symbol = "demo_init"
compatibility_minimum = "4.7"
reloadable = true

[libraries]
; comment
linux.debug.x86_64 = "./linux/libdemo.linux.template_debug.x86_64.so"
linux.release.x86_64 = "./linux/libdemo.linux.template_release.x86_64.so"

[dependencies]
linux.x86_64 = {
    "./linux/libthird.so.1": ""
}
"""


class CheckTest(unittest.TestCase):
    def make(self, gdext, files):
        root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        with open(os.path.join(root, "project.godot"), "w") as handle:
            handle.write("config_version=5\n")
        os.makedirs(os.path.join(root, "bin", "linux"))
        for name, data in files.items():
            with open(os.path.join(root, "bin", name), "wb") as handle:
                handle.write(data)
        path = os.path.join(root, "bin", "demo.gdextension")
        with open(path, "w") as handle:
            handle.write(gdext)
        return path

    def all_files(self):
        return {
            "linux/libdemo.linux.template_debug.x86_64.so": b"\x7fELF...demo_init...",
            "linux/libdemo.linux.template_release.x86_64.so": b"\x7fELF...demo_init...",
            "linux/libthird.so.1": b"\x7fELF",
        }

    def test_good(self):
        path = self.make(GOOD, self.all_files())
        self.assertEqual(problems_of(path), [])
        self.assertEqual(cg.main([path]), 0)

    def test_missing_release(self):
        files = self.all_files()
        del files["linux/libdemo.linux.template_release.x86_64.so"]
        problems = problems_of(self.make(GOOD, files))
        self.assertTrue(any("file not found" in p and "template_release" in p for p in problems), problems)

    def test_debug_only_platform(self):
        text = GOOD.replace('linux.release.x86_64 = "./linux/libdemo.linux.template_release.x86_64.so"\n', "")
        problems = problems_of(self.make(text, self.all_files()))
        self.assertTrue(any("no release key" in p for p in problems), problems)

    def test_wrong_symbol(self):
        files = self.all_files()
        files["linux/libdemo.linux.template_debug.x86_64.so"] = b"\x7fELF...other_init..."
        problems = problems_of(self.make(GOOD, files))
        self.assertTrue(any("entry_symbol demo_init not found" in p for p in problems), problems)

    def test_swapped_build(self):
        text = GOOD.replace("linux.release.x86_64 = \"./linux/libdemo.linux.template_release", "linux.release.x86_64 = \"./linux/libdemo.linux.template_debug")
        problems = problems_of(self.make(text, self.all_files()))
        self.assertTrue(any("release key but points to a debug library" in p for p in problems), problems)

    def test_missing_dependency(self):
        files = self.all_files()
        del files["linux/libthird.so.1"]
        problems = problems_of(self.make(GOOD, files))
        self.assertTrue(any("[dependencies]" in p for p in problems), problems)

    def test_require_platform(self):
        path = self.make(GOOD, self.all_files())
        problems = problems_of(path, require=["windows.x86_64"])
        self.assertIn("required windows.x86_64 has no [libraries] key", problems)
        self.assertEqual(problems_of(path, require=["linux.x86_64"]), [])

    def test_res_paths(self):
        text = GOOD.replace('"./linux/', '"res://bin/linux/')
        self.assertEqual(problems_of(self.make(text, self.all_files())), [])

    def test_missing_configuration(self):
        text = GOOD.replace('entry_symbol = "demo_init"\n', "")
        problems = problems_of(self.make(text, self.all_files()))
        self.assertIn("[configuration] has no entry_symbol", problems)

    def test_unbuilt_platforms_are_listed_not_reported(self):
        text = GOOD.replace("[dependencies]", 'windows.debug.x86_64 = "./windows/demo.windows.template_debug.x86_64.dll"\nwindows.release.x86_64 = "./windows/demo.windows.template_release.x86_64.dll"\n\n[dependencies]')
        path = self.make(text, self.all_files())
        problems, not_built = cg.check(path)
        self.assertEqual(problems, [])
        self.assertEqual(not_built, ["windows.x86_64"])
        problems = problems_of(path, require=["windows.x86_64"])
        self.assertTrue(any("windows.debug.x86_64: file not found" in p for p in problems), problems)

    def test_mingw_prefix_hint(self):
        text = GOOD.replace("[dependencies]", 'windows.debug.x86_64 = "./windows/demo.windows.template_debug.x86_64.dll"\nwindows.release.x86_64 = "./windows/demo.windows.template_release.x86_64.dll"\n\n[dependencies]')
        files = self.all_files()
        files["windows/libdemo.windows.template_debug.x86_64.dll"] = b"MZ demo_init"
        os_path = self.make(text, {})
        root = os.path.dirname(os.path.dirname(os_path))
        os.makedirs(os.path.join(root, "bin", "windows"))
        for name, data in files.items():
            with open(os.path.join(root, "bin", name), "wb") as handle:
                handle.write(data)
        problems = problems_of(os_path)
        self.assertTrue(any("MinGW keeps the lib prefix" in p for p in problems), problems)

    def test_bad_input(self):
        path = self.make("[libraries]\nlinux.x86_64 = {\n", {})
        self.assertEqual(cg.main([path]), 2)
        self.assertEqual(cg.main([path + ".missing"]), 2)


if __name__ == "__main__":
    unittest.main()
