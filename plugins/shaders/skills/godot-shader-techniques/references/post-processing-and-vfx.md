# Post-processing, Shadertoy ports, transparency, ray marching, stencil (Godot 4.6+)

Read this when you are building a full-screen effect, palette or retro filter, porting a Shadertoy shader, fixing transparency sorting or depth problems, fading objects by distance, ray marching a volume, using 3D textures, or masking with the stencil buffer.

Book for the "Deeper" pointers: *The Godot Shaders Bible* ("Shaders Bible"; PDF page = printed page + 1).

---

## 1. Pick the post-processing route

| Route | Sees | Depth/normals | Editor preview | Use for |
|---|---|---|---|---|
| `CanvasLayer` → full-rect `ColorRect` with a `canvas_item` shader | Final 3D image **after tonemap** + 2D drawn below it | No | 2D editor only; run the game for 3D scenes | Color grading, palettes, pixelation, CRT, vignettes, UI-aware effects |
| `MeshInstance3D` full-screen quad with a `spatial` shader | Opaque 3D pass (**linear HDR, before tonemap**, no transparents) | `hint_depth_texture`, `hint_normal_roughness_texture` (Forward+ only) | Yes, in the 3D viewport | Fog, outlines from depth/normals, world-space scans, soft intersections |
| `Environment` built-ins (glow, adjustments, color-correction LUT) | Whole frame | n/a | Yes | Grading or a LUT palette without custom code (try this first) |
| `Compositor` + `CompositorEffect` (compute) | Any stage you hook | Yes | Yes | Heavy or multi-pass effects that need compute; more code |
| Render 3D into a low-res `SubViewport`, show it with nearest filtering | Everything | n/a | Yes | True low-resolution retro look (cheaper than shader pixelation) |

## 2. canvas_item full-screen pass

```glsl
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, repeat_disable, filter_nearest;

void fragment() {
	vec3 c = textureLod(screen_tex, SCREEN_UV, 0.0).rgb;
	COLOR = vec4(c, 1.0);
}
```

Setup rules:
- `ColorRect` anchors = Full Rect, inside a `CanvasLayer` (use a high `layer` to stay above the HUD, or a low one to leave the HUD untouched).
- Set `mouse_filter = MOUSE_FILTER_IGNORE`. Otherwise the overlay eats every click meant for the UI below.
- Screen copies are lazy. The **first** item in a canvas that reads `hint_screen_texture` triggers one copy, and later readers in the same canvas reuse it. To chain two passes, put a `BackBufferCopy` (copy mode Viewport) between them, or put the second pass on its own `CanvasLayer`. Otherwise pass 2 doesn't see pass 1.
- Use `filter_nearest` for pixel-exact reads. Use `filter_linear_mipmap` + `textureLod(screen_tex, uv, lod)` for cheap blur. Mipmap generation costs extra every frame.
- `SCREEN_PIXEL_SIZE` = 1 / viewport size in pixels (fragment only). Effects measured in screen pixels should use it so they look the same at any resolution, or stay deliberately resolution-dependent.
- Values are display-referred (sRGB, 0..1) unless `use_hdr_2d` is on. That suits palette mapping.

Deeper: Shaders Bible ch.4 "Post-Processing and the Game Boy Effect", PDF pp. 284–297.

## 3. spatial full-screen quad (depth-aware)

Scene: `MeshInstance3D` + `QuadMesh` (size 2×2) in front of the camera, `cast_shadow = off`, `extra_cull_margin = 16384` (so it is never frustum-culled).

