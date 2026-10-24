# Spaces, Matrices and Shader Stages (Godot 4.6+)

Read this file when a shader moves vertices, mixes positions or directions from different sources, needs world or object coordinates in `fragment()`, builds a TBN, writes a billboard, or overrides `POSITION`. Every snippet below compiles on 4.7.
Book for the "Deeper" lines: *The Godot Shaders Bible* ("Shaders Bible"; PDF page = printed page + 1).

## 1. Conventions that cause silent bugs

- Godot is right-handed and Y-up. In view space the camera looks down **-Z**, so visible fragments have `VERTEX.z < 0` and linear depth is `-VERTEX.z`.
- UV origin is the **top-left** corner and V grows downward. Image "up" is therefore -V.
- Matrices are column-major. `m[i]` is column i, and `mat3(a, b, c)` takes **columns**. `M * v` applies the transform. `v * M` applies `transpose(M)`, which is the inverse only for pure rotations.
- Suffix variables with their space (`pos_os`, `n_ws`, `view_vs`, `v_ts`). A `dot()` between vectors from two different spaces still compiles, but the result is meaningless.
- A built-in that is missing in a stage is a compile error, not a zero. Custom functions cannot read stage built-ins (`NORMAL`, `VERTEX`…). Pass them as arguments. `TIME` and uniforms are readable everywhere.

## 2. Which space each built-in lives in (spatial)

| Built-in | `vertex()` | `fragment()` | `light()` |
|---|---|---|---|
| `VERTEX` | object (world with `world_vertex_coords`) | view-space position | not available, pass a varying |
| `NORMAL` | object | view | view |
| `TANGENT`, `BINORMAL` | object | view | not available, pass a varying |
| `VIEW` (unit, surface → camera) | not available | view | view |
| `LIGHT` (unit, surface → light) | n/a | n/a | view |
| `NODE_POSITION_WORLD`, `CAMERA_POSITION_WORLD`, `CAMERA_DIRECTION_WORLD` | world | world | not available |
| `NODE_POSITION_VIEW` | view | view | not available |
| `POSITION` (write only) | clip space; overrides the projection | n/a | n/a |
| `FRAGCOORD` | n/a | window pixels in xy, depth in z | yes |
| `SCREEN_UV` | n/a | 0–1 over the viewport | yes |
| `UV`, `UV2` | texture space (does not change when the object moves) | same | same |

Rule: lighting math works in **view space** because that is what `fragment()` and `light()` give you. Convert only the one vector you need, and not the whole lighting setup.

Deeper: Shaders Bible ch.1 "Introduction to Spaces", PDF pp. 23–26; "Rendering Stages and Pipeline", PDF pp. 35–40.

## 3. Built-in matrices

| Matrix | Maps | Stages | Notes |
|---|---|---|---|
| `MODEL_MATRIX` | object → world | vertex, fragment, light | `[3].xyz` = origin, `length([0].xyz)` = X scale |
| `MODEL_NORMAL_MATRIX` | object → world, for normals | vertex, fragment | inverse-transpose; correct under non-uniform scale |
| `VIEW_MATRIX` | world → view | all | |
| `INV_VIEW_MATRIX` | view → world | all | `[0]` camera right, `[1]` up, `[2]` back (forward = `-[2]`), `[3]` camera position |
| `MODELVIEW_MATRIX` | object → view | vertex only, **writable** | write it to change how the mesh is placed (billboards) |
| `MODELVIEW_NORMAL_MATRIX` | object → view, for normals | vertex only, writable | update it whenever you write `MODELVIEW_MATRIX` |
| `PROJECTION_MATRIX` / `INV_PROJECTION_MATRIX` | view ↔ clip | all | |
| `MAIN_CAM_INV_VIEW_MATRIX` | main camera's view → world | vertex | stays the main camera's matrix during shadow passes |

After `vertex()`, Godot computes `PROJECTION_MATRIX * MODELVIEW_MATRIX * vec4(VERTEX, 1.0)` for you. If you write `POSITION` anywhere in the shader, that value is used as is. You then own the projection for every vertex, in every pass.

```glsl
shader_type spatial;
varying vec3 pos_os;   // object space, carried to fragment()
varying vec3 pos_ws;   // world space

void vertex() {
	pos_os = VERTEX;
	pos_ws = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;   // point: w = 1
	vec3 n_ws = normalize(MODEL_NORMAL_MATRIX * NORMAL); // normal: normal matrix
}

void fragment() {
	// view -> world, recomputed per pixel (no varying needed)
	vec3 p_ws = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 n_ws = mat3(INV_VIEW_MATRIX) * NORMAL;     // view matrix has no scale: mat3 is fine
	vec3 v_ws = mat3(INV_VIEW_MATRIX) * VIEW;
	float dist = length(CAMERA_POSITION_WORLD - p_ws);
	ALBEDO = vec3(fract(pos_os.y), n_ws.y * 0.5 + 0.5, dist * 0.01);
}
```

