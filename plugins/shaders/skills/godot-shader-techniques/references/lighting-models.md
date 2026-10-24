# Custom Lighting in Godot Shaders (4.6+)

Read this file before writing a `light()` function, a toon/NPR material, specular, rim, anisotropic or hemispheric lighting, or before touching color-space conversion, normal maps or `.gdshaderinc` libraries. Every snippet compiles on 4.7. For spaces and the TBN, see `spaces-and-matrices.md`.
Book for the "Deeper" lines: *The Godot Shaders Bible* ("Shaders Bible"; PDF page = printed page + 1).

## 1. Decide first: do you need `light()` at all?

| Goal | Use |
|---|---|
| PBR look with custom textures/masks | no `light()`; write `ALBEDO`, `ROUGHNESS`, `METALLIC`, `NORMAL_MAP`, `EMISSION` |
| Cheap banded toon | `render_mode diffuse_toon, specular_toon;` (`ROUGHNESS` controls the edge softness); add `light()` only if this is not enough |
| Rim glow | built-in `RIM`, `RIM_TINT` (driven by `ROUGHNESS`) when there is no `light()`; otherwise section 5 |
| Brushed metal / hair highlight | built-in `ANISOTROPY` + `ANISOTROPY_FLOW` with the default specular; custom model (section 6) only for stylized control |
| Ambient from sky/ground colors for the whole scene | Environment ambient (Sky or Color); custom hemispheric (section 7) only per material |
| No lighting | `render_mode unshaded;` (the cheapest option) |
| Stylized response to each light (ramps, tinted terminator, custom specular shape) | `light()` |

## 2. How `light()` works

- Defining `light()` replaces only the **per-light BRDF** of this material. It does not switch the renderer to deferred mode. The engine still adds ambient light, reflections (sky, ReflectionProbe, VoxelGI/SDFGI), emission and fog.
- It runs **after `fragment()`, once per light per pixel**. A pixel that no light reaches never runs it, and a scene with no lights never runs it.
- `DIFFUSE_LIGHT` and `SPECULAR_LIGHT` start at zero and accumulate across lights. **Always use `+=`.** Writing `=` throws away the lights already added.
- The engine then composes `DIFFUSE_LIGHT * ALBEDO * (1 - METALLIC) + SPECULAR_LIGHT + ambient + EMISSION`.
  - Do not multiply diffuse by `ALBEDO` yourself; the result would be albedo².
  - Specular is not tinted by albedo.
- `LIGHT_COLOR` is color × energy × **π**. The built-in Lambert divides by π, so `NdotL * LIGHT_COLOR * ATTENUATION / PI` matches StandardMaterial3D brightness. Leaving out `/ PI` makes the result π times brighter.
- `ATTENUATION` already includes distance falloff **and shadows**.
- Readable in `light()`:
  - `NORMAL`, `VIEW` and `LIGHT` (all unit vectors in view space);
  - `LIGHT_COLOR`, `ATTENUATION`, `LIGHT_IS_DIRECTIONAL`;
  - `ALBEDO`, `ROUGHNESS`, `METALLIC`, `SPECULAR_AMOUNT`, `BACKLIGHT`;
  - `UV`, `FRAGCOORD` and the matrices;
  - varyings written in `fragment()`.
- **Not** readable in `light()`: `VERTEX`, `TANGENT`, `BINORMAL`, `NODE_POSITION_WORLD`, `CAMERA_POSITION_WORLD`. Copy them into varyings in `fragment()`.
- With `light()` present, `fragment()` outputs that only the built-in BRDF reads stop doing anything: `RIM`, `RIM_TINT`, `ANISOTROPY*`, `CLEARCOAT*`. `ROUGHNESS` and `METALLIC` still drive ambient and reflections.
- Cost scales with pixels × lights.
  - Forward+ clusters lights.
  - Mobile caps the lights per mesh.
  - Compatibility re-draws the mesh for each extra light.
  - Move any per-pixel work that does not depend on the light into `fragment()`.

Deeper: Shaders Bible ch.2 "Introduction to the Lambertian Model", PDF pp. 99–101; "Implementing the Lambertian Model", PDF pp. 102–113.

