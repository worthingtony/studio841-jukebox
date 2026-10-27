"""
Home Assistant entities through MQTT discovery: VirtualDJ connected, Automix running, now
playing, up next, the queue, and an Autopilot switch.

The app logs in as its own Mosquitto user. The broker's ACL limits that user to studio841/#
and this app's discovery topics (Tony, 2026-10-26): other apps' lock and alarm command topics
are on the same broker, and this app will serve guests. So nothing here may publish outside
those topics, except the one deliberate probe below.

The payload builders are pure functions so they test without a broker; MqttBridge is the
paho client around them.
"""
import json, logging, re, threading, time
from . import flow

log = logging.getLogger(__name__)

BASE = "studio841/jukebox"
NODE = "studio841_jukebox"
STATUS = f"{BASE}/status"           # online / offline (last will)
STATE = f"{BASE}/state"
NOW = f"{BASE}/now"                 # now playing's attributes
QUEUE = f"{BASE}/queue"             # the queue's attributes
AUTOPILOT_SET = f"{BASE}/autopilot/set"
HA_STATUS = "homeassistant/status"  # HA's birth message: publish discovery again
MAX_STATE = 255                     # HA's limit for a sensor state

# What the broker's access list grants this login (DOCS.md). The self-check below tests it.
ALLOWED = re.compile(r"^(studio841/.+|homeassistant/[^/]+/studio841_jukebox/.+|homeassistant/status)$")
PROBE = "zzz-acl-probe/studio841_jukebox"  # outside ALLOWED on purpose: no one should ever see it
CHECK_SECONDS = 5


def allowed(topic):
    return bool(ALLOWED.match(topic))


def song_name(song):
    if not song:
        return ""
    name = f"{song.get('artist')} - {song.get('title')}" if song.get("artist") else (song.get("title") or "")
    return name[:MAX_STATE]


def discovery(version):
    """[(topic, payload)] that create the entities, under one device."""
    device = {"identifiers": [NODE], "name": "Studio 841 Jukebox", "manufacturer": "worthingtony",
              "model": "VirtualDJ Remote bridge", "sw_version": version}

    def entity(component, oid, name, **extra):
        cfg = {"name": name, "unique_id": f"{NODE}_{oid}", "device": device,
               "availability_topic": STATUS, "state_topic": STATE, **extra}
        return f"homeassistant/{component}/{NODE}/{oid}/config", json.dumps(cfg)

    return [
        entity("binary_sensor", "virtualdj", "VirtualDJ", device_class="connectivity",
               value_template="{{ 'ON' if value_json.connected else 'OFF' }}"),
        entity("binary_sensor", "automix", "Automix", device_class="running",
               value_template="{{ 'ON' if value_json.automix_on else 'OFF' }}"),
        entity("sensor", "now_playing", "Now playing", icon="mdi:music",
               value_template="{{ value_json.now_playing }}", json_attributes_topic=NOW),
        entity("sensor", "up_next", "Up next", icon="mdi:skip-next",
               value_template="{{ value_json.up_next }}"),
        entity("sensor", "queue", "Queue", icon="mdi:playlist-music", unit_of_measurement="songs",
               state_class="measurement", value_template="{{ value_json.queue }}",
               json_attributes_topic=QUEUE),
        entity("switch", "autopilot", "Autopilot", icon="mdi:playlist-plus",
               command_topic=AUTOPILOT_SET, payload_on="ON", payload_off="OFF",
               value_template="{{ 'ON' if value_json.autopilot else 'OFF' }}"),
    ]


def payloads(status):
    """The app's status -> {topic: payload} for state, now playing and the queue.
    The top of the Automix list is the song playing (checked 2026-10-26)."""
    automix = status.get("automix") or []
    decks = status.get("decks") or {}
    now = automix[0] if status.get("automix_on") and automix else None
    deck = next((d for d in decks.values() if d.get("loaded") and d.get("audible")
                 and (now is None or d.get("path") == now.get("path"))), None)
    if now is None and deck:
        now = {"artist": deck.get("artist"), "title": deck.get("title"), "path": deck.get("path")}
    connected = bool(status.get("connected"))
    state = {"connected": connected, "automix_on": bool(status.get("automix_on")),
             "autopilot": bool(status.get("autopilot")),
             "now_playing": song_name(now) if connected else "",
             "up_next": song_name(automix[1]) if connected and len(automix) > 1 else "",
             "queue": max(0, (status.get("automix_count") or 0) - 1) if connected else 0}
    attrs = {}
    if now:
        bpm = flow.bpm(now) or (deck or {}).get("bpm")
        attrs = {"artist": now.get("artist"), "title": now.get("title"),
                 "bpm": round(bpm, 1) if bpm else None, "key": flow.key_name(now),
                 "position": round(deck["pos"], 3) if deck and deck.get("pos") is not None else None}
    queue = {"songs": [song_name(s) for s in automix[1:]]}
    return {STATE: json.dumps(state), NOW: json.dumps(attrs), QUEUE: json.dumps(queue)}


