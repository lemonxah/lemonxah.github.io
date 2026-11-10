<!-- Copied from docs/user-content.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# User-generated content (`.zestenginepak`)

Players and creators can bring worlds, avatars and props into a running zestengine
game without recompiling it, the way VRChat loads worlds and avatars built in
Unity. A creator builds a package in the editor (Tools > Build Content
Package); the game loads it from a file or URL at runtime.

## Why this works without recompiling

A zestengine game is already split into data and code:

- Scenes, materials, models, textures, audio, animation clips/controllers,
  baked lighting and custom shader *sources* are all data files.
- Behaviour comes from components. A component on an object is just a type
  name plus serde (RON) data; the logic is compiled Rust that the game links
  statically (`run_game(config, |registry| ...)`).

So a package only has to carry the data. Every built-in component (lights,
colliders, rigid bodies, joints, animators, audio sources, particles, UI,
portals, nav agents, pawns, ...) already exists in every game, which covers a
lot of behaviour. Components from a project's plugins only exist in games that
link that plugin; the builder flags them and the loader drops any component the
running game doesn't have, with a warning.

Sandboxed WASM components can ship custom logic (see "WASM component modules"
below). For session-wide asset overrides, scene additions and matching multiplayer
mod profiles, see [Game mods](modding.md).

## Package format

A `.zestenginepak` is a zip archive (the `zip` crate was already in the dependency
tree; entries are deflated except already-compressed images/audio):

```text
manifest.ron                  PackageManifest
files/<project-relative path> entry .scene + every referenced asset
texcache/<path>.<srgb>.cbc    BC import-cache blobs for material textures
geocache/<model path>.zgeo    cluster DAGs of the models' big meshes (format 2)
thumbnail.png                 optional preview
```

`manifest.ron` holds:

| Field | Meaning |
|---|---|
| `format_version` | archive layout version (`PACKAGE_FORMAT_VERSION`; 2 adds `geocache/`, version 1 packages still open and build their cluster data on first load) |
| `engine_format` | asset format generation (`ENGINE_CONTENT_FORMAT`); newer packages are refused with a clear "update the game" error |
| `kind` | `World`, `Avatar` or `Prop` |
| `name`, `author`, `version`, `description`, `thumbnail` | metadata |
| `entry` | the entry scene inside `files/` |
| `components` | every component kind the content uses |
| `stats` | triangles, texture bytes, file bytes, objects, shaders (claims; re-measured at load) |
| `files` | file table: archive path, size, SHA-256 |
| `content_hash` | SHA-256 over the file table: the package id and cache key |

All three kinds use a `.scene` as the entry. A world is the scene itself (with
its `<scene>.lightmap/.lightdata/.occlusion/.reflprobe/.audiobake` sidecars);
an avatar or prop is its object hierarchy saved as a one-root scene. That keeps
a single loader path for everything.

Material textures travel twice: the source image (for anything that decodes
it) and the BC7/BC6H import-cache blob, so a game loads them without the
decode + block-compress step. Blobs are re-bound to the extracted file and
skipped on GPUs without BC support (the source is re-encoded instead).

Custom shaders travel as `.frag` source and are compiled by the game when the
content loads (`glslc`, like the editor). A game without `glslc` falls back to
the standard shader for those materials.

## Building (editor)

Tools > Build Content Package opens the build window:

- **World**: packages the open scene. Save it first so its baked sidecars sit
  next to it.
- **Avatar / Prop**: packages the selected object and its children. The root is
  moved to the origin.

Analyse shows what would be written (files, size, triangles, texture memory,
components, warnings, errors); Build writes `build/content/<name>.zestenginepak`
(or the chosen output path).

The builder (`zestengine_assets::package::plan_package`):

1. Classifies each component: engine built-in (kept), plugin (kept with a
   warning, or stripped by option), unknown (stripped).
2. Serializes the entry scene and collects its dependencies transitively by
   scanning every string in the RON (including strings nested inside component
   data) for project files, then the files those reference: materials ->
   textures and shaders, scenes -> models and bake sidecars, models -> `.meta`
   import settings, `.lmuv` markers, glTF buffers/images and FBX textures.
   Only whitelisted file types are packed (no binaries, no precompiled `.spv`).
