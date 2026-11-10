<!-- Copied from docs/shaders-unity-compat.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# Unity shader compatibility (Poiyomi, Mochie, lilToon, MToon, Standard)

Avatars and props authored in Unity use third-party shaders.
**Convert Unity Material** maps their *material values* onto ZestEngine shaders ([ZestEngine Toon](shaders.md) and
the PBR standard shader) and writes a report of everything it could not carry over.
Gaps become plan tasks (IMPLEMENTATION_PLAN.md, "Shader gaps").

## Rules this work follows

- Property names are the identifiers Unity serialises into every `.mat` file, and
  the meaning of their values comes from the shaders' public documentation
  (links below) and the labels the shaders show in the inspector.
- The converter scans `.shader` files for the declared shader name
  (`Shader "..."`) and uses it to identify the material mapping.
- Licences are recorded below for information; nothing here depends on them.

## Gap status (UNITY-2 .. UNITY-14)

What the engine gained for the Unity shader gaps, and what was left out with the reason.
"Done" means implemented, converter-mapped where the Unity side has a known
property, tested, and (for rendering) checked on a real device; the contact sheet
`docs/design/unity-fx-contact-sheet.png` shows every rendering phase of
`crates/zestengine-assets/tests/unity_fx.rs` (order is listed in the test output).

