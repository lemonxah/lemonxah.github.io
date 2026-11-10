<!-- Copied from docs/deployment/dedicated-server.md in the engine repository by sync.py. Edit it there, then run ./sync.py. -->

# Deploying a dedicated server (NET-7)

Step by step, from a project to a server players can join and an operator can watch. Reference for the
settings and admin commands is `docs/dedicated-server.md`; the networking model is `docs/networking.md`.

**Status of this guide.** The files it uses are generated and unit-tested as text (the generated config
parses and validates, the unit contains the hardening lines, the heartbeat / probe / metrics run in a real
loopback server). **Nothing here was run under systemd or Docker** by the people who wrote it: treat the
first deployment as a test, with `systemd-analyze verify` and `docker compose config` as the first checks.

## 1. What you deploy

| Item | Notes |
|---|---|
| `zestengine-server` | One static-ish binary (the project's own when it has components). No GPU, window or audio device. |
| `assets/` | The stripped cook. Read-only at run time. |
| `server.ron` | Settings. The one in `deploy/` is the production template. |
| **`state_dir`** | **The one folder that must persist**: `identity.key`, `bans.ron`, `world.state*`, `players.state*` (plus the `health.status` / `metrics.prom` heartbeat). Back it up. |

Ports (all UDP):

| Port | Purpose | Firewall |
|---|---|---|
| 9000 (`port`) | Game traffic | open to players |
| `admin_port` (convention: game + 1) | Signed remote admin | **operators only** |
| 47777 | LAN discovery | closed on a public host (`lan_discovery: false`) |
| 47800 | `zestengine-relay`, only if you run one | open only on the relay host |

There is **no HTTP health endpoint by default.** The ways to see that a server is alive are the heartbeat
file (`--healthcheck`, section 8), the signed `status` command over the admin port, and the optional
loopback listener (`metrics_addr`).

One `state_dir`, one game port and one admin port **per instance**; never share them.

## 2. Build

```sh
just build-server ~/games/arena          # -> ~/games/arena/build-server/
```

`build-server/` now holds the binary, `assets/`, `server.ron` (a development config), `run.sh`,
`build-report.txt` and `deploy/`:

```
deploy/arena.service            hardened systemd unit
deploy/arena@.service           template unit for several instances
deploy/server.ron               production settings (state_dir /var/lib/arena)
deploy/instance.ron.example     settings of one instance
deploy/arena.env.example        secrets (password, relay token)
deploy/Dockerfile, docker-compose.yml, kubernetes.yaml
deploy/nftables.nft, ufw.sh, logrotate.conf, install.sh, README.txt
```

The names come from the project name (`Arena X` becomes `arena-x`). The game port in the templates is the one the
boot scene's Network Manager names (`port`; 9000 when the scene has no Network Manager), and the admin port is that
plus one; the examples below show 9000/9001. Change `port` in `deploy/server.ron` (and the firewall files) only if you
want something else. **The build wipes `build-server/` on every run**, which is why the production `state_dir`
points at `/var/lib/<game>` and never at `build-server/assets/.server` (the development default,
`<project>/.server`, would be inside the folder a rebuild deletes).

Check what the server will actually use before starting it:

```sh
./zestengine-server --print-config --config deploy/server.ron
```

prints the effective settings (file, environment and flags merged; the password and relay token show as
`"<set>"`), validated, and exits.

## 3. Install on a systemd host

Copy the whole `build-server/` folder to the host, then:

```sh
sudo deploy/install.sh
```

The script creates a system user `arena`, installs the binary and assets to `/opt/arena/` (the old assets
move to `assets.old`), puts `server.ron` and `arena.env` in `/etc/arena/` **only if they do not exist** (an
edited config is never overwritten), and installs the two unit files. It does not enable or start anything and
does not touch the firewall. Then:

1. Edit `/etc/arena/server.ron`: `server_name`, `max_players`, admin keys (section 6).
2. Edit `/etc/arena/arena.env` (mode 0600): `ZESTENGINE_SERVER_PASSWORD`, `ZESTENGINE_RELAY_TOKEN`.
3. `sudo systemd-analyze verify /etc/systemd/system/arena.service`
4. `sudo systemctl enable --now arena`
5. `journalctl -u arena -f` and `/var/log/arena/server.log`.

What the unit does (`deploy/arena.service`):

- Runs as `User=arena` (comment in the file shows `DynamicUser=yes` as the alternative), `--no-console`
  (no stdin under a service manager), `WorkingDirectory=/opt/arena`.
- `StateDirectory=arena` creates `/var/lib/arena` (mode 0700) and makes it the only writable place besides
  `LogsDirectory=arena` (`/var/log/arena`). `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`,
  `PrivateDevices`, `NoNewPrivileges`, empty capability set, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`,
  `SystemCallFilter=@system-service`, `UMask=0077`. `MemoryDenyWriteExecute` is left off because a WASM
  sandbox with a JIT needs writable and executable pages.
- `Restart=on-failure`, `RestartForceExitStatus=75`, `SuccessExitStatus=0`: a crash restarts it, the `restart`
  admin command (exit code 75) restarts it, a clean `shutdown` / SIGTERM does not. Five failed starts in a
  minute stop the loop (`StartLimit*`).
- `KillSignal=SIGTERM`, `TimeoutStopSec=10`: SIGTERM is graceful (players are told, state is saved); after
  10 s systemd sends SIGKILL. A save finishes in far less than that for normal worlds.
- `LimitNOFILE=65536`. Optional, commented: `CPUAffinity=2 3`, `Nice=-5`, `MemoryMax=2G`.

`state_dir` in `server.ron` and `StateDirectory=` in the unit must name the same folder
(`/var/lib/arena`). If you change one, change the other.

## 4. Docker

```sh
cd build-server
cp deploy/arena.env.example deploy/arena.env      # then edit
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps    # "healthy" once the heartbeat is fresh
```

The image is built from the prebuilt binary (no Rust toolchain in the image): `debian:stable-slim` (the
`BASE` build argument), a non-root user (uid 10001), `VOLUME /var/lib/arena`, `EXPOSE 9000/udp 9001/udp`,
`HEALTHCHECK` = `zestengine-server --healthcheck`, `STOPSIGNAL SIGTERM`. The compose file adds a named
volume for the state folder, `restart: unless-stopped` (which also honours the exit code 75 of `restart`),
`stop_grace_period: 10s`, a read-only root file system, `cap_drop: [ALL]`, `no-new-privileges`, and
publishes the game port; the admin port line is commented and bound to `127.0.0.1`: expose it only to
operators.

The binary is dynamically linked against glibc, so the base image needs a glibc at least as new as your
build machine's. For a fully static image use the musl target (section 12) with
`BASE=gcr.io/distroless/static-debian12:nonroot` (remove the `useradd` line, use uid 65532).

`docker compose` publishes UDP through the host's NAT; for more than a few hundred packets per second per
player consider `network_mode: host` on a dedicated host instead.

### Kubernetes

`deploy/kubernetes.yaml` is a PersistentVolumeClaim (1 Gi, `ReadWriteOnce`) for the state folder, a Deployment and a
Service. Build and push the image first (section 4's Dockerfile), set `image:` to your registry path, create the secret
with the password and relay token (`kubectl create secret generic <game>-env --from-literal=ZESTENGINE_SERVER_PASSWORD=...`,
the secret is optional in the manifest), then `kubectl apply -f deploy/kubernetes.yaml`. What the manifest decides:
**one replica with `strategy: Recreate`** (the saved world, bans and the pinned server identity live in one volume, so two
servers must never share it, and an update stops the old pod first); `terminationGracePeriodSeconds: 15` so SIGTERM can
save and send the shutdown redirect; a non-root user (10001) with a read-only root file system and no capabilities
(`/tmp` and the log folder are `emptyDir`s); startup and liveness probes that run `zestengine-server --healthcheck` (the
heartbeat file, no network); the Service is `type: LoadBalancer` for **UDP** with `externalTrafficPolicy: Local` so
players' real addresses reach the server (bans and rate limits are per address). Your provider's load balancer must
support UDP; otherwise switch the Service to `NodePort` and open that port. The signed admin port is deliberately not
in the Service: reach it with `kubectl port-forward` (UDP needs a tunnel) or a separate internal Service. Not run on a
cluster; it is generated text with unit tests.

## 5. Firewall

`deploy/nftables.nft` and `deploy/ufw.sh` are examples, not scripts to run blindly: they open the game port,
restrict the admin port to an operators' address range, and keep LAN discovery (47777) closed. Check with
`nft -c -f deploy/nftables.nft` before loading anything. The admin port is also protected by Ed25519
signatures, timestamps and a per-address rate limit, but replies are signed, not encrypted: put it behind a
VPN or an allow-list, do not leave it open to the internet.

## 6. Admin keys

On **your own machine**:

```sh
zestengine-admin keygen --out ~/.config/arena-admin.key     # prints the public key
```

Paste the public key into `admin_keys` (uncomment the block and `admin_port` in `server.ron`; the shipped
placeholder `PUT_THE_64_HEX_DIGIT_PUBLIC_KEY_HERE` is refused at start, on purpose), roles `Observer`,
`Moderator`, `Admin`. The secret key never goes on the server. Operate:

```sh
zestengine-admin --server host:9001 --server-key <server public key> --key ~/.config/arena-admin.key status
```

The server's public key is in its log at start (`server key ...`) and is the pinned identity (section 7).

**Rotating a key**, with no downtime: add the new key beside the old one, `reload` (an `Admin` key can send
it), check the new key works (`status`), remove the old one, `reload` again. A key that is removed stops
working at the `reload`. Rotating all keys because of a leak: do the same with the leaked key removed first.

## 7. State directory: backup, restore, upgrade

`state_dir` holds everything that cannot be rebuilt:

| File | What |
|---|---|
| `identity.key` | The server's signing identity. Players pin it on first join and refuse a changed one. **Losing it makes returning players' games refuse the server (changed identity)**, and invalidates every `--server-key` your operators hold. |
| `bans.ron` | Bans by player id. |
| `world.state*`, `players.state*` | Persistent scene objects and per-player data, with `persist_keep` (default 3) older generations next to each. |

**Backup**: copy the folder while the server runs (files are replaced atomically and each generation is
checksummed) or, safer, after `systemctl stop`:

```sh
sudo tar -C /var/lib -czf arena-state-$(date +%F).tgz arena
```

(For Docker: `docker run --rm -v arena_state:/s -v $PWD:/b debian:stable-slim tar -C /s -czf /b/state.tgz .`.)
Keep `identity.key` somewhere extra safe (it is 32 secret bytes) and out of shared backups.

**Restore**: stop the server, replace the folder content with the backup keeping owner `arena` and mode
0700, start. A damaged current file falls back to the previous generation and the bad one is kept as
`.corrupt-<unix>`.

**Move to another machine**: copy `state_dir` (above all `identity.key`), keep the same address or announce
the new one; players are not asked anything because the identity is the same.

**Upgrade** (new build, same identity): the state folder is outside the build folder, so just replace the
binary and assets.

```sh
sudo systemctl stop arena                  # or the graceful redirect below
sudo deploy/install.sh                     # copies the binary and assets, keeps /etc/arena and /var/lib/arena
sudo systemctl start arena
```

A state file written by a newer version is not silently overwritten by an older server (it is reported), so
keep the backup from before a version jump and do not run an older build on a newer state folder.

**Graceful upgrade with a redirect.** Bring up the new version on a second port (or another host), then:

```sh
zestengine-admin ... shutdown 203.0.113.9:9010     # players get a notice and their game follows the address
```

`shutdown <addr>` and `restart <addr>` offer the address (`host:port` or a relay room code) to every player
as they are disconnected; `shutdown_redirect` in `server.ron` sets a default. The follow itself is
implemented in the player and loopback-tested only; verify it with a real client before relying on it.

## 8. Monitoring

**Heartbeat and probe.** Every `health_interval` seconds (5 by default, 0 = off) the server rewrites
`<state_dir>/health.status` (plain `key=value`: `state`, `updated_unix`, `pid`, `ticks`, `players`,
`tick_mean_ms`, `bytes_out_per_s`, `bans` ...) and `<state_dir>/metrics.prom` (Prometheus text format). On a
clean stop `state=stopped` is written.

```sh
zestengine-server --healthcheck --config /etc/arena/server.ron      # exit 0 alive, 1 not, 2 bad arguments
```

needs no network and no keys; it reads only `state_dir` from the config (so it runs in a container without the
project), and fails when the file is missing, stale (default: older than three intervals, at least 30 s) or
says anything but `running`. A hung tick loop stops the heartbeat, so a frozen server is caught too. Use it as
a Docker `HEALTHCHECK` (already in the Dockerfile), a cron job, or a systemd watchdog sidecar. Run as a user
that can read `state_dir` (`sudo -u arena`).

**Metrics.**

| Series (`zestengine_` prefix) | Meaning |
|---|---|
| `up`, `uptime_seconds`, `ticks_total`, `tick_rate_hz` | Liveness and tick counter. A flat `ticks_total` is a stuck server. |
| `tick_ms_mean`, `tick_ms_max` | Tick cost since the last reading. Alert when the mean passes about 60 percent of `1000 / tick_rate` ms (20 ms at 30 Hz) or the max passes the full period. |
| `players`, `max_players` | Load. |
| `net_bytes_in_total`, `net_bytes_out_total`, `net_bytes_in_per_second`, `net_bytes_out_per_second` | Traffic. |
| `violations_total`, `muted_total` | Validation hits; a spike is a misbehaving client or an attack. |
| `interest_enabled`, `interest_objects`, `interest_relevant_avg`, `interest_held_by_budget`, `interest_merged_total` | Interest management (NET-5). |
| `bans` | Active bans. |

For Prometheus either read `metrics.prom` with the node exporter's textfile collector
(`--collector.textfile.directory=/var/lib/arena`, only `*.prom` files are read), or enable the optional
listener:

```ron
metrics_addr: "127.0.0.1:9100",     // loopback only; any other address is refused at start
```

serving `GET /health` (200 or 503) and `GET /metrics`. It is **off by default**, has no authentication
(hence loopback), answers one request at a time with a 1 s timeout, and its numbers are those of the last
heartbeat. Put a reverse proxy or an agent in front of it if a remote scraper needs it. Several instances:
`9100 + N`.

The signed `status` and `stats` commands over the admin port are the authoritative view (they run on the
server thread); the stats line in the log repeats every `stats_interval` seconds.

**Logs.** `log_path` (the template uses `/var/log/arena/server.log`) is size-rotated by the server
(`log_max_mb` x `log_keep`); the same lines go to the journal / `docker logs`. `deploy/logrotate.conf` adds
daily rotation with compression (`copytruncate`; raise `log_max_mb` so the two do not both rotate).

## 9. Several instances on one host

`deploy/arena@.service` is a template unit: `%i` is the instance name and selects `/etc/arena/%i.ron`, with
`StateDirectory=arena/%i` (so `state_dir: "/var/lib/arena/%i"` written out in that file).

```sh
sudo cp /opt/arena/deploy/instance.ron.example /etc/arena/eu1.ron      # edit port, admin_port, state_dir, server_name
sudo systemctl enable --now arena@eu1
```

**Port allocation rule.** Instance number N (0, 1, 2, ...) takes game UDP `9000 + 10*N`, admin UDP
`game + 1`, metrics (loopback TCP) `9100 + N`. The state folder is `/var/lib/arena/<instance>`, the log is
`/var/log/arena/<instance>.log`. The gaps leave room to grow without renumbering. Only one instance may
answer LAN discovery (47777): write `lan_discovery: false` in all of them on a public host. Give each
instance its own cores with `systemctl edit arena@eu1` (`CPUAffinity=`), and size them as in section 10.
Instances share the binary and `assets/`, so an upgrade restarts them one by one:
`systemctl restart arena@eu1`, wait for `--healthcheck`, next.

## 10. Sizing a VPS

Numbers come from the NET-5 scale test (`docs/networking.md`, "Interest management"): 200 simulated clients
walking at 4 m/s and reporting at 15 Hz plus 100 server-simulated NPCs, tick 30 Hz, **server part of a tick
only**, in-memory transport (no kernel packet I/O), optimised dev profile, one machine. Real numbers will be
higher; measure your own game with `--print-config`'s settings and the `tick_ms_mean` series.

| Case (200 players) | Server CPU per tick (mean, p99) | Out per client | Total out |
|---|---|---|---|
| 1200 m world, interest on (100 m) | 2.3 ms, 4.8 ms | 5.1 kB/s | 1.0 MB/s (8 Mbit/s) |
| 300 m dense, interest on | 6.6 ms, 19.0 ms | 38.9 kB/s | 8.0 MB/s (64 Mbit/s) |
| 300 m dense, interest + 12 kB/s budget | 5.6 ms, 8.3 ms | 11.6 kB/s | 2.4 MB/s (19 Mbit/s) |
| interest **off** | 31.6 to 32.7 ms, 69 to 93 ms | 293 kB/s | 60 MB/s: not viable |

Rules of thumb that follow:

- **CPU**: the simulation is one thread. One fast core runs one instance of up to about 100 to 200 players
  with interest management on (the tick budget at 30 Hz is 33 ms). More players means more instances, not
  more cores per instance. Reserve one extra core per host for the kernel's UDP handling.
- **Interest management is not optional** above a few dozen players in a big world: switch it on in
  `server.ron` (`interest: (enabled: true, radius: 100.0, budget: 12000)`).
- **Bandwidth**: size by the "Total out" column, with 50 percent headroom, and by your provider's monthly
  transfer: 2.4 MB/s is about 6 TB per month at full load. A 50-player VR session targets about 3.6 MB/s
  (see the NET-5 leftovers: not measured against real avatar traffic).
- **Memory**: not measured. A scene plus replication state for a few hundred objects is small; plan 512 MB to
  1 GB per instance until you measure `ps -o rss` on your game (this is a guess, not a result).
- **Disk**: the cooked assets (`build-report.txt`) plus a few MB of state.

A practical starting point: a 2 vCPU / 2 GB VPS with 100 to 250 Mbit/s runs one instance for 50 to 100 players
comfortably; check `tick_ms_mean` with real players before adding more.

## 11. Client connect checklist (PC and Quest)

Before announcing the server:

1. Server log says `hosting "..." on UDP 9000`, `--healthcheck` is 0, the firewall allows UDP 9000 from the
   internet (test from outside: `nc -u -z host 9000` only proves the port is not rejected).
2. Client and server are built from the same engine version and the same project content (the game's scenes
   and components must match what the server cooked).
3. PC: connect with `host:9000` (direct) or pick the server from the directory, if `directory:` is set.
   If the server has a password, the player enters it (it keys the session encryption).
4. A second join on another day is not refused for a changed identity (if it is, `identity.key` changed:
   section 7).
5. Quest: same address or the directory; the headset must be on a network that allows outbound UDP to the
   port (guest and hotel Wi-Fi often do not); mobile hotspots work. Check the headset's clock is right.
6. A player joins, moves, and appears for a second client; `players` / `status` over the admin port shows
   both; the player count in `zestengine_players` follows.
7. `restart`/`shutdown` with an address: the players get the notice and (once verified with real clients)
   follow it.
8. Behind NAT without a port forward: set `relay` to a `zestengine-relay` and give players the room code
   instead of an address.

## 12. Cross-compiling

`ZESTENGINE_SERVER_TARGET=<triple> just build-server <project>` builds the server for another target
(`cargo build --release --target <triple>`; the binary is taken from `target/<triple>/release/`).
`scripts/check-server-cross.sh [triples...]` (or `just check-server-cross`) runs `cargo check -p
zestengine-server --target <triple>` for each triple that `rustup target list --installed` lists, and says
`SKIP` for the others. It is **not run in CI**. What was found on the machine that wrote this:

| Target | Result |
|---|---|
| `x86_64-unknown-linux-gnu` (host) | `cargo check -p zestengine-server --locked` passes. |
| `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-gnu` | **Not installed there, not tried** (`rustup target add ...`). Unknown whether they build. |
| `i686-unknown-linux-gnu` (installed) | **Fails**: `glam 0.15.2` (a transitive dependency of the asset and physics stack) asserts alignments that do not hold on 32-bit x86 (`E0080`). 32-bit hosts are not a target. |

What to expect, unverified: `cargo check` does not link, so passing it does not prove a build. A real
build for `aarch64-unknown-linux-gnu` needs a cross linker (`aarch64-linux-gnu-gcc`, configured as
`[target.aarch64-unknown-linux-gnu] linker = ...` in `.cargo/config.toml`) and, for crates with C code, a
cross C compiler; `x86_64-unknown-linux-musl` needs `musl-gcc` for the same reason. `cargo zigbuild` or
the `cross` tool replace both when installed. The project's own server crate (projects with components) is
built from the project's `target/` folder with the same `--target`, so a project's component crate must
cross-compile too. Please report the first real result of each target in `IMPLEMENTATION_PLAN.md`.

## 13. Checklist

- [ ] `state_dir` is outside the build folder and backed up (identity first).
- [ ] Secrets in `arena.env`, not in `server.ron` (mode 0600).
- [ ] Admin port firewalled to operators; key pair made on an operator machine.
- [ ] `lan_discovery: false` on public hosts.
- [ ] `systemd-analyze verify` clean; `systemctl restart` and `kill -TERM` tested once (players told, state saved).
- [ ] `--healthcheck` returns 0; an alert on `zestengine_ticks_total` not increasing.
- [ ] One test client per platform joined from outside the network.