- To get an object-space position in `fragment()`, use a varying. Rebuilding it with `inverse(MODEL_MATRIX)` costs a 4×4 inverse per pixel.
- Use the varying `pos_ws` when it needs to be stable. Use the `INV_VIEW_MATRIX` path when you need no extra interpolator.

Deeper: Shaders Bible ch.1 "Introduction to Matrices" and "Built-in Matrices", PDF pp. 73–84.

## 4. Points vs directions

| Kind | Homogeneous w | Transform with | After transform |
|---|---|---|---|
| Point (vertex, light position) | 1.0 | full `mat4` | divide by `w` only after a projection |
| Direction (view dir, light dir, tangent) | 0.0 (or `mat3(M)`) | upper 3×3 | `normalize()` if the matrix scales |
| Normal | — | inverse-transpose (`MODEL_NORMAL_MATRIX`, `MODELVIEW_NORMAL_MATRIX`) | `normalize()` |

- `w = 0` ignores translation but keeps scale and shear. A scaled object gives directions that are not unit length, so renormalize them.
- Normals transformed with the plain model matrix are wrong under non-uniform scale or shear. Normals lean toward the stretched axis and lighting slides.
- `LIGHT`, `VIEW` and `NORMAL` are directions, so lighting is a comparison of angles (`dot`). Never subtract a direction from a point.

Deeper: Shaders Bible ch.2 "Vector: Points vs. Directions", PDF p. 114.

## 5. Which space to use

| Effect wants… | Space | How |
|---|---|---|
| Lighting, rim, fresnel, specular | view | use `NORMAL`, `VIEW`, `LIGHT` directly |
| To stay fixed in the world while the object moves (triplanar ground, snow on top faces, height fog, world grid, position-based color hash) | world | `pos_ws` varying or `INV_VIEW_MATRIX` |
| To stick to the mesh (dissolve by local height, wobble, local gradients) | object | `pos_os = VERTEX` varying in `vertex()` |
| Detail relative to the surface (normal maps, parallax, anisotropy direction) | tangent | TBN (section 7) |
| Screen-locked (vignette, dither, screen distortion) | screen | `SCREEN_UV`, `FRAGCOORD` |
| Texture lookup that follows the art | UV | `UV` |

"Sky color from above" style tests (`n.y`) must use a **world** normal. The view-space `NORMAL.y` changes when the camera pitches.

## 6. Stages, as they matter for writing code

1. **`vertex()`** runs per vertex, in object space. It also runs in the **depth prepass and shadow passes**, where `VIEW_MATRIX` and `PROJECTION_MATRIX` belong to the light. Camera-dependent vertex code (billboards, camera-facing offsets) then faces the light. Use `MAIN_CAM_INV_VIEW_MATRIX` or branch on `IN_SHADOW_PASS`.
2. **Rasterization** interpolates varyings with perspective correction. Use `varying flat int id;` for values that must not blend.
3. **`fragment()`** runs per visible pixel and writes surface data (`ALBEDO`, `NORMAL_MAP`, `ROUGHNESS`, `EMISSION`, `ALPHA`).
4. **`light()`** runs after `fragment()`, **once per light per pixel**, and accumulates into `DIFFUSE_LIGHT` and `SPECULAR_LIGHT`. It does not run if no light reaches the pixel. See `lighting-models.md`.
5. **Composition** (engine): diffuse × albedo × (1 − metallic), + specular, + ambient/reflections, + emission, then fog, exposure, tonemap and the linear → sRGB output.

Renderer differences:

| Renderer | Behavior |
|---|---|
| Forward+ | clustered lights, cheap many-light scenes |
| Mobile | caps the lights per mesh |
| Compatibility | draws extra additive passes per light, so per-light cost is a whole extra draw |

Vertex displacement does not update the mesh AABB. Displaced parts get frustum-culled at screen edges. Set `extra_cull_margin` or `custom_aabb` on the GeometryInstance3D.

Deeper: Shaders Bible ch.1 "Rendering Stages and Pipeline", PDF pp. 35–40.

## 7. Tangent space and the TBN