| Plan item | Status | What exists / why not |
|---|---|---|
| UNITY-2 Stencil effects | **Done** (GUI unverified) | The scene depth is now a depth-stencil image (`D32_SFLOAT_S8_UINT`, else `D24_UNORM_S8_UINT` / `D16_UNORM_S8_UINT`; `ZESTENGINE_STENCIL=0` keeps plain `D32_SFLOAT`, where material stencil is ignored). Every colour pass attaches the stencil aspect (cleared to 0): main, depth prepass, Flux prepass, Hi-Z late split, planar mirrors, reflection capture, camera targets and preview, XR (single and multiview, MSAA resolve), impostor / text / VR overlay pipelines. Shadow maps stay depth-only `D32`; the opaque depth copy is a depth-only copy. `MaterialFeatures.stencil` (`StencilState`: reference, read / write mask, per face compare + pass / fail / zfail op, `color_mask`, `depth_write`) and the inspector's **Stencil** section drive a per-pipeline-variant stencil state (all eight Unity compare funcs and ops, front and back faces separate). The default state is inactive and draws byte-identically. The converter maps `_StencilRef` / `_StencilReference` / `_Stencil`, `_StencilComp` / `_StencilCompareFunction`, `_StencilPass` / `_StencilPassOp` / `_StencilOp`, `_StencilFail*`, `_StencilZFail*`, `_StencilReadMask`, `_StencilWriteMask`, the `...Front` / `...Back` variants, `_ColorMask` and `_ZWrite` (only next to stencil / colour masking), and the Poiyomi `_StencilType` preset (1 = writer: Always + Replace; 2 = reader: Equal; explicit compare / pass values win; the preset numbering is an unverified assumption). **Draw order**: a writer must draw before its readers: give it a lower render queue (Unity `Geometry-1` or `Geometry+1`). Within one queue the order is the renderer's state sort and gives no guarantee. Materials with a non-default stencil state skip the GPU-driven batches (they draw in strict queue order on the CPU path), and a writer with ZWrite off skips the depth prepass. Not done: a stencil `Ref` driven per instance or animated; Poiyomi's `_StencilType` UI presets beyond writer / reader; stencil in custom HLSL `Stencil{}` blocks of imported `.shader` files (only material properties are read). Sprite masks use stencil bit 7 (`0x80`) only, so 3D stencil bits 0..6 and sprite masks do not interact; keep 3D references below `0x80` in scenes with sprite masks. |
| UNITY-3 Grab pass | **Done** (mip chain only for transmission) | `MaterialFeatures.grab` / model `grab` ("Scene Colour Read" in the inspector): the main pass copies opaque colour + depth before the first transparent or grab draw (the copy the water already used). Custom shaders get `u_opaque_color`, `u_opaque_depth`, `zestengine_grab(frag, offset_px, fallback)`, `zestengine_grab_blur(frag, offset_px, radius_px, fallback)` and `zestengine_grab_world_pos`. A custom shader with a `GRAB` toggle that is on sets the feature automatically. The copy has a mip chain only on frames that draw a transmission material (rough transmission, UNITY-8); the grab helpers read mip 0 and blur with a 16-tap jittered disc (coarse above about 20 px). Toon `GRAB` feature: tint, normal-driven distortion, blur, chromatic split. lilToon refraction mode and Poiyomi grab pass map to it. HLSL custom shaders do not get the grab helpers. The copy is taken only in the main camera pass: reflection captures, planar mirrors and the model preview see the fallback colour. |
| UNITY-4 Screen FX volume | **Done** | `shaders/zestengine_screenfx.frag` ("ZestEngine Screen FX"): a box or sphere mesh re-samples the opaque scene for the pixels where the scene point behind it lies inside the shape (reconstructed from the opaque depth copy), with filtering (hue, saturation, contrast, brightness, tint, invert), shake, distortion, blur, pixelate, chromatic split and noise, soft edge falloff. Mochie Screen FX materials are reported as having no converter (property names are unverified; set the volume up by hand with the presets). Not done: a global (non-mesh) screen volume that follows the camera, and the volume does not apply to transparent objects (it reads the opaque copy). |
| UNITY-5 AudioLink-style input | **Partial** | Done: `audio_analysis.rs` (FFT band analyser: bass, low mid, high mid, treble, volume, 64-frame history; tested with sine sweeps), Toon `AUDIO` feature (band-driven emission, alpha, rim and hue shift), `LoadedScene::set_audio_bands` (writes only the uniform block, no dirty flag), Poiyomi AudioLink emission / rim band mapping. Not done: nothing taps the audio engine's mixed output yet, so the bands are zero until a caller feeds `AudioAnalyzer` with samples (or animates `audio_bands` by hand). Reason: the engine mixes through rodio sinks (and Steam Audio voices), and a correct tap needs the summed output, which rodio does not expose; a per-source tap would have to sum analyses. There is no AudioLink texture (history is on the CPU analyser only) and no vertex-offset modulation (no vertex hook, see UNITY-11). |
| UNITY-6 Flipbook | **Done** | Toon `FLIPBOOK`: sprite sheet (columns, rows, frames), fps or manual frame, crossfade, tint, replace / add / multiply, emission; tile edges inset by half a texel so filtering never reads the next frame. Poiyomi stores frames in a `Texture2DArray` asset, which cannot be read, so the converter maps the numbers and reports the texture. |
| UNITY-7 Toon additions | **Done** (outline texture mask skipped) | Wrapped lighting mode (`wrap_amount`), shadow layer 3, RGBA colour masking (`COLOR_MASK`: per-channel tint and hue shift), `hue_shift` / `hue_speed` / `brightness`, per-vertex outline width (`outline_vertex_width`, red vertex colour), and converter aliases: matcap 2, emission 2, dissolve, decal (Poiyomi decal, lilToon Main 2nd), detail normal / albedo, lilToon reflection and specular, shadow 3, HSV. Skipped: outline width mask texture (the outline hull runs in the vertex stage, which has no material texture bound), Poiyomi specular / reflection aliases (property names not known well enough to guess). |
| UNITY-8 PBR detail / transmission | **Done** (GUI unverified) | Standard shader: a **detail layer** (albedo with Multiply x2 / Overlay / Add / Replace, normal, ORM, mask, own tiling / offset; each strength 0 = off), **thin translucency** (back-lit light through the surface: colour, power, normal distortion, a translucency or thickness map; the shadow lookup is offset to the light's side) and **transmission** (the opaque scene copy seen through the surface, tinted, offset by the shading normal; it turns Scene Colour Read on). Five new set-1 samplers (bindings 17-21) and five vec4s appended to the fx block; every existing binding keeps its number, and every pipeline shares the one `set1_layout` (cluster, prepass, shadow, XR, impostor, preview, skybox), whose sets are all written by `create_material` / `bind_material_slots` / the skybox set. Serde defaults load old materials unchanged. Checked on the real device by `tests/unity_fx.rs` phases P00-P15 (`docs/design/pbr-detail-transmission-contact-sheet.png`). **Rough transmission, transmission texture, glTF thickness: done** (GUI unverified): the opaque colour copy has a mip chain (box-filtered blits, built only on frames that draw a transmission material); the shader takes `lod = 6 x blur x roughness x (0.35 + 0.65 x thickness)` and averages a 5-tap tent over that level (new fx `trans3`: blur, thickness, map flag; inspector Blur / Thickness / Map Green = Transmission). The translucency / thickness map (binding 21) is shared: red = thickness (with Map Is Thickness), green = transmission factor (with Map Green = Transmission); a glTF model's `transmissionTexture` (R) and `thicknessTexture` (G) are repacked into it at import (`ModelIdentity::material_volume_maps`, import cache format 9), thickness factor `1 - exp(-2 x metres)`. Colour probes at roughness 0 / 0.5 / 1: blue leaking 5 px into the red half 0 / 148 / 200 of 231, thickness 0 gives 65. Found on the way: draws with Scene Colour Read were eligible for the GPU-culled camera batches, which never take the opaque copy, so transmission on standard materials saw a stale copy (the earlier P12-P15 passed on the previous test's copy); they now keep the CPU path. Not carried: dispersion, XR (no opaque copy in the VR pass), reflection captures, transmission on cluster-path meshes, a thickness texture with its own UV set (the packed map uses the material's). |
| UNITY-9 VRM MToon in glTF | **Done** (editor button unverified) | `mtoon::import_mtoon_materials` turns the MToon materials of a VRM 1.0 / 0.x into ZestEngine Toon `.material` files: glTF textures are written out of the model and copied through the converter's own texture step, outline / rim / matcap / shade colour come from the same MToon table, and the model's material remap table is filled. It runs as part of the model importer's **Extract Materials** (before the plain extract, which then skips what is mapped); it is not automatic on first import because the importer does not write project files. Tested on a real VRM 0.x (`Vivixx Vtube.vrm`: 18 of 18 materials MToon, every base-colour texture resolved, 53 textures written; that avatar has no outlines) and on a synthetic VRM 1.0 with an outline. Not carried: the per-pixel shade texture, UV animation, outline width modes beyond a fixed scale. |
| UNITY-10 Panosphere, hue / brightness, front-face cull, blend modes, distance fade | **Done** | Per-material `blend` (Alpha, Additive, Multiply, Premultiplied) and `cull_front` in the render pipeline key, model and inspector; Toon `PANOSPHERE` (equirectangular sky by view direction, spin, blend, unlit) and `DISTANCE_FADE` (screen-door dither when opaque), plus the hue / brightness controls. The converter maps Poiyomi modes 5-8 and `_SrcBlend` / `_DstBlend`. |
| UNITY-11 Vertex hooks | **Done** (GUI unverified) | A custom GLSL shader's `// @vertex` ... `// @endvertex` section defines `zestengine_vertex(inout VertexData v)` (object position / normal / tangent / UVs / colour, `model`, `world_position`, world-space `world_offset`, `time`, the shader's `// @property` block, textures, keywords, `frame`). It runs in every pass that draws the material with the same code: `standard.vert` for main / depth prepass / XR multiview / planar (one module, so the prepass and the EQUAL-tested main pass agree), `shadow.vert` for the shadow pass (swaying geometry casts the swayed shadow; its layer re-renders every frame). Built with `glslc` on first use (`vertex_hook.rs`); existing shaders are untouched (no section = no extra module). Template `shaders/zestengine_wind_sway.frag`; docs/shaders.md, "Vertex hook". GPU tests (`gpu_tests/vertex_tess.rs`, `zestengine-assets/tests/vertex_hook.rs`): lean 27.0 px vs 27.5 projected, hooked shadow tip px 151 vs 150.9 (unhooked 125 vs 124.9), prepass + EQUAL 0 of 867 px differ, shadow depth = camera depth. Not done: no baked sidecar for the hook SPIR-V; no instance colour / param; the previous-frame position assumes no hook motion (TAA ghosting when fast); HLSL has no hook. Cluster: custom-shader materials never use the cluster path, so there is no cluster hook module (hooked casters draw as ordinary meshes in the shadow pass too). **Converter**: Poiyomi / lilToon vertex manipulation (`_VertexManipulationLocalTranslation`, `_Wind`, ...) stays "not supported": the hook is shader code, not a property set, so there is nothing to map to. |
| UNITY-12 Fur, tessellation, LTCGI, Voronoi / truchet, depth FX | **Partial** | **Fur: done** (GUI unverified): Toon `FUR` feature (`fur_tip`, `fur_root`, `fur_length`, `fur_layers`, `fur_density`); the renderer draws the mesh once per shell (one instanced draw each, shell index in the push constants) with `fur.vert` / `fur.frag`: the shell is pushed out along its normals, a procedural strand grid on the UV keeps the pixels inside a tapering strand with a hashed length; opaque and alpha-tested so nothing needs sorting. Shaded by a wrapped key-light term over a root-to-tip ramp (no shadows, no GI, no wind or gravity). A fur material is excluded from the GPU-culled batches (like an outline) and is not drawn on the cluster path. **Tessellation: done** (GUI unverified): `MaterialParams::tess` (`TessParams`: enabled, scale, midlevel, target edge px, max factor, phong; inspector **Tessellate** under the Displacement slot) displaces the mesh by the height map through hardware tessellation stages (`tess.tesc` / `tess.tese`), levels from the screen-space edge length, Phong smoothing, height-slope normals. One extra pipeline-key bit; the stages are in the main pass, depth prepass (same modules: EQUAL agrees), XR multiview, planar / capture passes and the shadow pass (`shadow.vert -DZE_TESS` + `tess.* -DSHADOW`, tessellated from the same camera so the shadow follows the displaced surface). Casters with a displaced material draw separately from the shared shadow batches and re-render every frame; displaced materials skip the GPU-culled camera batches and the cluster path (ordinary draw). No tessellation on the device: draws flat. The compute pre-subdivision fallback was weighed and not built (docs/shaders.md). GPU tests: edge-on plateau top row 91 vs 90.6 projected, prepass + EQUAL 0 of 6 260 px differ (flat-prepass control 2 983), shadow depth = camera depth, wall shadow 211 vs 212.0 projected, XR multiview layers = per-eye passes (IoU 1.0). Not verified: planar / capture passes with a displaced material, Flux's depth prepass draws them flat. **Area lights (LTCGI-equivalent): done** (GUI unverified): the `Area Light` component (core, serde defaults, registered, inspector) is a rectangle or disc emitter with colour, intensity (emitted radiance), range, two sided and an optional emission texture (project path or `camera:<id>`, so a second camera is a live screen light). Shading is linearly transformed cosines written from the 2016 paper: diffuse is the exact clamped-cosine integral over the polygon (horizon clip + Lambert's edge sum), specular the same integral through the inverse LTC matrix of the GGX lobe at (N.V, roughness), scaled by the split-sum reflectance the shader already uses. The matrix table is our own Nelder-Mead fit (`crates/zestengine-render/src/ltc.rs`, 24 x 24 cells, relative L1 error 0-4 % up to N.V about 0.24 and 10-30 % beyond at mid roughness, the last column is reused for flatter angles), generated into `shaders/ltc_lut.glsl` (`cargo test -p zestengine-render --release --lib regenerate_lut -- --ignored`, 8 s). A light is two `frame.lights` entries (kinds 4 / 5 + continuation 6); the renderer packs the 8 nearest to the camera each frame ([`Renderer::set_area_lights`] fed by `gather_area_lights`) and copies each textured light's texture into a 4 x 2 tile RGBA16F atlas with a mip chain (set-1 binding 22, one shared image written into every material set; the lobe picks a mip by its width on the light's plane, so a screen light blurs with distance and roughness). Toon takes the diffuse form factor through its cel ramp. No shadows (v1), no tube shape, the texture is sampled once per lobe (not integrated over the polygon), not drawn in reflection captures, camera previews or XR. Checks (`tests/unity_fx.rs` A00-A10, `docs/design/area-lights-contact-sheet.png`): along a falloff line the GPU matches the CPU reference of the same math within 0.5 % (0.738 vs 0.736 at the centre), the specular peak of a glossy plane is at y 1.64 (CPU 1.68, mirror geometry 1.67) with equal level, a red | blue texture lights the left / right red / blue, one sided lights leave the back dark while two sided match the front, ten lights draw only the eight nearest, a disc matches a square of the same area. **Light Volumes: done** (GUI unverified) by extending the existing `Light Probe Volume` (it already had the oriented box, the probe grid, the editor bake, trilinear SH-L1 sampling and cascades): `blend_distance` > 0 turns it into a Light Volume (weight x smoothstep edge fade, blended with the other Light Volumes covering the point, replacing the probe / ambient light for objects without a lightmap), `.lightdata` v3 stores blend and weight (files without Light Volumes keep the old layout), `Renderer::set_light_volumes` appends their probes to the SH buffer behind the baked ones (frame UBO `MAX_PROBE_VOLUMES` 4 -> 8: 4 baked cascades + 4 Light Volumes, `ProbeVolume.params`; the custom-shader preambles mirror it and skip Light Volumes). Checks (V00-V04): a uniform sky of 0.5 reproduces 0.386 vs 0.384 analytic, the edge fade follows the smoothstep (0.227 / 0.2304 at half fade), two volumes (0.2 | 0.8) blend to the CPU reference within 0.007, weights 3 : 1 give 0.2705 vs 0.2688. L1 only (the bake stores SH-L1; L2 would need the bake shader and probe layout changed), custom shaders ignore Light Volumes, lightmapped surfaces never use them. Voronoi / truchet / depth FX are not done. |
| UNITY-13 Verify alias tables against real avatars | **Partial** | A Unity project (735 `.mat`, 247 Poiyomi) and the Poiyomi / Mochie packages on this machine were read for **property names only** (no shader source). Verified and fixed in this pass: Poiyomi grab pass, dissolve, flipbook, panosphere, AudioLink, decal, detail, and the Mochie Screen FX names; see the tables below. Still unverified: the lilToon and MToon-on-Unity tables, Mochie Standard (no Mochie Standard material on the machine), Mochie Glass (none either), and the importer's "Convert Unity materials next to this model" button. The vertex-hook / tessellation work (UNITY-11, UNITY-12) added no converter mapping: Poiyomi / lilToon vertex manipulation, wind and tessellation property names were NOT in any real material read here (no Pro material on this machine), so they stay unmapped and are reported as unsupported rather than guessed. |
| UNITY-14 Drag a package / folder onto the Files panel | **Skipped** | Files panel and `.prefab` / `.fbx` GUID maps are editor work outside this pass. |