```glsl
shader_type spatial;
render_mode unshaded, fog_disabled, depth_draw_never, depth_test_disabled, shadows_disabled;

uniform sampler2D screen_tex : hint_screen_texture, repeat_disable, filter_nearest;
uniform sampler2D depth_tex : hint_depth_texture, repeat_disable, filter_nearest;

void vertex() {
	POSITION = vec4(VERTEX.xy, 1.0, 1.0);   // straight to clip space, covers the screen
}

vec3 view_pos_from_depth(vec2 screen_uv, float raw_depth, mat4 inv_proj) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(screen_uv, raw_depth) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth);
#endif
	vec4 v = inv_proj * vec4(ndc, 1.0);
	return v.xyz / v.w;
}

void fragment() {
	float raw = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	vec3 view_pos = view_pos_from_depth(SCREEN_UV, raw, INV_PROJECTION_MATRIX);
	float linear_depth = -view_pos.z;                                // meters from camera
	vec3 world_pos = (INV_VIEW_MATRIX * vec4(view_pos, 1.0)).xyz;
	vec3 scene = textureLod(screen_tex, SCREEN_UV, 0.0).rgb;
	float fog = 1.0 - exp(-linear_depth * 0.03);
	ALBEDO = mix(scene, vec3(0.6, 0.7, 0.8), fog);
}
```

Facts and traps:
- Since 4.3, depth is **reverse-Z** in Forward+/Mobile (1 = near, 0 = far). Old snippets that use `depth * 2.0 - 1.0` for z are wrong there. Compatibility still uses GL's −1..1, so branch with `CURRENT_RENDERER` (preprocessor define, 4.4+).
- Reading the screen, depth or normal texture moves the material to the **transparent pass**. The quad never sees other transparent objects. Raise its material `render_priority` so it draws after the other transparents.
- The screen texture here is **linear HDR before tonemapping**, and your output gets tonemapped again. Hard palette colors shift, so do palettes on the canvas_item route.
- The camera ray for any screen pixel (for ray marching from a quad): `normalize(view_pos_from_depth(SCREEN_UV, 0.5, INV_PROJECTION_MATRIX))` in view space. Rotate it to world with `mat3(INV_VIEW_MATRIX)`. The origin is `CAMERA_POSITION_WORLD` (perspective only).

## 4. Palette quantization (Game Boy style and similar)

```glsl
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, repeat_disable, filter_nearest;
uniform sampler2D palette : filter_nearest, repeat_disable;   // N x 1 strip, darkest -> brightest
uniform int pixel_size : hint_range(1, 16) = 4;
uniform vec2 contrast = vec2(0.1, 0.9);                       // luminance remap window
uniform float dither : hint_range(0.0, 1.0) = 0.5;

const float BAYER4[16] = float[16](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0,
		3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void fragment() {
	vec2 block = float(pixel_size) * SCREEN_PIXEL_SIZE;
	vec2 cell = floor(SCREEN_UV / block);
	vec3 src = textureLod(screen_tex, (cell + 0.5) * block, 0.0).rgb;   // block center

	int n = textureSize(palette, 0).x;
	float l = smoothstep(contrast.x, contrast.y, luma(src));
	ivec2 b = ivec2(mod(cell, 4.0));
	l += ((BAYER4[b.x + b.y * 4] + 0.5) / 16.0 - 0.5) * dither / float(n);
	int idx = clamp(int(l * float(n)), 0, n - 1);
	COLOR = vec4(texelFetch(palette, ivec2(idx, 0), 0).rgb, 1.0);
}
```

Rules:
- Use `texelFetch` (integer texel) on the palette strip. It is exact and needs no "+0.5 band center" math or V flip.
- Without a texture, use `uniform vec4 colors[4] : source_color;`, or a `GradientTexture1D` with constant interpolation sampled at `vec2(l, 0.5)`.
- For arbitrary palettes (not luminance-ordered), loop over the entries and keep the nearest color by `dot(d, d)`. It costs O(N) per pixel, so keep N ≤ 16.
- Dither **before** quantizing (ordered Bayer, or blue noise) to get rid of banding. Index the dither by the pixel-art cell, not the screen pixel, when you also pixelate.
- Sample the **center** of each block: `(floor(uv / block) + 0.5) * block`. Adding a whole block instead shifts the image by one cell.
- Checkerboard / screen-door overlay: `mod(cell.x + cell.y, 2.0)`.

