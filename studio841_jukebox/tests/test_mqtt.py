"""MQTT payloads without a broker. The topic test is the one the broker ACL relies on."""
import json, re, unittest
from pathlib import Path
from jukebox import __version__, mqtt

ALLOWED = re.compile(r"^(studio841/.+|homeassistant/[a-z_]+/studio841_jukebox/.+)$")  # = the ACL


def song(artist, title, path, bpm=None, key=None):
    s = {"artist": artist, "title": title, "path": path}
    if bpm:
        s["bpm"] = str(60 / bpm)
    if key:
        s["key"] = str(key)
    return s


class Mqtt(unittest.TestCase):
    def test_every_topic_is_inside_the_acl(self):
        topics = [t for t, _ in mqtt.discovery("x")] + list(mqtt.payloads({}).keys())
        topics += [mqtt.STATUS, mqtt.AUTOPILOT_SET]
        for cfg in (json.loads(p) for _, p in mqtt.discovery("x")):
            topics += [v for k, v in cfg.items() if k.endswith("_topic")]
        for t in topics:
            self.assertRegex(t, ALLOWED)

    def test_discovery_names_match_the_planned_entity_ids(self):
        # HA builds the entity id from the device name + entity name: "Studio 841 Jukebox" + "Now playing"
        names = {json.loads(p)["unique_id"]: json.loads(p)["name"] for _, p in mqtt.discovery("0.2.0")}
        self.assertEqual(names["studio841_jukebox_now_playing"], "Now playing")
        self.assertEqual(names["studio841_jukebox_virtualdj"], "VirtualDJ")
        self.assertEqual(names["studio841_jukebox_autopilot"], "Autopilot")
        self.assertEqual(len(names), 6)

    def test_payloads_take_now_playing_from_the_top_of_automix(self):
        top = song("Cameo", "Candy", "netsearch://ap1", bpm=112, key=17)
        status = {"connected": True, "automix_on": True, "autopilot": True, "automix_count": 7,
                  "automix": [top, song("Madonna", "Holiday", "netsearch://ap2")],
                  "decks": {"1": {"loaded": True, "audible": True, "path": "netsearch://ap1", "pos": 0.29, "bpm": 112.4}}}
        p = mqtt.payloads(status)
        state = json.loads(p[mqtt.STATE])
        self.assertEqual(state, {"connected": True, "automix_on": True, "autopilot": True,
                                 "now_playing": "Cameo - Candy", "up_next": "Madonna - Holiday", "queue": 6})
        now = json.loads(p[mqtt.NOW])
        self.assertEqual((now["bpm"], now["key"], now["position"]), (112.0, "C#", 0.29))
        self.assertEqual(json.loads(p[mqtt.QUEUE])["songs"], ["Madonna - Holiday"])

    def test_disconnected_clears_now_playing(self):
        state = json.loads(mqtt.payloads({"connected": False, "automix": [song("a", "b", "p")]})[mqtt.STATE])
        self.assertEqual((state["connected"], state["now_playing"], state["queue"]), (False, "", 0))

    def test_autopilot_command(self):
        self.assertIs(mqtt.autopilot_command(b"ON"), True)
        self.assertIs(mqtt.autopilot_command(b"off"), False)
        self.assertIsNone(mqtt.autopilot_command(b"maybe"))

    def test_version_matches_config(self):
        config = (Path(__file__).parent.parent / "config.yaml").read_text()
        self.assertIn(f'version: "{__version__}"', config)


if __name__ == "__main__":
    unittest.main()