### ZestEngine side reference (new)

| Feature | Where | Notes |
|---|---|---|
| Blend mode, Cull Front Faces, Scene Colour Read | Material inspector (Transparency / Geometry) and `MaterialFeatures { blend, cull_front, grab }` in `.material` files | serde defaults: old materials load unchanged |
| `zestengine_blend_mode` | custom shader constant (0 alpha, 1 additive, 2 multiply, 3 premultiplied) | Multiply has no alpha term, so shaders fade towards white themselves (Toon does) |
| Grab helpers | custom GLSL preamble | see UNITY-3 |
| Custom texture slots | 24 per shader (was 20) | Toon is at 22 |
| Toon `lighting_mode` Wrapped | appended after Flat, so existing indices are unchanged | |
| Toon features | `COLOR_MASK`, `FLIPBOOK`, `PANOSPHERE`, `DISTANCE_FADE`, `GRAB`, `AUDIO` | all off in the presets |
| `outline_vertex_width` | Toon `OUTLINE` group | the renderer reads a negative outline width as "scale by red vertex colour" |

### Converter aliases added for the gaps (Poiyomi rows checked against real `.mat` files; lilToon rows unverified)

| Concept | lilToon | Poiyomi |
|---|---|---|
| Cull front | `_Cull` 1 | `_Cull` 1 |
| Blend mode | `_SrcBlend` / `_DstBlend` | `_Mode` 5-8, `_SrcBlend` / `_DstBlend` |
| Refraction / grab | `_TransparentMode` 3, `_RefractionStrength`, `_RefractionColor`, `_RefractionColorFromMain` | `_EnableGrabpass`, `_GrabpassColor`, `_GrabPassBrightness`, `_GrabBlurDistance` (x200 px) **(names seen in real preset materials)** |
| Hue / brightness | `_MainTexHSVG` | `_MainHueShift`, `_MainBrightness` (present in real materials) |
| Shadow layer 3 | `_Shadow3rdColor`, `_Shadow3rdBorder`, `_Shadow3rdBlur` | n/a |
| Matcap 2 | `_UseMatCap2nd`, `_MatCap2ndTex`, `_MatCap2ndBlend`, `_MatCap2ndBlendMode`, `_MatCap2ndBlendMask` | `_Matcap2`, `_Matcap2Intensity`, `_Matcap2Mask` |
| Emission 2 | `_UseEmission2nd`, `_Emission2ndMap`, `_Emission2ndColor` | `_EnableEmission1`, `_EmissionMap1`, `_EmissionColor1` |
| Second layer / decal | `_UseMain2ndTex`, `_Main2ndTex`, `_Color2nd`, `_Main2ndTexBlendMode` (full-UV decal) | `_DecalEnabled`, `_DecalTexture`, `_DecalColor`, `_DecalRotation`, `_DecalPosition`, `_DecalScale` **(verified in real materials)** |
| Detail | `_UseBump2ndMap`, `_Bump2ndMap`, `_Bump2ndScale` | `_DetailTex`, `_DetailNormalMap`, `_DetailMask`, `_DetailTexIntensity`, `_DetailNormalMapScale` **(verified)** |
| Dissolve | n/a | `_EnableDissolve`, `_DissolveNoiseTexture`, `_DissolveAlpha` (the amount; `_DissolveCutoff` does not exist), `_DissolveEdgeWidth`, `_DissolveEdgeColor`, `_DissolveEdgeEmission` **(verified)** |
| Reflection / specular | `_UseReflection`, `_Smoothness`, `_Metallic`, `_ApplySpecular` | n/a |
| Flipbook | n/a | `_EnableFlipbook`, `_FlipbookTexArray` (a Texture2DArray asset: unreadable, reported), `_FlipbookTotalFrames`, `_FlipbookFPS`, `_FlipbookCurrentFrame` (with `_FlipbookManualFrameControl`), `_FlipbookCrossfadeEnabled`, `_FlipbookColor` **(verified; `_FlipbookTex`, `_FlipbookColumns`, `_FlipbookRows` do not exist)** |
| Panosphere | n/a | `_PanoToggle`, `_PanosphereTexture`, `_PanosphereColor`, `_PanospherePan` (x = spin) **(verified; `_PanoRotationSpeed` does not exist)** |
| AudioLink | n/a | `_EnableAudioLink`; add rows are vectors whose green is the gain: `_AudioLinkRimEmissionAdd` / `_AudioLinkRimBrightnessAdd` + `_AudioLinkRimEmissionBand`, `_AudioLinkAddEmission` / `_AudioLinkEmission0CenterOut` + their `..Band` (0-3) **(verified present; only 3 of ~480 materials set a non-zero gain)** |
| Outline vertex width | `_OutlineVertexR2Width` | n/a (width mask textures are reported) |
| Lighting Wrapped | n/a | `_LightingMode` 2 |

