extends Node
## Copy into a copy of the project, edit the constants, and register it as an autoload in override.cfg.
## Pass the output JSON path after `--`. Run with --fixed-fps and --disable-vsync, so every run reaches
## the same game state at the same frame and frames take as long as they really need.

const WARMUP_FRAMES := 300 # skips loading and first-use shader compiles
const SAMPLE_FRAMES := 1200
# frame, keycode, pressed: gets the game to the state to measure, before the warmup ends
const STEPS := []

var frame := 0
var last_usec := 0
var frame_ms := PackedFloat32Array()
var gpu_ms := PackedFloat32Array()
var script_ms := PackedFloat32Array()
var draw_calls := PackedInt32Array()
var primitives := PackedInt32Array()
var out_path := ""
var process_start := 0
var physics_start := 0
var physics_usec := 0


func _ready() -> void:
	seed(12345)
	# Runs last in each step; the tree signals fire first, so the gap is the time spent in scripts.
	process_priority = 1000
	process_physics_priority = 1000
	get_tree().process_frame.connect(func(): process_start = Time.get_ticks_usec())
	get_tree().physics_frame.connect(func(): physics_start = Time.get_ticks_usec())
	var args := OS.get_cmdline_user_args()
	assert(args.size() == 1, "pass the output path after --")
	out_path = args[0]
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)


func _physics_process(_delta: float) -> void:
	physics_usec += Time.get_ticks_usec() - physics_start


func _process(_delta: float) -> void:
	frame += 1
	for step in STEPS:
		if step[0] == frame:
			var event := InputEventKey.new()
			event.keycode = step[1]
			event.physical_keycode = step[1]
			event.pressed = step[2]
			Input.parse_input_event(event)
	var now := Time.get_ticks_usec()
	if frame > WARMUP_FRAMES:
		var rid := get_viewport().get_viewport_rid()
		frame_ms.append((now - last_usec) / 1000.0)
		gpu_ms.append(RenderingServer.viewport_get_measured_render_time_gpu(rid))
		script_ms.append((now - process_start + physics_usec) / 1000.0)
		draw_calls.append(int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)))
		primitives.append(int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)))
	last_usec = now
	physics_usec = 0
	if frame == WARMUP_FRAMES + SAMPLE_FRAMES:
		_finish()


func _finish() -> void:
	var report := {
		"gpu": RenderingServer.get_video_adapter_name(),
		"renderer": RenderingServer.get_current_rendering_method(),
		"size": get_viewport().get_visible_rect().size,
		"frames": frame_ms.size(),
		"frame_ms": _stats(frame_ms),
		"gpu_ms": _stats(gpu_ms),
		"script_ms": _stats(script_ms),
		"draw_calls": _stats(draw_calls),
		"primitives": _stats(primitives),
		"nodes": Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
		"orphan_nodes": Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT),
		"static_memory_mb": Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0,
		"video_memory_mb": Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0,
	}
	var file := FileAccess.open(out_path, FileAccess.WRITE)
	assert(file != null, "could not write " + out_path)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("PERF frame median %.2f ms, p99 %.2f ms, draw calls %d" % [report.frame_ms.median, report.frame_ms.p99, report.draw_calls.median])
	get_tree().quit()


func _stats(values: Variant) -> Dictionary:
	var sorted := Array(values)
	sorted.sort()
	var at := func(q: float): return sorted[mini(int(q * sorted.size()), sorted.size() - 1)]
	return {"median": at.call(0.5), "p95": at.call(0.95), "p99": at.call(0.99), "max": sorted[-1]}
