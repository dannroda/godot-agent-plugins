extends SceneTree
## Compares perf_probe reports.
##   godot --headless --script compare_perf.gd -- BEFORE.json AFTER.json [--time-percent=10] [--count-percent=1]
## Exit code: 0 no regression, 1 regression, 2 bad input or the two runs are not comparable.
## p99 is printed but never fails the check: it moved more than 10% between runs of unchanged code.

const TIMES := ["frame_ms", "gpu_ms", "script_ms"]
const COUNTS := ["draw_calls", "primitives"]
const TOTALS := ["nodes", "orphan_nodes", "static_memory_mb", "video_memory_mb"]


func _init() -> void:
	var paths: Array[String] = []
	var time_percent := 10.0
	var count_percent := 1.0
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--time-percent="):
			time_percent = arg.get_slice("=", 1).to_float()
		elif arg.begins_with("--count-percent="):
			count_percent = arg.get_slice("=", 1).to_float()
		else:
			paths.append(arg)
	if paths.size() != 2:
		printerr("usage: BEFORE.json AFTER.json [--time-percent=10] [--count-percent=1]")
		quit(2)
		return
	var before: Variant = JSON.parse_string(FileAccess.get_file_as_string(paths[0]))
	var after: Variant = JSON.parse_string(FileAccess.get_file_as_string(paths[1]))
	if not before is Dictionary or not after is Dictionary:
		printerr("could not read both reports")
		quit(2)
		return
	for key in ["gpu", "renderer", "size"]:
		if before[key] != after[key]:
			printerr("not comparable: %s is %s, then %s" % [key, before[key], after[key]])
			quit(2)
			return
	# A game that failed to load draws almost nothing, which would otherwise look like a huge improvement.
	if after.nodes < before.nodes * 0.5 or after.draw_calls.median < before.draw_calls.median * 0.5:
		printerr("not comparable: nodes %d -> %d, draw calls %d -> %d. Did the game load and reach the same state?" % [before.nodes, after.nodes, before.draw_calls.median, after.draw_calls.median])
		quit(2)
		return
	var worse := 0
	for key in TIMES:
		worse += _line(key + " median", before[key].median, after[key].median, time_percent)
		print("info   %-20s %10.2f -> %10.2f" % [key + " p99", before[key].p99, after[key].p99])
	for key in COUNTS:
		worse += _line(key + " median", before[key].median, after[key].median, count_percent)
	for key in TOTALS:
		worse += _line(key, before[key], after[key], count_percent)
	print("%d metrics got worse" % worse)
	quit(1 if worse > 0 else 0)


func _line(label: String, a: float, b: float, limit: float) -> int:
	var change := 100.0 * (b - a) / a if a > 0.0 else (0.0 if b == a else 100.0)
	var bad := change > limit
	print("%s  %-20s %10.2f -> %10.2f  %+.1f%%" % ["WORSE" if bad else "ok   ", label, a, b, change])
	return 1 if bad else 0
