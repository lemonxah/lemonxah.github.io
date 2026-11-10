# ECS tutorial: a coin collector

This tutorial builds one small feature end to end: the player walks into coins, the coins vanish, and a
score on screen goes up. It uses every part of the ECS once (components, systems, events, contacts,
registration, the editor, a test), so it is the quickest way to see how the pieces fit before reading
the [ECS Guide](ECS.md) in full.

The code on this page was compiled and run against `zestengine-core`, including the test at the end.

**What you will write**

| Piece | Kind | Job |
|---|---|---|
| `Collector` | component | Marks objects that can pick coins up (the player). |
| `Coin` | component | Marks a pickup and says what it is worth. |
| `ScoreBoard` | component | Remembers the score and writes it into a `UI Text`. |
| `Collected` | event | "Something was picked up." Connects the coin to the score. |
| `game::coin_pickup` | system | Notices a player touching a coin. Runs in the `Events` stage. |
| `game::score_board` | system | Adds up `Collected` events and updates the text. Runs in `LateUpdate`. |

Notice what is *not* there: the coin never talks to the score board. The coin announces what happened,
the score board listens. Either side can change or be removed without touching the other.

## Before you start

You need a project with a `plugins/components` crate (**File → New Project** creates one, see
[Getting started](getting-started.md)). All of the code below goes in one new file,
`plugins/components/src/coin_collector.rs`.

## Step 1: the data

Components are plain structs that implement `TypedComponent`. They must be `Serialize + Deserialize +
Default`.

```rust
use serde::{Deserialize, Serialize};
use zestengine_core::ecs::{ContactPhase, ObjectContext, SceneEvent, Stage, run_ordered};
use zestengine_core::{ComponentRegistry, MotionContext, ObjectId, TypedComponent, UiText};

/// Marker: objects that can pick coins up. It has no data; its presence is the data.
#[derive(Default, Serialize, Deserialize)]
pub struct Collector {}

impl TypedComponent for Collector {
    const NAME: &'static str = "Collector";
}

/// A pickup worth `value` points.
#[derive(Serialize, Deserialize)]
pub struct Coin {
    pub value: u32,
}

impl Default for Coin {
    fn default() -> Self { Self { value: 1 } }
}

impl TypedComponent for Coin {
    const NAME: &'static str = "Coin";
}

/// Shows the score in this object's `UiText`.
#[derive(Default, Serialize, Deserialize)]
pub struct ScoreBoard {
    #[serde(skip)]
    pub score: u32,
}

impl TypedComponent for ScoreBoard {
    const NAME: &'static str = "Score Board";
}
```

Three things to notice:

- **`NAME` is permanent.** It is how the Add Component menu, the `.scene` file and event bindings refer
  to the type. Pick it once.
- **`value` is saved; `score` is not.** Everything without `#[serde(skip)]` is written to the scene and
  shown in the inspector, so a designer can make a 10-point coin. `score` is scratch state that only
  exists while playing, so it is `#[serde(skip)]`.
- **`Collector` is empty on purpose.** A "tag" component is the ECS way to say *this object is a kind of
  thing*. Systems then ask "does the other object carry a `Collector`?".

> **Imports.** `MotionContext` looks unused, but it is the trait that provides `self_id()` and the transform
> helpers on `obj`. If the compiler says "no method named `self_id`", this import is missing.

## Step 2: the event

An event is any `'static` type. Declare it next to the code that emits it:

```rust
/// Event: `by` picked up something worth `value`.
pub struct Collected {
    pub by: ObjectId,
    pub value: u32,
}
```

It refers to objects by `ObjectId`, the stable UUID every object has and scenes save, rather than by a
runtime handle.

## Step 3: the pickup system

When two colliders touch, the engine reports a contact to **both** objects during the `Events` stage. The
system looks for contacts where *this coin* was entered by something that is a `Collector`:

```rust
registry.register_system_for::<Coin>("game::coin_pickup", Stage::Events, |world, ctx| {
    let contacts = ctx.services.scene_events;
    run_ordered(world, ctx, |coin: &mut Coin, obj| {
        let me = obj.self_id();
        for contact in contacts {
            if let SceneEvent::Contact { object, other, trigger: true, phase: ContactPhase::Enter, .. } = contact
                && *object == me
                && obj.get::<Collector>(*other).is_some()
            {
                obj.emit(Collected { by: *other, value: coin.value });
                obj.destroy_self();
            }
        }
    })
});
```

