# Changelog

## 0.1.0 - 2026-10-25
- First build. Poses as a VirtualDJ Remote ("Studio 841 Jukebox"): reconnects on its own,
  shows now playing, the Automix list and the catalogue on a status page (HA ingress).
- Autopilot (off by default): keeps a runway of fallback songs in Automix, each chosen to flow
  from the one before (tempo and key), no repeats within `history_hours`.
- No guest requests yet.
