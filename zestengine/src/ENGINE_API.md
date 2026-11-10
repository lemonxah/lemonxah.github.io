<!-- Copied from ENGINE_API.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# ZestEngine Engine API Guide

What you can *do* from game code: move things, find and edit other objects, spawn and destroy, cast
rays, push bodies, read input, play sounds, change scenes, save progress, talk over the network.

This guide is organised by task. For how components, systems, stages and events fit together, read the
[ECS Guide](ECS.md) first. For the exact signature and full documentation of every function, use the
[API reference](https://lemonxah.github.io/zestengine/docs/api/zestengine_core/ecs/struct.EcsMoveHost.html).
The scripting sandbox has its own guide: [WASM.md](WASM.md).

The code in the recipes at the end of this guide is compiled and run by
[`crates/zestengine-core/tests/ecs_guide.rs`](https://github.com/lemonxah/zestengine/blob/main/crates/zestengine-core/tests/ecs_guide.rs).

## Getting started

### A project

**File → New Project** scaffolds a standalone Cargo project:

```text
my-game/
├── Cargo.toml            the game binary (links zestengine-engine, no editor)
├── project.zestengine    name, starting scene, control bindings, physics and audio settings
├── src/main.rs           the entry point
├── plugins/components/   your components, systems and entities (see the ECS guide)
├── scenes/  materials/  shaders/  textures/
```

`src/main.rs` is short and yours to edit:

```rust
use anyhow::Result;

fn main() -> Result<()> {
    zestengine_engine::init_logging();

    // A shipped build carries assets.pak next to the executable; during `cargo run`
    // the assets live in the project folder.
    let exe_assets = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("assets")))
        .filter(|p| p.join("project.zestengine").is_file());
    let assets_root = exe_assets.unwrap_or_else(|| std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    let config = zestengine_engine::GameConfig::from_project_dir(assets_root)?;
    zestengine_engine::run_game(config, |registry| {
        zestengine_project_components::zestengine_register(registry);
    })
}
```

- `GameConfig::from_project_dir` reads `project.zestengine`: the starting scene (**Project Settings →
  Starting scene**), window title, control bindings, physics, audio and rendering settings. Build a
  `GameConfig` by hand (`GameConfig { boot_scene: "scenes/main.scene".into(), width: 1280.0, height: 720.0, ..Default::default() }`)
  when you want full control; every field has a default.
- `run_game(config, register)` opens the window, loads the boot scene and runs the frame loop until the
  window closes. `register` receives the `ComponentRegistry` after the built-in components are added: this
  is where your project's components, systems and entities are registered (see
  [Plugins in a project](ECS.md#plugins-in-a-project)).
- **Editor Play mode and a shipped game run the same loop.** **File → Build Game** (or
  `zestengine --build`) produces a standalone executable with an `assets.pak` next to it.

### How your code is called

You do not write a main loop. You register **systems**, and every frame the engine runs them stage by
stage (see [Stages](ECS.md#stages)). A system receives:

| You get | Is | Use it to |
|---|---|---|
| `world: &SystemWorld` | Read access to every component through hecs queries | Find and edit component data |
| `ctx: &mut SystemContext` | The frame: `dt`, `time`, `input`, event bus, command queue, engine services | Read time and input, emit events, queue commands |
| `host: &mut EcsMoveHost` | A per-object toolbox (inside `run_ordered`) | Everything in this guide |

### Immediate and queued

Every operation in this guide is one of two kinds, and the tables below say which:

- **Immediate**: reads, and writes that edit component data in place (`host.edit::<T>(..)`,
  `host.set_translation(..)`). The change is visible to every system that runs later in the same stage.
- **Queued**: anything that pushes a `ComponentCommand` (spawn, destroy, impulses, scene loads, sounds,
  saves, network). The engine applies queued commands, in order, when the stage finishes. Spawn calls
  return the new `ObjectId` right away, but the object exists only once the stage ends.

### Targets

Methods that act on another object take `impl Into<ObjectRef>`: an `ObjectRef` field from your
component, or a plain `ObjectId`. An unset, deleted or hidden target is not an error: reads return `None`,
writes return `false` or do nothing.

## Moving things

`Transform` has three parts, **local** to the parent: `translation`, `rotation`, `scale`. For an object
with no parent, local equals world. Pick the right space for the job:

| Want to … | Call | Space | Timing |
|---|---|---|---|
| Read my position | `host.translation()` / `host.world_position()` | local / world | immediate |
| Move me | `host.set_translation(v)` / `host.set_world_position(v)` | local / world | immediate |
| Turn me | `host.set_rotation(q)` / `host.set_world_rotation(q)` | local / world | immediate |
| Read my full world pose | `host.self_transform()` | world | immediate |
| Read another object's pose | `host.transform_of(target)`, `host.position_of(target)`, `host.matrix_of(target)` | world | immediate |
| Move another object | `host.set_world_position_of(target, v)`, `host.set_world_transform_of(target, Some(pos), Some(rot))` | world | immediate |
| Change another object's local pose | `host.set_local_transform(target, translation, rotation, scale)` (each `Option`) | local | immediate |
| Slide a character through the world | `host.move_character(delta)` | world | queued |

Read a position, change it, write it back. Writing a world position to a parented object's *local*
translation is the classic mistake; `set_world_position` converts through the parent chain for you:

```rust
fn update(&mut self, host: &mut EcsMoveHost<'_, '_>) {
    let direction = host.input.axis2("Move");
    let step = Vec3::new(direction.x, 0.0, -direction.y) * self.speed * host.dt;
    let position = host.translation() + step;
    host.set_translation(position);
}
```

`Transform` itself has `forward()` (local −Z in world space), `right()`, `up()` and `matrix()`.

**Frame-rate independent motion.** Multiply speeds by `host.dt`. To ease toward a target, close a share
of the gap each frame with `1 − e^(−k·dt)`, which gives the same result at any frame rate (see the
[smooth follow recipe](#smooth-follow-camera)):

```rust
let blend = 1.0 - (-sharpness * host.dt).exp();
host.set_world_position(here.lerp(wanted, blend));
```

**Moving physical things.** A character with a `Character` component moves with `move_character(delta)`
(it slides along walls and climbs steps; gravity is yours to apply, and `host.grounded()` says whether it
touched the ground). Rigid bodies move through forces and impulses (see [Physics](#physics)). Writing
the transform of a dynamic or fixed body teleports it to that pose; a kinematic body follows its
transform every physics step (and pushes the dynamic bodies it meets), which is how platforms and doors
are moved from code.

The `translation()`, `set_translation()`, `world_position()` and similar methods come from the
`MoveHost` trait: `use zestengine_core::MoveHost;`.

**The camera** is an object with a `Camera` component; `host.set_active_camera(target)` makes it the one
that renders.

## Finding and reading other objects

| Want to … | Call | Returns |
|---|---|---|
| My own id | `host.self_id()` | `ObjectId` |
| Read a component | `host.get::<T>(target)` / `host.get_self::<T>()` | `Option<Ref<T>>` |
| Resolve an id to the runtime entity | `host.entity_of(target)` | `Option<Entity>` (None if hidden) |
| List objects that carry a component | `host.objects_with::<T>()` | `Vec<ObjectId>` in scene order |
| Find an object by name | `host.find_object("Player")` | first match in scene order |
| Is it active? | `host.is_active(target)` | `bool` |
| Pick a spawn location | `host.spawn_point("Red Team")`, `host.spawn_point_for(tag, slot)` | `Option<Transform>` |

Prefer `ObjectRef` fields over names: names are cosmetic, need not be unique, and cost a scan. `get`
returns a checked borrow, so drop it before you edit the same component. Lookups find **inactive**
objects too (`objects_with`, `find_object`, `get`): check `host.is_active(target)` when it matters.

## Editing other objects

| Want to … | Call | Timing |
|---|---|---|
| Change a component in place | `host.edit::<T>(target, \|c\| c.hp -= 10.0)` | immediate |
| Switch an object on/off | `host.set_active(target, false)` | queued |
| Edit a material parameter | `host.modify_material(target, slot, \|m\| m.emission_intensity = 2.0)` | queued |
| Read a material | `host.material_params(target, slot)` | immediate |
| Fire particles | `host.emit_particles(target, 40)` | immediate |
| Steer a nav agent | `host.set_destination(target, pos)`, `host.stop_agent(target)` | immediate |
| Write a synced variable | `host.set_net_var(target, "key", value)` | immediate locally, then replicated |

`edit` returns `true` if it found the object and the component. The closure of `modify_material` runs
later, so it must own what it uses (`move`). `modify_material` edits the scene's **shared** material
entry, so every object that uses that material changes with it; give an object its own material
(a `.material` file per object, or `PerInstance` parameters) when only one should change.

## Spawning and destroying

| Want to … | Call | Notes |
|---|---|---|
| Spawn a `.prefab` | `host.spawn_prefab("prefabs/enemy.prefab", pos, rot)` | path relative to the project |
| Spawn a registered entity | `host.spawn_entity("Crate", pos, rot)` | see [Entities](ECS.md#entities) |
| Clone a scene object | `host.instantiate(original, pos, rot)` | returns `Option<ObjectId>`; the clone is a new root |
| Spawn on every peer | `host.net_spawn("prefabs/bullet.prefab", pos, rot)`, `net_spawn_server`, `net_clone` | see [Networking](#networking) |
| Remove an object and its children | `host.destroy(target)` / `host.destroy_self()` | queued |
| Hide without removing | `host.set_active(target, false)` | queued |

All of these are queued. The spawn calls return the new `ObjectId` immediately so you can store it; the
object exists, runs its `Start` systems and appears from the next stage on.

A common pattern is a disabled template object in the scene that you clone and switch on:

```rust
if let Some(id) = host.instantiate(self.bullet_template, muzzle, rotation) {
    host.set_active(id, true);
}
```

`instantiate` keeps the original's enabled state and scale, and returns an id even if the original no
longer exists (that id then never resolves).

**Initial velocity.** A new object's physics body is created at the next physics sync, and
`add_impulse` / `set_velocity` do nothing for an object without a body (and only affect *dynamic* bodies).
So give a spawned projectile its speed from its own system on its first `Update` or `FixedUpdate`, not from the spawner in
the same stage.

## Physics

Queries are immediate; pushes are queued.

| Want to … | Call | Timing |
|---|---|---|
| Cast a ray | `host.raycast(origin, dir, max_dist)` → `Option<RayHit>` | immediate |
| Cast with a filter | `host.raycast_filtered(origin, dir, max_dist, &RayFilter { layer_mask, include_triggers, exclude })` | immediate |
| Find objects in a sphere | `ctx.services.physics.unwrap().overlap_sphere(center, radius, &filter)` | immediate |
| Read a body's velocity | `ctx.services.physics.unwrap().velocity(id)` | immediate |
| Ask whether a character is grounded | `host.grounded()` | immediate |
| Push a body | `ctx.commands.push(ComponentCommand::AddForce { id, force })`, `host.add_impulse(target, impulse)` | queued |
| Set velocity | `host.set_velocity(target, v)` | queued |
| Twist a body | `ctx.commands.push(ComponentCommand::AddTorque { id, torque })` | queued |
| Drive a joint motor | `ctx.commands.push(ComponentCommand::SetJointMotor { id, speed, max_force })` | queued |
| 2D ray | `host.raycast2d(origin, dir, max_dist)`, `raycast2d_filtered` | immediate |

A `RayHit` has `object`, `point`, `normal` and `distance`. `raycast` ignores trigger colliders and the
caster's own colliders; the filter's `layer_mask` has one bit per layer. Physics runs at a fixed 60 Hz:
continuous forces belong in `FixedUpdate`, one-off impulses can go anywhere. 2D physics lives in the same
queries (`overlap_circle2d`, `circle_cast2d`, `box_cast2d`, … on `PhysicsQuery`).

If a system reads `services.physics` and there is no physics world (a test, a headless tool), it is
`None`; `host.raycast` then returns `None` too.

**Contacts** (collisions and trigger overlaps) are not polled: they arrive as scene events in the
`Events` stage. See [Scene events](ECS.md#scene-events-contacts-and-animation-markers).

## Input

`ctx.input` / `host.input` is a snapshot of named actions:

```rust
host.input.down("Fire")       // held
host.input.pressed("Jump")    // went down this frame
host.input.released("Fire")   // went up this frame
host.input.axis("Throttle")   // -1..1
host.input.axis2("Move")      // Vec2: x right, y forward
```

Default actions: `Move`, `Look`, `Jump`, `Sprint`, `Crouch`, `Fire`, `Interact`, `Grab`, `Voice` on
keyboard-and-mouse and gamepad; VR adds hand actions. Players can rebind them; an action that does not
exist reads as "not pressed", never an error. See [Input](ECS.md#input) in the ECS guide.

Rebinding from game code (a controls menu) goes through queued input commands:

| Call | Does |
|---|---|
| `host.input_bindings()` | The live `Bindings` (all schemes), if available |
| `host.control_scheme()` | The scheme currently in use |
| `host.rebind_with(scheme, action, slot, index, source, policy)` | Rebind one binding |
| `host.tune_action(scheme, action, tuning)` | Change sensitivity, invert Y, deadzone |
| `host.reset_scheme_bindings(scheme)` | Back to defaults |
| `host.capture_next_input(kind, device)` / `captured_input()` / `is_capturing_input()` | "Press a key to bind" |
| `host.binding_conflicts(scheme)` | Actions that share an input |

The built-in `Controls Menu` component does all of this without code.

## Screen pointer and UI

| Want to … | Call |
|---|---|
| Game view size in pixels | `host.screen_size()` |
| Pointer position (top-left origin) | `host.pointer_position()` → `Option<Vec2>` |
| Ray under the pointer | `host.pointer_ray()` → `Option<(origin, direction)>`; `host.screen_ray(pixel)` for any pixel |
| Project a world point to the screen | `host.world_to_screen(position)` |
| Is the pointer over a UI element? | `host.pointer_over_ui()`: skip world clicks when true |
| Was a UI button clicked? | `host.ui_clicked(button)` (reported the frame after the click) |
| Escape / gamepad back pressed? | `host.ui_cancel_pressed()` |
| Is a text field being edited? | `host.ui_text_editing()`: skip gameplay input when true |

UI is built from components (`UI Canvas`, `UI Rect`, `UI Panel`, `UI Image`, `UI Text`, `UI Button`,
`UI Toggle`, `UI Slider`, `UI Text Field`, `UI Progress Bar`, `UI Pause Menu`), laid out in the **UI
Editor** tab. Gameplay reads and writes them like any other component:

```rust
host.edit::<UiText>(self.score_label, move |t| t.text = format!("Score {score}"));
if host.ui_clicked(self.play_button) { host.load_scene("scenes/level1.scene"); }
```

Buttons also have an **On click** list that needs no code (load a scene, show/hide/toggle an object,
quit).

## Audio

| Want to … | Call | Timing |
|---|---|---|
| One-shot sound at a position | `host.play_sound_at("audio/boom.ogg", pos, volume)` | queued |
| One-shot, not positional | `ctx.commands.push(ComponentCommand::PlaySound { clip, position: None, volume })` | queued |
| Start / stop an `Audio Source` | `ctx.commands.push(ComponentCommand::PlayAudio(id))` / `StopAudio(id)` | queued |
| Set a mixer bus volume (linear gain, 0 is silent) | `host.set_bus_volume("music", 0.5)` | queued |
| Mute a bus | `ctx.commands.push(ComponentCommand::SetBusMuted { bus, muted })` | queued |

Clip paths are relative to the project (`.wav`, `.ogg`, `.flac`, `.mp3`). Put an `Audio Listener` on the
camera or the player's head. Spatial sources (`Audio Source`) render through Steam Audio: HRTF,
distance rolloff, directivity, occlusion and reflections.

## Animation

Animation state lives in the `Animator` component; edit it like any component:

```rust
host.edit::<Animator>(self.body, |a| {
    a.set_float("Speed", speed);          // drives blend trees and transitions
    a.set_bool("Grounded", grounded);
    a.set_trigger("Jump");                // consumed by the transition it fires
});
host.edit::<Animator>(self.body, |a| a.play("Run", 0.2));      // cross-fade a clip over 0.2 s
host.edit::<Animator>(self.body, |a| a.play_state("Die", 0.1)); // force a controller state
```

Read state back with `host.get::<Animator>(target)`: `is_playing(clip)`, `finished()`,
`current_state(layer)`, `is_in_state(layer, state)`, `get_float` / `get_bool` / `get_int`. Clip event
markers arrive as `SceneEvent::Animation` in the `Events` stage and as `AnimationEvent` broadcasts;
every controller state change broadcasts `AnimatorStateChanged`. As a shortcut for movement code,
`host.set_animator_bool(name, value)` sets a bool on the object's own Animator.

## Navigation

Add a `NavMesh Surface` (baked from colliders when play starts) and give characters a `Nav Agent`:

```rust
host.set_destination(self.enemy, player_position);   // immediate: edits the agent
host.stop_agent(self.enemy);
let walkable = host.nearest_walkable(point);          // Option<Vec3>
let path = ctx.services.nav.and_then(|nav| nav.find_path(from, to)); // Option<Vec<Vec3>>
host.rebake_navmesh();                                // queued: after the level changed
```

## Scenes saves and settings

| Want to … | Call | Timing |
|---|---|---|
| Switch scene | `host.load_scene("scenes/level2.scene")` | queued; the host swaps after the stage |
| Start loading in the background | `host.preload_scene(path)`; a later `load_scene` is then instant | queued |
| Stream a room in / out | `host.load_scene_additive(path)` / `host.unload_scene(path)` | queued |
| Carry an object over a scene change | `host.keep_on_scene_change(target, true)` | queued |
| Quit | `host.quit()` | queued |
| Store a value | `host.save_value("level", 3_i64)`, `remove_save_value(key)` | queued |
| Write / read a slot file | `host.write_save("slot1")`, `host.load_save("slot1")` | queued; a load takes effect next pass |
| Read saved data | `host.save_data()` → `Option<&SaveGame>` with `int`, `float`, `bool`, `str`, `vec3` | immediate |
| Translate a string | `host.tr("menu.play")`, `host.language()`, `host.set_language("fr")` | tr/language immediate; set queued |
| Lock the cursor | `host.set_cursor_locked(true)` | queued |
| Pause / slow-mo | `host.set_time_scale(0.0)` … `1.0` | queued |

`SaveValue` is `Bool`, `Int`, `Float`, `Str` or `Vec3`. Saves go to the user data folder in a built game.
Localisation tables are `localization/*.loc` files. A scene with a `Scene Portal` component streams and
switches with no code at all: a trigger collider, the target scene and a mode.

## Networking

Networking is built in: an offline game and a multiplayer game run the same systems.

| Want to … | Call |
|---|---|
| Am I in a session / the host / a client? | `host.connected()`, `host.is_server()`, `host.is_client()` |
| Who am I, who is here? | `host.local_peer()`, `host.peers()` |
| Do I control this object? | `host.has_authority(id)`: its owner, the host for unowned objects, always true offline |
| Is another peer driving this object? | `host.driven_remotely()`: skip local input when true |
| Spawn on every peer | `host.net_spawn(prefab, pos, rot)`; as server-owned: `net_spawn_server`; clone: `net_clone` |
| Despawn on every peer | `host.net_despawn(target)` |
| Write a synced variable | `host.set_net_var(target, "key", NetValue::Int(3))` / `set_net_var_self`. Returns false without permission |
| Read a synced variable | `host.net_var(target, "key")` / `net_var_self("key")`; `net_var_changes()` lists what changed |
| Send a remote call | `host.rpc("Explode", args, RpcTarget::All)` (reliable), `rpc_unreliable(..)`, or `rpc_self(..)` for the object's own RPCs; `send_rpc(object, name, args, target, reliable)` is the general form |
| Receive remote calls | `host.rpcs()`, `host.rpcs_named("Explode")`, `host.rpcs_for_self()` (offline, an RPC addressed to yourself is delivered locally) |
| Who owns this object? | `host.owner_of(target)`; `has_authority_of(target)` |
| Claim / give up / hand over an object | `host.request_ownership_of(target)`, `release_ownership_of(target)`, `transfer_ownership(target, peer)` |
| Session quality | `host.net_rtt()` / `net_rtt_ms()`, `net_quality()`, `net_events()`, `peer_name(id)` |
| Host a session, join, leave | `host.net_host(port)`, `host.net_join("1.2.3.4:7777")`, `host.net_disconnect()`, `host.net_load_scene(path)` (host switches every peer) |
| Remove a player | `host.net_kick(peer, reason, ban)` (host only) |

`NetValue` is `Bool`, `Int`, `Float`, `Vec3`, `Quat`, `Str` or `Bytes`. `RpcTarget` is `All`, `Others`,
`Server`, `Owner` or `Peer(id)`. Components can be restricted to one side with `TypedComponent::NET_ROLE`
(a `Server` component is stripped from players, a `Client` one from a dedicated server). Session commands
(`NetHost`, `NetJoin`, `NetDisconnect`, `NetKick`, …) are applied by the host application, not the play
session, which is why they are queued like every other command.

**Things that surprise people.**

- `has_authority(id)` is true offline, but on a *client* it is false for any object with no recorded
  owner, including ordinary non-networked scene objects (an unowned object belongs to the host). Guard
  local-only objects with `driven_remotely()` instead, which checks that the object is actually networked.
- `i_am_host()` is false offline (it needs a session); `has_authority` is true. They answer different questions.
- A synced variable another peer wrote is announced as an event at the start of the frame, but the
  component is updated at the end of it: in the frame you see the change, `net_var(..)` still returns the
  old value.
- The host cannot `net_despawn` an object a client owns (it fails the authority check): take the object
  with `transfer_ownership` first, or have the owner despawn it.
- A self-initiated `net_disconnect()` does not deliver a `Disconnected` event to your own systems.
- `NetValue` has no 64-bit float: send a time or large number as `Bytes` (or two ints) to keep precision.

**Lag compensation.** For hit checks on a server, `host.ray_cast_rewound(shooter, origin, dir, max_dist)`
casts against where the targets were when the shooter fired, and `ray_cast_at(time, …)` against any
recent moment (`net_time()` is the current simulation time). The rewind window is the session's configured maximum (default 0.25 s, hard cap 0.9 s).

### Content packages

`.zestenginepak` packages carry worlds, avatars and props that can be loaded at run time by path, URL or
content id. The calls are queued; progress and results come back as events:

```rust
let request = host.load_content("https://example.com/forest.zestenginepak");
let (request, root) = host.spawn_content("chair.zestenginepak", position, rotation);
host.spawn_avatar(self.player, "avatars/robot.zestenginepak");
host.enter_world(world_id);
host.unload_content(id);
for event in host.content_events() { /* progress, loaded, spawned, world entered, failed */ }
```

## Time

| Value | Meaning |
|---|---|
| `host.dt` | Seconds this frame × time scale. `0` while paused. In `FixedUpdate`, the fixed step (1/60). |
| `host.unscaled_dt` | Real frame time; use it for UI and pause menus. A single frame is clamped to 0.25 s. |
| `host.time` | Scaled seconds since Play started. |
| `host.water_time` | The shared water clock (networked clients agree on it). |
| `host.time_scale()` | The current scale (1 normal). |

## Events

Broadcasting between systems, contacts and animation markers, and action bindings are explained in
[Events](ECS.md#events). The engine's own events are ordinary types you can read from any system with
`host.events::<T>()`:

| Event | Emitted when |
|---|---|
| `DamageEvent { target, source, amount, point }` | A weapon hit something |
| `DeathEvent { object }` | A `Health` reached zero |
| `ScoreEvent { points }` | A target dummy was knocked down |
| `AnimationEvent { object, name, args }` | An animation clip marker fired |
| `AnimatorStateChanged { object, layer, from, to }` | An animator controller changed state |
| `ActionEvent { name, source, instigator }` | A binding ran the built-in *Emit Event* action |
| `NetRpc { from, object, name, args }` | A remote call arrived (also through `rpcs_for_self`) |

## Command reference

Systems queue [`ComponentCommand`](https://lemonxah.github.io/zestengine/docs/api/zestengine_core/enum.ComponentCommand.html)s;
`EcsMoveHost` has a helper for the common ones, and any command can be pushed with
`ctx.commands.push(..)`. The play session applies most itself; the rest are handed to the host
application (the window, the network session, content loading).

| Command | Helper | Applied by |
|---|---|---|
| `SpawnPrefab`, `SpawnEntity`, `Instantiate`, `Destroy`, `SetActive` | `spawn_prefab`, `spawn_entity`, `instantiate`, `destroy`, `set_active` | play session |
| `SetLocalTransform`, `SetWorldTransform` | (edit the transform directly instead) | play session |
| `Modify { id, type_id, f }` | (prefer `edit`) | play session |
| `ModifyMaterialParams`, `AssignMaterial` | `modify_material` | play session |
| `AddForce`, `AddImpulse`, `AddTorque`, `SetVelocity`, `SetJointMotor`, `MoveCharacter` | `add_impulse`, `set_velocity`, `move_character` | play session (physics) |
| `RebakeNavMesh` | `rebake_navmesh` | play session |
| `PlaySound`, `PlayAudio`, `StopAudio`, `SetBusVolume`, `SetBusMuted` | `play_sound_at`, `set_bus_volume` | play session (audio) |
| `SaveSet`, `SaveRemove`, `SaveWrite`, `SaveLoad`, `SetLanguage` | `save_value`, `remove_save_value`, `write_save`, `load_save`, `set_language` | play session |
| `SetTimeScale` | `set_time_scale` | play session |
| `Emit` | `ctx.emit(event)` | play session (event bus) |
| `InvokeAction`, `FireActions` | (action bindings) | play session |
| `NetSpawn`, `NetDespawn`, `NetSetVar` | `net_spawn`, `set_net_var` | play session (replication) |
| `LoadScene`, `PreloadScene`, `LoadSceneAdditive`, `UnloadScene`, `KeepOnSceneChange` | `load_scene`, … | host application |
| `SetActiveCamera` | `set_active_camera` | play session |
| `SetCursorLocked`, `SetResolution`, `SetVsync`, `SetShadowResolution`, `Quit` | `set_cursor_locked`, `quit` | host application |
| `NetHost`, `NetJoin`, `NetDisconnect`, `NetKick`, `NetLoadScene`, `NetMessage`, `NetRpc`, `RequestOwnership`, `ReleaseOwnership`, `TransferOwnership` | `rpc_self`, `request_ownership_of` | host application (network) |
| `Content(..)` | (user-generated content: worlds, avatars, props) | host application |
| `Input(..)` | `input_command`, `rebind_with`, `tune_action` | host application |
| `Body(..)`, `CalibrateTrackers`, `ClearTrackerCalibration`, `SetOscFaceTracking` | (VR body and face tracking menus) | host application |
| `WaterImpact` | (water effects) | play session |

## Recipes

### Smooth follow camera

Run in `LateUpdate`, after the target has moved this frame.

```rust
#[derive(Serialize, Deserialize)]
pub struct SmoothFollow {
    pub target: ObjectRef,
    pub offset: [f32; 3],
    pub sharpness: f32,
}

impl SmoothFollow {
    fn update(&mut self, host: &mut EcsMoveHost<'_, '_>) {
        let Some(goal) = host.position_of(self.target) else { return };
        let wanted = goal + Vec3::from(self.offset);
        let here = host.world_position();
        // 1 - e^(-k·dt) is the share of the gap to close this frame: the result is
        // the same whether the game runs at 30 or 240 frames per second.
        let blend = 1.0 - (-self.sharpness * host.dt).exp();
        host.set_world_position(here.lerp(wanted, blend));
    }
}

registry.register_system_for::<SmoothFollow>("game::smooth_follow", Stage::LateUpdate, |world, ctx| {
    run_ordered(world, ctx, SmoothFollow::update)
});
```

### Click to select

```rust
#[derive(Default, Serialize, Deserialize)]
pub struct ClickToSelect {
    #[serde(skip)]
    pub selected: Option<ObjectId>,
}

impl ClickToSelect {
    fn update(&mut self, host: &mut EcsMoveHost<'_, '_>) {
        if !host.input.pressed("Fire") || host.pointer_over_ui() { return; }
        let Some((origin, direction)) = host.pointer_ray() else { return };
        self.selected = host.raycast(origin, direction, 500.0).map(|hit| hit.object);
    }
}
```

### Pause menu

`set_time_scale(0.0)` stops `dt` (and physics), while systems keep running, so a pause menu keeps
working on `unscaled_dt` and UI events.

```rust
#[derive(Default, Serialize, Deserialize)]
pub struct PauseToggle {
    #[serde(skip)]
    pub paused: bool,
}

impl PauseToggle {
    fn update(&mut self, host: &mut EcsMoveHost<'_, '_>) {
        if host.ui_cancel_pressed() {
            self.paused = !self.paused;
            host.set_time_scale(if self.paused { 0.0 } else { 1.0 });
            host.set_cursor_locked(!self.paused);
        }
    }
}
```

### More

The [ECS guide](ECS.md) holds the full recipes for taking damage (events), pickups (contacts), doors
(state and actions), spawners (entities), timers, a poison zone (two components) and a ray gun
(physics). The production versions of all of these ship in `crates/zestengine-core/src/kit/`: read
`combat.rs` (health, hitscan weapons), `character.rs` (first and third person controllers),
`topdown.rs` (click-to-move, interactables) and `rts.rs` (selection and formations).
