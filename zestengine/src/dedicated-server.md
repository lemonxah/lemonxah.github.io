<!-- Copied from docs/dedicated-server.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# Dedicated server

`zestengine-server` (NET-2) hosts a project scene with no window, GPU, audio device or
headset. It is the same gameplay, physics and networking code the player runs
(`zestengine_engine::server::HeadlessHost` plus a hosting `NetSession`), driven by a fixed tick loop.
The Network Manager's `dedicated` mode is forced on: the server gets no player of its own; every
joiner gets the Network Manager's player prefab at a Spawn Point (same rules as a player-host).

## Build

```sh
cargo build --release -p zestengine-server        # target/release/zestengine-server
just server <project-dir>                          # debug build + run
```

The crate depends on `zestengine-engine` with `default-features = false`, so the `client` feature is
off. `cargo tree -p zestengine-server -e normal` has none of `ash`, `winit`, `egui`, `cpal`,
`rodio`, `gilrs`, `openxr`, `audionimbus`, `gpu-allocator`, `shaderc`, `zestengine-render` or
`zestengine-xr`; the renderer is the inert stand-in `zestengine-render-lite`. Direct dependencies:
`zestengine-engine`, `zestengine-core`, `anyhow`, `serde`, `ron`, `tracing`, `tracing-subscriber`, `libc`
(and `windows-sys` on Windows).

## Run

```sh
zestengine-server --project ~/games/arena --port 9000 --max-players 16
zestengine-server --config server.ron
zestengine-server --project ~/games/arena --headless-selftest   # load, host, join a loopback client, stop; exit 0
./build-server/run.sh                                           # a Dedicated server build (see below)
```

| Flag | Meaning |
|---|---|
| `--project <dir>` | Project folder (holds `project.zestengine`). Required (flag or file). |
| `--scene <path>` | Project-relative scene. Default: the project's boot scene. |
| `--port <n>` | UDP port. Default: the scene's Network Manager port, else 9000. `0` = OS picks. |
| `--max-players <n>` | Players at once (the server does not count). Default 16. |
| `--tick-rate <hz>` | Fixed tick rate, 1 to 240. Default 30. |
| `--name <text>` | Server / session name (LAN discovery). |
| `--password <text>` | Join password = the session secret. Prefer `ZESTENGINE_SERVER_PASSWORD` (not visible in `ps`). |
| `--config <server.ron>` | Settings file. Flags override it; the environment password sits between. |
| `--log <file>` | Also log to this file, rotated by size. |
| `--log-level <l>` | `error`..`trace` or a `tracing` filter such as `info,zestengine_engine::net=debug`. |
| `--no-lan` | Do not answer LAN discovery queries. |
| `--no-console` | Do not read admin commands from stdin. |
| `--healthcheck` | Probe a running server through its heartbeat file under `state_dir`; exit 0 alive, 1 not (stale, stopped, missing). No project, network or keys needed. |
| `--health-max-age <s>` | Heartbeat age `--healthcheck` accepts. Default: three `health_interval`s, at least 30. |
| `--print-config` | Print the effective settings (file, environment and flags merged; password and relay token hidden) as RON and exit. |
| `--headless-selftest` | Smoke test, see above. |

Exit codes: 0 after a graceful stop, 1 when startup fails after logging began, 2 for a bad command
line or config, 101 after a panic (logged with file and line, log file flushed).

## `server.ron`

Copy `crates/zestengine-server/server.example.ron`. Every field is optional; unknown fields are an
error. `port: 9000` needs no `Some(..)`.