## 3. Formula sheet

`n` = `NORMAL`, `l` = `LIGHT`, `v` = `VIEW`, `h = normalize(l + v)`, `t`/`b` = tangent/binormal, `m` = shininess.

| Model | Formula | Notes |
|---|---|---|
| Lambert diffuse | `max(n·l, 0)` | independent of the view |
| Wrapped diffuse | `max((n·l + w) / (1 + w), 0)` | softens the terminator (built-in: `diffuse_lambert_wrap`) |
| Phong specular | `max(reflect(-l, n)·v, 0)^m` | |
| Blinn-Phong specular | `max(n·h, 0)^m`, gated by `n·l > 0` | cheaper and more stable; needs about 4× the Phong exponent for the same spot size |
| Normalized Blinn-Phong | `(m + 8) / (8π) · max(n·h, 0)^m · n·l` | keeps energy roughly constant as `m` changes |
| Rim | `(1 - max(n·v, 0))^p` | `p` of 1–2 is broad, 4–8 is a thin edge |
| Schlick Fresnel | `F0 + (1 - F0)(1 - v·h)^5` | `F0` is about 0.04 for dielectrics |
| Ashikhmin-Shirley specular | `√((au+1)(av+1)) / (8π) · (n·h)^((au(h·t)² + av(h·b)²) / (1 - (n·h)²)) / ((v·h) · max(n·l, n·v)) · F` | anisotropic lobe; `au` stretches across `t`, `av` across `b` |
| Hemispheric ambient | `mix(ground, sky, n_ws.y · 0.5 + 0.5)` | needs the **world** normal |

## 4. Diffuse + Blinn-Phong, plus a toon variant

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color;
uniform float shininess : hint_range(1.0, 512.0) = 64.0;
uniform float spec_strength : hint_range(0.0, 4.0) = 1.0;

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb;
}

void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	vec3 radiance = LIGHT_COLOR * ATTENUATION;
	DIFFUSE_LIGHT += radiance * ndl / PI;                 // matches the built-in Lambert

	vec3 h = normalize(LIGHT + VIEW);
	float spec = pow(max(dot(NORMAL, h), 0.0), shininess);
	spec *= (shininess + 8.0) / (8.0 * PI);               // energy normalization
	SPECULAR_LIGHT += radiance * spec * ndl * spec_strength * SPECULAR_AMOUNT; // light's Specular slider
}
```

Toon `light()` (replace the one above):

```glsl
shader_type spatial;
uniform vec3 shade_color : source_color = vec3(0.25, 0.22, 0.45);
uniform float edge_softness : hint_range(0.001, 0.5) = 0.03;
uniform float spec_size : hint_range(0.0, 1.0) = 0.15;

void light() {
	float ndl = dot(NORMAL, LIGHT);
	float lit = smoothstep(0.0, edge_softness, ndl) * ATTENUATION;  // hard terminator, shadows included
	DIFFUSE_LIGHT += mix(shade_color, vec3(1.0), lit) * LIGHT_COLOR / PI;
	float nh = dot(NORMAL, normalize(LIGHT + VIEW));
	SPECULAR_LIGHT += step(1.0 - spec_size * 0.1, nh) * lit * LIGHT_COLOR / PI;
}
```

- `shade_color` is added **once per light**. With several lights the shadow tint stacks. Keep stylized shading to one key light, or move the tint into the ambient/emission term.
- `smoothstep` on `ndl` alone keeps omni falloff smooth. Applying it to `ndl * ATTENUATION` also makes the shadow edges and the light radius hard.

Deeper: Shaders Bible ch.2 "Introduction to the Blinn-Phong Model" and "Implementing the Blinn-Phong Model", PDF pp. 115–123.

## 5. Rim / Fresnel

Choose by what the rim represents:

- **Edge glow that ignores lights** (selection outline, force field, ghost): compute it in `fragment()` and write it to `EMISSION`. It is applied once, even in the dark, and does not stack with the light count.
- **Back-light or sheen that needs a light**: compute it in `light()` and mask it with the light direction.

```glsl
shader_type spatial;
uniform vec3 rim_color : source_color = vec3(0.4, 0.8, 1.0);
uniform float rim_power : hint_range(0.5, 8.0) = 3.0;
uniform float rim_strength : hint_range(0.0, 4.0) = 1.0;

