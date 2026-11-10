<!-- Copied from docs/shaders.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# zestengine standard shader

The single default shader used by every world and avatar, on PC and mobile.
Inspired by Poiyomi: one heavily configurable **uber-shader** instead of many
small shaders, so creators toggle features instead of writing GLSL.

## Flux math

The shared helpers in `crates/zestengine-render/shaders/flux_common.glsl`
provide the sampling and lighting calculations used by Flux:

- Screen probes use four real spherical-harmonic coefficients, with basis
  `(1/sqrt(4*pi), sqrt(3/(4*pi)) * (-y, z, -x))`. The signs and order preserve
  the existing screen-probe buffer convention. This is distinct from the
  positive-axis convention in the baked/world-volume probes.
- Diffuse irradiance is the hemispherical integral of incoming radiance times
  the cosine with the surface normal. For degree zero and one, the convolution
  factors are `pi` and `2*pi/3`. The helper evaluates those four RGB coefficients directly. The resolve still uses only the directional ratio; the denoised
  scalar gather supplies brightness. See Ramamoorthi and Hanrahan (2001),
  [An Efficient Representation for Irradiance Environment Maps](https://graphics.stanford.edu/papers/envmap/envmap.pdf),
  equations 3, 7 and 9. The basis normalization is computed from pi.
- Hemisphere sampling projects a uniformly sampled disk onto a hemisphere:
  radius squared is uniform and height is `sqrt(1-radius_squared)`. This is
  Malley's method, explained in
  [Physically Based Rendering, section A.5.3](https://pbr-book.org/4ed/Sampling_Algorithms/Sampling_Multidimensional_Functions#Cosine-WeightedHemisphereSampling).
  A unit-quaternion rotation carries the local direction into the surface frame.
  The north/south chart boundary remains at `normal.z = -0.5` to preserve the
  directional-bin convention shared by tracing, temporal history and denoising.
- The RGB firefly limiter applies one scale so that the largest channel does
  not exceed the configured ceiling, preserving color ratios.

`gpu_tests::flux_math` exercises the actual production GLSL against analytic
constant/linear lighting integrals, the spherical-harmonic addition theorem,
cosine-distribution moments, both poles, chart boundaries, sampling endpoints,
wall-normal continuity and RGB ratios. Run it with:

```sh
cargo test -p zestengine-render --lib gpu_tests::flux_math -- --nocapture --test-threads=1
```

As with other GPU tests, a machine without a usable Vulkan device reports a
skip. A compilation or skipped test is not evidence of numerical correctness.

## Why an uber-shader

Poiyomi's model works because creators get a huge feature surface behind
checkboxes, and the shader compiler strips everything unused. We replicate
that with **SPIR-V specialization constants + compile-time variant flags**:

- Authoring time: every feature is a material property in the editor.
- Build/publish time: the material's enabled-feature set selects (or bakes) a
  shader variant; disabled features cost zero GPU time.
- Runtime: variants are cached in a pipeline cache keyed by
  `(feature_bits, vertex_layout, render_state, tier)`.

## Feature set (target, phased)

**Phase 1 — core PBR/toon hybrid**
- Base: albedo × vertex color, normal map, metallic/roughness/AO (ORM packed)
- Lighting modes: `PBR`, `Toon` (ramp or step shading), blend between them
- Emission with masks
- Alpha modes: opaque / cutout / transparent (premultiplied)
- Double-sided rendering with proper normal flip

**Phase 2 — the "Poiyomi feel"**
- Shading ramps / gradient lighting, shadow tinting
- Rim lighting (color, power, masked)
- Matcaps (add/multiply/replace, masked, 2 slots)
- Outlines (inverted-hull, color/width properties, distance fade)
- UV manipulation: tiling/offset, panning, rotation per texture slot
- Detail maps (albedo/normal second set)

**Phase 3 — flair**
- Audio-link-style reactive params (driven by engine-side audio analysis bus)
- Dissolve (alpha + edge glow), glitter/sparkle, iridescence
- Flipbook/spritesheet animation
- Vertex animation hooks (wind, sway: the custom-shader `// @vertex` hook below; jiggle is handled by spring bones instead)

## Tiers

| | PC (`tier_pc`) | Mobile (`tier_mobile`) |
|---|---|---|
| Lighting | Full PBR IBL + analytic lights | Baked/SH ambient + 1 directional |
| Texture slots | All | Albedo, normal (optional), emission, ORM |
| Matcap/rim/outline | Yes | Rim yes; matcap 1 slot; outlines optional |
| Transparency | Full | Cutout strongly preferred |
| Target | Desktop Vulkan 1.3 | Quest-class (Vulkan 1.1, tiled GPU) |

Same material asset, two compilation targets. The mobile tier compiles the
same source with `TIER_MOBILE` set, which forces cheap fallbacks for features
out of budget (matcap→off, PBR→simplified BRDF, etc.). Creators see one
material; the publisher emits both variants and validates mobile budget.

## Material inspector GUI

The shader is only as good as its inspector. Creators interact with the GUI,
not the SPIR-V. The egui material inspector (zestengine-editor) is a first-class
part of the shader spec:

- **Collapsible feature sections**, each with a master enable toggle in the
  header (toggle off = section collapses, variant bit clears, GPU cost gone).
  Disabled sections render dimmed, never hidden, for discoverability.
- **Search/filter bar** across all property names ("rim" jumps you to rim
  lighting), like Poiyomi's ctrl+F workflow.
- **Live preview**: edits apply to the running scene immediately, with no
  apply button. Variant recompiles happen async with the old pipeline kept
  until the new one is ready (no hitching).
- **Texture slots** as thumbnail widgets: click to assign, right-click to
  clear; per-slot UV controls (tiling/offset/pan speed/rotation) fold out
  under the thumbnail.
- **Proper widgets per type**: color = picker with HDR intensity for
  emission; ranges = sliders with drag-to-type; ramps = gradient editor
  widget; masks = channel-select dropdown (R/G/B/A).
- **Presets**: save/load named property bundles (full material or
  per-section), shippable with the platform (e.g. "Toon Skin", "Glossy
  Metal") and shareable as small JSON/RON files.
- **Tier preview toggle** in the inspector header: PC ⇄ Mobile, showing
  exactly what the mobile tier degrades, plus a live mobile-budget meter
  (texture memory, variant cost) so creators see Quest problems *while*
  authoring rather than at publish time.
- **Reset-to-default** per property (right-click) and per section.

Build order: a minimal version of this inspector ships **with M2** (phase 1
features need it for testing) and grows with each shader phase. The
inspector and the shader are one deliverable, not two.

## Implementation notes

- Source language: **Slang** or GLSL with includes, decided at milestone M2.
  Compiled to SPIR-V at build time (`glslc`/`slangc`), variants via
  specialization constants where possible, preprocessor defines where not
  (e.g. texture binding presence).
- Bindless-ish material model on PC (descriptor indexing) to keep one
  pipeline across materials with the same feature bits; classic descriptor
  sets on mobile tier.
- Material parameters serialize into the glTF material `extras` /
  a `VRSH_materials_standard` extension so worlds and VRM avatars carry vrsh
  materials portably while staying valid glTF for other tools.

## Custom shaders (property system v2)

Any `.frag` (GLSL) or `.hlsl` (HLSL) file anywhere in the project (not only
`shaders/`) appears in the material Shader picker. The engine prepends a
preamble, compiles via `glslc` at runtime and hot-reloads on save (about 2 s
polling; property values are carried over by name). Compile errors show in
the Inspector (with your own line numbers) and in the log; the material draws
the error swirl until the file compiles again. Files > Create > New Shader
writes a commented GLSL starter (`zestengine_assets::SHADER_TEMPLATE`;
`HLSL_SHADER_TEMPLATE` is the HLSL equivalent).

The file is the fragment stage plus, optionally, a **vertex hook** (see "Vertex
hook" below); the rest of the vertex stage is the engine's. Do not write a
`#version` line.

### Property declarations

Properties are `// @` comment directives, anywhere in the file:

```glsl
// @shader "Wobble"
// @property tint "Tint" Color = (1, 0.5, 0.1, 1)
// @property speed "Speed" Range(0, 10) = 2
// @property mode "Mode" Enum(Flat, Wavy, Noisy) = Wavy @keyword
// @feature GLOW "Glow"
// @property glow_color "Color" Color3(HDR) = (4, 2, 1)
// @property glow_mask "Mask" Texture2D = white @linear
// @property glow_width "Width" Float = 0.5 @show_if(mode != Flat)
// @end
// @preset "Cheap" GLOW=0 mode=Flat
```

`@property name ["Label"] Type [= default] [flags]`

| Type | Widget | GLSL type | Default |
|---|---|---|---|
| `Range(min, max)` | slider | `float` | number |
| `Float` | drag value | `float` | number |
| `Int`, `IntRange(min, max)` | drag / slider | `int` | number |
| `Toggle` | checkbox | `bool` (see below) | `0` / `1` |
| `Enum(A, B, C)` | combo | `int`, plus `const int name_A = 0;` ... | option name or index |
| `Color`, `Color(HDR)` | colour picker (+ intensity for HDR) | `vec4` | `(r, g, b, a)` |
| `Color3`, `Color3(HDR)` | colour picker | `vec3` | `(r, g, b)` |
| `Vector`, `Vector2`, `Vector3` | drag fields | `vec4` / `vec2` / `vec3` | `(x, y, ...)` |
| `Texture2D` | texture slot (drop an image) + tiling/offset | `sampler2D name`, `vec4 name_st`, `name_uv(uv)` | `white`, `black`, `normal`, `gray` |

Flags: `@keyword` (Toggle / Enum / Int become a specialization constant, see
variants), `@linear` / `@srgb` (texture colour space; colour textures default
to sRGB, `normal` and `gray` defaults to linear), `@show_if(expr)`,
`@tooltip("text")`.

Grouping and layout directives:

- `@feature NAME "Label" [= 1]`: declares a keyword Toggle `NAME` and opens a
  foldout whose header checkbox is that toggle. Off = dimmed in the Inspector
  and compiled out of the material's variant.
- `@foldout "Label" [@show_if(expr)]` ... `@end`: a plain foldout group.
- `@header "Text"`: sub-heading above the next property.
- `@show_if expr` ... `@end_show_if`: condition for a run of properties.
- `@preset "Name" a=1 b=Option c=(1,0,0,1)`: Inspector preset; selecting it
  writes those values (usually the feature keywords).

Conditions: `name` (non-zero), `!name`, `name == value` / `!=` / `<` / `<=` /
`>` / `>=` (enum option names allowed), combined with `&&` and `||` (OR of
ANDs). Hidden properties keep their values.

The legacy v1 pragmas (`//! shader "Name"`, `//! prop tint color default(...)`,
kinds `float`, `toggle`, `color`, `color3`) still work unchanged: they pack into
15 push-constant floats and can be mixed with v2 properties.

### Data flow

1. **Asset** (`zestengine-assets/src/shader_props.rs`): the parser builds a
   `ShaderSource` with each property's storage: push lane (v1), std140 byte
   offset in the material block, keyword constant id, or texture binding.
2. **Material**: values live in `MaterialModel::custom_values` (lanes 0..15 =
   v1 push block, v2 values from lane 16) and are saved by property name in
   `.material` files and inline scene materials (`custom`); texture properties
   are saved by name in `textures.shader`. Old files load unchanged.
3. **GPU**: `apply_material` uploads the std140 bytes to the material's set 2
   uniform buffer (binding 0, max 4096 bytes), binds texture properties at
   set 2 bindings 1..20 (unassigned = the declared default), pushes the v1
   lanes, and sets the material's keyword values on the pipeline key.
4. **Shader**: the generated declarations name everything after the property,
   so the body just uses `tint`, `speed`, `GLOW`, `texture(glow_mask,
   glow_mask_uv(v_uv))`. Non-keyword toggles read as `bool` (`#define name
   (_cp_name > 0.5)`).

| Set / binding | Contents |
|---|---|
| set 0 | frame UBO (lights, shadows, probes, post), shadow atlas (1), probe SH (2), lightmaps (3), screen GI (4), environment cube (7) |
| set 1, bindings 0-3 | fixed material slots `t_albedo`, `t_normal`, `t_orm`, `t_emission` (also editable in the custom shader Inspector) |
| set 2, binding 0 | generated `ZestEngineMaterial` std140 block |
| set 2, bindings 1..20 | `Texture2D` properties in declaration order |
| push constants | `pc.model`, v1 props in `pc.d0..d3`, lightmap layer in `pc.d3.w` |
| spec constants 0..31 | `@keyword` properties; id 63 = `zestengine_alpha_mode` (0 opaque, 1 cutout, 2 blend) |

### Provided by the preamble

| | |
|---|---|
| Varyings | `v_world_pos`, `v_normal`, `v_uv`, `v_uv1`, `v_color`, `v_tangent` |
| Uniforms | `u_time`, `u_camera_pos`, `u_ambient`, `u_light_count`, the full `frame` UBO |
| Lights | `zestengine_light(i, pos, out L, out radiance)` (attenuation, spot cone, baked-light skip), `zestengine_shadow(i, pos, n, L)` (cascades, cube faces, PCF), `zestengine_direct_lambert(pos, n)` (shadowed), `zestengine_direct_diffuse(pos, n)` (unshadowed) |
| GI | `zestengine_baked_gi(pos, n)` (lightmap + realtime probes, screen-space Flux GI, probe GI, ambient: the standard shader's priority), `zestengine_gi(pos, n)`, `zestengine_probe_irradiance(pos, n, out coverage)` |
| Reflections | `zestengine_env(pos, R, roughness)` (reflection probe, box-projected, or sky) |
| Misc | `zestengine_postfx(color, gl_FragCoord.xy)` (call before writing), `zestengine_dither(fragcoord)`, `zestengine_alpha_mode` |
| Output | `o_color`; `o_gbuf` is zeroed (not an SSR reflector) before your `main` runs |

Alpha mode and double-sided still come from the material's Transparency /
Geometry sections (pipeline state); read `zestengine_alpha_mode` to cut out.

### HLSL

`.hlsl` files use the same directives and bindings. Implement
`float4 zestengine_frag(ZestEngineInput i)`; the engine adds the `main` entry point.
`ZestEngineInput` has `world_pos`, `normal`, `uv`, `color`, `tangent`, `uv1`,
`frag_coord` (SV_Position) and `front_facing`. Every texture is a
`Texture2D x` with a `SamplerState sampler_x` at the same binding (glslc's
`-fauto-combined-image-sampler` merges them into the combined samplers the
pipeline uses); `ZESTENGINE_SAMPLE(x, uv)` expands to `x.Sample(sampler_x, uv)`.
The material block is a `cbuffer` with explicit `packoffset`s matching the
std140 layout, keywords are `[[vk::constant_id(N)]] const` values, matrices
are column-major as the engine writes them (use `mul(M, v)`). The helper
functions have the same names and signatures as in GLSL. Compiled with
`glslc -x hlsl -fshader-stage=frag`.

```hlsl
// @shader "Rim Glow"
// @property tint "Tint" Color = (1, 1, 1, 1)
// @feature RIM "Rim"
// @property rim_color "Rim Color" Color3(HDR) = (2, 2, 2)
// @end
float4 zestengine_frag(ZestEngineInput i) {
    float4 albedo = ZESTENGINE_SAMPLE(t_albedo, i.uv) * tint;
    float3 n = normalize(i.front_facing ? i.normal : -i.normal);
    float3 c = albedo.rgb * (zestengine_direct_lambert(i.world_pos, n) + zestengine_baked_gi(i.world_pos, n));
    if (RIM) c += rim_color * pow(1.0 - saturate(dot(n, normalize(u_camera_pos - i.world_pos))), 3.0);
    return float4(zestengine_postfx(c, i.frag_coord.xy), albedo.a);
}
```

### Keyword variants (shader_feature model)

One shader file contains every feature; `@keyword` / `@feature` properties
decide which of them a material's GPU program contains.

- At runtime the shader compiles once to a SPIR-V module whose keywords are
  specialization constants. Each material's keyword set is part of its
  pipeline key, so every distinct set gets its own pipeline, built lazily the
  first time a material with that set draws and cached afterwards. When the
  driver builds a specialized pipeline it folds the constants, so
  `if (GLITTER) { ... }` with GLITTER off is removed: no branch, no texture
  sample, no register pressure from the disabled code. Toggling a keyword in
  the Inspector switches pipelines without recompiling GLSL.
- Non-keyword properties (sliders, colours) are uniform reads: changing them
  never creates a variant. Use `@keyword` for anything that gates sizeable
  code or texture fetches, plain properties for values.
- Game builds (`bundle.rs`) precompile every shader to a `.spv` sidecar
  (players need no glslc) and additionally bake the exact keyword sets their
  scenes and `.material` files use into `<shader>.variants/<hash>.spv`, with
  the keywords compiled as plain constants so glslc's optimizer strips the
  disabled code from the SPIR-V itself. The runtime prefers a baked variant
  when one exists and otherwise falls back to specializing the shared module.
- Cost model: variant count is bounded by the keyword combinations materials
  actually use (not 2^N); each costs one pipeline object. The test
  `zestengine_toon_variants_strip_disabled_features` checks that ZestEngine Toon's
  Simple variant compiles to roughly half the SPIR-V of Heavy with a quarter
  of the texture samples, and that the heavy-only samplers (dissolve,
  glitter, decal, detail, parallax, second matcap, hair shift) are absent.

### Vertex hook

A custom GLSL shader can move its own vertices: waving grass, banners, flags, breathing,
shatter. Put a function in a `// @vertex` ... `// @endvertex` section anywhere in the file:

```glsl
// @property sway "Sway (m)" Range(0, 1) = 0.15
// @vertex
void zestengine_vertex(inout VertexData v) {
    float h = clamp(v.position.y / 2.0, 0.0, 1.0);
    v.world_offset.x += sin(v.time * 2.0 + v.world_position.x) * sway * h * h;
}
// @endvertex
void main() { /* the fragment stage, unchanged */ }
```

`VertexData` (the engine declares it; you only fill it):

| Field | Type | Meaning |
|---|---|---|
| `position` | `vec3` | object-space position, in / out (write it to displace in object space) |
| `normal` | `vec3` | object-space normal, in / out (the engine re-normalises it after the world transform) |
| `tangent` | `vec4` | object-space tangent xyz and handedness w, in / out |
| `uv`, `uv1` | `vec2` | first UV set and the lightmap UVs, in / out |
| `color` | `vec4` | vertex colour, in / out (the fragment sees the new value as `v_color`) |
| `model` | `mat4` | object to world, read only |
| `world_position` | `vec3` | the vertex in world space BEFORE the hook, read only |
| `world_offset` | `vec3` | added to the world position after the transform; starts at 0 (wind and other world-space pushes) |
| `time` | `float` | seconds, the engine clock (`frame.misc.x`) |
| `vertex_index` | `int` | `gl_VertexIndex` |

The hook can also read `frame` (the frame uniform block: camera, lights, ...), every `// @property`
(floats, vectors, colours, keywords, enums, and texture properties with `textureLod(name, uv, 0.0)`;
`name_uv(uv)` applies tiling) and `ZESTENGINE_PI`. It cannot read `//!prop` push-constant
properties (the shadow pass has different push constants): use `// @property`. The section is cut out of
the file before the fragment stage is compiled, so it may use names the fragment stage does not have
(and the other way round); share helpers by writing them in both. Line numbers in compile errors are the
file's own. HLSL shaders have no hook.

**One hook, every pass.** The engine splices your function into its own vertex shaders and builds them
with `glslc` the first time a pipeline needs each one: the main pass, the depth prepass, the XR
(multiview) pass and planar mirrors share one module (`standard.vert`), so the depth prepass and the
EQUAL-tested main pass compute bit-identical positions; the shadow pass has its own (`shadow.vert`) that runs
the same function, so swaying grass casts the shadow of the swayed surface. Because the shadow depends on
`time`, a layer holding a hooked caster re-renders every frame. A shader without a section compiles
exactly as before (no extra module, no extra pipeline state; tested).

Limits and conventions:

- **Previous-frame position.** The motion vectors (TAA / upscaling) assume the displacement did not change since the
  last frame, so only the object's own movement shows as velocity. Fast hooks ghost slightly under temporal upscaling.
- **Bounds.** Culling uses the mesh's own bounds (`DrawCmd::bound_radius`): give a swaying object a bound with margin.
- **Cluster path.** Custom-shader materials are never drawn through the cluster (virtual geometry) path (they
  draw the ordinary mesh, like before), so a hook never meets cluster vertex pulling; hooked casters are left out of
  the cluster shadow batches too and draw as ordinary meshes.
- **GPU-driven batches.** Custom shaders were never in the GPU-culled indirect batches; unchanged.
- **Instance colour / param** are not given to the hook (the shadow pass has no such stream).
- **`glslc` at run time.** Like every custom shader the hook is compiled when the shader registers (a hook that does
  not compile fails the shader, naming the line); the other pass modules compile on first use. A game that ships
  without `glslc` should keep to fragment-only shaders for now (the hook's SPIR-V is not baked into a sidecar yet).
- **Template.** `shaders/zestengine_wind_sway.frag` ("ZestEngine Wind Sway"): sway amplitude, speed, plant height, gust and
  wind direction, rooted at object `y = 0`, lit and shadowed. Copy it as the starting point for foliage, cloth-like
  props or banners.

### Tessellation and displacement (standard shader and custom shaders)

A material can displace its geometry by a height map with hardware tessellation: the material's
**Tessellate** switch (Material inspector, under the Displacement slot) or `MaterialParams::tess`
(`TessParams`: `enabled`, `scale`, `midlevel`, `edge_px`, `max_factor`, `phong`; `.material` files
carry it, old files load unchanged). The height map is the Displacement texture slot (binding 16, white = peak).

- **Subdivision** follows the screen-space length of each triangle edge: an edge is split until its pieces are about
  `edge_px` pixels long, up to `max_factor` (at most 64). The level of an edge depends only on its two world
  positions and the camera, so neighbouring triangles agree and the surface has no cracks.
- **Shape.** New vertices are placed by Phong tessellation (`phong` 0..1 pulls them toward the curved surface the
  vertex normals imply) and pushed along the smoothed normal by `(height - midlevel) * scale` (world units).
  The shading normal comes from the height field's slope in the tangent frame, so lighting follows the displaced
  surface. The height map is sampled at a mip matching the subdivision. While tessellation is on, parallax mapping is off.
- **Every pass.** The material's pipelines get a tessellation control and evaluation stage in the main pass, the depth prepass
  (same modules and an `invariant` position: the EQUAL-tested main pass agrees pixel for pixel), the XR multiview pass,
  planar mirrors and reflection captures (all `record_scene_draws`), and the shadow pass (`shadow.vert -DZE_TESS` +
  `tess.tesc/tess.tese -DSHADOW`, which tessellate from the SAME camera, so the shadow is cast by the surface the camera sees).
  Casters with a displaced material draw separately from the shared shadow batches and re-render their layer every frame.
- **Cost.** One extra pipeline-key bit (`PipelineKey::tess`); a material without the switch has no tessellation stages
  and the same pipelines as before. Displaced materials draw on the CPU path (not in the GPU-culled indirect batches).
- **Cluster path.** A tessellated material is never drawn through the cluster path: it falls back to the ordinary mesh draw
  (and is left out of the cluster shadow batches), like custom shaders.
- **Devices.** Needs `tessellationShader` (and `multiviewTessellationShader` for the XR pass). Without it the material draws
  flat (use parallax mapping there). A compute pre-subdivision fallback was considered and not built: tessellation hardware is
  universal on desktop GPUs, absent mainly on some mobile / standalone-VR parts (where subdividing a mesh every frame is the
  wrong cost anyway), and a fallback would need its own copy of the shadow / prepass / XR plumbing to stay consistent.
- **Mesh needs.** Triangle lists with normals, UVs and tangents (the tangent's handedness picks the bitangent); the mesh should
  be reasonably dense (the patch is the original triangle). Water, outline and fur draws are not tessellated.
- **Bounds.** Culling uses the original mesh's bounds: give a displaced object a bound with margin.

### ZestEngine Toon (`shaders/zestengine_toon.frag`)

A Poiyomi-style toon shader written on this system. Presets: **Simple**
(albedo, multilayer toon ramp, shadows, optional alpha), **Medium** (adds
normal map, rim, matcap, toon specular, emission), **Heavy** (everything).
Presets only set keywords; features can be toggled individually afterwards.

| Poiyomi group | ZestEngine Toon |
|---|---|
| Lighting modes | `lighting_mode`: Ramp (ramp texture), Multilayer (math toon, two layers with border/blur/colour), Realistic (GGX/Lambert with toon blend, metallic/roughness, ORM), Flat; min/max brightness, monochrome lighting, indirect strength, AO; all scene lights, shadows (`RECEIVE_SHADOWS`), lightmaps, probe and Flux GI |
| Shadows | shadow colour, strength, shadow mask, ramp, second shadow layer |
| Rim lighting | colour (HDR), width, sharpness, light-based, mask, Add / Replace / Multiply |
| Matcaps | 2 slots, each with mask, strength, light-based, Add / Multiply / Replace / Screen |
| Specular | Toon (size, smoothness), Anisotropic hair (Kajiya-Kay, shift noise, two lobes, tangent/bitangent), Realistic GGX; mask |
| Reflections | reflection probe / sky with fresnel |
| Emission | 2 slots: scroll, pulse, hue shift over time, masks |
| Outlines | `OUTLINE` + `outline_color` + `outline_width`: the engine draws an inverted-hull pass after the object (any custom shader can opt in with these three property names) |
| Dissolve | noise texture, amount, edge width and HDR edge glow, invert |
| Glitter | procedural sparkle cells, density, size, speed, view dependence, rainbow, mask |
| Decal | 1 slot with UV position / scale / rotation, Replace / Multiply / Add, emission |
| Detail | detail albedo (x2) and normal with mask and tiling |
| UV tile discard | 4x4 tiles on UV0 or UV1 |
| Vertex colour | Multiply, Tint, AlphaOnly, EmissionMask; sRGB linearize |
| Alpha | cutout (material Transparency mode + cutoff), dithered, blend, alpha mask, offset, fresnel fade, alpha boost from emission |
| Parallax | steep parallax with height map, scale, steps |

Out of scope (not feasible in this engine today): AudioLink (no audio
analysis texture), grab-pass refraction / glass blur (no scene-colour copy is
exposed to material shaders), stencil chains (no stencil attachment state per
material), geometry shader effects (vertex offsets and wind are the vertex hook, tessellated
displacement is the material's Tessellate switch, see above), per-material outline masks / per-vertex outline width (the hull
pass uses one width), multi-pass fur, and Poiyomi's light-volume /
"VRChat light probe" specifics.

### Unity shader compatibility

Materials authored for Poiyomi, Mochie, lilToon, MToon and Unity Standard convert to ZestEngine Toon / the
PBR standard shader on import (Files panel: Convert Unity Material, Convert Unity folder, Import Unity package).
Property mapping, the list of unsupported features with priorities, licence notes and sources are in
[shaders-unity-compat.md](shaders-unity-compat.md); the gaps are tracked as UNITY-* tasks in IMPLEMENTATION_PLAN.md.
