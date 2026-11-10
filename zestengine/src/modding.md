<!-- Copied from docs/modding.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# Game mods

Mods reuse `.zestenginepak`, the existing asset loaders and sandboxed WASM
components. A mod adds `files/mod.ron` to the package. It can replace assets
exposed by a game and append objects to exposed scenes. The same profile runs
in editor Play, built games and dedicated servers.

## Identity without a registry

A mod has a canonical UUID v4, generated **once** by `ModManifest::new` or the
editor's **Create mod manifest (new UUID)** button. Generation uses the engine's
OS-random UUID generator and needs no internet service. Accidental collisions
are negligibly unlikely. Keep the UUID when publishing updates; generate a new
one for an independent fork. Names and authors are display metadata.

A UUID identifies a mod; it is not an authorship certificate. Multiplayer
compares the ordered list of UUIDs, exact versions and package content hashes,
plus the target game ID and mod API version. Copying an ID onto different
contents does not pass that comparison. The package SHA-256 file table covers
`mod.ron` and every packaged payload, and payload hashes are checked at install
and extraction.

## Game setup

Open **Project Settings > Mods**:

1. Set a stable Game ID and a Mod API version. Keep the game ID stable across
   display-name changes; increment the API when the game's mod contract breaks.
2. Expose exact asset paths, or directory prefixes ending in `/`. For example,
   `scenes/main.scene` permits replacement or additions to that scene, and
   `items/` permits replacement assets below that directory.
3. Expose any component actions mod WASM may invoke, as exact
   `Component.Action` names, for example `Health.Damage`.

A mod cannot grant itself additional paths or WASM action permissions. Its
manifest must target this game and this API version. Games can disable mods.
Native DLL/shared-library plugins are not loaded from mod packages. Mods may
use components already linked into the game, including game-specific ones;
missing required component types cause loading to fail instead of silently
changing gameplay.

## Authoring

In **Project Settings > Mods > Build a mod package**, enter a project-relative
manifest filename (for example `my-mod.ron`) and entry scene, then create the
manifest. This does not overwrite an existing file or regenerate its UUID.
Edit that manifest to describe the package:

```ron
(
    id: "c54364ed-1920-4a08-a962-169bab11a5ec", // example only: generate your own
    name: "Extra equipment",
    author: "Creator",
    version: "1.0.0",
    game_id: "my-game",
    game_api: 1,
    dependencies: [],
    conflicts: [],
    load_after: [],
    overrides: {"items/equipment.ron": "mod-assets/equipment.ron"},
    additions: {"scenes/main.scene": "scenes/equipment.scene"},
    actions: ["Health.Damage"],
)
```

Paths on the left are game paths; paths on the right are assets in the creator
project. The entry scene and assets referenced by the manifest are packaged
with their dependencies. The entry scene is not automatically appended:
`additions` declares the scene attachments. An empty entry scene supports a
replacement-only mod. Build writes `build/content/<uuid>.zestenginepak`.

Dependencies use `(id: "<uuid>", version: Some("1.0.0"))`; `None` accepts any
installed version at resolution time. Multiplayer still requires the exact
resolved versions. Dependencies must be installed and explicitly enabled.
Cycles, missing dependencies and declared conflicts fail validation.
`load_after` orders an enabled mod after another enabled mod. Otherwise profile
order decides precedence; later replacements win and produce a warning.

Additive scene objects receive deterministic namespaced IDs, preserving their
internal references without colliding with the base scene. Mod asset references
use `_mods/<uuid>/files/...` on every machine, including replicated prefab paths.
WASM file references resolve inside each machine's session snapshot. Mod WASM
uses bounded memory and fuel, has no WASI filesystem/network access, runs on the
server in multiplayer, and can invoke only the actions granted by the game and
requested by the mod. Use the existing Network Object, Network Variables and
network spawn facilities to replicate gameplay results.

## Installation and profiles

The Mods manager is available in Project Settings and through **F10** in a
built desktop game. Enter the path to a `.zestenginepak`, install it, enable the
wanted mods, adjust order, then **Validate and save profile**. Installing an
update replaces the installed version with the same UUID. Changes take effect
on the next game session or after stopping and restarting editor Play.

The default library is the user's data directory under
`zestengine/<game-id>/mods`; a project without a Game ID uses
`.zestengine/mods` in its project. Packages are stored as `<uuid>.zestenginepak`.
Profiles are `profiles/<name>.ron`:

```ron
(enabled: ["c54364ed-1920-4a08-a962-169bab11a5ec"])
```

`active.profile` selects the profile last saved in the manager. The project
configuration's `mods.profile` supplies the fallback name (`default`). A missing
profile means no enabled mods.

For a server, install the packages and profile into its library and set these
optional environment variables before startup:

```sh
export ZESTENGINE_MOD_DIR=/srv/my-game/mods
export ZESTENGINE_MOD_PROFILE=cooperative
```

The runtime freezes an asset snapshot before loading scenes or connecting.
Changing installed packages does not mutate a running session. Editor Play
requires the scene to be saved before applying mods and restores the authored
project on Stop. Start modded Play before opening an editor network session;
an existing session with a different profile must be disconnected.

## Multiplayer and saves

The encrypted handshake includes a digest of the resolved mod lock. The host
rejects mismatches **before admitting a peer or sending the world**. Missing or
extra mods, altered contents, differing versions and differing resolved order
all fail. This also applies to reconnects and host migration. Protocol version
8 is required on all peers.

A rejection lists the server's required UUIDs, versions and hashes in load
order, bounded to fit a handshake packet. Large lists are truncated with an
instruction to obtain the full profile from the server operator. Distribute
the packages and profile together; no online mod registry or automatic mod
download service is required or provided.

Save slots record the same mod lock. Loading an incompatible save logs an error
and preserves live state. Old saves with no mod metadata remain compatible with
unmodded sessions. Compatibility checks cannot prove a modified client is
honest; they prevent accidental content mismatch, not cheating.

## Scope and ownership

- `zestengine-core::mods`: serializable contracts, UUID validation, permissions,
  dependency/load-order resolution and save compatibility. No filesystem UI.
- `zestengine-assets::mods`: archive building/verification, installation, profiles
  and asset snapshots. Reuses the existing package format and import validators.
- `zestengine-engine::modding`: shared startup lifecycle; `modding_ui`: shared
  manager; networking enforces admission and Play enforces save compatibility.
- `zestengine-editor::editor_mods`: Play/Stop lifecycle and authoring UI hooks.
  Dedicated servers use the same engine startup path.

The initial implementation provides manual package distribution and desktop
management UI, not a mod catalog, subscriptions, signatures, automatic downloads,
a VR-native management panel or hot swapping. Profiles allow one installed
version per UUID. Mod snapshots copy project assets, so large projects need
additional temporary disk space. Asset dependencies must be packaged; external
resources in model formats should be embedded or explicitly replaced alongside
the model. Ordinary glTF external buffers/images are rebased on replacement.
