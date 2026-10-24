# Procedural shapes, animation, vertex work and rotations (Godot 4.6+)

Read this when you are drawing shapes or masks in a shader without textures, animating with `TIME`, moving vertices (wind, wobble, pulse, billboards), rotating points or geometry in a shader, or choosing between `canvas_item` and `spatial` for an effect.

Book for the "Deeper" pointers: *The Godot Shaders Bible* ("Shaders Bible"; PDF page = printed page + 1).

---

## 1. Coordinate setup for 2D math

- Godot `UV` has its origin at the **top-left** and V grows **downward**, in both `canvas_item` and `spatial` (on a QuadMesh too). Shapes you design in a y-up graph (Desmos and similar) come out flipped unless you flip V.
- Centered, y-up, aspect-correct space:

```glsl
vec2 centered_uv(vec2 uv, float aspect) {   // aspect = width / height
	vec2 p = uv * 2.0 - 1.0;                  // -1..1
	p.y = -p.y;                               // y up
	p.x *= aspect;                            // circles stay circles
	return p;
}
```

- Getting the aspect ratio:
  - `canvas_item` on a Sprite2D or TextureRect drawn at native size: `TEXTURE_PIXEL_SIZE.y / TEXTURE_PIXEL_SIZE.x`.
  - On a ColorRect there is no real texture, so `TEXTURE_PIXEL_SIZE` is useless. Pass the size as a uniform or instance uniform, or estimate it in `fragment()` with `vec2 px = 1.0 / fwidth(UV);` (rect size in screen pixels; this breaks if the node is rotated).
- Sprite sheets, `AtlasTexture`, `region_enabled` and AnimatedSprite2D frames give `UV` in **atlas space**, not 0..1 per frame. Remap before you run any SDF math (`REGION_RECT` in canvas `fragment()`, verify its exact format), or put the procedural layer on its own node.
- Use the built-ins `radians()` and `degrees()` rather than writing `PI / 180.0` by hand. Expose angles in degrees with `hint_range(0.0, 360.0)` and convert inside the shader.

## 2. Masks: comparisons vs SDF + smoothstep

| Technique | Edge quality | Use for |
|---|---|---|
| `float(a < b)` or `step(b, a)` | Hard and aliased; shimmers when it moves or is minified | Pixel-art looks, internal binary masks |
| `smoothstep(e0, e1, x)` with fixed edges | Soft, but the blur width changes with zoom and resolution | Glows and deliberate soft falloff |
| SDF + `fwidth` | About one pixel of AA at any scale | Default for crisp procedural shapes |

Rule: write shapes as **signed distance** (negative inside, positive outside), then turn the distance into coverage once, at the end.

```glsl
// --- primitives (p is already centered and in shape-local space) ---
float sd_circle(vec2 p, float r) { return length(p) - r; }

float sd_box(vec2 p, vec2 half_size) {
	vec2 d = abs(p) - half_size;
	return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}

float sd_round_box(vec2 p, vec2 half_size, float r) {
	return sd_box(p, half_size - vec2(r)) - r;
}

float sd_segment(vec2 p, vec2 a, vec2 b) {
	vec2 pa = p - a;
	vec2 ba = b - a;
	float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
	return length(pa - ba * h);              // subtract a radius for a capsule
}

// --- boolean ops on distances ---
float op_union(float a, float b)     { return min(a, b); }
float op_intersect(float a, float b) { return max(a, b); }
float op_subtract(float a, float b)  { return max(a, -b); }     // a minus b
float op_smooth_union(float a, float b, float k) {               // k = blend radius
	float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
	return mix(b, a, h) - k * h * (1.0 - h);
}

// --- distance -> coverage with ~1px anti-aliasing ---
float fill(float d) {
	float w = fwidth(d);
	return 1.0 - smoothstep(-w, w, d);
}
float stroke(float d, float thickness) { return fill(abs(d) - thickness); }
```