void fragment() {
	ALBEDO = vec3(0.5);
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), rim_power);
	EMISSION = rim_color * rim * rim_strength;           // view-only glow
}

void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * ndl / PI;
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), rim_power);
	float facing_light = smoothstep(-0.2, 0.4, dot(NORMAL, LIGHT)); // only on the lit side
	SPECULAR_LIGHT += LIGHT_COLOR * ATTENUATION * rim * facing_light * rim_strength / PI;
}
```

- If the rim goes into `DIFFUSE_LIGHT`, it gets multiplied by albedo and darkened by `METALLIC`. Put it in `SPECULAR_LIGHT` or `EMISSION` when the color must stay exact.
- On a flat-shaded or low-poly mesh the rim shows faceting, because `n·v` is constant per face. That comes from the mesh, not from a bug in the formula.

Deeper: Shaders Bible ch.2 "Introduction to the Rim (Fresnel) Effect" and "Implementing the Rim Effect", PDF pp. 129–138.

## 6. Anisotropic specular (Ashikhmin-Shirley)

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color;
uniform float au : hint_range(1.0, 512.0) = 256.0;   // sharpness across the tangent
uniform float av : hint_range(1.0, 512.0) = 4.0;     // sharpness across the binormal
uniform float f0 : hint_range(0.0, 1.0) = 0.3;
varying vec3 t_vs;
varying vec3 b_vs;

float ashikhmin_shirley(vec3 n, vec3 l, vec3 v, vec3 t, vec3 b) {
	vec3 h = normalize(l + v);
	float nh = max(dot(n, h), 1e-4);
	float vh = max(dot(v, h), 1e-4);
	float nl = max(dot(n, l), 1e-4);
	float nv = max(dot(n, v), 1e-4);
	float ht = dot(h, t);
	float hb = dot(h, b);
	float e = (au * ht * ht + av * hb * hb) / max(1.0 - nh * nh, 1e-4);
	float spec = sqrt((au + 1.0) * (av + 1.0)) * pow(nh, e) / (8.0 * PI * vh * max(nl, nv));
	float fresnel = f0 + (1.0 - f0) * pow(1.0 - vh, 5.0);
	return spec * fresnel;
}

void fragment() {
	t_vs = TANGENT;      // not readable in light()
	b_vs = BINORMAL;
	ALBEDO = texture(albedo_tex, UV).rgb;
}

void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	vec3 radiance = LIGHT_COLOR * ATTENUATION;
	DIFFUSE_LIGHT += radiance * ndl / PI;
	SPECULAR_LIGHT += radiance * ndl * ashikhmin_shirley(NORMAL, LIGHT, VIEW, t_vs, b_vs);
}
```

- The highlight stretches **perpendicular to the high exponent**. For hair, the strands must run along the tangent, which means along U, or along V if `au` and `av` are swapped. Strand direction depends on the UV layout. If the UVs do not follow the strands, rotate `t`/`b` with a flow map: `t = normalize(TANGENT * f.x + BINORMAL * f.y)`.
- Multiply the result by `ndl`. Without it, highlights appear on the side facing away from the light.
- To break up the highlight, modulate it with a strand or noise mask (sampled in `fragment()`, passed as a varying). Do not use albedo brightness for this; it couples color to shine.
- All of the guards (`max(..., 1e-4)`) are needed. At grazing angles `1 - (n·h)²` reaches 0 and the exponent turns into inf/NaN, which shows up as black or white pixels.

Deeper: Shaders Bible ch.2 "Introduction to the Anisotropic Effect", PDF pp. 139–147; "Implementing the Ashikhmin-Shirley Model", PDF pp. 148–164.

## 7. Hemispheric ambient

Compute it in `fragment()` and output it through `EMISSION`, with the engine's ambient disabled. Do **not** add it to `DIFFUSE_LIGHT` inside `light()`: there it is added once per light, and it disappears where no light reaches.

