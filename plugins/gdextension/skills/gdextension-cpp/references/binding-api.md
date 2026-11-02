# Binding API (godot-cpp 10)

Everything marked "checked" ran in the test extension on Godot 4.7.2 and 4.8 beta 2. Bitfields and vararg methods come from godot-cpp's own test project (`test/src/my_test.cpp` in the godot-cpp repo), which its CI runs; they weren't rerun here.

Put all bindings in `static void _bind_methods()`. Names in `D_METHOD` are what GDScript sees; give every argument a name, because it shows in the docs and in autocompletion.

## Methods

```cpp
ClassDB::bind_method(D_METHOD("step", "delta"), &MyNode::step);
ClassDB::bind_method(D_METHOD("make_items", "count"), &MyNode::make_items, DEFVAL(2));     // default argument
ClassDB::bind_static_method("MyNode", D_METHOD("add_ints", "a", "b"), &MyNode::add_ints);  // MyNode.add_ints(2, 3)
```

Checked: default arguments, static methods called on the class name from GDScript, `const` methods.

Argument and return types that cross into GDScript: `bool`, integer types, `float`/`double`, `String`, `StringName`, `NodePath`, math types (`Vector2`, `Transform3D`, …), `Variant`, `Array`, `Dictionary`, `TypedArray<T>`, `TypedDictionary<K, V>` (API 4.4+), packed arrays, `Object *` and pointers to your node classes, `Ref<T>` for RefCounted types, and enums that have a `VARIANT_ENUM_CAST`. Pass big values as `const T &`.

## Properties

```cpp
ClassDB::bind_method(D_METHOD("set_speed", "speed"), &MyNode::set_speed);
ClassDB::bind_method(D_METHOD("get_speed"), &MyNode::get_speed);

ADD_GROUP("Motion", "");          // inspector group for the properties that follow
ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "speed", PROPERTY_HINT_RANGE, "0,1000,0.1,or_greater,suffix:px/s"), "set_speed", "get_speed");
ADD_PROPERTY(PropertyInfo(Variant::INT, "mode", PROPERTY_HINT_ENUM, "Linear,Ping-Pong"), "set_mode", "get_mode");
ADD_PROPERTY(PropertyInfo(Variant::OBJECT, "stats", PROPERTY_HINT_RESOURCE_TYPE, "MyStats"), "set_stats", "get_stats");
ADD_PROPERTY(PropertyInfo(Variant::PACKED_STRING_ARRAY, "tags"), "set_tags", "get_tags");
```

Checked: the range hint is visible in `ClassDB.class_get_property_list()`, and a Resource property accepts your own Resource class. The second argument of `ADD_GROUP` is a prefix: with `"motion_"`, the group takes the properties named `motion_*`, and the inspector hides the prefix. That is the engine's behavior for its own classes; it wasn't rerun here.

Validate in the setter and refuse bad values with `ERR_FAIL_COND_MSG(p_speed < 0.0, "speed must be >= 0");`. Checked: the value stays unchanged, and the error shows the C++ line and the GDScript line that called it.

A Resource setter that should refresh the editor calls `emit_changed()`.

