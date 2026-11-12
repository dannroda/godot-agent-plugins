#!/usr/bin/env python3
"""Parses every GDScript file of a Godot 4 project headlessly, with the
project's own warning levels, and fails if any file doesn't compile.

    python3 check_project.py PROJECT_DIR [--godot PATH]

Skips addons/ and .godot/. Imports the project first when its class cache
is missing, so `class_name` types resolve. Uses $GODOT, else `godot`.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def scripts_of(project):
    for file in sorted(project.rglob("*.gd")):
        if not {"addons", ".godot"} & set(file.relative_to(project).parts):
            yield file


def run(godot, project, *args):
    return subprocess.run([godot, "--headless", "--path", str(project), *args],
                          capture_output=True, text=True, timeout=120)


def check(project, godot):
    """Returns {res:// path: [error lines]} for each script that fails."""
    if not (project / ".godot" / "global_script_class_cache.cfg").exists():
        run(godot, project, "--import")
    failures = {}
    # shortcut: one Godot launch per file (~0.25 s each); fine to a few hundred scripts.
    for file in scripts_of(project):
        res = "res://" + file.relative_to(project).as_posix()
        result = run(godot, project, "--check-only", "--script", res)
        if result.returncode != 0:
            failures[res] = [line.strip() for line in (result.stdout + result.stderr).splitlines()
                             if "SCRIPT ERROR" in line or line.strip().startswith("at: GDScript")]
    return failures


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    args = parser.parse_args(argv)
    if not (args.project / "project.godot").is_file():
        parser.error(f"no project.godot in {args.project}")
    failures = check(args.project.resolve(), args.godot)
    for res, lines in failures.items():
        print(f"FAIL {res}")
        for line in lines:
            print(f"  {line}")
    total = sum(1 for _ in scripts_of(args.project))
    print(f"{len(failures)} of {total} scripts failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
