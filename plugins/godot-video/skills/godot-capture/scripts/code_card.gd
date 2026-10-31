extends SceneTree
## Records a code excerpt with Movie Maker, read from the file so it matches the source exactly.
##   godot --path copy --fixed-fps 24 --write-movie card.avi --script code_card.gd -- SECONDS FILE FIRST_LINE LAST_LINE [HEADER]

const FADE_SECONDS := 0.2
const BACKGROUND := Color(0.08, 0.09, 0.12)
const TEXT := Color(0.9, 0.91, 0.88)
const HEADER := Color(0.6, 0.72, 0.85)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 4:
		printerr("pass SECONDS FILE FIRST_LINE LAST_LINE after --")
		quit(1)
		return
	var first := args[2].to_int()
	var last := args[3].to_int()
	var lines := FileAccess.get_file_as_string(args[1]).split("\n")
	if first < 1 or last < first or last > lines.size():
		printerr("lines %d-%d are not in %s" % [first, last, args[1]])
		quit(1)
		return
	# The root window is still 100x100 here, so read the size from the settings.
	var height: int = ProjectSettings.get_setting("display/window/size/viewport_height")
	var width: int = ProjectSettings.get_setting("display/window/size/viewport_width")

	var background := ColorRect.new()
	background.color = BACKGROUND
	background.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.modulate.a = 0.0
	margin.add_theme_constant_override("margin_left", int(width * 0.06))
	margin.add_theme_constant_override("margin_right", int(width * 0.04))
	root.add_child(margin)
	var column := VBoxContainer.new()
	column.alignment = BoxContainer.ALIGNMENT_CENTER
	column.add_theme_constant_override("separation", int(height * 0.03))
	margin.add_child(column)
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["monospace"])
	var title := "%s:%d-%d" % [args[1].get_file(), first, last] if args.size() < 5 else args[4]
	column.add_child(_label(title, font, int(height * 0.028), HEADER))
	var excerpt := "\n".join(lines.slice(first - 1, last)).replace("\t", "    ")
	# Long lines shrink the text instead of running off the edge.
	var size := int(height * 0.045)
	var available := width * 0.9
	var widest := 0.0
	for line in excerpt.split("\n"):
		widest = maxf(widest, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x)
	if widest > available:
		size = int(size * available / widest)
		print("code_card: text reduced to %d px; if that is hard to read, use fewer or shorter lines" % size)
	column.add_child(_label(excerpt, font, size, TEXT))
	margin.create_tween().tween_property(margin, "modulate:a", 1.0, FADE_SECONDS)
	await create_timer(args[0].to_float()).timeout
	quit()


func _label(text: String, font: Font, size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_override("font", font)
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	return label
