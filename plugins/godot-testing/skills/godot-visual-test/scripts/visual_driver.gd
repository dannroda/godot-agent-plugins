extends Node
## Copy into the capture copy of the project and edit STEPS and SHOTS for one test.
## Register it as an autoload in override.cfg. Pass the output folder after `--`.

# frame, keycode, pressed
const STEPS := [
	[60, KEY_ENTER, true],
	[62, KEY_ENTER, false],
]
# frame: checkpoint name
const SHOTS := {
	30: "start",
	240: "after_enter",
}

var frame := 0
var out_dir := ""


func _ready() -> void:
	seed(12345)
	process_priority = -1000
	var args := OS.get_cmdline_user_args()
	assert(args.size() == 1, "pass the output folder after --")
	out_dir = args[0]
	DirAccess.make_dir_recursive_absolute(out_dir)


func _process(_delta: float) -> void:
	frame += 1
	for step in STEPS:
		if step[0] == frame:
			var event := InputEventKey.new()
			event.keycode = step[1]
			event.physical_keycode = step[1]
			event.pressed = step[2]
			Input.parse_input_event(event)
	if SHOTS.has(frame):
		_shoot(SHOTS[frame], frame == SHOTS.keys().max())


func _shoot(shot_name: String, is_last: bool) -> void:
	await RenderingServer.frame_post_draw
	var path := out_dir.path_join(shot_name + ".png")
	var error := get_viewport().get_texture().get_image().save_png(path)
	assert(error == OK, "could not save " + path)
	print("VISUAL_SHOT ", shot_name, " frame ", frame)
	if is_last:
		get_tree().quit()
