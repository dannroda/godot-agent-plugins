---
name: "gdextension-build"
description: "Use when building or shipping a Godot 4 C++ GDExtension: SCons and CMake commands and options (target, platform, arch, api_version, build_profile, debug_symbols, use_hot_reload), build times, cross-compiling for Windows with MinGW and for Android with the NDK, checking the .gdextension file against the libraries on disk, exporting a game that uses the extension, packaging it as an addon, and CI. Writing the extension is in gdextension-cpp."
---

# Build and ship a GDExtension

Checked with godot-cpp 10.0.0-stable, SCons 4.11 and CMake on Linux. Linux and Windows (MinGW) builds were exported with Godot 4.7.2 templates and run, the Windows one under Wine. Android arm64 libraries were built with NDK r30 but not run on a device. macOS, iOS and Web weren't tested here; their rows below come from godot-cpp's build scripts.

Layout and terms follow `gdextension-cpp`: sources in `src/`, test project in `project/`, libraries in `project/bin/<platform>/`.

## Targets

| `target=` | Loaded by | Defines |
|---|---|---|
| `template_debug` (default) | The editor, and debug exports | `DEBUG_ENABLED` |
| `template_release` | Release exports | none (adds `NDEBUG`) |
| `editor` | Only if the `.gdextension` has `.editor` entries | `TOOLS_ENABLED`, `DEBUG_ENABLED` |

The editor loads the `debug` entry, so `template_debug` is enough for development. Build `editor` only for code that must exist only in the editor (`#ifdef TOOLS_ENABLED`).

## SCons

```bash
scons platform=linux target=template_debug          # -j defaults to the CPU count
scons platform=linux target=template_release
scons platform=windows use_mingw=yes target=template_debug
ANDROID_HOME=$HOME/Android/Sdk scons platform=android arch=arm64 target=template_debug ndk_version=<installed version>
```

| Option | Default | Notes |
|---|---|---|
| `api_version` | none, required | Set it in the SConstruct (see `gdextension-cpp`) |
| `build_profile=build_profile.json` | none | Only the engine classes you list get bindings. A clean build took 3.9 s instead of 51 s (71 files instead of 1094, 32 threads). |
| `debug_symbols` | off, unless `dev_build=yes` | Turn it on to debug; see `gdextension-debug` |
| `use_hot_reload` | off | Needed for `reloadable = true` to work |
| `precision=double` | single | Only for a double-precision Godot build. Adds `.double` to the file name. |
| `dev_build=yes` | off | No optimization, `DEV_ENABLED`, symbols on. Adds `.dev`. |
| `compiledb=yes` | off | Writes `compile_commands.json` for clangd and IDEs |

The output name is `lib<name>.<platform>.<target>.<arch><SHLIBSUFFIX>`, from `env["suffix"]`. A one-file change rebuilt in 2.6 s; godot-cpp itself only rebuilds when its options change.

Build profile, listing the engine classes your code uses (their parents come in automatically):

```json
{
	"type": "feature_profile",
	"enabled_classes": ["Node2D", "Resource", "RefCounted", "Engine", "OS"]
}
```

With fewer bindings generated, code can lose headers it was getting through other headers. Include what you use, then rerun the tests.

## CMake

The template's `CMakeLists.txt` works the same way:

```bash
cmake -S . -B build -G Ninja -DGODOTCPP_TARGET=template_debug
cmake --build build -j
```

Checked: a clean build took 47 s and passed the same tests as the SCons build. The options are the SCons ones in capitals with `GODOTCPP_` in front: `GODOTCPP_API_VERSION` (defaults to 4.7 here, unlike SCons), `GODOTCPP_BUILD_PROFILE`, `GODOTCPP_USE_HOT_RELOAD`, `GODOTCPP_PRECISION`. Read the suffix and platform from the target (`get_target_property(GODOTCPP_SUFFIX godot::cpp GODOTCPP_SUFFIX)`) so file names match the SCons build. Use one build system per project: both write to the same `project/bin/`.

## Platforms