## 5. Porting from Shadertoy: checklist

| Shadertoy | Godot |
|---|---|
| `void mainImage(out vec4 fragColor, in vec2 fragCoord)` | `void fragment()`. Paste the body, or keep it as a helper `vec4 main_image(vec2 frag_coord)` |
| `fragColor` | `COLOR` (canvas_item). In spatial: `ALBEDO` + `ALPHA`, usually with `render_mode unshaded` |
| `fragCoord` (pixels, **origin bottom-left**) | `vec2(UV.x, 1.0 - UV.y) * resolution`. `FRAGCOORD.xy` has a **top-left** origin; flip y if you use it |
| `iResolution.xy` | `1.0 / SCREEN_PIXEL_SIZE` (full-screen rect), `VIEWPORT_SIZE` (spatial), or a uniform for a smaller rect |
| `iTime` | `TIME` (scaled by `time_scale`, wraps at the rollover; see procedural-and-vertex.md §3) |
| `iTimeDelta`, `iFrame`, `iDate` | Uniforms you set from GDScript |
| `iMouse` | Uniform. Convert y: `viewport_height - mouse.y`. `.zw` (click state) is your own logic |
| `iChannel0..3` | `uniform sampler2D channel0 : repeat_enable, filter_linear_mipmap;` (Shadertoy defaults to repeat + mipmaps) |
| Channel "vflip" (on by default) | When sampling with bottom-left-origin coords, flip: `texture(channel0, vec2(uv.x, 1.0 - uv.y))` |
| `iChannelResolution[i]` | `vec2(textureSize(channel0, 0))` |
| `texture2D`, `textureCube` | `texture()`; `samplerCube` |
| Buffer A–D (multipass), feedback | One `SubViewport` per buffer feeding a `ViewportTexture`. For feedback, ping-pong two SubViewports, or use a `CompositorEffect` |
| Keyboard texture | Uniforms or an `Image` you update |

Language traps:
- **No implicit int↔float conversion.** `x * 2`, `vec2 * int`, `float f = 1;` and `pow(x, 2)` are all errors. Write `2.0` or `float(i)`.
- **No mutable globals.** Turn them into `const`, locals passed through functions, or uniforms.
- Remove `precision` statements and `#version`. `#define` and `#if` work (Godot preprocessor).
- Shadertoy outputs display (sRGB) values. That is fine in canvas_item. In a spatial `unshaded` material `ALBEDO` is treated as linear, so convert or the result looks washed out: `pow(c, vec3(2.2))`.
- Shadertoy tolerates huge loops. On your target hardware, profile before shipping a 200-step loop on a full-screen quad.

Deeper: Shaders Bible ch.4 "Porting an Effect from Shadertoy", PDF pp. 298–300.

## 6. Transparency, depth, sorting, distance fades

What puts a spatial material in the **transparent (sorted) pass**:
- Writing `ALPHA`. Exception: a pure cutout with `ALPHA_SCISSOR_THRESHOLD` or `ALPHA_HASH_SCALE` stays opaque. Adding `ALPHA_ANTIALIASING_EDGE` to a cutout moves it back to the transparent pass, with a depth prepass.
- Reading `hint_screen_texture`, `hint_depth_texture` or `hint_normal_roughness_texture`.
- `depth_draw_never`, `depth_test_disabled` or `depth_test_inverted`, or a blend mode other than mix with alpha.

Consequences of the transparent pass: objects are sorted back to front **per object** (by AABB center, plus `VisualInstance3D.sorting_offset`), not per triangle. They don't appear in the depth or screen textures, SSAO or SSR. They **don't cast shadows** unless `depth_prepass_alpha` (or alpha antialiasing) is on, according to the Forward+ source.

