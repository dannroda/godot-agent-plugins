extends Node
## Records a person playing, then replays their inputs under Movie Maker. Autoload in the capture copy only.
##   record: godot --path copy --fixed-fps 60 -- --replay-mode=record --session=DIR
##   replay: godot --path copy --fixed-fps 60 --write-movie DIR/render.avi -- --replay-mode=replay --session=DIR [--to=SECONDS] [--camera=FILE]
## Record writes events.bin (every input event with its frame), state.csv (player position and room per
## frame) and marks.json (F9 presses, in seconds). Replay re-injects the events on the same frames, compares
## state.csv frame by frame and writes desync.txt at the first mismatch. Without --replay-mode it does nothing.
## Optional setup.txt in the session ("cmd;cmd;..."): step i runs at frame 30 + 90 * i in both modes.
##
## Adapted from a recorder that kept a 28 s boss fight in sync for 1700 frames (Godot 4.5.1, keyboard and
## gamepad). Fill in GAME HOOKS for your game before trusting it: as published here it is only compile-checked.

const SEED := 20261103
const MARK_KEY := KEY_F9
const FPS := 60.0
const OUT := Vector2(1920, 1080)
## Name of the SubViewport the game draws its world into. Empty if it draws straight into the root window.
const GAME_VIEWPORT := "GameViewport"

var mode := ""
var session := ""
var args := {}
var frame := 0
var events: FileAccess
var state: FileAccess
var marks: Array = []
var setup: PackedStringArray
var replay: Array = []  # [[frame, event], ...]
var replay_i := 0
var ref_state: PackedStringArray
var last_frame := 0
var desynced := -1
var shots: Array = []  # camera segments, see _shot_at()
var node_rngs := 0
var game_vp: SubViewport
var view: SubViewport  # replay only: native 1920x1080 view of the game's world
var follow_pos := Vector2.INF


# --- GAME HOOKS: adapt these -------------------------------------------------

## Seed every RandomNumberGenerator the game keeps in autoloads or static vars.
func _seed_game_rngs() -> void:
	pass  # e.g. Utils.rng.seed = SEED + 1


## Seed per-instance generators. Runs on node_added, before the node's _ready.
func _seed_node(n: Node) -> void:
	var rng = n.get("rng")  # change the property name if your nodes use another one
	if rng is RandomNumberGenerator:
		node_rngs += 1
		rng.seed = SEED + 100 + node_rngs


func _player() -> Node2D:
	return get_tree().get_first_node_in_group("player") as Node2D


## Something that changes when the player changes room or level; "" if nothing fits.
func _room() -> String:
	var scene := get_tree().current_scene
	return scene.scene_file_path.get_file() if scene else ""


## Runs one setup.txt step, e.g. a debug command. Must do the same thing in both modes.
func _run_setup_command(cmd: String) -> void:
	push_warning("[replay] no handler for setup step '%s'" % cmd)


## Replay without --hud: hide HUD and debug text. Runs once the game's view exists.
func _hide_hud() -> void:
	pass


# --- start -------------------------------------------------------------------

func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else "true"
	mode = args.get("replay-mode", "")
	if mode == "":
		set_process(false)
		return
	session = args.get("session", "")
	process_priority = -1000  # count the frame before any game code runs
	Input.use_accumulated_input = false  # same event stream live and replayed
	seed(SEED)
	_seed_game_rngs()
	get_tree().node_added.connect(_on_node_added)
	if FileAccess.file_exists(session.path_join("setup.txt")):
		setup = FileAccess.get_file_as_string(session.path_join("setup.txt")).strip_edges().split(";", false)
	if mode == "record":
		events = FileAccess.open(session.path_join("events.bin"), FileAccess.WRITE)
		state = FileAccess.open(session.path_join("state.csv"), FileAccess.WRITE)
		get_tree().root.window_input.connect(_on_window_input)
		print("[replay] recording to ", session, "  (F9 marks a moment)")
	elif mode == "replay":
		# The root renders at window size; the GUI keeps its base layout.
		get_tree().root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
		get_window().size = Vector2i(OUT)
		RenderingServer.frame_pre_draw.connect(_frame_view)
		_load_session()
		_load_camera(args.get("camera", session.path_join("camera.json")))
		_inject(0)  # events that arrived before the first frame


func _on_node_added(n: Node) -> void:
	_seed_node(n)
	if mode == "replay" and n is SubViewport and n.name == GAME_VIEWPORT:
		_add_view.call_deferred(n)


# --- record ------------------------------------------------------------------

func _on_window_input(e: InputEvent) -> void:
	if e is InputEventKey and e.keycode == MARK_KEY:
		if e.pressed and not e.echo:
			marks.append(frame)
			print("[replay] mark %d at %.2fs" % [marks.size(), frame / FPS])
		return
	events.store_var([frame, e], true)


# --- replay ------------------------------------------------------------------

func _load_session() -> void:
	var f := FileAccess.open(session.path_join("events.bin"), FileAccess.READ)
	while f.get_position() < f.get_length():
		var e = f.get_var(true)
		if e == null:  # the game was killed mid-write: keep what was saved
			push_warning("[replay] events.bin is truncated after %d events" % replay.size())
			break
		replay.append(e)
	ref_state = FileAccess.get_file_as_string(session.path_join("state.csv")).split("\n", false)
	last_frame = ref_state.size()
	if args.has("to"):
		last_frame = mini(last_frame, int(float(args.to) * FPS))
	print("[replay] %d events over %d frames" % [replay.size(), last_frame])


