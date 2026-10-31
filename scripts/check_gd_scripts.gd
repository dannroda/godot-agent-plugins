extends SceneTree
## Compiles GDScript files without running them, and fails if any has an error.
##   godot --headless --path EMPTY_PROJECT --script check_gd_scripts.gd -- FILE.gd...


func _initialize() -> void:
	var failed := 0
	var paths := OS.get_cmdline_user_args()
	for path in paths:
		var script := GDScript.new()
		script.source_code = FileAccess.get_file_as_string(path)
		if script.source_code.is_empty() or script.reload() != OK:
			printerr("FAIL ", path)
			failed += 1
	print("%d of %d scripts failed" % [failed, paths.size()])
	quit(1 if failed > 0 or paths.is_empty() else 0)
