extends SceneTree
## Runs test_*.gd files against a GDExtension, headless, and exits with a code CI can gate on.
##
##   godot --headless --path project --script res://extension_tests.gd -- --dir=res://tests --class=MyNode,MyResource
##
## Each test file extends RefCounted and has methods named test_*(t). Call t.check(condition, "what")
## inside them. A test method may await (for example `await t.tree.process_frame`).
##
## Exit codes: 0 all passed, 1 a check failed, 2 the extension or a class didn't load, or no tests ran.
## Run it under `timeout`: a script that fails to parse can leave the process running.

var tree: SceneTree
var _failures := 0
var _checks := 0
var _current := ""


func check(condition: bool, what: String) -> void:
	_checks += 1
	if condition:
		print("PASS %s: %s" % [_current, what])
	else:
		_failures += 1
		printerr("FAIL %s: %s" % [_current, what])


func _initialize() -> void:
	tree = self
	_run.call_deferred()


func _run() -> void:
	# Inside _initialize the tree isn't running yet, so thread guards stay silent.
	# Wait one frame so a scene call from the wrong thread prints its error here too.
	await process_frame

	var dir := "res://tests"
	var classes: PackedStringArray = []
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--dir="):
			dir = arg.trim_prefix("--dir=")
		elif arg.begins_with("--class="):
			classes = arg.trim_prefix("--class=").split(",", false)

	if GDExtensionManager.get_loaded_extensions().is_empty():
		printerr("ERROR no GDExtension loaded. Run `godot --headless --import` once, and read the load errors above.")
		quit(2)
		return
	for name in classes:
		if not ClassDB.class_exists(name):
			printerr("ERROR class %s isn't registered" % name)
			quit(2)
			return

	var files := DirAccess.get_files_at(dir)
	var ran := 0
	for file in files:
		if not (file.begins_with("test_") and file.ends_with(".gd")):
			continue
		var script: GDScript = load(dir.path_join(file))
		if script == null or not script.can_instantiate():
			_failures += 1
			printerr("FAIL %s: script doesn't load" % file)
			continue
		var suite: Object = script.new()
		for method in suite.get_method_list():
			var name: String = method.name
			if not name.begins_with("test_"):
				continue
			_current = "%s:%s" % [file.get_basename(), name]
			ran += 1
			await suite.call(name, self)
		if suite is Node:
			suite.free()

	if ran == 0:
		printerr("ERROR no test_* methods found in %s" % dir)
		quit(2)
		return
	print("DONE tests=%d checks=%d failures=%d" % [ran, _checks, _failures])
	quit(1 if _failures else 0)