| Platform | Command | Notes |
|---|---|---|
| Linux | `platform=linux` | godot-cpp adds an `$ORIGIN` rpath, so `.so` files next to the library are found, and links libstdc++ statically (not with `use_hot_reload=yes`) |
| Windows from Linux | `platform=windows use_mingw=yes` | Needs `x86_64-w64-mingw32-g++`. The file keeps the `lib` prefix. Links libgcc and libstdc++ statically, so only Windows system DLLs are needed. |
| Windows | `platform=windows` | MSVC. No `lib` prefix. |
| Android | `platform=android arch=arm64` (and `x86_64` for emulators) | `ANDROID_HOME` set. The library needs `libc++_shared.so`. godot-cpp 10.0.0 expects NDK `28.1.13356709`: with another one installed, pass `ndk_version=<folder name under $ANDROID_HOME/ndk>`, or it stops with `Could not find NDK toolchain`. |
| macOS | `platform=macos` (universal by default) | Needs Xcode; build on a Mac or in CI. Sign the library for distribution. |
| iOS | `platform=ios` | Static libraries packed in an `.xcframework`; godot-cpp's test project has the `.gdextension` form, including `[dependencies]` for godot-cpp itself |
| Web | `platform=web` | Needs Emscripten at the version the Godot web templates use. The template uses `.nothreads` builds; the web export needs "Extensions Support" turned on (from the Godot docs, not tested here). |

A third-party library is built per platform too. Keep it in folders named by platform and architecture (`thirdparty/foo/lib/windows.x86_64/`) and pick the folder from `env["platform"]` and `env["arch"]`. MinGW linked the Linux `.a` into the Windows DLL **with no error or warning**; only the folder naming stopped that from shipping.

## Check the .gdextension file

```bash
python3 <skill>/scripts/check_gdextension.py project/bin/my_ext.gdextension --require linux.x86_64,windows.x86_64
```

It reports missing files, an `entry_symbol` that isn't in a library, a platform with a debug key but no release key (or the reverse), keys and file names that disagree, a Windows name that only differs by the `lib` prefix, and missing `[dependencies]` files. Exit 0 means no problems, 1 means problems, 2 means bad input.

Platforms with no file for any of their keys are listed as not built and don't fail the check, because templates list every platform from the start. Name the platforms you ship in `--require`, so a missing one fails. Run it before every export and in CI.

## Export

Exports copy the library that matches the export's platform and build next to the game. Checked with Linux and Windows release exports:

```bash
godot --headless --path project --export-release Linux ../export/linux/game.x86_64
timeout 60 ../export/linux/game.x86_64 --headless
```

- With no `release` library, the release export still finished, with only a warning (`No "x86_64" library found for GDExtension`). The game then printed `No GDExtension library found for current OS and architecture` and kept running. Build both targets for every platform you ship, and treat that warning as an error.
- Third-party shared libraries aren't copied unless listed in `[dependencies]`. Without that, the exported game printed `libnoisy.so.1: cannot open shared object file` **and kept running without quitting**. With the entry below, it was copied and the game ran:

  ```ini
  [dependencies]
  linux.x86_64 = {
      "./linux/libnoisy.so.1": ""
  }
  ```
  The value is the folder inside the export, and `""` means next to the executable.
- Always run an exported build under `timeout` in scripts.
- An `export_presets.cfg` written by hand needs `include_filter=""` and `exclude_filter=""` in every preset, or Godot prints `Couldn't find the given section "preset.0" and key "include_filter"` (the export still worked).

## Package as an addon

Put the `.gdextension` and the libraries in `addons/my_ext/` (`bin/<platform>/` inside it, with `./` paths), and add a `plugin.cfg` only if you also ship an editor plugin. Commit the libraries to releases, not to the source branch. Users need no compiler: they copy the folder and open the project. Headless runs and CI also need `godot --headless --import` once.

## CI

Build a matrix of `platform` × `target`, upload the libraries, then assemble the addon in one job. godot-cpp-template's `.github/workflows/make_build.yml` already does that for Linux, Windows, macOS, Android, iOS and Web. Add two steps after assembly: `check_gdextension.py` with `--require` for each shipped platform, and the headless tests from `gdextension-cpp` on Linux for each Godot version you support.