| Need | Use |
|---|---|
| Leaves, fences, hair cards, hard cutouts | `ALPHA_SCISSOR_THRESHOLD = 0.5;`. Stays opaque, casts shadows, no sorting |
| Cutout with smooth edges | Scissor + `ALPHA_ANTIALIASING_EDGE` and `ALPHA_TEXTURE_COORDINATE = UV * vec2(textureSize(tex, 0));`, plus `render_mode alpha_to_coverage` with MSAA on |
| Soft cutout, no sorting | `ALPHA_HASH_SCALE` (noisy; pairs well with TAA) |
| Mostly opaque, self-overlapping, needs soft alpha | `render_mode depth_prepass_alpha` (writes depth for alpha ≈ 1 parts, blends the rest) |
| Glass, smoke, holograms | Plain alpha (`ALPHA`). Keep geometry convex/non-intersecting, or split meshes |
| Ordering two transparent materials | Material `render_priority` (higher draws later, on top) or `sorting_offset`. Neither changes order relative to opaque objects |
| Transparent mesh must hide what is behind it | `depth_draw_always` (writes depth in the transparent pass; later transparents behind it vanish) |

Texture-side fixes for ragged alpha edges: import the alpha texture **Lossless** (or high-quality VRAM). VRAM compression bleeds into the alpha channel. Enable mipmaps, and premultiply or bleed color into transparent texels.

Distance or occluder fade without sorting problems: **dither + discard** keeps the object opaque.

```glsl
shader_type spatial;

global uniform vec3 player_position;     // Project Settings > Shader Globals; set from the player
uniform sampler2D albedo_tex : source_color;
uniform float fade_radius = 1.5;
uniform float fade_softness = 0.75;

varying vec3 world_pos;

float ign(vec2 p) {   // interleaved gradient noise: stable per pixel, cheap
	return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

float dist_to_segment(vec3 p, vec3 a, vec3 b) {
	vec3 ab = b - a;
	float h = clamp(dot(p - a, ab) / dot(ab, ab), 0.0, 1.0);
	return length(p - a - ab * h);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb;
	if (!IN_SHADOW_PASS) {   // in the shadow pass the "camera" is the light
		float d = dist_to_segment(world_pos, CAMERA_POSITION_WORLD, player_position);
		float visible = smoothstep(fade_radius - fade_softness, fade_radius, d);
		if (visible < ign(FRAGCOORD.xy)) {
			discard;
		}
	}
}
```
```gdscript
func _physics_process(_delta: float) -> void:
	RenderingServer.global_shader_parameter_set(&"player_position", global_position)
```

- To fade near the camera instead, replace `d` with `distance(world_pos, CAMERA_POSITION_WORLD)`. StandardMaterial3D has this built in: `distance_fade_mode` = Pixel Dither / Object Dither.
- An alpha fade (`ALPHA *= fade`) gives smoother results but brings sorting and shadow problems. Pair it with `depth_prepass_alpha`.
- `hash(SCREEN_UV)` noise is resolution-dependent and swims with the camera, so use `ign(FRAGCOORD.xy)` or a Bayer matrix.

Soft intersections (soft particles, water shoreline) use the depth texture:

```glsl
// in a transparent spatial shader, with depth_tex and view_pos_from_depth() from §3
float scene_z = -view_pos_from_depth(SCREEN_UV, textureLod(depth_tex, SCREEN_UV, 0.0).r, INV_PROJECTION_MATRIX).z;
float soft = clamp((scene_z - (-VERTEX.z)) / 0.5, 0.0, 1.0);   // 0.5 m fade band
ALPHA *= soft;
```

Deeper: Shaders Bible ch.4 "Transparencies and Distance", PDF pp. 301–316.

## 7. Ray marching a volume in a box