## How conversion works

1. **Read** the Unity `.mat` (text YAML; `unity_mat.rs`). Tolerates Unity versions,
   the older `first:/second:` layout, multi-document files and garbage. Binary `.mat`
   files are reported (switch Unity to Force Text).
2. **Identify** the shader: built-in Standard by GUID; then by name (from the
   `.shader` file the material's shader GUID points at, e.g. `.poiyomi/Poiyomi Toon`,
   `Hidden/Locked/.poiyomi/...`, `Mochie/Standard`, `lilToon`, `VRM/MToon`); then by
   **property signature** for locked / renamed shaders.
3. **Map** (`unity_convert.rs`) through alias tables into a ZestEngine material.
   Colours are converted sRGB to linear (HDR emission colours are stored linear by
   Unity and are kept), tiling/offset is carried, alpha mode from the shader's
   mode property (or keywords / render queue), cull mode, cutoff, emission, matcaps,
   rim, shadow layers, normal map, outline.
4. **Resolve textures**: Unity GUIDs are looked up through the `.meta` files of the
   folder you point at; the textures are copied to `textures/unity/` and given the
   right import kind with `ensure_first_import_for_slot` (sRGB colour, normal map).
   Metallic / smoothness / occlusion are repacked into one ORM texture
   (R occlusion, G roughness = 1 - smoothness, B metallic). Formats the engine does
   not load (PSD, TIFF, DDS) are reported.