def autopilot_command(payload):
    """True / False for a switch command, None for anything else."""
    p = payload.decode(errors="replace").strip().upper() if isinstance(payload, bytes) else str(payload).upper()
    return {"ON": True, "OFF": False}.get(p)


class MqttBridge:
    """Connects in the background and reconnects on its own. publish() sends only what changed."""

    def __init__(self, opts, version, on_autopilot, on_acl=lambda result: None):
        import paho.mqtt.client as mqtt  # here, so the tests don't need paho
        self.version, self.on_autopilot, self.on_acl = version, on_autopilot, on_acl
        self.sent, self.lock = {}, threading.Lock()
        self.checking, self.outside = False, []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=NODE)
        # A bug in a callback must not stop the network loop: log it and carry on
        self.client.suppress_exceptions = True
        self.client.enable_logger(log)
        self.client.username_pw_set(opts["mqtt_username"], opts.get("mqtt_password"))
        self.client.will_set(STATUS, "offline", retain=True)
        self.client.reconnect_delay_set(1, 60)
        self.client.on_connect, self.client.on_message = self._connected, self._message
        self.client.connect_async(opts["mqtt_host"], opts["mqtt_port"], keepalive=30)
        self.client.loop_start()

    def _connected(self, client, userdata, flags, reason, properties):
        if reason.is_failure:
            log.warning("MQTT login refused: %s", reason)
            return
        log.info("MQTT connected")
        client.subscribe([(AUTOPILOT_SET, 0), (HA_STATUS, 0)])
        self._start_acl_check()
        self._announce()
        with self.lock:
            sent, self.sent = self.sent, {}
        for topic, payload in sent.items():  # the broker may have lost them
            self._send(topic, payload)

    def _announce(self):
        for topic, payload in discovery(self.version):
            self.client.publish(topic, payload, retain=True)
        self.client.publish(STATUS, "online", retain=True)

    # --- access-list self-check (studio841-jukebox#5) ---
    def _start_acl_check(self):
        """Its own positive control: publish PROBE *retained*, then subscribe to everything.
        - With the list off, the broker keeps the probe and hands it straight back.
        - With the list on, the publish is refused and nothing is kept, so it can't come back.
        A '#' listen alone proved nothing: on 2026-10-26, with the list off, 5 s of it saw nothing
        outside the app's own topics, because nothing else on the broker is retained."""
        with self.lock:
            self.checking, self.outside = True, []
        self.client.publish(PROBE, json.dumps({"from": NODE, "version": self.version,
                                               "at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                            qos=1, retain=True)
        threading.Timer(1, lambda: self.client.subscribe("#", 0)).start()
        threading.Timer(1 + CHECK_SECONDS, self._finish_acl_check).start()

    def _finish_acl_check(self):
        self.client.unsubscribe("#")
        self.client.publish(PROBE, "", qos=1, retain=True)  # clear it; refused too when the list is on
        with self.lock:
            self.checking, outside = False, list(self.outside)
        if outside:
            log.warning("ACL check: OPEN - saw %d topics outside this login's own, e.g. %s",
                        len(outside), ", ".join(outside[:3]))
        else:
            log.info("ACL check: limited - its retained probe didn't come back, and nothing outside "
                     "its own topics arrived in %d s", CHECK_SECONDS)
        self.on_acl({"reads": "open" if outside else "ok", "outside": len(outside), "probe": PROBE,
                     "at": time.strftime("%H:%M:%S")})

    def _message(self, client, userdata, msg):
        if not allowed(msg.topic):
            with self.lock:
                if self.checking and msg.topic not in self.outside:
                    self.outside.append(msg.topic)
            return
        if msg.topic == HA_STATUS and msg.payload == b"online":
            self._announce()
        elif msg.topic == AUTOPILOT_SET:
            on = autopilot_command(msg.payload)
            if on is not None:
                self.on_autopilot(on)

    def _send(self, topic, payload):
        with self.lock:
            if self.sent.get(topic) == payload:
                return
            self.sent[topic] = payload
        self.client.publish(topic, payload, retain=True)

    def publish(self, status):
        for topic, payload in payloads(status).items():
            self._send(topic, payload)

    def close(self):
        try:
            self.client.publish(STATUS, "offline", retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):  # not connected: the last will says it instead
            pass
        self.client.loop_stop()
        self.client.disconnect()
