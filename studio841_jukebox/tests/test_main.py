"""The service loop against a fake VirtualDJ connection: what a failed tick does."""
import time, unittest
from unittest import mock
from jukebox import main


class FakeVdj:
    """Fails the first `fail` Automix reads; VirtualDJ 'disconnects' after the first good one."""

    def __init__(self, fail):
        self.fail, self.accepts, self.reads, self.dropped = fail, 0, 0, 0
        self.connected, self.values = False, {}

    def accept(self):
        self.accepts += 1
        if self.accepts > 1:
            raise SystemExit  # the loop came back to waiting: end the test here
        self.connected = True

    def watch(self, script):
        return 0

    def folder(self, path, **kw):
        return [{"path": "c1"}]

    def automix(self):
        self.reads += 1
        if self.fail:
            self.fail -= 1
            raise TimeoutError("no listing for 'playlist'")
        self.connected = False
        return [{"path": "now"}]

    def drop(self):
        self.dropped += 1
        self.connected = False


def run(vdj, **opts):
    jb = main.Jukebox(dict(main.DEFAULTS, **opts), None, vdj=vdj)
    with mock.patch.object(main.time, "sleep"), mock.patch.object(main.log, "warning"):
        with unittest.TestCase().assertRaises(SystemExit):
            jb.run()
    return jb


class Loop(unittest.TestCase):
    def test_a_few_failed_ticks_keep_the_connection(self):
        vdj = FakeVdj(fail=main.MAX_FAILURES - 1)
        jb = run(vdj)
        self.assertEqual((vdj.reads, vdj.dropped), (main.MAX_FAILURES, 0))
        self.assertIn("no listing", jb.status["last_error"])

    def test_repeated_failures_drop_the_connection(self):
        vdj = FakeVdj(fail=99)
        run(vdj)
        self.assertEqual((vdj.reads, vdj.dropped), (main.MAX_FAILURES, 1))

    def test_an_empty_catalogue_warns_once(self):
        jb = main.Jukebox(dict(main.DEFAULTS, autopilot=True), None, vdj=FakeVdj(fail=0))
        with mock.patch.object(main.log, "warning") as warn:
            for _ in range(3):
                jb.top_up([{"path": "now"}], time.time())
        self.assertEqual(warn.call_count, 1)


if __name__ == "__main__":
    unittest.main()
