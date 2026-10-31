extends SceneTree
## Records a text card with Movie Maker, using the project's default theme and font.
##   godot --path copy --fixed-fps 24 --write-movie card.avi --script title_card.gd -- SECONDS "TITLE" ["SUBTITLE"]

const FADE_SECONDS := 0.25
const BACKGROUND := Color(0.05, 0.05, 0.09)


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	assert(args.size() >= 2, "pass SECONDS and TITLE after --")
	var seconds := args[0].to_float()
	var layout := CenterContainer.new()
	layout.set_anchors_preset(Control.PRESET_FULL_RECT)
	var column := VBoxContainer.new()
	layout.add_child(column)
	# The root window is still 100x100 here, so read the size from the settings.
	var height: int = ProjectSettings.get_setting("display/window/size/viewport_height")
	column.add_child(_label(args[1], int(height * 0.09)))
	if args.size() > 2:
		column.add_child(_label(args[2], int(height * 0.035)))
	var background := ColorRect.new()
	background.color = BACKGROUND
	background.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	root.add_child(layout)
	var tween := layout.create_tween()
	layout.modulate.a = 0.0
	tween.tween_property(layout, "modulate:a", 1.0, FADE_SECONDS)
	await create_timer(seconds).timeout
	quit()


func _label(text: String, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", font_size)
	return label
