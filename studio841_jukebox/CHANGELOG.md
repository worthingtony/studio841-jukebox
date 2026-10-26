# Changelog

## 0.1.1 - 2026-10-26
- A failed tick no longer drops the connection. 0.1.0 went back to waiting after one
  unanswered request while VirtualDJ still held the old connection, and sat there for an hour.
  Now it keeps going, and only after 5 failures in a row closes the connection so VirtualDJ
  dials again.
- TCP keepalive on the connection, so a dead link shows in under a minute, not ~16.
- Songs can be taken out of the Automix list (`<filedelete>`, checked against VirtualDJ).
- Autopilot warns once, not every 3 s, when the catalogue has nothing left to add.
- Adding a song still counts as done if Automix moved on a song during the read-back.

## 0.1.0 - 2026-10-25
- First build. Poses as a VirtualDJ Remote ("Studio 841 Jukebox"): reconnects on its own,
  shows now playing, the Automix list and the catalogue on a status page (HA ingress).
- Autopilot (off by default): keeps a runway of fallback songs in Automix, each chosen to flow
  from the one before (tempo and key), no repeats within `history_hours`.
- No guest requests yet.