Domain tricks (apply them to `p` *before* you evaluate the shape):
- Mirror symmetry: `p.x = abs(p.x);` draws one eye and gets both.
- Translate: `sd_circle(p - center, r)`.
- Rotate the shape by `+a`: evaluate at `rot2(-a) * p` (see §6).
- Repeat: `p = mod(p + 0.5 * cell, cell) - 0.5 * cell;`
- Uniform scale: `sd(p / s) * s` (multiply back so the distance stays in real units and the AA stays correct).

Composite layers back to front with `mix`. Don't add masks together:

```glsl
vec3 col = background;
col = mix(col, body_color, fill(d_body));
col = mix(col, eye_color,  fill(d_eyes));
float alpha = max(fill(d_body), fill(d_outline));   // not a sum: overlaps would give >1
```

Pitfalls:
- Overlapping masks combined with `+` → values above 1 → blown-out color or alpha. Use `max` (union), `clamp`, or `mix` layering.
- A hard `float(cond)` shape on a 3D quad sparkles in motion. Convert it to an SDF, or at least AA it with `fwidth` of the expression you compare.
- `fwidth` and `dFdx` are only meaningful in `fragment()`/`light()`. Inside a loop or a non-uniform branch the derivatives can be garbage, so compute `fwidth` outside the branch.
- Gradients of non-Euclidean "distances" (for example `x^4 + y^4 < r^4` superellipses, or any implicit inequality) are not unit length. `fwidth` AA still works because it measures the actual screen gradient, but `stroke()` widths will vary along the shape.
- Procedural shapes cost ALU per pixel on every frame. For a static icon, bake it to a texture. Keep procedural for shapes that animate or are parameterized.

Deeper: Shaders Bible ch.3 "Drawing with Functions and Inequalities", PDF pp. 189–201; "Procedural Character in GDSL", PDF pp. 207–227.

## 3. Time-based animation

Facts about `TIME`:
- It counts seconds since engine start. It **is scaled by `Engine.time_scale`** and is **not stopped by pausing the SceneTree**.
- It wraps at `rendering/limits/time/time_rollover_secs` (default 3600). Anything that isn't periodic with a period dividing the rollover jumps once an hour. Keep `sin(TIME * k)` frequencies moderate. `fract(TIME / period)` is safe only when the rollover is a multiple of `period`.
- For time that must pause, or be per-gameplay-clock, use a global shader uniform that you drive yourself:

```glsl
global uniform float game_time;   // declare in Project Settings > Shader Globals first
```
```gdscript
var _t: float = 0.0
func _process(delta: float) -> void:   # node with the process_mode you want
	_t += delta
	RenderingServer.global_shader_parameter_set(&"game_time", _t)
```

Building blocks:

| Want | Expression |
|---|---|
| Loop 0→1 | `fract(TIME / period)` |
| Ping-pong 0→1→0 | `abs(fract(TIME / period) * 2.0 - 1.0)` |
| Smooth pulse 0..1 | `0.5 + 0.5 * sin(TIME * TAU / period)` |
| Ease | `smoothstep(0.0, 1.0, t)`, or `t * t * (3.0 - 2.0 * t)` |
| Event every N s that lasts D s | `float c = mod(TIME, N); float k = clamp(c / D, 0.0, 1.0); float active = step(c, D);` |

Example: a glossy sweep on a UI image that runs for 0.6 s every 3 s. It is masked by the image's own alpha, so it adapts to any texture with one shared material:

```glsl
shader_type canvas_item;

uniform vec4 shine_color : source_color = vec4(1.0, 1.0, 1.0, 0.6);
uniform float period = 3.0;
uniform float sweep_time = 0.6;
uniform float band_width : hint_range(0.01, 0.5) = 0.12;
uniform vec2 band_dir = vec2(1.0, 0.35);   // direction the band travels

void fragment() {
	// COLOR already holds texture * modulate here; don't resample TEXTURE.
	float c = mod(TIME, period);
	float k = clamp(c / sweep_time, 0.0, 1.0);
	float active = step(c, sweep_time);
	vec2 dir = normalize(band_dir);
	float pos = dot(UV - 0.5, dir);                  // about -0.7..0.7 across the rect
	float center = mix(-0.8, 0.8, k);
	float band = 1.0 - smoothstep(0.0, band_width, abs(pos - center));
	COLOR.rgb += shine_color.rgb * shine_color.a * band * active * COLOR.a;
}
```