Approach: a `BoxMesh` (size 1) bounds the volume. Do the work in **box-local space**: then rotation, scale and position of the node all work. Cull **front** faces so the effect still renders with the camera inside the box. Stop at the box exit **and** at opaque scene depth. Bail out early once nearly opaque.

```glsl
shader_type spatial;
render_mode unshaded, cull_front, depth_draw_never, shadows_disabled, fog_disabled;

uniform sampler3D density_tex : filter_linear, repeat_disable;   // data texture: no source_color
uniform sampler2D depth_tex : hint_depth_texture, repeat_disable, filter_nearest;
instance uniform vec3 light_dir_local = vec3(0.0, 1.0, 0.0);   // toward the light, box space, normalized
uniform vec3 color_lit : source_color = vec3(1.0);
uniform vec3 color_shadow : source_color = vec3(0.35, 0.4, 0.5);
uniform float density_scale = 4.0;
uniform int max_steps : hint_range(8, 256) = 64;
uniform int light_steps : hint_range(0, 8) = 4;

varying vec3 cam_local;
varying vec3 frag_local;

void vertex() {
	cam_local = (inverse(MODEL_MATRIX) * vec4(CAMERA_POSITION_WORLD, 1.0)).xyz;
	frag_local = VERTEX;
}

vec3 view_pos_from_depth(vec2 screen_uv, float raw_depth, mat4 inv_proj) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vec3 ndc = vec3(screen_uv, raw_depth) * 2.0 - 1.0;
#else
	vec3 ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth);
#endif
	vec4 v = inv_proj * vec4(ndc, 1.0);
	return v.xyz / v.w;
}

vec2 box_hit(vec3 ro, vec3 rd) {   // slab test against [-0.5, 0.5]^3
	vec3 inv = 1.0 / rd;
	vec3 t0 = (vec3(-0.5) - ro) * inv;
	vec3 t1 = (vec3(0.5) - ro) * inv;
	vec3 tmin = min(t0, t1);
	vec3 tmax = max(t0, t1);
	return vec2(max(max(tmin.x, tmin.y), tmin.z), min(min(tmax.x, tmax.y), tmax.z));
}

float density_at(vec3 p) {
	if (any(greaterThan(abs(p), vec3(0.5)))) {
		return 0.0;   // repeat_disable clamps to the edge texel; never sample outside
	}
	return textureLod(density_tex, p + 0.5, 0.0).r * density_scale;
}

void fragment() {
	vec3 ro = cam_local;
	vec3 rd = frag_local - cam_local;   // not normalized: t = 1 at this (back-face) fragment
	vec2 t = box_hit(ro, rd);
	float t_start = max(t.x, 0.0);      // camera inside the box -> start at the camera
	float raw = textureLod(depth_tex, SCREEN_UV, 0.0).r;
	float scene_z = -view_pos_from_depth(SCREEN_UV, raw, INV_PROJECTION_MATRIX).z;
	float t_end = min(t.y, scene_z / -VERTEX.z);   // view depth is linear in t along the ray

	float step_t = max(t_end - t_start, 0.0) / float(max_steps);
	float step_len = step_t * length(rd);          // box units, for Beer-Lambert
	float jitter = fract(52.9829189 * fract(dot(FRAGCOORD.xy, vec2(0.06711056, 0.00583715))));

	float transmittance = 1.0;
	vec3 acc = vec3(0.0);
	for (int i = 0; i < max_steps; i++) {
		float ti = t_start + (float(i) + jitter) * step_t;
		if (ti > t_end || transmittance < 0.01) {
			break;                                  // early out: left the volume or opaque enough
		}
		vec3 p = ro + rd * ti;
		float d = density_at(p);
		if (d <= 0.001) {
			continue;
		}
		float od = 0.0;                             // optical depth toward the light
		for (int j = 1; j <= light_steps; j++) {
			od += density_at(p + light_dir_local * (0.08 * float(j)));
		}
		float lit = exp(-od * 0.08);
		float absorb = 1.0 - exp(-d * step_len);
		acc += transmittance * absorb * mix(color_shadow, color_lit, lit);
		transmittance *= 1.0 - absorb;
	}
	float alpha = 1.0 - transmittance;
	ALBEDO = acc / max(alpha, 1e-4);   // acc is premultiplied; un-premultiply for blend_mix
	ALPHA = alpha;
}
```
```gdscript
@export var sun: DirectionalLight3D
@onready var _box: MeshInstance3D = $CloudBox
func _process(_delta: float) -> void:
	# DirectionalLight3D shines along its -Z, so +Z points toward the light.
	var to_light_local: Vector3 = (_box.global_basis.inverse() * sun.global_basis.z).normalized()
	_box.set_instance_shader_parameter(&"light_dir_local", to_light_local)
```