```glsl
shader_type spatial;
render_mode ambient_light_disabled;
uniform sampler2D albedo_tex : source_color;
uniform vec3 sky_color : source_color = vec3(0.55, 0.65, 0.85);
uniform vec3 ground_color : source_color = vec3(0.25, 0.2, 0.15);
uniform float blend_softness : hint_range(0.0, 0.5) = 0.1;
uniform float ambient_strength : hint_range(0.0, 2.0) = 1.0;

void fragment() {
	vec3 albedo = texture(albedo_tex, UV).rgb;
	vec3 n_ws = mat3(INV_VIEW_MATRIX) * NORMAL;           // world normal, not view
	float t = smoothstep(blend_softness, 1.0 - blend_softness, n_ws.y * 0.5 + 0.5);
	ALBEDO = albedo;
	EMISSION = albedo * mix(ground_color, sky_color, t) * ambient_strength;
}
```

- `EMISSION` is not darkened by SSAO, by `AO`, or by `METALLIC`. Multiply in an AO texture yourself if you need occlusion.
- `NORMAL` in `fragment()` does **not** include the `NORMAL_MAP` perturbation, because Godot applies the map after `fragment()`. If the ambient needs normal-map detail, build the normal manually (section 10) and use that.
- For a hemispheric look across the whole scene, prefer a ProceduralSkyMaterial (sky and ground colors) as the ambient source. That works with every material.

Deeper: Shaders Bible ch.2 "Hemispheric Shading", PDF pp. 165–171.

## 8. Linear vs sRGB

Godot does 3D lighting in **linear** space. It converts to sRGB once at output, after tonemapping. Your job is to feed linear values in, and never to convert the outputs.

| Input | Declaration | Why |
|---|---|---|
| Albedo/color texture | `uniform sampler2D t : source_color;` | decoded sRGB → linear on sample |
| Color picked in the inspector | `uniform vec3 c : source_color = vec3(...);` | color picker, converted to linear |
| Normal map | `: hint_normal` | linear data and a flat-normal default |
| Roughness, metallic, AO, masks, height, flow, noise | no color hint (`hint_default_white`/`black` is fine) | data must stay linear; `source_color` would bend the values |
| Vertex `COLOR` authored in sRGB | convert manually (below) | `COLOR` arrives raw |

```glsl
// color_space.gdshaderinc: exact piecewise sRGB transfer functions
#ifndef COLOR_SPACE_INC
#define COLOR_SPACE_INC
vec3 srgb_to_linear(vec3 c) {
	return mix(pow((c + 0.055) / 1.055, vec3(2.4)), c / 12.92, lessThanEqual(c, vec3(0.04045)));
}
vec3 linear_to_srgb(vec3 c) {
	return mix(1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, c * 12.92, lessThanEqual(c, vec3(0.0031308)));
}
#endif
```

- Applying `linear_to_srgb()` to `DIFFUSE_LIGHT`, `SPECULAR_LIGHT` or `ALBEDO` **encodes twice**. Mid-tones get brighter and contrast flattens. Some tutorials do this deliberately to make highlights "pop". Treat that as an art control with a named uniform, never as a correctness step.
- `canvas_item`: 2D renders in sRGB by default. With `Viewport.use_hdr_2d` (4.2+), 2D blends in linear space, and color hints/conversions then matter as they do in 3D (verify per project).

Deeper: Shaders Bible ch.2 "From Linear Lighting to sRGB", PDF pp. 124–128.

## 9. ShaderInclude (`.gdshaderinc`)

- Create it with FileSystem → New → ShaderInclude. It can hold functions, `const`, `#define`, uniforms and varyings. It must **not** contain `shader_type`.
- Include it with `#include "res://shaders/lib/lighting.gdshaderinc"`. A path relative to the including file also works.
- Wrap every include in `#ifndef X / #define X / #endif`. Otherwise two includes that share a dependency fail with "redefinition" errors.
- Functions in an include cannot read stage built-ins (`NORMAL`, `LIGHT`, …). Pass them as arguments; `TIME` and uniforms are fine.
- Uniforms declared in an include appear on **every** material that includes it. Keep libraries free of uniforms unless that is what you want.
- Editing an include recompiles every shader that uses it. Expect a hitch in the editor, not at runtime.

