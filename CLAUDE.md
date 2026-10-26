# Studio 841 Jukebox - working notes

HA app for Tony's basement jukebox. Read README.md, then the design in
worthingtony/basement-sound `jukebox/README.md` (decisions, protocol evidence, plan).

## Rules
- **Bump `version` in config.yaml (and the Dockerfile label, CHANGELOG) on every deploy** - HA
  builds from the branch; without a bump a stale build is invisible.
- **Never print `/data/options.json`** or any option value - options will hold credentials.
- **Testing against Tony's VirtualDJ is live.** Reads are fine. Anything that adds to the Automix
  list, or turns `autopilot` on, needs Tony's OK first, and say what will be added.
- Repo is public: no library file paths, captures or credentials in commits.
- Tests: `cd studio841_jukebox && python3 -m unittest discover tests` (stdlib only).
- Run locally on the Mac (temporary, read-only): `cd studio841_jukebox && python3 -m jukebox.main
  --options <file>` with `{"remote_name": "ZZZ CLAUDE jukebox"}` - that name is already accepted in
  VirtualDJ; it advertises with macOS `dns-sd` and withdraws it on exit. Status: http://127.0.0.1:8099/

## Protocol quick facts (details: basement-sound README)
- VirtualDJ connects to the Remote (Bonjour `_vdjremote8._tcp`); accept list is by name.
- Frame: `8JDV` + uint32 total length + uint16 type + body. Registrations numbered from 0.
- `get_title` and `get_time` don't work through the Remote; use `get_title_before_remix`, `song_pos`.
- Folder XML tempo is seconds per beat; key 0-11 minor / 12-23 major from G#.
