# Studio 841 Jukebox

Drives VirtualDJ's Automix from Home Assistant by posing as a **VirtualDJ Remote**.

## First run
1. Start the app. It announces itself on the network as **Studio 841 Jukebox**.
2. In VirtualDJ: **Settings → Remote**, accept **Studio 841 Jukebox**.
3. Open **Jukebox** in the HA sidebar: it should say *VirtualDJ connected* and show both decks.

## Options
- **catalogue** - the curated playlist, as a VirtualDJ folder path: `mylists:/<name>.subfolders`.
- **autopilot** - off by default. On, it keeps **runway** songs queued, adding catalogue songs
  that flow from the last one. It only ever adds; it never removes or reorders.

## Good to know
- The Remote protocol is undocumented. After a VirtualDJ update, check the status page still
  shows the Automix list.
- If VirtualDJ is closed or the MacBook asleep, the page says *not connected*; the app waits.