5. **Write** `materials/unity/<name>.material` and `<name>.convert.txt` beside it.
   The report lists Mapped, Approximated, Not supported yet, unmapped properties
   with a value, and a one-line list of zero / empty ones. Nothing is dropped silently.

Entry points (Files panel context menu): **Convert Unity Material...** on a `.mat`,
**Convert Unity folder...** on a directory (task with progress and a summary
notification), **Import Unity package...** on a `.unitypackage` (gzip tar, read
with `flate2` already in the tree; extracted to a temp folder, then converted as a
folder). The model importer's *Search and Remap* picks converted materials
by name (the `.material` is named after the Unity material, which is the FBX
material name); `unity_convert::add_to_model_remap` fills the remap table directly.

## Support summary

| Shader | Converts to | Level |
|---|---|---|
| Poiyomi Toon (free), Poiyomi Pro | ZestEngine Toon | core look: base, alpha, shadows, rim, matcap, emission, outline, normal |
| lilToon | ZestEngine Toon | same set (property names from the lilToon material layout) |
| VRM/MToon (Unity side) | ZestEngine Toon | base, shade colour/shift/toony, rim, emission, outline, cull, alpha |
| Mochie Standard (+ Lite / Mobile) | PBR standard | textures, metallic / roughness / occlusion packed, normal, emission, alpha, cull |
| Unity Standard, Standard (Specular), URP/Lit | PBR standard | as above; specular setup approximated |
| Mochie Screen FX / Screen FX X | ZestEngine Screen FX | filtering, blur, shake, distortion, pixelation, noise, chromatic split; amounts approximate; fog / DoF / zoom / SST / Sobel / triplanar reported unsupported; volume = Everywhere |
| Mochie Water / Glass / Particle / LED / Uber, others | placeholder PBR + report | colour, textures, alpha only; the report says "unsupported". Glass has no converter: no Mochie Glass material exists on this machine to read its property names from |