- `TANGENT` follows +U. In Godot `BINORMAL` follows image-up (−V). This matches the OpenGL / Y+ normal-map convention that Godot uses.
- In `fragment()`, `mat3 TBN = mat3(TANGENT, BINORMAL, NORMAL);` (columns, view space).
  - Tangent → view: `TBN * v_ts`.
  - View → tangent: `v_vs * TBN` (the transpose, valid because the basis is about orthonormal). This is the same as `vec3(dot(T,v), dot(B,v), dot(N,v))`.
- Converting a tangent-space vector to a **UV** offset flips Y: `uv_dir = vec2(v_ts.x, -v_ts.y)`. Godot's own height-map code builds the basis with `-BINORMAL` for this reason.
- The mesh must have tangents. Imported scenes need the `meshes/ensure_tangents` import option (on by default). An `ArrayMesh` needs an `ARRAY_TANGENT` array, and a `SurfaceTool` mesh needs `generate_tangents()`. Without tangents Godot prints a runtime warning, and normal maps and parallax shade wrongly.
- `TANGENT` and `BINORMAL` are not readable in `light()`. Copy them to varyings in `fragment()`.

Fake interior depth (eyes, windows, gems), with no geometry:

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color, repeat_disable;
uniform sampler2D depth_mask : hint_default_white; // white = deepest
uniform float depth : hint_range(0.0, 0.3) = 0.1;

void fragment() {
	mat3 tbn = mat3(TANGENT, BINORMAL, NORMAL);
	vec3 view_ts = normalize(VIEW * tbn);            // view -> tangent
	vec2 uv_dir = vec2(view_ts.x, -view_ts.y);       // tangent -> UV axes
	float d = depth * texture(depth_mask, UV).r;
	vec2 uv = UV - uv_dir * d;                        // subtract = recedes behind the surface
	ALBEDO = texture(albedo_tex, uv).rgb;
}
```

- Use `repeat_disable` (or clamp in code) so the shifted UVs do not pull in pixels from the opposite edge.
- Dividing `uv_dir` by `view_ts.z` gives true parallax, which grows strong at grazing angles. Clamp it, or keep the version without the divide for a stable stylized result.

Deeper: Shaders Bible ch.1 "Introduction to Tangent Space" and "Implementing Tangent Space", PDF pp. 50–66.

## 8. Per-object variation from world position

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color;

vec3 hash33(vec3 p) {
	p = fract(p * vec3(0.1031, 0.1030, 0.0973));
	p += dot(p, p.yxz + 33.33);
	return fract((p.xxy + p.yxx) * p.zyx);
}

void fragment() {
	vec3 tint = hash33(floor(NODE_POSITION_WORLD));   // changes only per whole meter
	ALBEDO = texture(albedo_tex, UV).rgb * mix(vec3(0.85), vec3(1.15), tint);
}
```

- Use `floor()`/snapping so the color does not flicker while the object moves.
- Many copies of one material each get their own look with no extra material. Prefer this to `make_unique()` per instance.
- **MultiMesh:** `NODE_POSITION_WORLD` is the node's origin, not each instance's (verify). Instead, hash `INSTANCE_ID` or `INSTANCE_CUSTOM` in `vertex()`, or `MODEL_MATRIX[3].xyz` there, and pass the result as a varying.

Deeper: Shaders Bible ch.1 "Configuring a Unique Object" and "Working with World Space Coordinates", PDF pp. 27–49.

## 9. Billboard by rewriting MODELVIEW_MATRIX

There is no need for `skip_vertex_transform` or for writing `POSITION` by hand:

```glsl
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D tex : source_color;

void vertex() {
	mat4 face_cam = mat4(MAIN_CAM_INV_VIEW_MATRIX[0], MAIN_CAM_INV_VIEW_MATRIX[1],
			MAIN_CAM_INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);   // camera rotation + node origin
	face_cam *= mat4(vec4(length(MODEL_MATRIX[0].xyz), 0.0, 0.0, 0.0),
			vec4(0.0, length(MODEL_MATRIX[1].xyz), 0.0, 0.0),
			vec4(0.0, 0.0, length(MODEL_MATRIX[2].xyz), 0.0),
			vec4(0.0, 0.0, 0.0, 1.0));                        // keep the node's scale
	MODELVIEW_MATRIX = VIEW_MATRIX * face_cam;
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	vec4 c = texture(tex, UV);
	ALBEDO = c.rgb;
	ALPHA = c.a;
}
```