| Field | Default | |
|---|---|---|
| `project` | `""` | Project folder. Required. |
| `scene` | boot scene | Project-relative scene. |
| `port` | scene's port, else 9000 | UDP port. |
| `tick_rate` | `30.0` | Hz, 1 to 240. |
| `max_catch_up_ticks` | `5` | Ticks run in one wake-up when behind; the rest of the backlog is dropped with a warning. |
| `max_players` | `16` | 1 to 4096. |
| `server_name` | `"ZestEngine Server"` | Session name and the server's player name. |
| `password` | `""` | Join secret (also keys the session encryption). Empty falls back to the scene's Network Manager `secret`. |
| `log_path` | none | Log file. |
| `log_level` | `"info"` | Level or filter. |
| `log_max_mb` / `log_keep` | `10` / `5` | Size rotation: `server.log` -> `server.log.1` .. `.N`. |
| `lan_discovery` | `true` | Answer LAN queries (UDP 47777). |
| `motd` | `""` | Private message to each joiner. |
| `admin_tokens` | `[]` | Retired shared-secret tokens: ignored (a warning is logged). Use `admin_keys`. |
| `restart_on_scene_end` | `false` | A component asking to quit reloads the scene for everyone instead of exiting. |
| `stats_interval` | `10.0` | Seconds between stats lines, 0 = off. |
| `console` | `true` | Read stdin admin commands. |
| `identity_file` | `<project>/.server/identity.key` | The server's signing key. Clients pin it on first join and refuse a changed one, so keep it across reinstalls. |
| `ban_file` | `<state_dir>/bans.ron` | Bans made by the strike system, the `ban` command or `NetSession::ban_fingerprint`, by player id, loaded at start. |
| `state_dir` | `<project>/.server` | Where saved state, bans and the identity live (see "Server services"). |
| `persist` / `persist_interval` / `persist_keep` | `true` / `60` / `3` | Persistent world and player state: on, seconds between saves (0 = only at shutdown), backup generations. |
| `admin_port` / `admin_bind` / `admin_keys` | none / `0.0.0.0` / `[]` | Signed remote admin. |
| `directory` / `directory_interval` | `""` / `30` | Relay (`host[:port]`) to list this server on, and the heartbeat in seconds. |
| `region` / `game` / `game_version` | `""` | What the directory lists; `game` defaults to the project folder's name. |
| `relay` / `relay_room` / `relay_token` | `""` | Open a room on this relay (join by code from behind a NAT); empty takes the scene's Network Manager. |
| `shutdown_redirect` | `""` | Offered to players when the server stops (`host:port` or a room code). |
| `health_interval` | `5.0` | Seconds between heartbeat writes (`<state_dir>/health.status`, `metrics.prom`); 0 = off. See `docs/deployment/dedicated-server.md`, "Monitoring". |
| `metrics_addr` | `""` (off) | Loopback `ip:port` of a tiny HTTP listener serving `/health` and `/metrics`; a non-loopback address is refused. |
| `validation` | the scene's Network Manager | Replaces the Network Manager's validation settings; name only the fields you change: `validation: (max_rewind: 0.2, rates: (rpc: (rate: 20.0, burst: 40.0)))`. See `docs/networking.md`, "Dedicated sessions". |
| `interest` | the scene's Network Manager | Interest management for big worlds (NET-5): `interest: (enabled: true, radius: 120.0, hysteresis: 20.0, budget: 60000, tiers: [(distance: 0.0, rate: 0.0), (distance: 60.0, rate: 10.0)], voice_range: 50.0)`. Off by default. See `docs/networking.md`, "Interest management". The `interest` console command lists each player's relevant objects and bytes/s. |
| `anticheat` | the scene's Network Manager | Anti-cheat provider (SEC-2): `anticheat: (provider: "none", require: false, pending_timeout: 30.0, options: {})`. `provider` is `none` (default), `eos` (Easy Anti-Cheat; the binding is not built, so it fails closed) or a provider the host program installs with `NetSession::set_anticheat`. With `require: true` a joining client is held out of gameplay (its data is ignored, like a muted peer) until the provider says Trusted; a rejection or `pending_timeout` seconds without an answer kicks it with the reason and counts a strike (repeat offenders are banned in `bans.ron`). `require: false` only logs and counts rejections. See `docs/research/security/anticheat.md`. |

Validation reports every problem at once (missing project, scene not in the project, rates out of
range, bad log filter, ...). Relative paths resolve against the working directory. Settings that
come from the scene's Network Manager (relay, room code, allow/ban lists, accounts, timeout) still
apply; the server then overrides name, player limit, discovery, password, sets the topology to Dedicated
and turns host migration off.

## Behaviour