3. Rejects shader sources that use `#include`.
4. Measures triangles (per placement), texture memory and object count and
   checks them against the kind's limits.
5. Avatars must have exactly one root; a missing Avatar Descriptor is added with
   defaults, and the skeleton is checked for a humanoid mapping.

### Avatar Descriptor

The `Avatar Descriptor` component marks an avatar root:

- `view_position`: eye point relative to the root (y = eye height). When the
  avatar is worn, the player's camera child moves here.
- `bone_map`: humanoid role -> joint name overrides for rigs the automatic
  mapper doesn't recognise (`hips`, `head`, `left_upper_arm`, `left_lower_arm`,
  `left_hand`, `right_*`, `left_upper_leg`, `left_lower_leg`, `left_foot`,
  `right_*`, plus `chest`, `neck`, `left_shoulder`, `right_shoulder`).
  Validated at build time with `HumanoidRig::map_with_overrides`.
- `collider_radius` / `collider_height`: applied to the player's Character
  Controller.

When an avatar is worn, its skinned parts get a `Humanoid IK` (source Auto):
the wearer's trackers drive it locally, and other players' copies follow their
replicated trackers. The descriptor's bone map applies to that IK. Parts that
carry blendshapes also get `Face Tracking` and `Lip Sync`, so faces and mouths
work with no setup.

## Loading at runtime

`ContentManager` (`crates/zestengine-engine/src/content.rs`) lives in the game
runtime and in the editor's Play mode. Gameplay drives it through `ctx`:

```rust
// Load only (validate + upload); result arrives as ContentEvent::Loaded.
let req = ctx.load_content("https://example.com/forest.zestenginepak");

// Spawn a prop in front of the player.
let (req, root) = ctx.spawn_content("/home/me/chair.zestenginepak", pos, rot);

// Make an avatar package the player's body.
ctx.spawn_avatar(self.player, avatar_id_or_path);

// Seamless world switch (objects marked keep_on_scene_change come along).
ctx.enter_world(world_id);

ctx.unload_content(id);

for e in ctx.content_events() {
    match e {
        ContentEvent::Progress { request, stage } => {}
        ContentEvent::Loaded { request, info } => {}      // info.id = content hash
        ContentEvent::Spawned { request, info, root } => {}
        ContentEvent::WorldEntered { request, info } => {}
        ContentEvent::Failed { request, source, error } => {}
        ContentEvent::Unloaded { id } => {}
    }
}
```

`source` is a file path, an `http(s)://` URL, or the content id (hash) of a
package loaded before.

Each request runs on a worker thread, mirroring the scene loader:

1. Resolve the source. Ids come straight from the cache; URLs are looked up in
   the cache index first, then downloaded through the `ContentFetcher`.
2. Open the archive and validate the manifest against the limits of its kind.
3. Extract into the cache (`<cache>/<content hash>/`), verifying every file's
   size and SHA-256 and the content hash. RON assets are rewritten so packaged
   paths become absolute paths into the extraction directory (packages can't
   collide with game assets or each other); relative paths that aren't in the
   package still resolve against the game's own assets, so content can reuse
   base-game assets. Unknown components are dropped and BC blobs installed.
   The directory only appears once complete; a cached extraction is reused
   when the hash and the game's component set match.
4. Decode models and textures and upload them on the transfer queue
   (`scene_loader::load_on_worker_checked`), with the real triangle count and
   texture memory checked before anything is uploaded.

The main thread then:

- **World**: hands the decoded scene to `SceneFlow::switch_to_loaded`, so the
  switch is the same seamless switch as `ctx.load_scene` (old world keeps
  running until the new one is ready, kept objects carried over).
- **Prop / Avatar**: appends the hierarchy to the current scene with fresh
  object ids (id references inside component data follow), tagged with an
  origin for unloading. Later spawns of the same package reuse the installed
  meshes and textures. Avatars are parented to the player, replace its previous
  avatar, and move its camera / capsule to the descriptor.

Downloads: the engine has no TLS client in its dependency tree, so the built-in
`HttpFetcher` handles plain `http://` (redirects, chunked encoding, size cap).
For HTTPS, a CDN or authentication, install a fetcher:

