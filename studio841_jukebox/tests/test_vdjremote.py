"""Unit tests for the Remote protocol codec, from bytes seen on the wire 2026-10-25.

  cd studio841_jukebox && python3 -m unittest discover tests
"""
import io, struct, unittest, zipfile
from jukebox import vdjremote as v


class Codec(unittest.TestCase):
    def test_frame_matches_the_remotes_hello(self):
        self.assertEqual(v.frame(v.T_HELLO, b"\x49\x03").hex(), "384a44560c0000002700" + "4903")

    def test_register_matches_the_remotes_bytes(self):
        # seen: 01 00 | 4b 00 | 00 00 00 00 | "automix"  and  ... | 4d 00 | "tfel" | "play_pause"
        self.assertEqual(v.register_body(0x4B, "automix"), b"\x4b\x00\0\0\0\0automix")
        self.assertEqual(v.register_body(0x4D, "play_pause", "left"), b"\x4d\x00tfelplay_pause")

    def test_framer_splits_and_holds_partial_messages(self):
        stream = v.frame(5, b"a") + v.frame(37, b"bc")
        f = v.Framer()
        self.assertEqual(f.feed(stream[:13]), [(5, b"a")])
        self.assertEqual(f.feed(stream[13:]), [(37, b"bc")])

    def test_values(self):
        self.assertEqual(v.parse_value(bytes.fromhex("1e00 6c6f6f62 01000000 00")), (30, True))
        self.assertEqual(v.parse_value(bytes.fromhex("0a00 74787400 07000000") + b"Cloonee"), (10, "Cloonee"))
        qid, f = v.parse_value(bytes.fromhex("3600 6c617600 753a9d3e 00"))
        self.assertEqual(qid, 54)
        self.assertAlmostEqual(f, 0.3071, places=3)
        self.assertEqual(v.parse_value(bytes.fromhex("1f00 6c696166 05000780 00")), (31, None))

    def test_folder_plain_and_zipped(self):
        xml = ('<?xml version="1.0"?>\r\n<foldercontent path="playlist" name="playlist" total="1">'
               '<file path="netsearch://ap1" artist="A &amp; B" title="Sippin&apos; Yak" bpm="0.47">'
               '<ext order="2" /></file></foldercontent>')
        plain = struct.pack("<HI", 1, 1) + xml.encode()
        z = io.BytesIO()
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("data.xml", xml)
        zipped = struct.pack("<HI", 1, 2) + z.getvalue()
        for body in (plain, zipped):
            x = v.folder_body_xml(body)
            self.assertEqual(v.folder_path(x), "playlist")
            self.assertEqual(v.xml_files(x), [{"path": "netsearch://ap1", "artist": "A & B",
                                               "title": "Sippin' Yak", "bpm": "0.47"}])

    def test_songs_drop_separators(self):
        files = [{"path": "separator://AppleMusic"}, {"path": "netsearch://ap697195462", "bpm": "0.488290"},
                 {"path": "netsearch://bp1", "bpm": "0.0"}]
        self.assertEqual([f["path"] for f in v.songs(files)], ["netsearch://ap697195462", "netsearch://bp1"])

    def test_filedrop_escapes_and_positions(self):
        body = v.filedrop_body({"path": "netsearch://ap1", "artist": "A & B", "title": "Sippin' Yak"}, 2)
        self.assertEqual(body[:6], struct.pack("<HI", 0, 1))
        x = body[6:].decode()
        self.assertIn('<folderupdate path="playlist" name="playlist">', x)
        self.assertIn('artist="A &amp; B"', x)
        self.assertIn('position="2"', x)


if __name__ == "__main__":
    unittest.main()