- **Tick loop**: a monotonic accumulator yields whole fixed ticks; at most `max_catch_up_ticks` run per
  wake-up, the rest of the backlog is dropped (a rate-limited `server overloaded` warning) so a stall
  cannot snowball. Between ticks it sleeps (in slices of at most 50 ms so a stop is prompt) and spins
  only the last 1.5 ms. Inbound packets are read once per tick, so latency adds up to one tick.
- **Stats**: every `stats_interval` seconds one line: ticks (and per second), mean and max tick ms,
  players, bytes in/out and rates.
- **Joining**: the engine's handshake rejects a wrong protocol version, wrong password and a full
  session with an explanatory reason. Joins and leaves are logged with the player id and the short
  fingerprint.
- **Console** (stdin): `status`, `players`, `stats`, `kick <id> [reason]`, `ban <id|fingerprint> [30m|2h|7d|perm] [reason]`,
  `unban <fingerprint>`, `bans`, `say <text>`, `scene <path>`, `save`, `reload`, `restart [addr]`, `shutdown [addr]`,
  `quit`, `help` (plus `interest` when interest management is on). Without a stdin (a service manager) the console
  ends quietly. The same commands arrive over UDP as signed remote admin (below).
- **Shutdown**: SIGTERM, SIGINT (Ctrl+C), Ctrl+Break and console close on Windows, or `quit`. The server
  stops ticking, sends every player a close notice with the reason ("server shutting down"), closes the
  socket, flushes the log and exits 0. A second signal exits at once (130).
- **Identity**: the server keeps its own Ed25519 identity on disk; it is not shared with a player install.
  Clients pin it on first join (trust on first use).
- **Authority and validation (NET-4)**: the server is the authority for everything and checks what clients send:
  rate limits, NaN and bounds, movement budgets with teleport correction, VR pose limits, ownership rules
  (flagged objects, in reach, free, cooldown), RPC permissions, a spawn allow-list (none by default), size
  limits, timestamps, forged ids. Violations are counted per peer, logged rate limited, scored, and lead to
  a warning, muting, a kick with a reason and a ban by player id (`bans.ron`). The stats line shows the
  violation and muted counts. No player address is sent to other players. Details and the rule table:
  `docs/networking.md`.

## Content roles (`NetRole`)

Every scene object and every component has a role: `Both` (the default; old scenes mean this), `Client`
(only players have it) or `Server` (only the dedicated server has it). A dedicated server removes
`Client` content when it loads a scene and from every prefab or network spawn; a player that only ever
joins servers removes `Server` content (`zestengine_core::set_process_role(NetRole::Client)`, the player
keeps `Both` by default so offline play and listen hosts are unchanged); the editor keeps everything.

**Rules**
- An object's role hides it from the other side with its whole subtree. A child cannot be more
  permissive than a missing parent: a `Both` child of a `Client` object is gone on a server too.
- A component's effective role is the object's per-component override if it has one, else the
  type's default. Overrides are keyed like prefab component keys (`Kind`, `Kind#1` for a second one),
  stored in the scene entry (`net_role`, `component_roles`; both omitted when default) and are ordinary
  prefab-overridable properties (revert, apply, variants).
- A kept component may still hold an object id of a stripped object (a trigger pointing at a client-only
  effect, an event binding). It resolves to "missing" (no crash) and the load logs one warning naming
  both objects (`Root/Zone [Trigger Events] references stripped object Root/Smoke`).
- A game component declares its default with `const NET_ROLE: NetRole = NetRole::Server;` on its
  `TypedComponent` impl. Pattern for server-only logic: also put it behind your crate's own cargo feature so
  the code is not compiled into the client binary.

**Type defaults** (anything not listed is `Both`: colliders, rigid bodies, character controllers, joints,
triggers, navigation, network components, spawn points, Animator and Humanoid IK (poses feed hitboxes),
avatar data, scripts, Wasm scripts, the gameplay kit, water and buoyancy, VR Player / Avatar, Voice Chat)