Rules and traps:
- Cost ≈ pixels × steps × (1 + light_steps) texture reads. 64 × (1 + 4) = 320 fetches per covered pixel. Budget it, keep the box tight, and render big volumes into a half-resolution `SubViewport` if needed.
- **Jitter the start** (noise on `FRAGCOORD`) to trade banding for fine noise. With TAA on, that lets you cut the step count a lot.
- Use `textureLod(..., 0.0)` inside loops. Implicit-LOD `texture()` needs derivatives, which are undefined in divergent loops.
- Integrate with Beer–Lambert (`exp(-density * step_length)`) so the look doesn't change when you change the step count. Summing raw densities ties the look to the step size.
- The volume doesn't write depth. Other transparent objects sort against the box's AABB center only. Writing `DEPTH` is possible but forces per-pixel depth export (slower, breaks early-Z).
- An SDF ray march (sphere tracing) uses the same framing: step by the SDF value, stop at `d < epsilon * t` or `t > t_end`, cap the iterations.
- Perspective cameras only. For orthographic, the ray direction is the camera forward (`-INV_VIEW_MATRIX[2].xyz`) and the origin is the fragment position pushed back along it.

Deeper: Shaders Bible ch.4 "Ray Marching and 3D Textures", PDF pp. 317–334.

## 8. 3D textures (`sampler3D`)

- Sources:
  - `NoiseTexture3D` (procedural, can be seamless; good for clouds and fog).
  - An image imported with **Import As: Texture3D** and the horizontal/vertical slice counts that match the sheet (e.g. 8×8 slices for 64 depth layers).
  - `ImageTexture3D.create(format, w, h, depth, use_mipmaps, images)` from code.
- Declare data volumes **without** `source_color` (density is not a color). Use `filter_linear` for smooth volumes, and `repeat_enable` only for tiling noise.
- Memory grows with the cube of the size: 128³ RGBA8 = 8 MiB, while R8 = 2 MiB. Store density in one channel and pack other fields into G/B/A.
- 8-bit sources band in smooth gradients. Use EXR/half-float, or add jitter/dither when sampling.
- `sampler2DArray` (Texture2DArray) is not the same: no filtering between layers. Use it for animated flipbooks and terrain layers, not volumes.

## 9. Stencil buffer (4.5+)

Syntax: one `stencil_mode` line, outside functions. Flags: `read`, `write`, `write_depth_fail`. Compare: `compare_always` (default), `compare_equal`, `compare_not_equal`, `compare_less`, `compare_less_or_equal`, `compare_greater`, `compare_greater_or_equal`. Reference: an integer 0–255.

```glsl
stencil_mode write, 1;                 // writer: stores 1 where the fragment passes depth
stencil_mode read, compare_equal, 1;   // reader: draws only where buffer == 1
```

