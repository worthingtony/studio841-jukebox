import random, unittest
from jukebox import flow, planner


def song(path, bpm=None, key=None):
    s = {"path": path}
    if bpm:
        s["bpm"] = str(60 / bpm)
    if key is not None:
        s["key"] = str(key)
    return s


class Flow(unittest.TestCase):
    def test_key_codes_match_what_virtualdj_shows_as_text(self):
        # 2026-10-25: Mr. V = Cm (4), Duice = G (23), Jonathan - Savage = A (13)
        self.assertEqual(flow.key_name(song("a", 128, 4)), "Cm")
        self.assertEqual(flow.key_name(song("b", 128, 23)), "G")
        self.assertEqual(flow.key_name(song("c", 128, 13)), "A")
        self.assertEqual(flow.camelot(song("a", 128, 4)), (5, "A"))
        self.assertEqual(flow.camelot(song("b", 128, 23)), (9, "B"))
        self.assertIsNone(flow.key(song("unanalysed", None, 0)))

    def test_key_score_on_the_camelot_wheel(self):
        cm, gm, eb, a = song("cm", 128, 4), song("gm", 128, 11), song("eb", 128, 19), song("a", 128, 13)
        self.assertEqual(flow.camelot(gm), (6, "A"))
        self.assertEqual(flow.camelot(eb), (5, "B"))
        self.assertEqual(flow.key_score(cm, cm), 1.0)
        self.assertEqual(flow.key_score(cm, gm), 0.9)    # neighbour
        self.assertEqual(flow.key_score(cm, eb), 0.8)    # relative major
        self.assertEqual(flow.key_score(cm, a), 0.0)

    def test_tempo_score_allows_half_and_double_time(self):
        self.assertEqual(flow.tempo_score(song("x", 128), song("y", 126)), 1.0)
        self.assertEqual(flow.tempo_score(song("x", 128), song("y", 64)), 1.0)
        self.assertEqual(flow.tempo_score(song("x", 128), song("y", 100)), 0.0)
        self.assertIsNone(flow.tempo_score(song("x", 128), song("y")))

    def test_fit(self):
        self.assertEqual(flow.fit(song("x", 128, 4), song("y", 127, 11)), "green")
        self.assertEqual(flow.fit(song("x", 128, 4), song("y", 95, 13)), "red")


class Planner(unittest.TestCase):
    def test_round_robin_layers(self):
        now = song("now", 128, 4)
        automix = [now, song("ann1"), song("fb1"), song("bob1"), song("fb2"), song("ann2"), song("fb3")]
        guest_of = {"ann1": "Ann", "bob1": "Bob", "ann2": "Ann"}
        # Cat's first pick: after every layer-0 pick (ann1, bob1), before Ann's second
        p = planner.insert_position(automix, song("cat1"), "Cat", guest_of, max_shift=0)
        self.assertEqual(p, 4)
        # Bob's second pick: after ann2 (layer 1)
        p = planner.insert_position(automix, song("bob2"), "Bob", guest_of, max_shift=0)
        self.assertEqual(p, 6)

    def test_never_before_start(self):
        automix = [song("now"), song("loaded-next")]
        self.assertEqual(planner.insert_position(automix, song("p"), "Ann", {}, start=2), 2)

    def test_flow_picks_the_better_slot_within_the_shift(self):
        now = song("now", 128, 4)                               # Cm 128
        automix = [now, song("far", 95, 13), song("near", 127, 11), song("end", 128, 4)]
        pick = song("pick", 128, 4)                              # Cm 128 - fits beside now/end
        p = planner.insert_position(automix, pick, "Ann", {}, max_shift=2)
        self.assertIn(p, (1, 3))
        self.assertNotEqual(p, 2)  # not wedged between the 95 BPM song and the 127

    def test_runway_and_fallback(self):
        automix = [song("now"), song("a")]
        self.assertEqual(planner.runway_short(automix, 1, 5), 4)
        cat = [song("c1", 128, 4), song("c2", 100, 13), song("a", 128, 4)]
        fb = planner.next_fallback(song("x", 128, 4), cat, exclude={"a"}, rng=random.Random(1), top=1)
        self.assertEqual(fb["path"], "c1")
        self.assertIsNone(planner.next_fallback(None, cat, exclude={"c1", "c2", "a"}))


if __name__ == "__main__":
    unittest.main()