Reading it line by line:

- `register_system_for::<Coin>` runs the system only while at least one enabled `Coin` exists, so a level
  without coins pays nothing.
- `run_ordered` calls the closure once per active `Coin`, in scene order, with the component and an
  `ObjectContext` (`obj`) bound to that coin's object. Disabled objects are skipped for you.
- `ctx.services.scene_events` is this frame's list of contacts. The pattern keeps only trigger overlaps
  (`trigger: true`) that just started (`ContactPhase::Enter`), where the receiver (`object`) is this coin.
- `obj.get::<Collector>(*other)` reads a component from the *other* object. It returns `None` if the
  object has none, so a crate or a wall touching the coin is ignored.
- `obj.emit(..)` broadcasts the event. `obj.destroy_self()` queues the coin for removal; it disappears
  when the stage ends.

## Step 4: the score system

The score board reads `Collected` events and writes the total into a `UiText`. UI elements are
components like any other, so updating them is an ordinary edit:

```rust
impl ScoreBoard {
    fn update(&mut self, obj: &mut ObjectContext<'_, '_>) {
        for collected in obj.events::<Collected>() {
            self.score += collected.value;
        }
        let id = obj.self_id();
        let text = format!("Score {}", self.score);
        obj.edit::<UiText>(id, move |ui| ui.text = text);
    }
}

registry.register_system_for::<ScoreBoard>("game::score_board", Stage::LateUpdate, |world, ctx| {
    run_ordered(world, ctx, ScoreBoard::update)
});
```

`LateUpdate` is the right stage for anything that mirrors the frame's final state onto the screen.
`obj.edit::<UiText>(id, ..)` changes the `UiText` on the same object as the `ScoreBoard`, so put both
components on one object.

## Step 5: register everything

Both systems and all three components are handed to the engine from one function:

```rust
pub fn register(registry: &mut ComponentRegistry) {
    registry.register_ecs::<Collector>();
    registry.register_ecs::<Coin>();
    registry.register_ecs::<ScoreBoard>();

    // ... the two register_system_for calls from steps 3 and 4 go here
}
```