```rust
struct MyFetcher;
impl zestengine_engine::content::ContentFetcher for MyFetcher {
    fn fetch(&self, url: &str, dest: &Path, max_bytes: u64, progress: &dyn Fn(u64, Option<u64>)) -> Result<(), String> {
        // ureq / reqwest / platform HTTP here
    }
}
content_manager.set_fetcher(Arc::new(MyFetcher));
```

### Cache

The per-user cache defaults to `<cache dir>/<game title>/content`
(`GameConfig::content_cache` overrides it; the editor uses
`<project>/.zestengine_content`). It holds one directory per content hash,
`sources.ron` (URL -> hash, so a URL isn't downloaded twice) and `downloads/`.
`ContentCache::prune(max_bytes, keep)` evicts least-recently-used packages;
`evict(hash)` removes one.

### Developer overlay

Set `GameConfig::content_overlay` (or `ZESTENGINE_CONTENT_OVERLAY=1`) and press F8
in a built game: it lists `.zestenginepak` files in `<cache>/inbox`,
`<assets>/content` and `ZESTENGINE_CONTENT_DIR`, with Spawn / Wear / Enter buttons,
the loaded packages with Unload, and a log of content events and warnings.

## Safety model (untrusted content)

- **No native code, ever.** Nothing in a package is executed. File types are
  whitelisted at build and load; anything else (including `.so/.dll`) is
  dropped. Precompiled shader binaries (`.spv`) are never packed or extracted;
  shader sources are compiled by the game and `#include` is rejected, so a
  shader can't read local files at compile time.
- **No import hooks.** Model import hooks (`ModelImportHook`, IMP-6) are native
  plugin code, so they are editor-only. They only run after the editor's plugin
  loader enabled them, never in the standalone player, never inside content
  extraction (`ContentCache::extract` suppresses them), and never for any file
  under a `ContentCache` root (`import_hooks::mark_untrusted_root`), even in the
  editor. If UGC ever needs import customisation it gets data-only import steps
  in the `.meta`, never code.
- **Integrity.** Every file's size and SHA-256 is checked against the manifest
  and the manifest's file table against the content hash; a mismatch aborts the
  load and leaves nothing in the cache.
- **Paths.** Manifest paths must be normalized relative paths (no `..`, no
  absolute or drive paths, no duplicates). On extraction, strings in RON assets
  that point outside the package (absolute, `~/`, or climbing with `..`) are
  blanked with a warning. glTF buffer/image URIs must resolve inside the
  package or the package is refused.
- **Resource limits** (`ContentLimits::for_kind`, overridable with
  `ContentManager::set_limits`):

  | | World | Avatar | Prop |
  |---|---|---|---|
  | package size | 512 MiB | 64 MiB | 64 MiB |
  | unpacked size | 1 GiB | 200 MiB | 200 MiB |
  | files | 4096 | 512 | 512 |
  | triangles | 5 M | 150 k | 250 k |
  | texture memory | 1 GiB | 150 MiB | 128 MiB |
  | texture size | 8192 | 4096 | 4096 |
  | objects | 50 k | 2 k | 2 k |
  | custom shaders | 32 | 8 | 8 |
  | cluster data (`max_dag_bytes`) | 512 MiB | 48 MiB | 48 MiB |

  Besides the hard limits, content gets a **performance rank** (Excellent to Very
  Poor) from its triangles, materials, bones, blendshapes and texture memory
  (`zestengine_assets::perf_rank`, budgets per kind and Desktop / Mobile tier;
  `PackageStats` records the counts). Players set a minimum rank, a maximum
  number of shown avatars and a culling distance; other players' avatars that
  fail are not drawn (Tools > Performance in the editor).

  Limits are checked on the manifest's claims (fail fast), on archive entry
  sizes while reading (zip-bomb guard: reads are capped at the declared size),
  and on the measured data before upload, with errors naming each exceeded
  limit. BC cache blobs are fully validated (format, dimensions, per-mip byte
  counts) before they reach the GPU upload.
- **Unknown components** are dropped with warnings; component data that fails
  to deserialize is dropped by the registry as for any scene.

Known gaps: an FBX can name an absolute texture path that the importer tries
before the packaged relative one (read-only, local rendering only; prefer glb
for UGC). Other scenes a world links to by portal load through the normal
scene path, so the per-package limits only apply to the entry scene.

## Limitations

- Unloading a prop/avatar removes its objects immediately; its GPU meshes and
  textures stay allocated until the next world switch (the renderer frees
  resources per scene, not per handle). Spawning the same package again reuses
  them.
- Worn avatars replicate (content id + URL on the player's Network Avatar,
  see [networking.md](https://github.com/lemonxah/zestengine/blob/main/docs/networking.md)); one worn from a local file only reaches
  peers that already cached it.
- HTTPS needs a game-provided fetcher (no TLS client in the dependency tree).
- Custom shaders need `glslc` on the player's machine.
- Only one world switch per package can be pending at a time; content loaded in
  the editor's Play mode is forgotten when Play stops.

## WASM component modules

A package may carry `.wasm` modules that a `Wasm Script` component loads (the
component's `module` field is path-rewritten like any other asset reference).
The module's manifest actions show up in the event-binding dropdowns of other
objects, and bindings call them with typed arguments. The ABI (manifest, value
encoding, exports, host imports) is documented in
`crates/zestengine-core/src/wasm/mod.rs`; `guest/zest-guest` is a Rust helper
for authors.

Validation, with no guest code run, at build (errors) and again at extraction
(the package is refused):

- file size at most `ContentLimits::max_wasm_bytes` (1 MiB for worlds, 512 KiB
  for props), at most `max_wasm_modules` modules (16 / 4; avatars carry none);
- imports only from the `host` namespace and only functions on the allowlist;
  no WASI, no imported memory, table or global;
- exactly one exported 32-bit memory within the page cap (64 pages = 4 MiB);
- a valid `zest_manifest` custom section (modules in packages must have one),
  declaring only the capabilities untrusted content may use (`state`, `events`,
  `read`; never `invoke`), and the exports its actions and properties need.

At run time a module inside an extracted package is untrusted: tighter limits
(1 M instructions per call, 4 MiB, 256 KiB guest stack), and other objects'
bindings may call only actions its manifest flags `ugc_safe`, and only if
`allow_wasm_actions` is set in the package kind's limits. The content manager
registers each extracted package's `files` folder as untrusted
(`zestengine_core::wasm::register_untrusted_root`); the trust of a module is its
location. A trap (out of fuel, stack overflow, `unreachable`) disables the
component and logs one error.

## Game-wide mods and further scripting work

[Game mods](modding.md) reuse these archives and sandboxed components for asset
replacements, additive scenes, explicit game-granted action permissions, offline
UUID identities and multiplayer profile matching. A game's mod API version is
separate from the engine's WASM ABI and package format versions.

Further scripting APIs (for example additional physics queries or a visual
scripting graph interpreter) can extend the existing deferred-command model.
They should share its permission and resource boundaries rather than introduce
a second unrestricted execution path.

Native plugin dylibs (the editor's hot-reload path) are never an option for
untrusted content.

## Code map

- `crates/zestengine-assets/src/package.rs`: format, builder (`plan_package`,
  `write_package`), reader (`PackageReader`), validation, `ContentCache`,
  extraction / sanitizing, SHA-256.
- `crates/zestengine-core/src/wasm/`: the WASM component ABI (`abi.rs` codec and
  manifest, `sandbox.rs` inspection / limits / host imports, `component.rs` the
  `Wasm Script` component); `package::validate_wasm_module` applies it to packages.
- `crates/zestengine-assets/src/tex_cache.rs`: `texture_cache_blob`,
  `seed_texture_cache`, `validate_compressed`.
- `crates/zestengine-core/src/content.rs`: `ContentKind`, `ContentEvent`,
  `ContentCommand`, `AvatarDescriptor`, the `ctx` methods.
- `crates/zestengine-engine/src/content.rs`: `ContentManager`, worker
  (`load_package_on_worker`), `HttpFetcher`, F8 overlay, editor build window.
- `crates/zestengine-engine/src/scene_loader.rs`: `load_on_worker_checked`,
  `SceneFlow::switch_to_loaded`.
