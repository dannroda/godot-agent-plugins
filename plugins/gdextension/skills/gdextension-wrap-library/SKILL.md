---
name: "gdextension-wrap-library"
description: "Use when exposing an existing C or C++ library (an audio, physics, networking or SDK library like FMOD or Steamworks) to Godot 4 through a godot-cpp GDExtension: designing the wrapper classes, owning native handles, translating errors, linking statically or dynamically per platform, shipping the library's own shared files ([dependencies], rpath), callbacks that arrive on the library's threads, and C++ exceptions. Builds the basics from gdextension-cpp and gdextension-build."
---

# Wrap a C or C++ library

Checked with godot-cpp 10.0.0-stable on Godot 4.7.2 and 4.8 beta 2, wrapping a small C library whose callbacks come from its own thread. It was linked statically and dynamically on Linux, statically for Windows (MinGW, run under Wine) and Android (built only), and exported for Linux and Windows.

Read `gdextension-cpp` first for the project layout and registration, and `gdextension-build` for platforms.

## Check the license first

Static linking puts the library inside your binary. An LGPL library needs dynamic linking, or extra steps, for a closed game. Commercial SDKs (FMOD, Wwise, Steamworks) usually forbid redistributing their files outside a game, so an addon may have to ask users to download them. Ask the user before you commit or redistribute vendor files.

## Design the Godot side first

Don't mirror the C API function by function. Write the API a GDScript user wants, and hide the C details behind it:

| C library | Godot side |
|---|---|
| `foo_ctx *foo_create()` / `foo_destroy(ctx)` | A `RefCounted` that owns the handle and destroys it in its destructor, or an engine singleton for a global context |
| A sound or body handle | A `RefCounted` or `Resource` per handle, or a `Node` when it lives in the scene (position, lifetime) |
| `int` error codes | `godot::Error` returns, `ERR_FAIL_*_MSG` with the library's message, or a signal for async errors |
| Callbacks with `void *userdata` | Signals, emitted on the main thread |
| `const char *` | `String` (`String(c_str)`; `str.utf8().get_data()` going back) |
| Buffers | `PackedByteArray` / `PackedFloat32Array` (`ptrw()` for a writable pointer) |
| A per-frame update call | `_process` in the singleton or node, or `RenderingServer`'s `frame_pre_draw` signal |

Keep the C headers out of your public headers: forward-declare the handle (`struct foo_ctx;`) and include the library header only in `.cpp` files.

```cpp
class FooPlayer : public RefCounted {
	GDCLASS(FooPlayer, RefCounted)
	foo_ctx *ctx = nullptr;

protected:
	static void _bind_methods();

public:
	FooPlayer() { ctx = foo_create(); }
	~FooPlayer() override {
		if (ctx) {
			foo_destroy(ctx);
		}
	}
	Error play(const String &p_path) {
		ERR_FAIL_NULL_V(ctx, ERR_UNCONFIGURED);
		int code = foo_play(ctx, p_path.utf8().get_data());
		ERR_FAIL_COND_V_MSG(code != 0, FAILED, String("foo_play: ") + foo_strerror(code));
		return OK;
	}
};
```

Paths: the library can't open `res://` paths. Pass `ProjectSettings::get_singleton()->globalize_path(path)` in the editor. In an exported game, files in the `.pck` aren't on disk: read them with `FileAccess::get_file_as_bytes()` and hand over the bytes, if the library can load from memory.

## Callbacks from the library's threads

Many libraries call back from their own threads. Checked:
- `emit_signal` inside such a callback ran the GDScript handlers **on the library's thread**, where scene calls fail (`Adding children to a node inside the SceneTree is only allowed from the main thread.`).
- Forwarding with `call_deferred` delivered every call, in order, on the main thread, after the current frame:

```cpp
static void on_step(int p_step, void *p_userdata) {          // called on the library's thread
	FooJob *self = static_cast<FooJob *>(p_userdata);
	callable_mp(self, &FooJob::_on_step_main).call_deferred(p_step);
}

void FooJob::_on_step_main(int p_step) {                      // main thread
	emit_signal("progress", p_step);
}
```

