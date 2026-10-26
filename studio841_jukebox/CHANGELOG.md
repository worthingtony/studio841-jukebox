# Changelog

## 0.2.1 - 2026-10-26
- No repeats across restarts: a song VirtualDJ played within `history_hours` (its own
  `lastplay`) isn't added again. Before, only the app's in-memory record counted, and two
  restarts wiped it: six songs came round again within the hour. Queued songs count as played.
- A stall clears sooner: the connection is dropped after 3 failed reads in a row, not 5
  (about 25 s, not 40). VirtualDJ dials back in within seconds.
- MQTT access-list self-check (#5). After connecting, the app listens to everything for 5 s
  and reports whether anything outside its own topics arrived. It then publishes once to
  `zzz-acl-probe/studio841_jukebox`, which a full-access subscriber should never see once the
  access list is on. The result is on the status page and in the log.

## 0.2.0 - 2026-10-26
- Home Assistant entities through MQTT discovery, under a "Studio 841 Jukebox" device:
  VirtualDJ (connected), Automix (running), Now playing (with artist, title, BPM, key and
  position), Up next, Queue (count, with the songs), and an Autopilot switch. The switch lasts
  until the app restarts; the `autopilot` option sets the start value.
- Needs its own Mosquitto login (`mqtt_username`, `mqtt_password`), limited by an ACL: see
  DOCS.md. Without one, the app runs as before with no entities.

## 0.1.2 - 2026-10-26
- Keys decode as VirtualDJ writes them: 1-12 minor and 13-24 major, both from A, and 0 means
  not analysed. 0.1.1 read A-flat minor (12) as A-flat major, and read 0 as A-flat minor
  when the song had a tempo. A song in A-flat major (24) showed the old reading was wrong.
- Status page: whether Automix is on, and how many songs it holds (the list still shows 12).
- The default catalogue is the `party` playlist.

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
