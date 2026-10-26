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

## Home Assistant entities (MQTT)
With an MQTT login the app appears in HA as a **Studio 841 Jukebox** device: *VirtualDJ*
(connected), *Automix* (running), *Now playing*, *Up next*, *Queue* and an *Autopilot* switch.
The switch lasts until the app restarts; the **autopilot** option sets the start value.

Give the app **its own Mosquitto user, limited by an ACL**, not the Supervisor's MQTT login,
which reaches every topic on the broker. This app will serve guests; a bug in it shouldn't be
able to publish to other apps' command topics (locks, alarms).

1. Mosquitto broker → Configuration → **Logins**: add a user, e.g. `jukebox`, with a long
   random password. Under **Customize**, set `active: true`, `folder: mosquitto`.
2. `/share/mosquitto/acl.conf`:
   ```
   acl_file /share/mosquitto/accesscontrollist
   ```
3. `/share/mosquitto/accesscontrollist`. Once ACLs are on, a user that isn't listed gets
   nothing, so list **every** user that already uses the broker with full access:
   ```
   user addons
   topic readwrite #

   user homeassistant
   topic readwrite #

   # ...each of your existing logins, with: topic readwrite #

   user jukebox
   topic readwrite studio841/#
   topic readwrite homeassistant/+/studio841_jukebox/#
   topic read homeassistant/status
   ```
4. Restart Mosquitto, then set **mqtt_username** and **mqtt_password** here and restart the app.

## Good to know
- The Remote protocol is undocumented. After a VirtualDJ update, check the status page still
  shows the Automix list.
- If VirtualDJ is closed or the MacBook asleep, the page says *not connected*; the app waits.