```glsl
// res://shaders/lib/lighting.gdshaderinc
#ifndef LIGHTING_INC
#define LIGHTING_INC
float lambert(vec3 n, vec3 l) { return max(dot(n, l), 0.0); }
float blinn_phong(vec3 n, vec3 l, vec3 v, float m) {
	return pow(max(dot(n, normalize(l + v)), 0.0), m) * step(0.0, dot(n, l));
}
float rim(vec3 n, vec3 v, float p) { return pow(1.0 - clamp(dot(n, v), 0.0, 1.0), p); }
#endif
```

```glsl
shader_type spatial;
#include "res://shaders/lib/lighting.gdshaderinc"

void light() {
	vec3 radiance = LIGHT_COLOR * ATTENUATION / PI;
	DIFFUSE_LIGHT += radiance * lambert(NORMAL, LIGHT);
	SPECULAR_LIGHT += radiance * blinn_phong(NORMAL, LIGHT, VIEW, 64.0);
}
```

Deeper: Shaders Bible ch.2 "ShaderInclude Implementation", PDF pp. 172–176.

## 10. Normal maps

Default path:

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color;
uniform sampler2D normal_tex : hint_normal;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.0;

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb;
	NORMAL_MAP = texture(normal_tex, UV).rgb;   // raw 0..1, no * 2 - 1
	NORMAL_MAP_DEPTH = normal_strength;
}
```

- Godot remaps the XY of `NORMAL_MAP`, **rebuilds Z from XY** (blue is ignored, so RG-compressed maps work) and applies the TBN.
- `NORMAL_MAP_DEPTH` (default 1.0) is a `mix` between the geometric normal and the mapped normal. Values above 1 extrapolate.
- `hint_normal` makes the editor re-import the assigned texture as a normal map (two-channel compression) and gives a flat default. Without the hint, the texture may be compressed as color and lose precision. Never read `.b` from it.
- Godot expects the **OpenGL / Y+** convention (green = up). For DirectX maps, enable the texture import option `process/normal_map_invert_y`, or use `nm.g = 1.0 - nm.g` in the shader.
- The mesh needs tangents (see `spaces-and-matrices.md` section 7).

Manual TBN, for when you need the perturbed normal **inside `fragment()`** (for rim, hemispheric ambient or detail blending):

```glsl
shader_type spatial;
uniform sampler2D normal_tex : hint_normal;
uniform sampler2D detail_tex : hint_normal;
uniform float detail_tiling = 8.0;

vec3 unpack_normal(vec4 s) {
	vec2 xy = s.rg * 2.0 - 1.0;
	return vec3(xy, sqrt(clamp(1.0 - dot(xy, xy), 0.0, 1.0)));
}

void fragment() {
	vec3 a = unpack_normal(texture(normal_tex, UV));
	vec3 d = unpack_normal(texture(detail_tex, UV * detail_tiling));
	vec3 n_ts = normalize(vec3(a.xy + d.xy, a.z * d.z));     // whiteout blend
	NORMAL = normalize(mat3(TANGENT, BINORMAL, NORMAL) * n_ts); // tangent -> view
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0); // now sees the detail
	ALBEDO = vec3(0.6);
	EMISSION = vec3(rim) * 0.3;
}
```

- Write **either** `NORMAL` (manual path) **or** `NORMAL_MAP`, never both, or the map is applied twice.
- To scale the strength in the manual path, scale `xy` before rebuilding Z, or `mix` the result with the geometric normal. Multiplying the whole sampled vector after `* 2 - 1` also scales Z and makes the normal non-unit.
- `canvas_item` also has `NORMAL_MAP` / `NORMAL_MAP_DEPTH`. Alternatively, set a `CanvasTexture` with a normal texture on the node; 2D handles the Y-down flip itself. `BENT_NORMAL_MAP` exists in spatial shaders (compiles on 4.6.3, 4.7.2 and 4.8).

Deeper: Shaders Bible ch.2 "Normal Map Implementation", PDF pp. 177–187.

## 11. 2D (`canvas_item`) light function

```glsl
shader_type canvas_item;
uniform float bands = 3.0;