func _inject(f: int) -> void:
	while replay_i < replay.size() and replay[replay_i][0] <= f:
		Input.parse_input_event(replay[replay_i][1])  # flushed before the next frame, as live input was
		replay_i += 1


func _load_camera(path: String) -> void:
	if not FileAccess.file_exists(path):
		return
	shots = JSON.parse_string(FileAccess.get_file_as_string(path))
	print("[replay] camera: %d segments from %s" % [shots.size(), path])


## camera.json: [{"from": 0, "to": 12.5, "mode": "game"},
##               {"from": 12.5, "to": 20, "mode": "follow", "zoom": 4, "offset": [0, -24], "smooth": 6}]
func _shot_at(t: float) -> Dictionary:
	for s in shots:
		if t >= float(s.get("from", 0)) and t < float(s.get("to", INF)):
			return s
	return {"mode": "game"}


func _add_view(vp: SubViewport) -> void:
	game_vp = vp
	view = SubViewport.new()
	view.size = Vector2i(OUT)
	view.world_2d = vp.world_2d  # same world, nothing duplicated
	view.transparent_bg = true  # whatever the game draws behind its view still shows
	view.snap_2d_transforms_to_pixel = true
	view.snap_2d_vertices_to_pixel = true
	view.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	view.audio_listener_enable_2d = false
	view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var up := vp.get_parent()
	while up and not up is CanvasLayer:
		up = up.get_parent()
	var game_layer := up as CanvasLayer
	var layer := CanvasLayer.new()  # same layer as the game's view, drawn just after it
	layer.layer = game_layer.layer if game_layer else 0
	var rect := TextureRect.new()
	rect.texture = view.get_texture()
	rect.size = OUT
	# The 1920 px texture is placed in base-layout units, so it lands on screen at 1920 px.
	rect.scale = Vector2.ONE * float(ProjectSettings.get_setting("display/window/size/viewport_width")) / OUT.x
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(view)
	layer.add_child(rect)
	(game_layer if game_layer else vp.get_parent()).add_sibling(layer)
	if not args.has("hud"):
		_hide_hud()


## Runs after all game logic for the frame, right before drawing.
func _frame_view() -> void:
	if view == null or not is_instance_valid(game_vp):
		return
	var k := OUT.x / game_vp.size.x  # game view -> 1920 px
	var s := _shot_at(frame / FPS)
	var p := _player()
	if s.get("mode", "game") != "follow" or p == null:
		# The game's camera exactly: room zoom, shake and transitions.
		follow_pos = Vector2.INF
		view.canvas_transform = Transform2D.IDENTITY.scaled(Vector2(k, k)) * game_vp.canvas_transform
		return
	var z := float(s.get("zoom", 4))  # an integer zoom keeps every art pixel the same size
	var off: Array = s.get("offset", [0, -24])
	var target := p.global_position + Vector2(off[0], off[1])
	if follow_pos == Vector2.INF:
		follow_pos = target
	else:
		follow_pos = follow_pos.lerp(target, 1.0 - exp(-float(s.get("smooth", 6)) / FPS))
	# Stay inside the game camera's limits, and keep its offset (shake).
	var cam := game_vp.get_camera_2d()
	var half := OUT / z / 2
	var c := follow_pos
	if cam:
		var lo := Vector2(cam.limit_left, cam.limit_top) + half
		var hi := Vector2(cam.limit_right, cam.limit_bottom) - half
		c.x = c.x if lo.x > hi.x else clampf(c.x, lo.x, hi.x)
		c.y = c.y if lo.y > hi.y else clampf(c.y, lo.y, hi.y)
		c += cam.offset
	view.canvas_transform = Transform2D(0, Vector2(z, z), 0, OUT / 2 - c.round() * z)


func _check_sync() -> void:
	if desynced >= 0 or frame - 1 >= ref_state.size():
		return
	var now := _state_line()
	if now != ref_state[frame - 1]:
		desynced = frame
		push_warning("[replay] DESYNC at frame %d (%.2fs): recorded '%s', replay '%s'"
				% [frame, frame / FPS, ref_state[frame - 1], now])
		FileAccess.open(session.path_join("desync.txt"), FileAccess.WRITE).store_line(
				"%d %.2f" % [frame, frame / FPS])


# --- both modes --------------------------------------------------------------

func _state_line() -> String:
	var p := _player()
	if p == null or not p.is_inside_tree():
		return "%d,-,-,%s" % [frame, _room()]
	return "%d,%.1f,%.1f,%s" % [frame, p.global_position.x, p.global_position.y, _room()]


func _run_setup() -> void:
	if setup.is_empty() or frame < 30 or (frame - 30) % 90 != 0:
		return
	var i := (frame - 30) / 90
	if i < setup.size():
		print("[replay] setup: ", setup[i].strip_edges())
		_run_setup_command(setup[i].strip_edges())


func _process(_delta: float) -> void:
	frame += 1
	_run_setup()
	if mode == "record":
		state.store_line(_state_line())
		return
	_check_sync()
	_inject(frame)
	if frame >= last_frame + 30:
		print("[replay] done%s" % ("" if desynced < 0 else ", DESYNC from %.2fs" % (desynced / FPS)))
		get_tree().quit()


func _exit_tree() -> void:
	if mode != "record":
		return
	events.close()
	state.close()
	FileAccess.open(session.path_join("marks.json"), FileAccess.WRITE).store_string(
			JSON.stringify(marks.map(func(f): return snappedf(f / FPS, 0.01))))
	print("[replay] saved %d frames, %d marks" % [frame, marks.size()])