The library holds `this` as userdata, so it must never call back after the object is gone. Stop and join its work in the destructor (`~FooJob() { foo_join(job); }`), and unregister callbacks before freeing anything they touch. Deferred calls to an object freed before they ran were dropped silently: no handler ran and nothing was printed. A raw pointer used on the library thread has no such protection. For long-lived jobs, keep a `Ref` to the wrapper until the job ends.

To poll instead, push results into a queue guarded by a mutex in the callback, and drain it in `_process`.

## Link the library

Build or download the library for **every platform and architecture**, and keep each in its own folder:

```
thirdparty/foo/include/foo.h
thirdparty/foo/lib/linux.x86_64/libfoo.a
thirdparty/foo/lib/windows.x86_64/libfoo.a        (MinGW) or foo.lib (MSVC)
thirdparty/foo/lib/android.arm64/libfoo.a
```

```python
# SConstruct, after env = SConscript("godot-cpp/SConstruct", ...)
foo = "thirdparty/foo/lib/{}.{}".format(env["platform"], env["arch"])
env.Append(CPPPATH=["thirdparty/foo/include"])
env.Append(LIBS=[File(foo + "/libfoo.a")])
```

Picking the folder from `env["platform"]` matters: MinGW linked the Linux `.a` into a Windows DLL without any error.

| | Static (`.a`, `.lib`) | Shared (`.so`, `.dll`, `.dylib`) |
|---|---|---|
| Ship | Only your library | Your library plus theirs, for every platform |
| Build the library with | `-fPIC` (it goes into a shared library) | its normal build |
| Linux search path | n/a | godot-cpp already links with an `$ORIGIN` rpath, so a `.so` next to yours is found |
| Windows search path | n/a | The DLL next to yours, or next to the game executable |
| Export | Nothing extra | List it in `[dependencies]` |

```ini
[dependencies]
linux.x86_64 = {
    "./linux/libfoo.so.1": ""
}
windows.x86_64 = {
    "./windows/foo.dll": ""
}
```

Without the entry, the Linux export lacked `libfoo.so.1`, and the game printed `<name>.so.1: cannot open shared object file` and kept running. With it, the file was copied next to the executable and the game ran. Ship the name in the library's `SONAME` (`readelf -d libfoo.so | grep SONAME`), here `libfoo.so.1`, not the `libfoo.so` link.

## C++ libraries and exceptions

godot-cpp compiles your code with `-fno-exceptions` (`disable_exceptions` defaults to yes). A `try`/`catch` around a library call stopped the build: `exception handling disabled, use '-fexceptions' to enable`. If the library reports errors by throwing:
- build with `disable_exceptions=no`, which compiled and ran in the test. Catch everything at the boundary and turn it into an `Error` or `ERR_FAIL_*_MSG`. An uncaught exception in a bound method ended Godot with `terminate called after throwing an instance of 'int'` and a core dump;
- or put the calls in one `.cpp` compiled with exceptions, behind functions that return error codes.

The C++ standard library, as linked by godot-cpp:

| Platform | Linked | Notes |
|---|---|---|
| Linux | statically (`use_static_cpp`, on by default) | `readelf -d` shows only libc, libm and ld-linux. Turning on `use_hot_reload` switches it off, and then the system's `libstdc++` is needed. |
| Windows, MinGW | statically | Only Windows system DLLs are needed |
| Android | `libc++_shared.so` | It must be in the APK; not run on a device here |

glibc itself is always the system's, so build Linux releases on the oldest distribution you support (godot-cpp-template's CI uses Ubuntu 22.04). A prebuilt C++ library must use the same standard library and compiler family as your build.

## Test

Add tests for the wrapper to the extension's headless tests (`gdextension-cpp`): open and close a handle 1000 times and check no instances leaked at exit; check callbacks arrive on the main thread (compare `OS.get_thread_caller_id()` with `OS.get_main_thread_id()` in the handler); free the wrapper while a job runs. Then export and run the exported game for each platform under `timeout`, because a missing dependency appears only there.