- Using `MAIN_CAM_INV_VIEW_MATRIX` makes the shadow face the main camera too. With `INV_VIEW_MATRIX`, the shadow-pass copy turns toward the light.
- For a Y-axis-only billboard (trees, sprites standing upright), keep `MODEL_MATRIX[1]` as the up column and build X from the camera's right vector.
- If `skip_vertex_transform` is set, you must move `VERTEX`, `NORMAL`, `TANGENT` and `BINORMAL` into view space yourself. If you forget the normals, lighting breaks while the mesh still looks right.

Deeper: Shaders Bible ch.1 "Built-in Matrices", PDF pp. 77–84.

## 10. Custom matrices

```glsl
shader_type spatial;
uniform float shear_x = 0.0;        // X moves with height
uniform vec3 scale = vec3(1.0);
uniform float twist = 0.0;          // radians per unit of height

mat3 shear_scale(vec3 s, float k) {
	// columns: images of the X, Y, Z axes
	return mat3(vec3(s.x, 0.0, 0.0), vec3(k * s.y, s.y, 0.0), vec3(0.0, 0.0, s.z));
}

mat2 rot2(float a) {
	float c = cos(a);
	float s = sin(a);
	return mat2(vec2(c, s), vec2(-s, c));  // CCW for M * v
}

void vertex() {
	mat3 m = shear_scale(scale, shear_x);
	VERTEX = m * VERTEX;
	VERTEX.xz = rot2(twist * VERTEX.y) * VERTEX.xz;
	NORMAL = normalize(transpose(inverse(m)) * NORMAL); // keep lighting right after shear / non-uniform scale
	// twist also bends normals; for small twists ignore it, otherwise rotate NORMAL.xz the same way
}
```

- Changes made to `VERTEX` in `vertex()` happen in object space, **before** `MODEL_MATRIX`. They stack with the node transform and leave the scene tree alone.
- Off-diagonal terms make one axis depend on another (shear). Column j holds where axis j goes.
- Build the matrix from uniforms or helper functions, not `#define` macros. Macros have no type checking, and an `int` literal in a macro argument fails inside `mat3()`.
- `mat4(1.0)` gives the identity. A single scalar fills the diagonal.
- Every time a vertex transform is not a rigid rotation, update `NORMAL` (and `TANGENT`) too. Otherwise the shape changes but the shading does not.

Deeper: Shaders Bible ch.1 "Implementing Custom Matrices", PDF pp. 85–95.

## 11. canvas_item spaces (2D)

| Matrix / built-in | Meaning |
|---|---|
| `VERTEX` in `vertex()` | local pixels (world with `world_vertex_coords`) |
| `MODEL_MATRIX` | local → world (canvas) |
| `CANVAS_MATRIX` | world → canvas view (includes Camera2D) |
| `SCREEN_MATRIX` | canvas view → clip |
| `SCREEN_UV`, `FRAGCOORD` | screen position in the fragment |

`skip_vertex_transform` in 2D means `VERTEX` must leave `vertex()` already in canvas-view space.

## 12. Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Sky/ground or "top faces" effect changes as the camera tilts | used view-space `NORMAL.y` | `mat3(INV_VIEW_MATRIX) * NORMAL` |
| Effect stays put on screen when the object moves | used `SCREEN_UV`/`VERTEX` (view) where world or object space was meant | pass `pos_os`/`pos_ws` varyings |
| Mesh vanishes after adding `skip_vertex_transform` | `VERTEX` never moved to view space | `VERTEX = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;` plus the normals |
| Lighting wrong after scaling or shearing in `vertex()` | normals not transformed | inverse-transpose, then normalize |
| Shadow of a billboard or camera-facing mesh is wrong | `vertex()` also runs in the shadow pass with the light's matrices | `MAIN_CAM_INV_VIEW_MATRIX` or `IN_SHADOW_PASS` |
| Displaced mesh pops out at screen edges | AABB not grown | `extra_cull_margin` / `custom_aabb` |
| Parallax or normal map pushes the wrong way on one axis | V axis vs BINORMAL sign | use `vec2(ts.x, -ts.y)` for UV offsets |
| Normal map / parallax does nothing or looks faceted, and a "requires tangents" warning appears | mesh has no tangents | `meshes/ensure_tangents` on import, or `generate_tangents()` |
| Every MultiMesh instance has the same "random" color | `NODE_POSITION_WORLD` is per node | `INSTANCE_ID`/`INSTANCE_CUSTOM` in `vertex()` |
| Depth reconstruction is upside down or flat on some renderers | reversed-Z (4.3+) and different NDC z ranges | Forward+/Mobile: `vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0)`; Compatibility needs `depth * 2.0 - 1.0` (verify) |