void light() {
	float ndl = max(dot(NORMAL, LIGHT_DIRECTION), 0.0);
	float q = floor(ndl * bands) / bands;                  // posterized 2D light
	LIGHT = vec4(LIGHT_COLOR.rgb * COLOR.rgb * LIGHT_ENERGY * q, LIGHT_COLOR.a);
}
```

- In 2D, `LIGHT` is the **output color** of the light (a `vec4`), not a direction. The direction is `LIGHT_DIRECTION`. Unlike 3D, you multiply by `COLOR` yourself.
- It runs per Light2D/PointLight2D per pixel. The engine applies the 2D shadow after this function; write `SHADOW_MODULATE` to tint it.

## 12. Render modes that change lighting (spatial)

| Mode | Effect |
|---|---|
| `unshaded` | no lighting at all; `ALBEDO` is the output; `light()` is ignored |
| `diffuse_burley` (default), `diffuse_lambert`, `diffuse_lambert_wrap`, `diffuse_toon` | built-in diffuse BRDF (ignored when `light()` exists) |
| `specular_schlick_ggx` (default), `specular_toon`, `specular_disabled` | built-in specular (ignored when `light()` exists) |
| `ambient_light_disabled` | drops Environment ambient and reflections; useful for testing a custom `light()` in isolation, required for custom ambient |
| `shadows_disabled` | the object receives no shadows (`ATTENUATION` has no shadow term) |
| `shadow_to_opacity` | lit areas become transparent (shadow catchers for AR/compositing) |
| `vertex_lighting` | per-vertex lighting, cheap and faceted |
| `fog_disabled` | skips the fog blend (for emissive UI-like meshes) |
| `ensure_correct_normals` | fixes normals under non-uniform scale |
| `sss_mode_skin` | skin subsurface profile |
| `specular_occlusion_disabled` | stops ambient occlusion from dimming reflections |
| `cull_disabled` | two-sided; check `FRONT_FACING` when back faces need different shading |

`diffuse_oren_nayar` no longer exists in 4.x (compile error).

## 13. Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Colors look muddy or squared | multiplied diffuse by `ALBEDO` in `light()` | the engine already does this; remove it |
| Gets brighter with every light added / ambient vanishes in unlit areas | constant or ambient term added to `DIFFUSE_LIGHT` in `light()` | move it to `EMISSION` in `fragment()` |
| Only the last light shows | `DIFFUSE_LIGHT = ...` | `+=` |
| Material π times brighter than its StandardMaterial3D neighbor | forgot `/ PI` | `LIGHT_COLOR * ATTENUATION * ndl / PI` |
| Light color/energy changes do nothing | used `ATTENUATION` alone | multiply by `LIGHT_COLOR` |
| `RIM` / `ANISOTROPY` stopped working | a custom `light()` exists | implement them in `light()` / `fragment()` |
| Washed-out, too-bright albedo | color texture without `source_color` | add `source_color` |
| Masks/roughness behave non-linearly | data texture tagged `source_color` | remove the hint |
| Inspector color looks lighter in-game | color uniform missing `source_color` | add it |
| Highlights flat and grey | `linear_to_srgb` applied to outputs | remove it; Godot encodes at output |
| Sky/ground ambient shifts as the camera tilts | used view-space `NORMAL.y` | `mat3(INV_VIEW_MATRIX) * NORMAL` |
| Lighting bumps are inverted on one axis | DirectX normal map | `process/normal_map_invert_y` |
| Normal map too strong/weak with odd lighting | scaled the vector after unpacking, Z included | `NORMAL_MAP_DEPTH`, or scale XY and then rebuild Z |
| Black or white speckles at silhouettes | division by ~0 in a specular denominator | `max(x, 1e-4)` guards |
| Specular on the shadowed side | missing the `n·l` gate | multiply by `ndl` or `step(0.0, ndl)` |
| "Unknown identifier TANGENT/VERTEX" in `light()` | not available there | varyings set in `fragment()` |
