---
name: "godot-shader-techniques"
description: "Use when writing or debugging non-trivial Godot 4.6+ shaders (.gdshader/.gdshaderinc): coordinate spaces and matrices, custom light() (toon, Blinn-Phong, rim/Fresnel, anisotropic, hemispheric), linear vs sRGB and source_color, normal maps and TBN, procedural SDF shapes and masks, TIME animation, vertex displacement/wind/billboards, rotations and quaternions, full-screen post-processing, palette/retro filters, Shadertoy ports, transparency/depth/sorting, ray marching, sampler3D, stencil. Complements a basic Godot shaders skill such as godot-shaders (awesome-gamedev-agent-skills)."
---

# Godot Shader Techniques (4.6+)

Engine facts here were compile-checked on 4.6.3 / 4.7.2 / 4.8-beta1 unless marked "(verify)". Read the reference that matches the task before writing the shader; each one ends with a pitfalls table.

| Task | Read |
|---|---|
| Moving vertices, world/object positions in `fragment()`, TBN, billboards, `POSITION`, `skip_vertex_transform`, custom matrices | `references/spaces-and-matrices.md` |
| Writing `light()`, toon/specular/rim/anisotropic materials, color hints, normal maps, `.gdshaderinc` | `references/lighting-models.md` |
| Shapes/masks without textures, `TIME` animation, wind/wobble/pulse, rotation in a shader, porting between `canvas_item` and `spatial` | `references/procedural-and-vertex.md` |
| Full-screen effects, palette/pixel filters, Shadertoy ports, transparency sorting, depth fades, volumes, `sampler3D`, stencil masks, performance | `references/post-processing-and-vfx.md` |

## Rules that prevent most shader bugs

**Spaces**
- In `fragment()`/`light()` of a spatial shader, `VERTEX`, `NORMAL`, `TANGENT`, `BINORMAL`, `VIEW` and `LIGHT` are in **view space**. "Up" is `mat3(INV_VIEW_MATRIX) * NORMAL`, not `NORMAL.y`.
- Points use w = 1 and directions w = 0. Transform normals with the inverse-transpose whenever the matrix is non-rigid (non-uniform scale or shear).
- GLSL `mat3(a, b, c)` takes **columns**. Matrices copied from row-major textbook notation come out transposed and rotate the wrong way.
- `BINORMAL` points along −V. A TBN for height or parallax tricks is `mat3(TANGENT, -BINORMAL, NORMAL)`.
- Camera-facing vertex code uses `MAIN_CAM_INV_VIEW_MATRIX`, or checks `IN_SHADOW_PASS`. Otherwise shadows face the light.

**Color**
- Add `source_color` to albedo/color samplers and color uniforms, and leave it off data textures (masks, noise, roughness, flow, density). The hint does the sRGB→linear decode.
- Never convert lighting output or `ALBEDO` to sRGB by hand: Godot encodes after tonemapping, so a manual conversion encodes twice.
- In `canvas_item`, `COLOR` arrives as vertex color × modulate × texture. Modify it; `COLOR = texture(TEXTURE, UV)` throws modulate away.

**Lighting**
- A custom `light()` replaces only the per-light BRDF; ambient, reflections, emission and fog stay the engine's. Always accumulate with `+=`.
- The engine multiplies diffuse by `ALBEDO` itself, so never multiply it into `DIFFUSE_LIGHT`. `LIGHT_COLOR` already includes π: Lambert is `LIGHT_COLOR * ATTENUATION * max(dot(NORMAL, LIGHT), 0.0) / PI`.
- Ambient or constant terms belong in `EMISSION` in `fragment()`. Added in `light()`, they run once per light and vanish where no light reaches.
- Built-in `RIM`, `ANISOTROPY` and `CLEARCOAT` do nothing once a custom `light()` exists.
- Guard specular denominators with `max(x, 1e-4)`.

**Geometry**
- Displaced vertices need recomputed (or co-rotated) normals and tangents, plus `extra_cull_margin` or `custom_aabb`. Otherwise the mesh pops out when its original bounds leave the screen.
- Anti-alias procedural edges with an SDF and `smoothstep` over `fwidth(d)`, not a hard `step` or `<`.
- Per-instance variation: `instance uniform` (canvas_item since 4.4), `INSTANCE_CUSTOM`, or a hash of the world origin. Don't encode IDs in modulate.

**Screen and transparency**
- A full-screen `ColorRect` overlay needs `mouse_filter = MOUSE_FILTER_IGNORE`. Screen-texture copies are shared, so chained passes need `BackBufferCopy` or separate CanvasLayers.
- Depth reconstruction: Forward+ and Mobile use reverse-Z with `ndc = vec3(SCREEN_UV * 2.0 - 1.0, depth)`. Compatibility needs a `CURRENT_RENDERER` branch.
- Prefer `ALPHA_SCISSOR_THRESHOLD` for foliage and fences: the material stays opaque, casts shadows and doesn't need sorting. Blended materials cast shadows only with `depth_prepass_alpha`.
- A material that reads stencil (4.5+) must be in the transparent pass.
- Inside loops, sample with `textureLod`. Ray marchers need a box slab test, the scene-depth limit and an early out on transmittance.

**Workflow**
- `TIME` is scaled by `Engine.time_scale` and keeps running while the tree is paused. Drive pausable effects from a uniform.
- Don't call `set_shader_parameter` every frame with the same value. Set it on change, or use a global shader uniform.
- Share code through `.gdshaderinc` with typed functions and `const`, not `#define` macros.

## Checking a shader without the editor

A shader that fails to compile still loads, so check it explicitly:

```gdscript
extends SceneTree  # godot --headless --script check_shader.gd -- res://path.gdshader
func _init() -> void:
	for path: String in OS.get_cmdline_user_args():
		var shader := Shader.new()
		shader.code = FileAccess.get_file_as_string(path)
		shader.get_shader_uniform_list()  # forces compilation; errors print as SHADER ERROR
	quit()
```

Grep the output for `SHADER ERROR`. `#include` paths only resolve when the script runs with `--path <project>`.

## Deeper

These skills are distilled from *The Godot Shaders Bible* (2026), and each reference cites its pages (PDF page = printed page + 1). The references note where the book is outdated or wrong. When they disagree with the book, trust the references.
