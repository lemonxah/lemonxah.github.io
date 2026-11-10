# ECS cheat sheet

The whole model on one page. Each row links to the guide section that explains it. New to this? Start
with the [tutorial](ecs-tutorial.md).

## The model in five lines

| Concept | Rule |
|---|---|
| **Component** | A struct with data. Implements `TypedComponent`. `NAME` never changes. |
| **System** | A `fn(&SystemWorld, &mut SystemContext)`. Finds components by query, edits them. No captured state. |
| **Stage** | When a system runs: `Start`, `FixedUpdate`, `Update`, `Gameplay`, `LateUpdate`, `Events`. |
| **Command** | A request that leaves component data (spawn, destroy, sound, scene load). Applied when the stage ends. |
| **Event** | `ctx.emit(x)` in frame *N*, `ctx.events::<X>()` in frame *N + 1*. |

## Skeleton: component, system, registration

```rust
use serde::{Deserialize, Serialize};
use zestengine_core::ecs::{ObjectContext, Stage, run_ordered};
use zestengine_core::{ComponentRegistry, MotionContext, TypedComponent};

#[derive(Serialize, Deserialize)]
pub struct Spinner {
    pub degrees_per_second: f32,   // saved in the scene, editable in the inspector
    #[serde(skip)]
    pub elapsed: f32,              // runtime only
}

impl Default for Spinner {
    fn default() -> Self { Self { degrees_per_second: 45.0, elapsed: 0.0 } }
}

impl TypedComponent for Spinner {
    const NAME: &'static str = "Spinner";
}

impl Spinner {
    fn update(&mut self, obj: &mut ObjectContext<'_, '_>) {
        self.elapsed += obj.dt;
        // obj.translation(), obj.set_translation(..), obj.input, obj.emit(..), obj.destroy_self() ...
    }
}

pub fn register(registry: &mut ComponentRegistry) {
    registry.register_ecs::<Spinner>();
    registry.register_system_for::<Spinner>("game::spinner", Stage::Update, |world, ctx| {
        run_ordered(world, ctx, Spinner::update)
    });
}
```

