# gdextension

- `gdextension-cpp`: start a C++ GDExtension with godot-cpp 10, register classes, properties, signals, enums and virtual methods, and test it headless. Includes `extension_tests.gd`, a test runner with exit codes for CI.
- `gdextension-build`: SCons and CMake builds, Windows and Android cross-compiling, exports, addons and CI. Includes `check_gdextension.py`, which checks a `.gdextension` file against the libraries on disk.
- `gdextension-debug`: load errors, readable backtraces, leaks, wrong-thread errors, code that runs in the editor, and a review checklist.
- `gdextension-wrap-library`: expose an existing C or C++ library, with per-platform linking, shared dependencies, callbacks from the library's threads and C++ exceptions.

The other three skills build on `gdextension-cpp`, so install it with them. Needs Godot, Python 3, a C++17 compiler and SCons or CMake. Checked with godot-cpp 10.0.0-stable on Godot 4.7.2 and 4.8 beta 2, on Linux: Linux and Windows (MinGW) builds exported and ran, the Windows one under Wine; Android arm64 was built but not run. macOS, iOS and Web weren't tested.

The skills assume godot-cpp-template's layout: sources in `src/`, a test project in `project/`, the `.gdextension` in `project/bin/`, and libraries in `project/bin/<platform>/`. They never load a new build into an open editor: a crash in native code takes the editor down with it, so builds are tested in a headless Godot first. With the [Godot Agent Harness](https://github.com/dannroda/godot-agent) v0.1.17 or later, the skills use its `build_extension`, `test_extension` and `restart_editor` tools, and fall back to the shell without them.
