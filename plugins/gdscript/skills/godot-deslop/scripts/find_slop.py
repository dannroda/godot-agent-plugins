#!/usr/bin/env python3
"""Flags generated-code noise in GDScript that the Godot parser accepts.

    python3 find_slop.py PATH...        (files or folders; skips addons/ and .godot/)

Prints FILE:LINE: RULE: message, and exits 1 when it finds something.
Add `# noslop` to a line to keep it on purpose. Parse errors and missing
types are the parser's job: see godot-strict-checks.
"""
import re
import sys
from pathlib import Path

TEMPLATE_COMMENTS = (
    "# Called when the node enters the scene tree for the first time.",
    "# Called every frame. 'delta' is the elapsed time since the previous frame.",
)
CALLBACKS = r"_ready|_process|_physics_process|_input|_unhandled_input|_unhandled_key_input|_enter_tree|_exit_tree|_init"
EMPTY_FUNC = re.compile(rf"^func\s+({CALLBACKS})\s*\(")
LINE_RULES = [
    # `get("x") == false` is not slop: get() returns null for a missing property.
    ("bool-compare", re.compile(r"^(?!.*\bget\().*[!=]=\s*(true|false)\b"),
     "compare to true/false: use the value, or `not value`"),
    ("null-and-valid", re.compile(r"(\w[\w.]*)\s*!=\s*null\s+and\s+is_instance_valid\(\s*\1\s*\)|is_instance_valid\((\w[\w.]*)\)\s+and\s+\2\s*!=\s*null"),
     "is_instance_valid() already returns false for null"),
    ("root-path", re.compile(r"""get_node(_or_null)?\(\s*["']/root/|\$["']?/root/|get_(tree\(\)\.)?(get_)?root\(?\)?\.get_node"""),
     "absolute /root/ path: use the autoload's name, an @export or setup() injection"),
    ("has-method", re.compile(r"\.has_method\(|^\s*has_method\("),
     "duck typing: a typed cast (`as Type`), `is Type` or a component check"),
    ("tween-new", re.compile(r"\bTween\.new\(\)"),
     "Tween.new() makes an invalid tween (runtime error): create_tween()"),
    ("placeholder", re.compile(r"#\s*(TODO:?\s*implement|implement (this|me|here)|your code here|add (your )?logic here|\.\.\.\s*$)", re.I),
     "placeholder left in: implement it or delete it"),
]


def check_text(text, is_test=False):
    """Returns (line, rule, message) for each finding in one GDScript source.
    Tests may use has_method() to check that an API exists."""
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines, 1):
        if "# noslop" in line:
            continue
        stripped = line.strip()
        if stripped in TEMPLATE_COMMENTS:
            found.append((i, "template-comment", "editor template comment: delete it"))
        code = stripped.split("#", 1)[0] if not stripped.startswith("#") else ""
        for rule, pattern, message in LINE_RULES:
            target = stripped if rule == "placeholder" else code
            if pattern.search(target) and not (is_test and rule == "has-method"):
                found.append((i, rule, message))
        match = EMPTY_FUNC.match(line)
        if match and _body_is_pass(lines, i):
            hint = " (an empty _process/_physics_process still runs every frame)" if "process" in match.group(1) else ""
            found.append((i, "empty-callback", f"{match.group(1)}() only passes: delete it{hint}"))
    return found


def _body_is_pass(lines, header_line):
    body = []
    for line in lines[header_line:]:
        if line.strip() and not line[0].isspace():
            break
        if line.strip() and not line.strip().startswith("#"):
            body.append(line.strip())
    return body == ["pass"]


def gd_files(paths):
    for path in map(Path, paths):
        if path.is_file():
            yield path
        else:
            for file in sorted(path.rglob("*.gd")):
                if not {"addons", ".godot"} & set(file.relative_to(path).parts):
                    yield file


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    count = 0
    for file in gd_files(argv):
        for line, rule, message in check_text(file.read_text(encoding="utf-8"), file.name.startswith("test_")):
            print(f"{file}:{line}: {rule}: {message}")
            count += 1
    print(f"{count} finding(s)", file=sys.stderr)
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