Registration variants: [`register_system`, `register_system_for::<T>`, `register_system_if`](ECS.md#systems).
Use `register_system_for::<T>` by default: it costs nothing while no enabled `T` exists.

## Which stage?

| I am writing … | Stage |
|---|---|
| Setup for a new instance (cache a position, spawn children) | `Start` (guard with a flag; see [Timers and state](ECS.md#timers-and-state)) |
| Continuous forces, anything tied to the physics rate | `FixedUpdate` (`dt` = 1/60) |
| Movement, controllers, AI steering, input handling | `Update` |
| Weapons, damage, pickups, health | `Gameplay` |
| Cameras following a target, HUD that mirrors state | `LateUpdate` |
| Reacting to collisions, trigger overlaps, animation markers | `Events` |

Details: [Stages](ECS.md#stages).

## Immediate or queued?

| Immediate (visible to later systems this stage) | Queued (applied when the stage ends) |
|---|---|
| Reads: `obj.get::<T>(t)`, `obj.position_of(t)`, `obj.raycast(..)` | `obj.spawn_entity(..)`, `spawn_prefab`, `instantiate` (the id returns at once, the object exists next stage) |
| `obj.edit::<T>(t, \|c\| ..)` | `obj.destroy(t)`, `obj.destroy_self()`, `obj.set_active(t, ..)` |
| `obj.set_translation(..)`, `set_world_position(..)` | `obj.add_impulse(..)`, `set_velocity(..)`, `move_character(..)` |
| | `obj.play_sound_at(..)`, `load_scene(..)`, `save_value(..)`, `net_spawn(..)` |

An event you emit is **not** visible to you in the same frame. See [Commands](ECS.md#commands) and the
[Engine API Guide](ENGINE_API.md#immediate-and-queued).

## I want to …

| I want to … | Write | Where |
|---|---|---|
| Move the object I am on | `obj.set_translation(obj.translation() + step * obj.dt)` | [Moving things](ENGINE_API.md#moving-things) |
| Move it in world space | `obj.set_world_position(v)` | [Moving things](ENGINE_API.md#moving-things) |
| Read player input | `obj.input.pressed("Fire")`, `down`, `released`, `axis`, `axis2("Move")` | [Input](ECS.md#input) |
| Point at another object | an `ObjectRef` field, then `obj.position_of(self.target)` | [Talking to other objects](ECS.md#talking-to-other-objects) |
| Read or change another object's component | `obj.get::<T>(t)`, `obj.edit::<T>(t, \|c\| ..)` | [Talking to other objects](ECS.md#talking-to-other-objects) |
| Find objects | `obj.objects_with::<T>()`, `obj.find_object("Player")` | [Finding and reading](ENGINE_API.md#finding-and-reading-other-objects) |
| Broadcast something happened | `obj.emit(MyEvent { .. })` | [Broadcast events](ECS.md#broadcast-events) |
| React to something that happened | `ctx.events::<MyEvent>()` / `obj.events::<MyEvent>()` | [Broadcast events](ECS.md#broadcast-events) |
| React to a collision or trigger | match `SceneEvent::Contact { .. }` in `Stage::Events` | [Scene events](ECS.md#scene-events-contacts-and-animation-markers) |
| Spawn a registered entity | `obj.spawn_entity("Crate", pos, rot)` | [Entities](ECS.md#entities) |
| Spawn a prefab | `obj.spawn_prefab("prefabs/enemy.prefab", pos, rot)` | [Spawning and destroying](ECS.md#spawning-and-destroying) |
| Remove an object | `obj.destroy_self()` / `obj.destroy(t)` | [Spawning and destroying](ECS.md#spawning-and-destroying) |
| Cast a ray | `obj.raycast(origin, dir, max)` → `Option<RayHit>` | [Physics and contacts](ECS.md#physics-and-contacts) |
| Push a rigid body | `obj.add_impulse(t, v)` | [Physics](ENGINE_API.md#physics) |
| Play a sound | `obj.play_sound_at("audio/pop.ogg", pos, 1.0)` | [Audio](ENGINE_API.md#audio) |
| Change UI text | `obj.edit::<UiText>(id, move \|ui\| ui.text = text)` | [Showing state in the UI](ECS.md#showing-state-in-the-ui) |
| Pause or slow time | `obj.set_time_scale(0.0)` | [Pause menu](ENGINE_API.md#pause-menu) |
| Switch scene | `obj.load_scene("scenes/level2.scene")` | [Scenes, saves and settings](ENGINE_API.md#scenes-saves-and-settings) |
| Make a function callable from the editor | `actions()` / `invoke_action(..)` on the component | [Actions and properties](ECS.md#actions-and-properties) |
| Test a system | `SceneWorld` + `registry.run_systems(..)` | [Testing systems](ECS.md#testing-systems) |

## Worked examples

Every one of these is in the guides with complete code, and is compiled and run by the engine's tests.

| Example | Shows | Read |
|---|---|---|
| `Rotator` | A component and its first system | [Systems](ECS.md#systems) |
| `PlayerMover` | `run_ordered`, input, `dt` | [The comfortable way](ECS.md#the-comfortable-way-run_ordered-and-objectcontext) |
| `Hitpoints`, `Hit`, `Died` | Events between systems, death announced once | [Broadcast events](ECS.md#broadcast-events) |
| `Coin`, `Collector`, `Collected` | Contacts and triggers | [Scene events](ECS.md#scene-events-contacts-and-animation-markers), and the [tutorial](ecs-tutorial.md) |
| `Lifetime` | A timed self-destruct | [Spawning and destroying](ECS.md#spawning-and-destroying) |
| `CrateSpawner` + `Crate` entity | Entities, spawning on a timer | [Entities](ECS.md#entities) |
| `Follower` | `ObjectRef`, reading another object | [Talking to other objects](ECS.md#talking-to-other-objects) |
| `PoisonZone` | Nested queries over two components | [Talking to other objects](ECS.md#talking-to-other-objects) |
| `Laser` | Raycasts, impulses, sounds | [Physics and contacts](ECS.md#physics-and-contacts) |
| `Door` | `Start`, state, actions bound from the editor | [Timers and state](ECS.md#timers-and-state), [Actions](ECS.md#actions-and-properties) |
| `ScoreBoard` | Mirroring state onto UI in `LateUpdate` | [Showing state in the UI](ECS.md#showing-state-in-the-ui) |
| `SmoothFollow` | Frame-rate independent easing | [Smooth follow camera](ENGINE_API.md#smooth-follow-camera) |
| `ClickToSelect` | Pointer rays, skipping clicks on UI | [Click to select](ENGINE_API.md#click-to-select) |
| `PauseToggle` | Time scale, cursor lock | [Pause menu](ENGINE_API.md#pause-menu) |

For larger, production-quality versions (health, hitscan weapons, character controllers, click-to-move,
RTS selection and formations) read the gameplay kit in the engine repository:
[`crates/zestengine-core/src/kit/`](https://github.com/lemonxah/zestengine/tree/main/crates/zestengine-core/src/kit).

## When something goes wrong

| Symptom | Usual cause |
|---|---|
| Panic: `… already borrowed` | Two borrows of one component type, one mutable. |
| Panic: `structural ECS access while component views are borrowed` | You tried to spawn, remove or despawn inside a system. Queue a command. |
| System never runs | Not registered, no enabled `T` for `register_system_for::<T>`, or the object is inactive. |
| Event never arrives | It is readable the *next* frame, never the same frame. |
| Object in the wrong place under a parent | A world position written to the local `Transform`. Use `set_world_position`. |

The full list is [Common mistakes](ECS.md#common-mistakes).
