extends SceneTree
## Compares every PNG in a baseline folder with the same file in an actual folder.
##   godot --headless --script compare_images.gd -- BASELINE ACTUAL DIFF [--tolerance=0] [--max-percent=0] [--ignore=x,y,w,h]...
## Exit code: 0 all match, 1 differences found, 2 bad arguments or no baseline images.

var tolerance := 0
var max_percent := 0.0
var ignored: Array[Rect2i] = []


func _init() -> void:
	var folders: Array[String] = []
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--tolerance="):
			tolerance = arg.get_slice("=", 1).to_int()
		elif arg.begins_with("--max-percent="):
			max_percent = arg.get_slice("=", 1).to_float()
		elif arg.begins_with("--ignore="):
			var v := arg.get_slice("=", 1).split_floats(",")
			ignored.append(Rect2i(int(v[0]), int(v[1]), int(v[2]), int(v[3])))
		else:
			folders.append(arg)
	if folders.size() != 3:
		printerr("usage: BASELINE ACTUAL DIFF [--tolerance=0] [--max-percent=0] [--ignore=x,y,w,h]")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(folders[2])
	var names := Array(DirAccess.get_files_at(folders[0])).filter(func(n): return n.ends_with(".png"))
	if names.is_empty():
		printerr("no PNG files in baseline ", folders[0])
		quit(2)
		return
	var failed := 0
	for file_name in names:
		if not _compare(file_name, folders[0], folders[1], folders[2]):
			failed += 1
	for file_name in DirAccess.get_files_at(folders[1]):
		if file_name.ends_with(".png") and file_name not in names:
			print("NEW   %s has no baseline" % file_name)
			failed += 1
	print("%d of %d checkpoints differ" % [failed, names.size()])
	quit(1 if failed > 0 else 0)


func _compare(file_name: String, baseline_dir: String, actual_dir: String, diff_dir: String) -> bool:
	var actual_path := actual_dir.path_join(file_name)
	if not FileAccess.file_exists(actual_path):
		print("FAIL  %s is missing from the run" % file_name)
		return false
	var a := Image.load_from_file(baseline_dir.path_join(file_name))
	var b := Image.load_from_file(actual_path)
	if a.get_size() != b.get_size():
		print("FAIL  %s size %s, baseline %s" % [file_name, b.get_size(), a.get_size()])
		return false
	a.convert(Image.FORMAT_RGB8)
	b.convert(Image.FORMAT_RGB8)
	var width := a.get_width()
	var height := a.get_height()
	var skip := PackedByteArray()
	skip.resize(width * height)
	for rect in ignored:
		var clipped := rect.intersection(Rect2i(0, 0, width, height))
		for y in range(clipped.position.y, clipped.end.y):
			_mark(skip, y * width + clipped.position.x, clipped.size.x)
	var da := a.get_data()
	var db := b.get_data()
	var out := PackedByteArray(da)
	var changed := 0
	var biggest := 0
	var box := Rect2i()
	for i in width * height:
		if skip[i]:
			continue
		var j := i * 3
		var d: int = maxi(maxi(absi(da[j] - db[j]), absi(da[j + 1] - db[j + 1])), absi(da[j + 2] - db[j + 2]))
		biggest = maxi(biggest, d)
		if d > tolerance:
			var cell := Rect2i(i % width, i / width, 1, 1)
			box = cell if changed == 0 else box.merge(cell)
			changed += 1
			out[j] = 255
			out[j + 1] = 0
			out[j + 2] = 0
	var percent := 100.0 * changed / float(width * height)
	var ok := percent <= max_percent
	print("%s  %s %.3f%% changed, largest channel difference %d, area %s" % ["PASS" if ok else "FAIL", file_name, percent, biggest, box])
	if not ok:
		Image.create_from_data(width, height, false, Image.FORMAT_RGB8, out).save_png(diff_dir.path_join(file_name))
	return ok


func _mark(skip: PackedByteArray, start: int, count: int) -> void:
	for i in range(start, start + count):
		skip[i] = 1