| Group | `Client` types |
|---|---|
| Lighting and rendering | Camera, Light, Light Probe Volume, FluxVoxel Light, Flux Volume, Reflection Probe, Planar Reflection, Per Instance, Volume (Post FX), Decal Projector, Terrain Foliage, Particle Emitter, LOD Group, Text 3D, Sprite Renderer, Sorting Group, Sprite Mask, Mesh Cloth, Cloth Colliders, Bone Cloth, Wind Zone |
| Audio | Audio Source, Audio Listener, Acoustic Material, Audio Probe Volume |
| UI | UI Canvas, UI Rect, UI Panel, UI Image, UI Text, UI Button, UI Toggle, UI Slider, UI Progress Bar, UI Pause Menu, UI Text Field, HUD Binding, Controls Menu |
| Player-side presentation | Follow Camera, RTS Camera, Lip Sync, Face Tracking, Blend Shapes, Avatar Menu Item, Menu Toggle, Menu Installer, Merge Animator, Merge Armature, Avatar Menu |

Mesh "renderers" are not components (a mesh object is an object with a model source): the server keeps
those objects, loads their collision geometry and skips everything render-only. The table lives in
`crates/zestengine-core/src/net_role.rs` (`builtin_default_role`).

**Editor**: the Inspector header has a *Network Role* dropdown (Both / Client only / Server only) and lists
warnings for the object's server-kept components that point at stripped objects or at files a server
build drops; each component's kebab menu has *Network Role* (and *Type default*). The Hierarchy shows a
`C` / `S` tag on objects that are not `Both` (dimmed on descendants that inherit it) and its filter
box matches `client` / `server`. Project Settings > Build has a *Dedicated server* target.

**Play as Server** (editor): Network window > *Play as Server* saves nothing itself; it runs the *saved* scene as a local
dedicated server on a loopback port on a background thread (`zestengine_engine::local_server::LocalServer`: the same
headless host as the server binary, Server-role content kept, Client-role stripped, strict validation, no persistence or
admin port) and joins it as a player, so the editor shows what a player sees. Leaving the session stops the server.

## Server build target

```sh
just build-server <project> [out-dir]      # cooks <project>/build-server, copies to out-dir if given
zestengine --build <project> --target server     # the same from the editor binary
```

Editor: Project Settings > Build > Target *Dedicated server* > *Build Server*. Output (`build-server/`):

```text
zestengine-server    the server binary
server.ron           project: "assets", the boot scene, the project name, tick 30 Hz, log under logs/
run.sh               cd into the folder and start with server.ron
assets/              the stripped cook (loose files)
build-report.txt     client vs server sizes, dropped files by class, per-scene strip counts, reference warnings
```

**Stripped cook** (`crates/zestengine-engine/src/server_build.rs`):
- Scenes and prefabs are rewritten with prefab links expanded and `Client` content removed; skybox and
  editor camera dropped. Reachability is recomputed from the stripped scenes, so a model, animation or data
  file used only by stripped content is not shipped.
- Models become collision-only blobs at their own path (`ZSM1`, `zestengine_assets::server_model`): positions
  and indices, authored collision pieces, instances, skeletons, animation clips and sub-asset ids; no
  normals, tangents, UVs, vertex colours, skin weights, blendshapes, spring bones, textures or materials.
  The model loader recognises the blob by its magic, so `.meta` sidecars and sub-asset ids keep working.
- Dropped by extension: images and skyboxes, sprite sheets and atlas products, audio, shaders (`.frag`,
  `.hlsl`, `.spv` ...), `.material`, fonts, video, baked lighting (`.lightmap`, `.reflprobe`, `.occlusion`,
  `.audiobake`, `.lmuv`), sidecars of dropped files, and the geometry / texture / atlas caches. Kept: scenes,
  prefabs, physics materials, navmesh data, animation clips and controllers, `.wasm` logic, data (`.ron`),
  `resources/`. No shader precompile, no ASTC, no geocache. The server reads loose files by default; `--pak` also writes
  `assets.pak` (see below).
- Roles use the built-in type defaults, the project-wide list (`net_role_overrides` in `project.zestengine`, edited in
  Project Settings > Network roles) and per-component overrides, in that order of increasing priority; a project
  component's own `NET_ROLE` is applied when the server loads the scene (the cook does not load project plugins).