Then hook the file into the plugin's `lib.rs`: add `mod coin_collector;` with the other `mod` lines and
`coin_collector::register(registry);` inside `zestengine_register`. (The **New Rust** menu does this
wiring for you when it creates a file; see [Plugins in a project](ECS.md#plugins-in-a-project).)

## Step 6: build the scene

In the editor, choose **Tools → Build & Reload Components**. The three components now appear in the
Add Component menu.

| Object | Components |
|---|---|
| **Coin** (a sphere or any mesh) | `Coin` with a value of your choice, plus a collider with **Is Trigger** on |
| **Player** | `Collector`, plus a collider and a rigid body or character controller |
| **Score** (a UI object, laid out in the **UI Editor** tab) | `UI Text`, plus `Score Board` on the same object |

Press Play and walk into a coin. It vanishes and the score goes up.

## What happens, frame by frame

```text
frame N    FixedUpdate   physics step: the player overlaps the coin's trigger
           Events        game::coin_pickup sees Contact(Enter)
                           emit Collected { by: player, value: 1 }
                           queue Destroy(coin)  → applied when the stage ends
frame N+1  LateUpdate    game::score_board reads Collected, score += 1, text = "Score 1"
```

Two rules from the [ECS Guide](ECS.md#events) explain the one-frame gap between the pickup and the new
score: an event emitted in frame *N* is readable throughout frame *N + 1*, and never in the frame that
emitted it. Neither system ever touches the other's data.

## Step 7: test it without a window

Systems are plain functions over a world, so you can test them headlessly: no GPU, no window, no engine
loop. Build a `SceneWorld`, register your code, run a stage, and look at the data and at the commands the
systems queued. First a small harness (it is the one from [Testing systems](ECS.md#testing-systems)):

```rust
use zestengine_core::ecs::{ContactPhase, SceneEvent, SceneWorld, Stage, SystemContext};
use zestengine_core::{AnyBox, ComponentCommand, ComponentRegistry, InputState, ObjectId, UiText};

#[derive(Default)]
struct Frame {
    dt: f32,
    input: InputState,
    events: Vec<AnyBox>,
    scene_events: Vec<SceneEvent>,
}

/// Run every system registered for `stage` once and return the commands they queued.
fn run(registry: &ComponentRegistry, scene: &SceneWorld, stage: Stage, frame: &Frame) -> Vec<ComponentCommand> {
    let mut commands = Vec::new();
    let mut ctx = SystemContext::new(&frame.input, &mut commands);
    ctx.dt = frame.dt;
    ctx.services.events = &frame.events;
    ctx.services.scene_events = &frame.scene_events;
    registry.run_systems(stage, scene, &mut ctx);
    commands
}

fn destroyed(commands: &[ComponentCommand]) -> Vec<ObjectId> {
    commands.iter().filter_map(|c| match c { ComponentCommand::Destroy(id) => Some(*id), _ => None }).collect()
}

fn emitted<E: 'static>(commands: &[ComponentCommand]) -> Vec<&E> {
    commands.iter().filter_map(|c| match c { ComponentCommand::Emit(event) => event.0.downcast_ref::<E>(), _ => None }).collect()
}

fn event<E: 'static>(value: E) -> AnyBox { AnyBox(Box::new(value)) }
```

Then the test. You fake what the engine would hand the systems (a contact, last frame's events) and
check what comes out:

```rust
#[test]
fn collecting_a_coin_scores_next_frame() {
    let mut registry = ComponentRegistry::default();
    register(&mut registry);

    let mut scene = SceneWorld::new();
    let coin = scene.spawn("Coin");
    let player = scene.spawn("Player");
    let board = scene.spawn("Board");
    scene.insert(coin, Coin { value: 5 }).unwrap();
    scene.insert(player, Collector {}).unwrap();
    scene.insert(board, ScoreBoard::default()).unwrap();
    scene.insert(board, UiText::default()).unwrap();
    let coin_id = scene.object_id(coin).unwrap();
    let player_id = scene.object_id(player).unwrap();
    let board_id = scene.object_id(board).unwrap();

    // The physics engine reports "`other` entered the coin's trigger".
    let touch = |other| SceneEvent::Contact {
        object: coin_id,
        other,
        trigger: true,
        phase: ContactPhase::Enter,
        two_dimensional: false,
    };

    // Something that is not a Collector touches the coin: nothing happens.
    let ignored = run(&registry, &scene, Stage::Events, &Frame { scene_events: vec![touch(board_id)], ..Default::default() });
    assert!(ignored.is_empty());

    // The player touches it: the coin is destroyed and a Collected event is announced.
    let commands = run(&registry, &scene, Stage::Events, &Frame { scene_events: vec![touch(player_id)], ..Default::default() });
    assert_eq!(destroyed(&commands), [coin_id]);
    let collected = emitted::<Collected>(&commands);
    assert_eq!((collected[0].by, collected[0].value), (player_id, 5));

    // Next frame the score board reads the events and updates its text.
    let events = vec![event(Collected { by: player_id, value: 5 }), event(Collected { by: player_id, value: 10 })];
    run(&registry, &scene, Stage::LateUpdate, &Frame { events, ..Default::default() });
    assert_eq!(scene.get::<UiText>(board).unwrap().text, "Score 15");
}
```

The harness does not apply queued commands, so you assert on the commands themselves (`Destroy`, `Emit`)
and feed events back in by hand. That keeps each test about one system and one frame.

## Variations to try

Each of these is a few lines, and each uses a call documented in the [Engine API Guide](ENGINE_API.md).

**Play a sound where the coin was.** Inside the pickup closure, before `destroy_self`:

```rust
let here = obj.world_position();
obj.play_sound_at("audio/pop.ogg", here, 1.0);
```

**Keep the score between sessions.** Saves are queued like every other side effect:

```rust
obj.save_value("best_score", self.score as i64);
obj.write_save("slot1");
```

**Make coins worth more than one point.** Nothing to write: select a coin and change *Value* in the
inspector.

**Coins that spin, expire or rain from the sky.** The [ECS Guide](ECS.md) has the pieces ready: a
`Rotator` ([Systems](ECS.md#systems)), a `Lifetime` ([Spawning and destroying](ECS.md#spawning-and-destroying))
and a `CrateSpawner` that spawns a registered [entity](ECS.md#entities) every few seconds.

## Where to go next

- [ECS cheat sheet](ecs-cheatsheet.md): the same building blocks as a quick reference, with an index of
  every worked example.
- [ECS Guide](ECS.md): stages, borrowing rules, entities, input, physics and the common mistakes table.
- [Engine API Guide](ENGINE_API.md): everything a system can do to the world, organised by task.
- [WASM Guide](WASM.md): the same ideas in sandboxed scripts, for content you do not fully trust.