Confidence: the **Poiyomi, lilToon and MToon property names** below are the serialised
names as used in `.mat` files, from the public documentation labels and the
serialisation conventions; they were not verified against a real exported
avatar in this pass (see "Unverified"). Poiyomi renames some properties
between 8.x, 9.x and 10.x, so each concept lists aliases and the converter takes the
first present.

## Poiyomi Toon (free) and Pro

Docs sections used: Color and Normals, Shading (Lighting Modes, Matcap, Rim Lighting,
Reflections and Specular), Special FX, Outlines, Rendering. Priority is for *importing
avatars that look right*.

| Poiyomi feature (property) | ZestEngine | Priority |
|---|---|---|
| Main texture `_MainTex`, colour `_Color`, tiling/offset | Albedo slot, `main_color` (linear), `main_st` | done |
| Rendering mode `_Mode` (opaque, cutout, fade, transparent) | features alpha mode | done |
| Additive / multiplicative modes (`_Mode` 5-8) | `blend` Additive / Multiply | done |
| `_Cutoff` | `alpha_cutoff` | done |
| `_Cull` (off / back) | double sided | done |
| `_Cull` front | `cull_front` (Cull Front Faces) | done |
| Normal map `_BumpMap`, `_BumpScale` | Normal slot, `normal_strength` | done |
| Second normal map / detail normal | `DETAIL` (`detail_normal`, `detail_albedo`) | done (unverified names) |
| `_Saturation` (main colour adjust) | `saturation` | done (approx) |
| Hue shift, brightness | `hue_shift`, `brightness` | done; colour grading not supported |
| RGBA colour masking | Toon `COLOR_MASK` | engine side done; converter does not map it (property names unknown) |
| Lighting: Texture Ramp, Multilayer Math, Flat, Realistic | `lighting_mode` Ramp / Multilayer / Flat / Realistic | done |
| Lighting: Wrapped | `lighting_mode` Wrapped | done |
| Lighting: Skin, ShadeMap, Cloth, SDF, PBR | Multilayer / Realistic (approx) | low: SDF face shadow |
| Shadow colour, strength, layers 1-2 (border, blur) | `shadow_color`, `shadow_strength`, `layer1_*`, `layer2_*` | done |
| Shadow layer 3 | `layer3_*` | done (lilToon mapped; Poiyomi has none) |
| Toon ramp `_ToonRamp`, offset | `ramp_tex`, `ramp_offset` | done |
| Min / max light brightness | `light_min`, `light_max` | done |
| Rim lighting (colour, width, sharpness, strength, mask) | `RIM` + `rim_*` | done |
| Rim blend modes, environmental rim, depth rim | not supported | low: add `rim_blend` aliases; depth rim needs depth access |
| Matcap 1 (texture, mask, add / multiply / replace, intensity) | `MATCAP` + `matcap_*` | done |
| Matcap 2 | `MATCAP2` | done (unverified names) |
| Matcap 3-4, matcap normal map, border, tint colour | not supported | low; tint into the texture |
| Emission (map, colour, strength, mask, scroll) | `EMISSION` + `emission_*` | done |
| Second emission | `EMISSION2` | done (unverified names) |
| Third / fourth emission | not supported | low |
| Specular / reflections (`_Metallic`, `_Smoothness`, maps) | `metallic` / `roughness` for Realistic lighting only | medium: Toon SPECULAR / REFLECTIONS aliases |
| Clear coat, anisotropic (hair) | anisotropic exists in Toon, mapping not done | medium |
| Outline (width, colour) | `OUTLINE` + `outline_width` (x5, approx) | done; per-vertex width done (`outline_vertex_width`); outline mask / texture not supported |
| Alpha mask, alpha mod | `alpha_mask`, `alpha_mod` | done |
| Distance fade | Toon `DISTANCE_FADE` | engine side done; converter does not map it |
| Dither, fresnel alpha | Toon has `alpha_dither`, `alpha_fresnel`; not mapped | low |
| Dissolve, decals | `DISSOLVE`, `DECAL` | done (unverified names) |
| Glitter, UV tile discard, parallax | Toon features exist; not mapped | low |
| Stencil effects (type, reference, comparison, ops, masks) | `MaterialFeatures.stencil` | done, see UNITY-2; `_ColorMask` 0 and `_ZWrite` 0 writers map to `color_mask` / `depth_write` |
| Flipbook / sprite sheet | Toon `FLIPBOOK` | done; frame texture arrays cannot be read |
| Panosphere / sky texture | Toon `PANOSPHERE` | done |
| Grab-pass refraction / blur / distortion | Toon `GRAB` | done (tint, blur, distortion; no normal-map distortion) |
| AudioLink | Toon `AUDIO` + `audio_analysis.rs` | partial: the mixed output is not tapped yet, see UNITY-5 |
| Vertex options (local translation, rotation, scale) | not mapped | the engine has a vertex hook now (UNITY-11) but it is shader code, so a converted material has nothing to map these to: write the hook by hand (template `zestengine_wind_sway.frag`); the report still lists them |
| Voronoi, truchet, pathing, depth FX, mirror, proximity colour, stats overlay | not supported | low |
| TPS, SSAO, contact shadows, squish, fur, tessellation (Pro) | fur and tessellation exist in the engine (UNITY-12) but are not mapped from Poiyomi properties (names unverified: no Pro material on this machine); the rest not supported | low |
| LTCGI-style area lights | engine `Area Light` component (own LTC implementation) | rectangle / disc, texture, no shadows, 8 nearest; see the UNITY-12 notes below. No Unity converter (LTCGI is a scripted integration) |
| Light Volumes | engine `Light Probe Volume` in Light Volume mode (blend distance > 0) | L1 SH, weight blend, edge fade; no converter (VRC Light Volumes are an external tool) |
| Bakery and other baked-lighting options | not supported | low |