Per-instance variation (so shared materials don't animate in lockstep):

| Source | Shader type | Notes |
|---|---|---|
| `instance uniform float phase;` | spatial (4.0+), canvas_item (**4.4+**) | `node.set_instance_shader_parameter(&"phase", randf() * TAU)`. Max 16 per shader. No extra material. |
| Hash of `NODE_POSITION_WORLD` | spatial | Free, stable, no script. `fract(sin(dot(NODE_POSITION_WORLD, vec3(12.9898, 78.233, 37.719))) * 43758.5453)` |
| Hash of `MODEL_MATRIX[3].xy` | canvas_item vertex | Node position. It changes as the node moves; fine for static props. |
| `INSTANCE_CUSTOM` | MultiMesh (enable `use_custom_data`) | Per-instance vec4, set CPU-side. |
| `COLOR`/modulate as an ID | — | Avoid. It tints the node, and in canvas `fragment()` `COLOR` already has modulate baked in. |

Deeper: Shaders Bible ch.3 "Animation and Procedural Modification", PDF pp. 202–206; "Adding a Specular Effect to the UI", PDF pp. 241–253.

## 4. Vertex displacement and animation

### canvas_item

- `VERTEX` is a `vec2` in **local pixels** with y pointing down. Godot applies `MODEL_MATRIX` after `vertex()`.
- You do **not** need `skip_vertex_transform` for local deformation. Use it only when you want to apply the transform yourself (then `VERTEX = (MODEL_MATRIX * vec4(VERTEX, 0.0, 1.0)).xy;`). `world_vertex_coords` gives you canvas-space `VERTEX` instead.
- A Control's local origin is its **top-left** corner. A centered Sprite2D's origin is its center. To scale or rotate around a pivot, subtract the pivot, transform, then add it back:

```glsl
shader_type canvas_item;

instance uniform vec2 pivot_px;          // e.g. control.size * 0.5; (0,0) for a centered Sprite2D
instance uniform float phase;
uniform float pulse_amount : hint_range(0.0, 0.5) = 0.06;
uniform float pulse_speed = 1.5;         // cycles per second

void vertex() {
	float s = 1.0 + pulse_amount * (0.5 + 0.5 * sin(TIME * pulse_speed * TAU + phase));
	VERTEX = pivot_px + (VERTEX - pivot_px) * s;
}
```
```gdscript
func _ready() -> void:
	var rect: TextureRect = $Icon
	rect.set_instance_shader_parameter(&"pivot_px", rect.size * 0.5)
	rect.set_instance_shader_parameter(&"phase", randf() * TAU)
```

- Prefer `Control.pivot_offset` + `scale` with a Tween for ordinary UI juice. A shader moves pixels only: the **mouse/focus rect stays where the layout put it**, and Containers don't know about it. Use the shader when you have many items, need a continuous ambient motion, or must not disturb layout.

### spatial

- `VERTEX`, `NORMAL`, `TANGENT` and `BINORMAL` are in **model space** (y up). Godot applies `MODELVIEW_MATRIX` afterwards. With `render_mode world_vertex_coords` they arrive in world space, which is handy for world-aligned wind.
- `NODE_POSITION_WORLD`, `CAMERA_POSITION_WORLD`, `MODEL_MATRIX` and `INV_VIEW_MATRIX` are available in `vertex()`. Compute world position there and pass it to `fragment()` through a `varying`.
- The vertex shader also runs in the shadow and depth passes, so displaced shadows stay in sync automatically. Collision shapes do **not** move.

Wind sway (foliage, grass, flags). The weight comes from height above the pivot, or from a painted vertex color:

```glsl
shader_type spatial;
render_mode world_vertex_coords, cull_disabled;

uniform vec2 wind_dir = vec2(1.0, 0.3);
uniform float wind_strength = 0.15;
uniform float wind_speed = 1.2;
uniform float sway_height = 2.0;        // world units over which weight goes 0 -> 1
uniform bool use_vertex_color_weight = false;

void vertex() {
	float h = clamp((VERTEX.y - NODE_POSITION_WORLD.y) / sway_height, 0.0, 1.0);
	float weight = use_vertex_color_weight ? COLOR.r : h * h;   // rooted base, loose top
	float phase = dot(NODE_POSITION_WORLD.xz, vec2(0.37, 0.71));
	float gust = sin(TIME * wind_speed + phase) + 0.4 * sin(TIME * wind_speed * 2.7 + phase * 1.3);
	vec2 d = normalize(wind_dir);
	VERTEX.xz += d * gust * wind_strength * weight;
}
```

Wobble or jelly (`VERTEX += NORMAL * sin(VERTEX.y * 8.0 + TIME * 4.0) * 0.03;`): this tears open hard-edged meshes, because split vertices with different normals move apart. Displace along a smooth field instead (`normalize(VERTEX)` from the pivot, or a fixed axis), or author smooth normals.

Billboards: a StandardMaterial3D billboard mode is usually enough. In a custom shader, override `MODELVIEW_MATRIX`. Use `MAIN_CAM_INV_VIEW_MATRIX`, which stays the main camera in shadow passes, so shadows face the right way:

```glsl
void vertex() {
	// spherical billboard, keeps node scale
	vec3 s = vec3(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz), length(MODEL_MATRIX[2].xyz));
	mat4 m = mat4(MAIN_CAM_INV_VIEW_MATRIX[0] * s.x,
			MAIN_CAM_INV_VIEW_MATRIX[1] * s.y,
			MAIN_CAM_INV_VIEW_MATRIX[2] * s.z,
			MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = VIEW_MATRIX * m;
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}
```
For a Y-axis-locked billboard (trees, characters), use `x = normalize(cross(vec3(0,1,0), cam_z))`, `y = (0,1,0)`, `z = cross(x, y)` with `cam_z = MAIN_CAM_INV_VIEW_MATRIX[2].xyz`.

Deeper: Shaders Bible ch.3 "Vertex Transformation and Animation", PDF pp. 228–240.

## 5. Pitfalls after you move vertices

**Normals are stale.** symptom → cause → fix:
- Lighting looks painted on and doesn't follow the waves → `NORMAL` still describes the undisplaced surface → recompute it.
  - For pure rotations (or uniform scale), apply the same `mat3` to `NORMAL`, `TANGENT` and `BINORMAL`. For non-uniform scale, normals need `transpose(inverse(m))`.
  - For heightfield displacement, use finite differences:

```glsl
float height(vec2 p) { return 0.2 * sin(p.x * 2.0 + TIME) * cos(p.y * 1.7 + TIME * 0.8); }

void vertex() {
	const float e = 0.05;
	vec2 p = VERTEX.xz;
	float hand = sign(dot(cross(NORMAL, TANGENT), BINORMAL));   // keep the mesh's handedness
	VERTEX.y += height(p);
	float hx = height(p + vec2(e, 0.0)) - height(p - vec2(e, 0.0));
	float hz = height(p + vec2(0.0, e)) - height(p - vec2(0.0, e));
	NORMAL = normalize(vec3(-hx, 2.0 * e, -hz));
	TANGENT = normalize(vec3(2.0 * e, hx, 0.0));
	BINORMAL = normalize(cross(NORMAL, TANGENT)) * hand;
}
```

**Culling uses the undeformed bounds.**
- Mesh pops out of view near screen edges, or a vertex-animated object vanishes when its origin leaves the frustum → the AABB comes from the original mesh → enlarge it:
  - `GeometryInstance3D.extra_cull_margin` grows the box uniformly (simple, but it also hurts shadow and occlusion culling).
  - `GeometryInstance3D.custom_aabb`, or `custom_aabb` on ArrayMesh/PrimitiveMesh/MultiMesh, sets an exact box. This is better for big one-directional offsets.
- 2D: a displaced canvas item disappears when its rect leaves the screen → `RenderingServer.canvas_item_set_custom_rect(get_canvas_item(), true, Rect2(-64, -64, 256, 256))`.

```gdscript
@onready var _tree: MeshInstance3D = $Tree
func _ready() -> void:
	_tree.custom_aabb = AABB(Vector3(-1.5, 0.0, -1.5), Vector3(3.0, 5.0, 3.0))
```

**Other traps.**
- Per-instance random rotation or scale computed in the shader runs on every vertex every frame. If it never changes, bake it into the node or MultiMesh transforms on the CPU once.
- Vertex animation driven by `TIME` gives correct motion vectors for TAA/FSR2 automatically. Animation driven by a uniform you change from script may smear under TAA.
- Big displacements on low-poly meshes look faceted. Vertex count bounds the detail; there is no per-pixel displacement.

## 6. Rotations

### 2D rotation

```glsl
mat2 rot2(float a) {
	float c = cos(a);
	float s = sin(a);
	return mat2(vec2(c, s), vec2(-s, c));   // counter-clockwise by a
}
// rotate a point:            p' = rot2(a) * p
// rotate a SHAPE by a (SDF): evaluate the shape at rot2(-a) * p   (or p * rot2(a))
```

**Matrix constructors take columns.** `mat3(v0, v1, v2)` and `mat2(v0, v1)` take **columns**, so text-book matrices written row by row come out **transposed**. That is the inverse rotation, so things spin the wrong way. Write columns, or `transpose()` once.

Rotate around a pivot: `p = rot2(a) * (p - pivot) + pivot;`. In y-down UV space a positive angle looks clockwise; flip y first if that matters.

### 3D: axis matrices and axis-angle

```glsl
mat3 rot_x(float a) { float c = cos(a), s = sin(a); return mat3(vec3(1, 0, 0), vec3(0, c, s), vec3(0, -s, c)); }
mat3 rot_y(float a) { float c = cos(a), s = sin(a); return mat3(vec3(c, 0, -s), vec3(0, 1, 0), vec3(s, 0, c)); }
mat3 rot_z(float a) { float c = cos(a), s = sin(a); return mat3(vec3(c, s, 0), vec3(-s, c, 0), vec3(0, 0, 1)); }

// Rodrigues: rotate v around unit axis k by angle a
vec3 rotate_axis(vec3 v, vec3 k, float a) {
	float c = cos(a);
	float s = sin(a);
	return v * c + cross(k, v) * s + k * dot(k, v) * (1.0 - c);
}
```

- Godot's default Euler order is **YXZ**: `Basis = Ry * Rx * Rz` (Z is applied first). Match it (`rot_y(e.y) * rot_x(e.x) * rot_z(e.z)`) if the angles come from `Node3D.rotation`.
- Gimbal lock comes from composing three Euler angles, not from matrices as such. Inside a shader you rarely need Euler angles at all.
- **Best practice: don't rebuild an object's orientation from Euler angles in the shader.** Pass the orientation directly. `Basis` → `uniform mat3`, `Quaternion` → `uniform vec4`, `Vector3` origin → `uniform vec3`:

```gdscript
@export var projector: Node3D
@export var target: GeometryInstance3D
func _process(_delta: float) -> void:
	var mat := target.material_override as ShaderMaterial
	mat.set_shader_parameter(&"proj_basis", projector.global_basis)
	mat.set_shader_parameter(&"proj_origin", projector.global_position)
```
```glsl
uniform mat3 proj_basis;
uniform vec3 proj_origin;
// world -> projector-local: transpose == inverse for an orthonormal basis (use inverse() if scaled)
vec3 to_projector(vec3 world_pos) { return transpose(proj_basis) * (world_pos - proj_origin); }
// planar projection: sample with to_projector(world_pos).xy + 0.5
```
Push uniforms only when the source transform changes (`set_notify_transform(true)` + `NOTIFICATION_TRANSFORM_CHANGED`), not every frame. The `@tool` + `_process` pattern is for editor preview only.

### Quaternions in a shader

Store them as `vec4(x, y, z, w)`. Godot's `Quaternion` maps directly onto a `vec4` uniform.

```glsl
vec4 quat_axis_angle(vec3 axis, float a) {
	return vec4(normalize(axis) * sin(a * 0.5), cos(a * 0.5));
}
vec4 quat_mul(vec4 a, vec4 b) {          // apply b first, then a
	return vec4(a.w * b.xyz + b.w * a.xyz + cross(a.xyz, b.xyz), a.w * b.w - dot(a.xyz, b.xyz));
}
vec3 quat_rotate(vec4 q, vec3 v) {        // = q * v * conj(q), unit q only
	vec3 t = 2.0 * cross(q.xyz, v);
	return v + q.w * t + cross(q.xyz, t);
}
vec4 quat_nlerp(vec4 a, vec4 b, float t) {
	b = dot(a, b) < 0.0 ? -b : b;         // shortest path
	return normalize(mix(a, b, t));
}
```

- `quat_rotate` costs 2 crosses. The textbook `q * p * conj(q)` costs 2 full quaternion products. To rotate many points, convert the quaternion to a `mat3` once, then multiply.
- Inverse rotation of a unit quaternion = `vec4(-q.xyz, q.w)`.
- Use quaternions when you **interpolate or compose** rotations per vertex (procedural joints, spinning debris with per-instance axis). For a fixed orientation, a `mat3` uniform is simpler and cheaper.

Deeper: Shaders Bible ch.3 "Introduction to Rotations", PDF pp. 254–257; "Implementing a Rotation Matrix", PDF pp. 258–266; "Quaternion Implementation", PDF pp. 267–283.

## 7. canvas_item vs spatial: what changes

| Aspect | `canvas_item` (2D, UI) | `spatial` (3D) |
|---|---|---|
| `VERTEX` | `vec2`, local pixels, y down | `vec3`, model space, y up |
| Main output | `COLOR` (arrives in `fragment()` already = vertex color × modulate × `TEXTURE`) | `ALBEDO`, `ALPHA`, `EMISSION`, `NORMAL_MAP`… |
| Lit by default | Only by Light2D; `unshaded` skips it | Yes; `render_mode unshaded` for flat color |
| Texture size | `TEXTURE_PIXEL_SIZE` (1/size) | `textureSize(tex, 0)` |
| Per-instance data | `instance uniform` (4.4+), `INSTANCE_CUSTOM` (MultiMesh), `MODEL_MATRIX[3].xy` | `instance uniform`, `INSTANCE_CUSTOM`, `NODE_POSITION_WORLD` |
| Matrices | `MODEL_MATRIX`, `CANVAS_MATRIX`, `SCREEN_MATRIX` | `MODEL_MATRIX`, `VIEW_MATRIX`, `PROJECTION_MATRIX`, inverses, `MODELVIEW_MATRIX` |
| Screen reads | `SCREEN_UV`, `SCREEN_PIXEL_SIZE`, `hint_screen_texture` | `SCREEN_UV`, `VIEWPORT_SIZE`, screen/depth/normal_roughness textures |
| Culling bounds | Item rect → `canvas_item_set_custom_rect` | AABB → `extra_cull_margin` / `custom_aabb` |
| Transparency | Alpha blends in draw order; no sorting issue | Moves the object to the sorted transparent pass (see post-processing-and-vfx.md §6) |
| Color space of output | sRGB-ish (unless HDR 2D) | Linear; tonemapped afterwards |

Porting rules:
- In `canvas_item`, **don't resample `TEXTURE`** to "get the color" (`COLOR = texture(TEXTURE, UV)` throws away modulate). Read and modify `COLOR`.
- A procedural shape that works on a ColorRect needs a y flip and `ALBEDO`/`ALPHA` when you move it to a QuadMesh. Writing `ALPHA` moves the mesh to the transparent pass; use `ALPHA_SCISSOR_THRESHOLD` for hard cutouts so it stays opaque.
- `source_color` matters in spatial (sRGB → linear). Leave it off data textures (masks, noise, flow, density).
