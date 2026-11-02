#!/usr/bin/env python3
"""Check a .gdextension file against the libraries on disk.

Usage:
  check_gdextension.py path/to/name.gdextension [--project DIR] [--require linux.x86_64,windows.x86_64]

Reports:
  - missing entry_symbol or compatibility_minimum
  - library and dependency paths that don't exist
  - entry_symbol not found in a library that exists
  - a platform and architecture with a debug key but no release key, or the reverse
  - a key and a file name that disagree about debug and release
  - a platform named in --require with a missing library

A platform and architecture (and precision or threads variant) with no file for any of
its keys, even with the lib prefix added or removed, counts as not built yet: it is listed, not reported, unless --require names it.

Exit codes: 0 no problems, 1 problems found, 2 bad input.
"""

import argparse
import json
import os
import sys

PLATFORMS = {"linux", "windows", "macos", "android", "ios", "web", "visionos"}
ARCHES = {"x86_32", "x86_64", "arm32", "arm64", "rv64", "wasm32", "universal", "ppc64"}


def parse(text):
    """Parse the INI-like .gdextension format, with { ... } values on several lines."""
    sections = {}
    section = None
    pending_key = None
    pending = []
    depth = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if pending_key is not None:
            pending.append(raw)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                sections[section][pending_key] = parse_value("\n".join(pending), lineno)
                pending_key = None
                pending = []
            continue
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            sections.setdefault(section, {})
            continue
        if "=" not in line or section is None:
            raise ValueError("line %d: expected key = value inside a [section]" % lineno)
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        depth = value.count("{") - value.count("}")
        if depth > 0:
            pending_key = key
            pending = [value]
            continue
        sections[section][key] = parse_value(value, lineno)
    if pending_key is not None:
        raise ValueError("unclosed { for key %s" % pending_key)
    return sections


def parse_value(value, lineno):
    value = value.strip()
    if value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("line %d: can't read dictionary: %s" % (lineno, error))
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    return value


def tags_of(key):
    tags = key.split(".")
    platform = next((t for t in tags if t in PLATFORMS), None)
    arch = next((t for t in tags if t in ARCHES), None)
    build = next((t for t in tags if t in ("debug", "release", "editor")), None)
    variant = tuple(sorted(t for t in tags if t in ("single", "double", "threads", "nothreads")))
    return platform, arch, build, variant


def resolve(path, gdext_dir, project_dir):
    if path.startswith("res://"):
        return os.path.join(project_dir, path[len("res://"):])
    return os.path.normpath(os.path.join(gdext_dir, path))


def find_project_dir(start):
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, "project.godot")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def check(gdext_path, project_dir=None, require=()):
    problems = []
    try:
        with open(gdext_path, encoding="utf-8") as handle:
            sections = parse(handle.read())
    except (OSError, ValueError) as error:
        raise ValueError("%s: %s" % (gdext_path, error))

    gdext_dir = os.path.dirname(os.path.abspath(gdext_path))
    if project_dir is None:
        project_dir = find_project_dir(gdext_dir)
    if project_dir is None:
        raise ValueError("no project.godot above %s; pass --project" % gdext_path)

    config = sections.get("configuration", {})
    symbol = config.get("entry_symbol")
    if not symbol:
        problems.append("[configuration] has no entry_symbol")
    if not config.get("compatibility_minimum"):
        problems.append("[configuration] has no compatibility_minimum")

    libraries = sections.get("libraries", {})
    if not libraries:
        problems.append("[libraries] is empty")

    groups = {}
    for key, path in libraries.items():
        platform, arch, build, variant = tags_of(key)
        if platform is None:
            problems.append("%s: no platform tag (one of %s)" % (key, ", ".join(sorted(PLATFORMS))))
            continue
        full = resolve(path, gdext_dir, project_dir)
        groups.setdefault((platform, arch, variant), []).append((key, path, build, full, os.path.exists(full)))

    required = []
    for wanted in require:
        platform, arch = (wanted.split(".", 1) + [None])[:2]
        required.append((platform, arch))

    def is_required(platform, arch, variant):
        if variant and variant not in (("single",), ("threads",)):
            return False
        return any(p == platform and (a is None or arch in (a, None)) for p, a in required)

    not_built = []
    for (platform, arch, variant), entries in sorted(groups.items(), key=str):
        label = ".".join(t for t in (platform, arch) + variant if t)
        built = any(exists or prefix_hint(full) for _key, _path, _build, full, exists in entries)
        if not built and not is_required(platform, arch, variant):
            not_built.append(label)
            continue
        found = set()
        for key, path, build, full, exists in entries:
            name = os.path.basename(path)
            if build == "release" and "template_debug" in name:
                problems.append("%s is a release key but points to a debug library: %s" % (key, path))
            if build == "debug" and "template_release" in name:
                problems.append("%s is a debug key but points to a release library: %s" % (key, path))
            if not exists:
                problems.append("%s: file not found: %s%s" % (key, path, prefix_hint(full)))
                continue
            found.add(build)
            if symbol and os.path.isfile(full):
                with open(full, "rb") as handle:
                    if symbol.encode() not in handle.read():
                        problems.append("%s: entry_symbol %s not found in %s" % (key, symbol, path))
        builds = {build for _key, _path, build, _full, _exists in entries}
        if None not in builds:
            if "release" not in builds:
                problems.append("%s has a debug library but no release key: release exports won't load it" % label)
            if "debug" not in builds:
                problems.append("%s has a release library but no debug key: the editor won't load it" % label)

    for platform, arch in required:
        if not any(p == platform and (arch is None or a in (arch, None)) for p, a, _v in groups):
            problems.append("required %s has no [libraries] key" % ".".join(t for t in (platform, arch) if t))

    for key, deps in sections.get("dependencies", {}).items():
        if not isinstance(deps, dict):
            problems.append("[dependencies] %s: value must be a { \"path\": \"target dir\" } dictionary" % key)
            continue
        for path in deps:
            if not os.path.exists(resolve(path, gdext_dir, project_dir)):
                problems.append("[dependencies] %s: file not found: %s" % (key, path))

    return problems, not_built


def prefix_hint(full):
    folder, name = os.path.split(full)
    other = name[3:] if name.startswith("lib") else "lib" + name
    if os.path.exists(os.path.join(folder, other)):
        return " (%s exists: MinGW keeps the lib prefix, MSVC drops it)" % other
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a .gdextension file against the libraries on disk.")
    parser.add_argument("gdextension")
    parser.add_argument("--project", help="Godot project folder (default: the nearest folder with project.godot)")
    parser.add_argument("--require", default="", help="Comma-separated platform.arch list that must have debug and release libraries")
    args = parser.parse_args(argv)
    require = [r.strip() for r in args.require.split(",") if r.strip()]
    try:
        problems, not_built = check(args.gdextension, args.project, require)
    except ValueError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    if not_built:
        print("NOT BUILT (no file for any of their keys, ignored): " + ", ".join(not_built))
    for problem in problems:
        print("PROBLEM " + problem)
    if not problems:
        print("OK " + args.gdextension)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