**`--strict-roles`**: `zestengine-build-server --strict-roles <project>` (or `ZESTENGINE_STRICT_ROLES=1`, which also
applies to Build Server in the editor) turns every cook warning (a scene kept unstripped, a model shipped whole) and every
"kept content references stripped content" lint into an error that lists them all and stops before compiling.

**`assets.pak`**: `--pak` (or `ZESTENGINE_SERVER_PAK=1`) also packs the cooked assets into `build-server/assets.pak` and
writes `server.ron` with `project: "assets.pak"`. The server accepts `project` as the pak file, or as a folder that
holds an `assets.pak` but no `project.zestengine`, unpacks it once per pak (named by a hash of its contents) into
`<state_dir>/assets/` and runs from there; with no `state_dir` the state folder is `.server` next to the pak. The
`deploy/` files still copy the loose `assets/` folder.

**Warnings** ("kept content references stripped content") are printed in the build log and listed in
`build-report.txt`: a kept component with an object id of a stripped object, or a path of a file the
server build drops (a gameplay script naming a texture or a sound).

**The binary**: a project with `plugins/components` gets a generated crate `target/zestengine-server/`
(`Cargo.toml` + `src/main.rs`, its own workspace root, lockfile seeded from the engine's) that depends on
`zestengine-server` (library) and the project's component crate with `default-features = false` (no `editor`
feature, so no editor UI or egui) and starts `zestengine_server::run_main(|registry|
<components>::zestengine_register(registry))`. A project without components uses the stock `zestengine-server`
from the engine checkout. Either way the binary is copied to `zestengine-server` in the output folder.
**Plugins at runtime.** `server.ron` may list built component `cdylib`s: `plugins: ["plugins/libzestengine_project_components.so"]`
(relative paths resolve against the server's working folder, as `log_path` does). They are loaded before the scene, so the scene's own
components resolve. Each library must export the ABI stamp (`zestengine_core::export_plugin_abi!();` in the plugin crate, already in the
scaffold) and must have been built by the same rustc, from the same engine version and with the same profile (debug / release) as the
server; otherwise the server refuses to start and the error says which plugin and what differs. A missing file, a file that is not a
shared library, a library without `zestengine_register` or without the stamp refuse the same way. Libraries stay loaded until exit.
Build them with the project's normal plugin build (`cargo build -p <plugin>`) and copy the file next to the server.

**Cross-compiling**: the host triple is used. `ZESTENGINE_SERVER_TARGET=x86_64-unknown-linux-gnu just build-server ..`
passes `--target <triple>` (install it with `rustup target add`, and configure a linker for it in
`.cargo/config.toml`); from Windows or macOS to Linux a `musl` target with `rust-lld`, or `cargo zigbuild`,
is the usual route. Only Linux x86_64 on a Linux host is the supported path today; see
`docs/deployment/dedicated-server.md`, "Cross-compiling", for what was and was not checked
(`scripts/check-server-cross.sh`).

**`deploy/`**: the build folder also gets a `deploy/` folder (systemd unit and `@` template unit, a production
`server.ron` with `state_dir` outside the build folder, env file, Dockerfile, compose file, nftables / ufw and
logrotate examples, `install.sh`, `kubernetes.yaml`), generated from the project's name; the game port is the one the
scene's Network Manager names (9000 when the scene has none). Guide: `docs/deployment/dedicated-server.md`.

**Content packages**: a package extracted on a server (`ExtractOptions { server_side: true, .. }`) skips the
files above (images, audio, shaders, materials ...), and the scene loader strips `Client` roles from its
scenes and spawns like it does for project content.

## Not there yet

- NET-3: a role change on several selected objects undoes only the primary object (server plugin loading and the plugins of "Play as Server" are done). A visual check of the new Project Settings > Network roles list and the Play as Server button was not done.
- NET-4: a visual check of the Validation inspector section. Voice loudness cannot be limited by the server (it relays
  opaque Opus frames); the packet size and rate are limited instead.
- NET-5: a GUI check of the inspector section (the 50-VR-player measurement is done: `docs/networking.md`, "VR bandwidth"; the dense-plaza case stays above the 3.6 MB/s target). Host
  migration under interest is handled (aliases and per-client state are reset on both sides) but has no end-to-end test.
- NET-6: matchmaking beyond the list, a server browser inside a *game* (the editor's Network window has one; a game
  builds its menu on `zestengine_engine::server_browser::ServerBrowser`), an encrypted admin channel (see "Why admin
  replies are signed, not encrypted"), a `Persistent State` inspector check on screen, relay-side directory persistence
  (the list rebuilds itself from heartbeats within one interval), a real-runtime check of the redirect follow.
- NET-7: nothing was run under systemd, Docker or Kubernetes (the files are generated and unit-tested as text), no
  signed admin `status` JSON for external monitors.

## Server services (NET-6)

### Persistent state

Add a **Persistent State** component (Add Component > Network) to a scene object and the server keeps it across
restarts. Flags: `transform` (position, rotation, scale), `variables` (the object's Network Variables), `per_player`
(on the player prefab's root: its Network Variables are saved under the owner's player id and handed back when that
player joins again, the prefab-spawned object being a different one every session).

```text
<state_dir>/world.state     per scene: flagged objects by scene object id (transform, variables)
<state_dir>/players.state   per player id (fingerprint): name, first/last seen, sessions, saved variables
<state_dir>/bans.ron        bans (engine format)
<state_dir>/identity.key    the server's signing key
```

- Restored when the scene loads (at start and after every scene switch); variables are written through the session
  (`NetSession::set_var`), so players that join later see them. Player data is restored as soon as the joiner's
  player object exists, and kept current every tick; nothing is restored for a player id the server has not seen.
- Written every `persist_interval` seconds, on the `save` command and at shutdown. Unchanged state is not rewritten,
  and a server whose project flags nothing writes no `world.state` at all. Scene objects are copied into the state every
  2 s and when `scene` is used, so a scene switch loses at most that.
- **File format** (`ZESTSTATE 1 <schema> <bytes> <crc32>` line, then RON): a save writes `<name>.tmp`, syncs it, rotates
  `<name>` to `.bak1` (`.bak1` to `.bak2` ... up to `persist_keep`), renames the temp file into place and syncs the
  folder. A crash leaves the old or the new generation, never half. A load takes the newest generation whose length
  and checksum match; a damaged one is moved aside as `<name>.corrupt-<unix>` (never rotated over a good backup) and
  logged as an error; with nothing usable the server starts from the authored scene. A file with a newer schema than
  the server understands is left untouched and never overwritten (the server runs without it and says so).
- Not persisted: objects spawned at runtime (no stable id), physics velocities (bodies restart at rest), anything
  not flagged. A scene object's *name* and *id* must not change between runs for its state to find it.

For a built server the project folder is the cooked `assets/`, so the default state folder is `build-server/assets/.server/`,
which a rebuild replaces. In production set `state_dir` outside the build folder (`/var/lib/mygame`); it is the one
directory that must survive redeploys (identity key, bans, world and player state).

### Signed remote admin

`admin_port` opens a UDP port that takes the console's commands from holders of an admin key. Make one on your
machine, list the public half in `server.ron`, and the server logs its own key at start (`server key ...`):

```sh
zestengine-admin keygen --out ops.key
# server.ron:  admin_port: 9100,  admin_keys: [(name: "ops", key: "<printed hex>", role: Admin)],
zestengine-admin --server host:9100 --server-key <server key> --key ops.key players
zestengine-admin --server host:9100 --server-key <server key> --key ops.key ban 7 2h griefing
```

Roles: `Observer` (status, players, stats, bans, interest, help), `Moderator` (+ kick, ban, unban, say), `Admin` (+ scene,
save, reload, restart, shutdown). The console on the host is always Admin. Exit code of the tool: 0 ran, 1 refused or
failed, 3 no signed answer.

| Protection | How |
|---|---|
| Authentication | Ed25519 signature over a domain tag, **the server's public key**, and the request; only listed keys act |
| Replay | timestamp within +/-30 s and not before the server started, and a `(key, nonce)` seen once; replays get `Stale` |
| Cross-server replay | the signature binds the target server's key |
| Tampering | any changed byte fails the signature; no reply is sent to anything unauthenticated |
| Amplification | unauthenticated sources get nothing; answers go to the sender of a valid signed request only |
| Flooding | token bucket per source IP (10 burst, 5/s) before any signature is checked |
| Spoofed answers | replies are signed with the server identity and bound to the requesting key and nonce |

Replies are signed, not encrypted: do not print secrets in command output. Keep `admin_port` firewalled to your
operators if you can (see "Why admin replies are signed, not encrypted" below). `reload` re-reads the command line's `--config` and applies `motd`, `stats_interval`,
`restart_on_scene_end`, `admin_keys`, `persist_interval` / `persist_keep`, `directory_interval`, `region`, `game`,
`game_version`, `shutdown_redirect`; it lists the changed settings that need a restart (port, tick rate, player limit,
password, project, ...) and refuses a file that does not validate. `restart` exits with code **75**; `shutdown`
and `quit` exit 0.

**Key rotation without a restart.** `keys` lists the keys in force; `key add <name> <64-hex> <observer|moderator|admin>`
lets a new key sign at once and `key remove <name|8+ digits>` retires one (Admin only). The changes are an overlay in
`<state_dir>/admin_keys.ron` over `server.ron`'s `admin_keys`: they survive a restart and a `reload`, and the effective
list is `(file keys - removed) + added`. The last Admin key cannot be removed, a key cannot be listed twice, and a
retired key gets no answer at all, like any unknown key. Rotation: add the new Admin key, check it works, remove the old
one.

**Reports.** A player (or a game script) calls `NetSession::report_player(peer, reason)`, or the RPC
`zestengine.report` with `[Int(peer), Str(reason)]` aimed at the server. The server checks the target is a connected
player other than the reporter and the reason fits a chat line, rate-limits it (3 burst, then one per 5 s), and logs it at
`warn`, keeps the last 200 in memory (`reports` for Moderators, `reports clear` empties it) and appends a line to
`<state_dir>/reports.log` with the reporter's and the target's fingerprints. Nobody else receives the report; act on it
with `ban <fingerprint>`.

**Bans.** `ban` takes a connected player's id or a 32-digit fingerprint (offline players), an optional duration
(`30m`, `2h`, `7d`, `perm`) and a reason (shown to the player, kept in `bans.ron`); it kicks the player if connected.
`unban` accepts a fingerprint or a unique prefix of 8 or more digits; `bans` lists them with the time left. They go
through the same list the strike system writes (`val.bans`), so a ban made by either survives restarts.

**Account linking (anti-cheat).** When a provider can name a client's account (`AntiCheatProvider::server_provider_id`:
an EOS product user id, a Steam id ...), the server links it to the player id once the client is Trusted. A ban of the
player (admin `ban`, or the strike system) also bans the account (a hashed key in the same ban list, so it survives
restarts); the same account arriving later under a new player key is removed as soon as the provider names it, and the new
key is banned too. The built-in providers name no accounts yet (the test provider can), so this is the plumbing, not a
verified EOS/Steam integration. The link itself is kept in memory for the session; the *ban* is what persists.

**Held clients.** With anti-cheat `require` on, a client that is not Trusted yet is in the session but out of the world: it
gets no catch-up (scene, objects, variables), no player object, and none of the broadcasts, snapshots, chat or RPCs, until
the provider trusts it (then the catch-up and the player object follow) or the pending timeout removes it.

### Why admin replies are signed, not encrypted

A reply is a status line, a player list, a ban list or a settings summary: operational data about the server, not secrets (no
password, key or token is ever printed, and no command reads one back). Signing (bound to the server identity, the
requesting key and the nonce) stops a forged or replayed answer; encryption would only hide player names and
fingerprints from someone who can already watch the operator's traffic, and it would need a key agreement and an AEAD on
a path that is deliberately a single stateless datagram each way. Where that is not acceptable, bind `admin_bind` to a VPN
or loopback address (or tunnel it); the port is never needed by players. If a future command has to return a secret it
must not use this channel.

### Server directory

A relay started with `--directory` is also a server list (`zestengine-relay --directory [--dir-ttl 90] [--dir-max 4096]
[--dir-per-ip 4] [--dir-allow KEYHEX]`). With `directory: "relay.example.com"` the server sends a signed announcement
(name, game, version, scene, region, players / max, port, relay room code, password flag) every `directory_interval`
seconds and a signed delisting at shutdown; a crashed server drops off when the TTL (default 90 s) runs out. Players
list with filters (region, game, version, name, hide full / empty / password-protected) using
`zestengine_relay::directory::query_blocking` (cookie handshake and paging are handled).

- The server cannot be spoofed: the entry is keyed by its Ed25519 identity, announcements are signed, timestamps must grow
  (a captured packet cannot relist a server that left), the listed address is where the announcement came from.
- Limits: token buckets per IP for announcements (6 burst, 0.5/s) and queries (8 burst, 2/s) before any signature work,
  4 listings per IP, 4096 in all, replies to unauthenticated senders are never larger than the request (queries need a
  cookie bound to the sender's address, the list itself is paged in packets of at most 1200 bytes).
- Also new on the relay: `--host-rate` / `--client-rate` (bytes per second, defaults 4 000 000 and 1 000 000) replace the
  fixed room cap.
- A server behind a NAT sets `relay` (and optionally `relay_room`): it opens a room, the directory entry carries the
  code, players join with it (`NetSession::join_with("CODE", ..)` with the relay set).

### Graceful shutdown

SIGTERM, `quit`, `shutdown` and `restart` save the state, delist, and tell every player why. `shutdown 10.0.0.2:9000`
(or `shutdown_redirect` in the config, or a room code) adds `[redirect: ...]` to the notice; a player's game that was
joined to a dedicated server follows it by joining the offered address with the same settings
(`zestengine_engine::server::follow_redirect`; it never follows a listen host's notice).

## Tests

`cargo test -p zestengine-server` (CPU only): config parsing, validation and flag override, console
parsing, pacer and catch-up cap under a synthetic heavy tick, log rotation, and in-process loopback
tests over real UDP (`tests/loopback.rs`): join and player spawn, replicated variable, motd, console
commands, max players, wrong password, protocol mismatch, graceful shutdown notice within a time
budget, port conflict and bad scene errors, `--headless-selftest`. NET-4 over real UDP
(`tests/validation.rs`): topology announced, no succession plan, the key pinned, a restarted server accepted, a
changed key refused with the clear error and accepted after the pin is cleared, abuse refused and counted, flood
then kick then ban by key, `bans.ron` surviving a restart, `server.ron` `validation:` reaching the session.

NET-6 tests (CPU only): the state file (`state_store.rs`: checksum, rotation, truncated / flipped / empty / garbage /
extended files, crash between the rotation and the final rename, every generation damaged, newer container), the
command language and roles (`admin.rs`), the signed admin wire (`remote.rs`: signatures, tampering, unknown keys,
foreign server, replay, stale clocks, restart window, roles, flood), the directory (`relay/src/directory.rs` unit tests:
forgery, replay, expiry, caps, rate limits, paging, text clamping; `relay/tests/directory.rs` over loopback UDP) and
`server/tests/services.rs` over real UDP: world objects and player data surviving restarts with a truncated current file
and with every generation damaged, interval and command saves, signed ban / unban / kick / say, replayed and forged
packets, `restart` and `shutdown`, `reload`, directory listing with heartbeat and delisting, join by room code
through the relay, and the shutdown redirect followed by a client.

NET-3 tests (CPU only): role serialisation and old scenes (`assets/src/scene_file.rs`), prefab override and
revert of roles (`prefab_link.rs`), strip rules, dangling-reference and asset lints (`net_strip.rs`),
collision blob round trip (`server_model.rs`), runtime filtering of scenes and spawns on server, client and
listen host (`engine/src/server.rs`), the cook of scaffolded `vr_social` and `topdown` projects with sizes,
`server.ron`, generated crate and recipe checks (`engine/src/server_build.rs`), and the server hosting a
scene with a test registry plus the generated `server.ron` parse (`zestengine-server/tests/roles.rs`).
