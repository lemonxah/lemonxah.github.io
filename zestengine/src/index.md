# ZestEngine Documentation

ZestEngine is a Vulkan game engine written in Rust, with a built-in editor, VR support, realtime
global illumination, physics, networking and a sandboxed WebAssembly scripting layer. Gameplay code is
plain Rust: **components** hold data, **systems** hold behaviour, and **entities** are ready-made objects
you place in a scene or spawn from code.

## Start here

| If you want to … | Read |
|---|---|
| See what the engine is and what it can do | [What is ZestEngine](overview.md), [Features and roadmap](features.md) |
| Install it, open the editor, build a game | [Getting started](getting-started.md) |
| **Write your first gameplay code, step by step** | [ECS tutorial: a coin collector](ecs-tutorial.md) |
| Understand components, systems, stages, events and entities, with working examples | [ECS Guide](ECS.md) |
| Find the right call fast | [ECS cheat sheet](ecs-cheatsheet.md) |
| Know how to move things, spawn things, raycast, play sounds, read input, save and network | [Engine API Guide](ENGINE_API.md) |
| Run sandboxed scripts for user-generated content and mods | [WASM Guide](WASM.md) |
| Look up an exact type or function | [Rust API Reference](api.md) |

## How the guides fit together

1. The **[ECS tutorial](ecs-tutorial.md)** builds one small feature from nothing: a component, two
   systems, an event, a scene and a test. Start there if you learn by doing.
2. The **[ECS Guide](ECS.md)** teaches the model. Every example in it is compiled and run by the
   engine's test suite, so the code you copy works.
3. The **[Engine API Guide](ENGINE_API.md)** is organised by task ("moving things", "spawning and
   destroying", "physics") and says for each operation whether it takes effect immediately or when the
   stage ends.
4. The **[WASM Guide](WASM.md)** covers the second way to write gameplay: modules compiled to
   WebAssembly that run in a sandbox, for content you do not fully trust.
5. The **[Rust API Reference](api.md)** is generated from the doc comments in the source.

## Your first system in 30 seconds

In the editor, open the Files panel, right-click, and choose **Create → New Rust → Component**, then
**New Rust → System**. The engine writes starter files into your project's `plugins/components` crate and
registers them in its `lib.rs`. Put data in the component, behaviour in the system:

```rust
fn rotate(world: &SystemWorld<'_>, ctx: &mut SystemContext<'_>) {
    for (_, (owner, rotator)) in world.query::<(&Owner, &Rotator)>().iter() {
        if !ctx.is_active(world, owner.0) { continue; }
        let mut transform = world.get_mut::<Transform>(owner.0).expect("every object has a Transform");
        let step = Quat::from_rotation_y(rotator.degrees_per_second.to_radians() * ctx.dt);
        transform.rotation = (step * transform.rotation).normalize();
    }
}
```

Then **Tools → Build & Reload Components**, add the component to an object and press Play. The
[ECS Guide](ECS.md) explains every line.

## Beyond gameplay code

| Topic | Page |
|---|---|
| Realtime global illumination without baking | [Flux](flux.md) |
| The uber-shader and Unity shader conversion | [The standard shader](shaders.md), [Unity shader compatibility](shaders-unity-compat.md) |
| Worlds, avatars and props loaded at run time | [User-generated content](user-content.md), [Game mods](modding.md) |
| VR body tracking and avatar fitting | [VR avatars](vr-avatars.md) |
| Hosting multiplayer | [Dedicated server](dedicated-server.md), [Deploying a dedicated server](deploy-dedicated-server.md) |

## Source

ZestEngine's source lives at [github.com/lemonxah/zestengine](https://github.com/lemonxah/zestengine).