Engine facts (Forward+/Mobile/Compatibility source):
- 8-bit buffer, cleared to 0 each frame. The read and write masks are fixed at 255; there are no custom bit masks in the shader syntax.
- `write` replaces the value when stencil **and depth pass**. `write_depth_fail` replaces it when **depth fails** (the occluded parts, for x-ray). Compare only has an effect together with `read`.
- Comparison order is Vulkan-style: `reference OP stored`. So `compare_greater` passes where `ref > buffer`.
- **A material that reads stencil must be in the transparent pass** (alpha blending, `depth_draw_never` or `depth_test_disabled`). Otherwise the engine prints "reads stencil but is not in the alpha queue".
- Stencil ops run only in the color pass. Opaque writers draw before every transparent reader. An opaque stencil writer forces a depth prepass, so writer fragments hidden by closer objects don't mark the stencil.
- Among transparent materials, a lower `render_priority` draws first. Give the writer the lowest priority when it is transparent too.
- `BaseMaterial3D.stencil_mode` offers ready-made Outline and X-Ray presets. Use them before you write a custom shader.

Recipes:

| Effect | Writer | Reader |
|---|---|---|
| Window or portal to a backdrop (sky, starfield) | Portal surface: opaque, `stencil_mode write, 1;`. Shape the opening with `discard`, not alpha | Backdrop: `render_mode unshaded, depth_draw_never, depth_test_disabled; stencil_mode read, compare_equal, 1;` |
| Hide something outside a region | Same writer | `stencil_mode read, compare_not_equal, 1;` |
| X-ray silhouette of a character behind walls | Character main material: `stencil_mode write, 2;` (marks its visible pixels) | `next_pass`: `render_mode unshaded, depth_draw_never, depth_test_inverted; stencil_mode read, compare_not_equal, 2;` (only occluded pixels, never over its own visible ones) |
| Portal into a full 3D room | Stencil alone can't clear depth inside the opening. Usually simpler: render the other side with a `SubViewport` camera and sample its texture by `SCREEN_UV` on the portal mesh | |

Pitfalls:
- Reader draws everywhere or nowhere → it is not in the transparent pass (check the error log), or the writer draws after it (`render_priority`).
- Ragged or soft portal edge → the writer used `ALPHA`. That moves it into the transparent pass and writes stencil even where alpha is 0. Use `discard` for the shape.
- A depth-tested reader behind an opaque writer's surface fails the depth test → make the writer transparent with `depth_draw_never` (and `ALPHA = 0.0` if it should be invisible), or give the reader `depth_test_disabled`.

Deeper: Shaders Bible ch.4 "Introduction to Stencil Buffer", PDF pp. 335–351.

## 10. Performance notes

- **Full-screen passes are paid per pixel.** At 4K that is about 8.3 M fragments per pass. Merge passes into one shader where you can. Every `BackBufferCopy` or new screen copy is another full-screen blit.
- **Overdraw:** big transparent quads, particles and volumes stack up. Shrink the geometry to the visible shape (a tight mesh rather than a quad), and prefer cutout (scissor/hash/dither) to blending where the look allows.
- **Texture reads:** dependent reads (UVs computed in the fragment) and 3D textures are the expensive part of ray marchers. Count fetches per pixel. Use `textureLod` in loops, single-channel formats, and lower-resolution volumes.
- **Branching:** branches on uniforms are effectively free. Per-pixel divergent branches run both sides across a warp. Early-out loops pay off when whole tiles exit together (empty space, opaque saturation).
- **`discard`**, `DEPTH` writes and alpha-to-coverage disable or weaken early-Z for that material. Keep `discard` shaders cheap before the discard point.
- **Screen and depth reads** in spatial force the transparent pass plus a copy of the opaque buffer. One post quad is fine; dozens of refractive objects are not.
- **Mipmapped screen texture** (`filter_linear_mipmap`) regenerates the mip chain every frame it is used.
- **Low resolution on purpose:** a pixelated, retro or volumetric look rendered in a smaller `SubViewport` is cheaper than full-resolution shader pixelation.
- Profile with the editor's Visual Profiler (GPU times per pass) and the Rendering → Draw Calls / Primitives monitors. Don't optimize by guessing.
