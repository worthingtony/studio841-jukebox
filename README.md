# Studio 841 Jukebox

A Home Assistant app that runs a hands-off guest jukebox on **VirtualDJ**: guests pick songs,
VirtualDJ's Automix plays and mixes them, nobody DJs.

It drives VirtualDJ by **posing as a VirtualDJ Remote** - the phone app's protocol, read off the
wire, which (unlike VDJScript) can add a song to Automix by path at an exact position. Design,
decisions and the protocol evidence live in
[basement-sound `jukebox/`](https://github.com/worthingtony/basement-sound/tree/main/jukebox).

| Version | What works |
|---|---|
| 0.1.0 | Connects as a Remote, reconnects on its own; status page (now playing, Automix list, catalogue) in the HA sidebar; **autopilot** (off by default) keeps a runway of fallback songs that flow (tempo + key) |
| 0.1.1 | Rides out slow answers instead of dropping the connection; keepalive spots a dead link in under a minute; can take songs out of Automix |
| 0.1.2 | Keys decode right (1-24); status shows whether Automix is on and its full count |
| 0.2.0 | HA entities over MQTT: connected, Automix, now playing, up next, queue, Autopilot switch |
| 0.2.1 | No repeats across restarts (VirtualDJ's lastplay); quicker stall recovery; MQTT access-list self-check |
| 0.2.2 | The ACL self-check proves itself: a retained probe comes back only if the list is off |
| next | Guest picks (round-robin, flow-aware slots), admin controls, MQTT entities, approve/deny notifications, request and TV pages |

## Install
Settings → Apps → App store → ⋮ → Repositories → add `https://github.com/worthingtony/studio841-jukebox`,
then install **Studio 841 Jukebox**. First run: see the app's Documentation tab.

## Layout
```
repository.json            the HA app repository
studio841_jukebox/
  config.yaml              the app: options, host network, ingress, no HA/Supervisor API
  Dockerfile, requirements.txt
  jukebox/vdjremote.py     the VirtualDJ Remote protocol (standard library)
  jukebox/flow.py          tempo and key (Camelot) scoring
  jukebox/planner.py       round-robin + flow slot choice, fallback runway
  jukebox/main.py          the service and status page
  tests/                   cd studio841_jukebox && python3 -m unittest discover tests
```

## Safety
- The app has **no Home Assistant or Supervisor API access** - guests will reach its request page
  from an open Wi-Fi, so a bug there reaches only this container.
- The status page answers only HA's ingress proxy.
- The Remote protocol is undocumented and could change with a VirtualDJ update.

MIT licence. Not affiliated with Atomix Productions / VirtualDJ.