For properties that only exist at runtime (a list that depends on other values), override `_get_property_list`, `_get`, `_set` and `_validate_property` (signatures in godot-cpp's test project, class `MyTestMain`).

## Signals

```cpp
ADD_SIGNAL(MethodInfo("bounced", PropertyInfo(Variant::INT, "count")));
// emit:
emit_signal("bounced", bounces);
```

Checked: GDScript connects with `node.bounced.connect(...)` and gets the typed argument. Signals emitted from another thread run their handlers on that thread; see `gdextension-wrap-library`.

## Enums and constants

```cpp
class MyNode : public Node2D {
	GDCLASS(MyNode, Node2D)
public:
	enum Mode { MODE_LINEAR, MODE_PINGPONG };
	// ...
};

VARIANT_ENUM_CAST(MyNode::Mode);   // after the class, outside the namespace

// in _bind_methods:
BIND_ENUM_CONSTANT(MODE_LINEAR);
BIND_ENUM_CONSTANT(MODE_PINGPONG);
```

Checked: `MyNode.MODE_PINGPONG` works in GDScript. Without `VARIANT_ENUM_CAST`, any bound method that takes or returns the enum fails to compile with `incomplete type 'godot::GetTypeInfo<godot::MyNode::Mode, void>'`.

Bitfields use `VARIANT_BITFIELD_CAST(MyNode::Flags)`, `BIND_BITFIELD_FLAG(FLAG_ONE)`, and `BitField<Flags>` in signatures. Constants without an enum: `BIND_CONSTANT(NAME)`.

## Virtual methods that GDScript overrides

```cpp
#include <godot_cpp/core/gdvirtual.gen.inc>

class MyNode : public Node2D {
	// ...
	GDVIRTUAL1RC(double, _compute_offset, double)   // 1 arg, R = returns, C = const
};

// _bind_methods:
GDVIRTUAL_BIND(_compute_offset, "t");

// calling it, with a fallback when no script overrides it:
double offset = 0.0;
if (!GDVIRTUAL_CALL(_compute_offset, travelled, offset)) {
	offset = travelled;
}
```

```gdscript
extends MyNode
func _compute_offset(t: float) -> float:
	return t * 2.0
```

Checked: the script override ran, and without a script the fallback ran. The macro names encode the signature: `GDVIRTUAL<n>` (no return), `GDVIRTUAL<n>R` (return), `C` for const, `_REQUIRED` variants for methods a script must implement. `GDVIRTUAL_IS_OVERRIDDEN(_name)` tests without calling.

Engine virtuals (`_process`, `_ready`, `_input`, `_draw`, `_get_configuration_warnings`) need no macro: override them in C++ with `override`.

## Notifications

```cpp
protected:
	void _notification(int p_what);

void MyNode::_notification(int p_what) {
	if (p_what == NOTIFICATION_READY) { /* ... */ }
}
```

No binding needed. godot-cpp calls the parent class's `_notification` for you, as the engine does (godot-cpp's test project checks this with `MyTestBase` and `MyTestChild`).

## Typed arrays and objects

```cpp
TypedArray<MyStats> MyNode::make_items(int p_count) const {
	TypedArray<MyStats> out;
	for (int i = 0; i < p_count; i++) {
		Ref<MyStats> s;
		s.instantiate();
		out.push_back(s);
	}
	return out;
}
```

Checked: GDScript receives an `Array[MyStats]` whose elements pass `is MyStats`.

Casting: `Object::cast_to<Node2D>(obj)` returns `nullptr` when the type doesn't match. Check before use.

## Callables

```cpp
callable_mp(this, &MyNode::on_done)            // bound to an instance
callable_mp_static(&MyNode::static_handler)    // static function
callable_mp(this, &MyNode::on_step).call_deferred(step);   // run on the main thread at the next idle time
```

Checked: `call_deferred` from a worker thread delivered every call, in order, on the main thread, after the current frame. Connect a C++ handler to a signal the same way: `node->connect("timeout", callable_mp(this, &MyNode::on_timeout));`.

## Engine singletons

```cpp
static MyService *service = nullptr;

// initialize, at MODULE_INITIALIZATION_LEVEL_SCENE:
GDREGISTER_CLASS(MyService);
service = memnew(MyService);
Engine::get_singleton()->register_singleton("MyService", service);

// uninitialize:
Engine::get_singleton()->unregister_singleton("MyService");
memdelete(service);
```

Checked: GDScript calls it as `MyService.next()`, and `Engine.has_singleton("MyService")` is true. Unregister and free it at the same level you created it, or it shows up among the leaked instances at exit.

## Using engine classes from C++

Engine classes are in `godot_cpp/classes/<snake_case>.hpp` (`engine.hpp`, `os.hpp`, `input.hpp`, `resource_loader.hpp`). Singletons: `Engine::get_singleton()`, `OS::get_singleton()`, `Input::get_singleton()`. Printing: `UtilityFunctions::print(...)` (`godot_cpp/variant/utility_functions.hpp`) or `print_line(...)`. Load a resource with `ResourceLoader::get_singleton()->load("res://...")`, which returns a `Ref<Resource>`.