## Mochie shaders

Source: the project wiki lists Standard, Water, Glass, Particle, Screen FX, LED Screen,
Uber, Avatar Props, Underwater Visuals, Corruption, Splat mapping and Taken
(some Patreon-only). Only **Standard** has a converter.

| Mochie Standard feature | ZestEngine | Priority |
|---|---|---|
| Base colour / albedo, tiling and offset | Albedo slot, base colour (linear) | done |
| Normal map and strength | Normal slot, `normal_strength` | done |
| Metallic and roughness / smoothness maps, occlusion | repacked ORM texture | done (check the roughness direction visually) |
| Packed map workflow | repacked ORM covers the common layouts | done as a repack; no separate feature |
| Specular workflow | approximated | low |
| Emission map, colour, mask | Emission slot, colour | done; mask low |
| Emission pulse, audio link | not supported | low / medium (with AudioLink) |
| Height map, parallax occlusion mapping | Displacement slot | done (approx) |
| Detail textures (albedo / normal / metallic / roughness, blend modes) | `detail` layer (albedo, normal, ORM, mask) | done for Unity Standard / URP / HDRP names (Mochie's own property names are unverified: no Mochie Standard material on the machine) |
| Alpha: blending mode, cutoff, alpha source | alpha mode and cutoff | done |
| Culling | double sided | done |
| Screen-space reflections, contact hardening, specular occlusion | not supported (the engine has its own SSR / RT reflections) | low: map `_SSR` to `screen_reflections` |
| Reflection / specular models (Unity Standard, Filament) | not supported | low |
| Subsurface scattering | thin translucency exists in the PBR shader | the Mochie property names are unverified (no Mochie Standard material on the machine); HDRP `_MaterialID` / `_ThicknessMap` / `_TransmissionTint` map to it |
| Rain, puddles, wind (vertex) | not supported | low |
| Triplanar, mip-map rescaling, extra UV sets | not supported | low |
| Integrations: Bakery, AreaLit | not supported | low |
| Water, Glass, Particle, Screen FX, LED, Uber, Underwater, Corruption | not supported; placeholder + report | Screen FX: use the ZestEngine Screen FX shader by hand (no converter); Glass: the grab pass now exists, no converter (property names unknown); Water: the engine has its own water; the rest low |

## lilToon and MToon (also converted)

| Concept | Properties (serialised names) | ZestEngine |
|---|---|---|
| lil base | `_Color`, `_MainTex`, `_Cutoff`, `_TransparentMode`, `_Cull` | albedo, alpha, cull (refraction / fur / gem modes reported) |
| lil shadows | `_UseShadow`, `_ShadowColor`, `_ShadowBorder`, `_ShadowBlur`, `_ShadowStrength`, `_Shadow2nd*` | layers 1-2 |
| lil rim | `_UseRim`, `_RimColor`, `_RimBorder`, `_RimBlur` | `rim_*` (approx) |
| lil matcap | `_UseMatCap`, `_MatCapTex`, `_MatCapBlend`, `_MatCapBlendMode`, `_MatCapBlendMask` | `matcap_*` |
| lil emission, outline | `_UseEmission`, `_EmissionMap`, `_EmissionColor`; `_OutlineWidth`, `_OutlineColor` (outline shader variants only) | `emission_*`, `OUTLINE` |
| MToon | `_ShadeColor`, `_ShadeShift`, `_ShadeToony`, `_ReceiveShadowRate`, `_RimColor`, `_RimFresnelPower`, `_SphereAdd`, `_OutlineWidth`, `_BlendMode`, `_CullMode` | shadow colour / border / blur, rim, additive sphere as matcap, outline, alpha, cull |
| MToon gaps | `_ShadeTexture`, UV animation, outline width modes | not supported (low) |

VRM models imported as glTF (`VRMC_materials_mtoon`, VRM 0.x `materialProperties`) are read by
`mtoon.rs`, which feeds the same table; wiring it into the model importer is open (UNITY-9).

## Licences (recorded, not depended on)

| Project | Licence as stated publicly | Note |
|---|---|---|
| Poiyomi Toon Shader (free, 9.x-10.x) | MIT (`LICENSE.txt` in the repository) | The repository asks that avatars do **not** bundle the `_PoiyomiShaders` folder. Pro is a paid Patreon tier; its shader source is private and its terms apply. |
| PoiyomiDocs (documentation) | MIT | |
| ThryEditor (Poiyomi's inspector) | MIT | |
| Mochie's Unity Shaders | MIT (public repository); some shaders Patreon-only (terms of that distribution apply) | |
| lilToon | MIT (public repository; not re-checked in this pass) | |
| UniVRM MToon | MIT (not re-checked in this pass) | |
| Unity built-in shaders | Unity's terms; the built-in Standard is identified by GUID only | |

## Sources

- Poiyomi documentation source (Docusaurus): https://github.com/poiyomi/PoiyomiDocs
  (sections `docs/shading`, `docs/color-and-normals`, `docs/special-fx`, `docs/outlines`,
  `docs/rendering`, `docs/vertex-options`, `docs/audio-link`; the hosted site
  docs.poiyomi.com was not reachable from the build machine, so the repository's
  `shading/main.mdx` and `color-and-normals/alpha-options.mdx` were read for the
  lighting modes and alpha options)
- Poiyomi Toon Shader repository and licence: https://github.com/poiyomi/PoiyomiToonShader
- Mochie's Unity Shaders repository: https://github.com/MochiesCode/Mochies-Unity-Shaders
- Mochie wiki, Standard Shader page (setting labels):
  https://github.com/MochiesCode/Mochies-Unity-Shaders/wiki/Standard-Shader
- Mochie wiki, Home (shader list): https://github.com/MochiesCode/Mochies-Unity-Shaders/wiki

## Unverified

- Serialised property names for Poiyomi 9/10, Mochie Standard, lilToon and MToon
  come from the documented labels and naming conventions; the Mochie Standard and
  Poiyomi blend-mode enum values and the Poiyomi lighting mode order follow the
  docs' list order. Verify with a real exported avatar and adjust the alias tables
  (`POIYOMI`, `LILTOON`, `MTOON` in `unity_convert.rs`).
- Outline width scale (Poiyomi x5) and the lilToon / MToon rim mappings are
  approximations. Everything marked Approximated in a report needs a visual check.
- Unity `.mat` files that Unity wrote in binary mode are not read.
- The aliases added for UNITY-3 to UNITY-10 (table above) are likewise names from
  the shaders' documentation and conventions; lilToon's refraction, `_MainTexHSVG`,
  `_Shadow3rd*`, `_MatCap2nd*`, `_Emission2nd*` and `_Main2nd*` names are the
  better known ones, the Poiyomi grab pass, flipbook, panosphere, AudioLink,
  dissolve and decal names are the least certain. A wrong name only means the
  feature is not carried over and shows in the report as an unmapped property.
- VRM 0.x `vectorProperties` colours are read as linear (UniVRM writes them
  linear); VRM outline widths use a fixed scale (0.002 m, or 0.4 cm in 0.x, is one
  ZestEngine outline unit).
- The grab pass was checked in the main viewport pass of a real renderer only. The
  Toon `GRAB` distortion direction (normal x to the right, y up on screen) was
  checked by the seam moving; the VR multiview path was not exercised.

## Real-data check (this pass)

Property names were read from `.mat` files only: a Unity project (`~/storage/avis/lemon_meringue`,
735 materials, 247 identified as Poiyomi), the Poiyomi 9.3 / 10 / 11 and Mochie 1.65 / 1.69 / 1.75
`.unitypackage` files and several avatar packages. `unity_convert.rs` carries
`real_poiyomi_materials_map_the_verified_names` (skipped when the project is absent). Findings:
the grab-pass names in the first draft were wrong (`_EnableGrabpass`, `_GrabpassColor`,
`_GrabBlurDistance` are the real ones), as were `_DissolveCutoff`, `_FlipbookTex`,
`_FlipbookColumns` / `_Rows`, `_PanoRotationSpeed` and the AudioLink emission / rim names; decal,
detail, panosphere, dissolve and flipbook-enable names were right. The only real grab-pass materials
found are Poiyomi *preset* files (shader guid 0), so the grab mapping is checked on names, not on a
shipped avatar. Mochie Screen FX has one real material (the prefab) whose effect toggles are all off,
so the effect-amount scales (px per unit) are choices, and the `*Model` enums are only assumed to
be 0 = off. No Mochie Glass or Mochie Standard material exists on the machine.

