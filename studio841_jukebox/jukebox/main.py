"""
Studio 841 Jukebox - the service.

Holds the connection to VirtualDJ (posing as a VirtualDJ Remote), keeps now playing, the
Automix list and the curated catalogue current, and serves a status page through HA ingress.
With `autopilot` on, it keeps a runway of fallback songs queued, each chosen to flow from the
one before. Guest requests come in a later version.

Options come from /data/options.json (the HA app) or --options FILE.
"""
import json, logging, os, signal, sys, threading, time
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import flow, planner
from .vdjremote import VdjRemote, ZeroconfAdvertiser, DnsSdAdvertiser

log = logging.getLogger("jukebox")

DEFAULTS = {"remote_name": "Studio 841 Jukebox", "remote_port": 4250, "status_port": 8841,  # = ingress_port; 8099 is taken on the Pi
            "catalogue": "mylists:/ZZZ CLAUDE test.subfolders", "autopilot": False, "runway": 6,
            "history_hours": 3, "log_level": "info"}

# Through the Remote, get_title answers a yes/no and get_time answers nothing (2026-10-25).
DECK_QUERIES = {"loaded": "loaded", "artist": "get_artist", "title": "get_title_before_remix",
                "path": "get_filepath", "audible": "is_audible", "pos": "song_pos", "bpm": "get_bpm"}

INGRESS_PEERS = {"172.30.32.2", "127.0.0.1"}  # HA's ingress proxy; localhost for development

# Ticks in a row that may fail before the connection is dropped so VirtualDJ dials again.
# 0.1.0 went back to waiting after one failure while VirtualDJ still held the old connection,
# and sat there an hour (2026-10-26).
MAX_FAILURES = 5


class Jukebox:
    def __init__(self, opts, advertiser, vdj=None):
        self.opts = opts
        self.vdj = vdj or VdjRemote(opts["remote_name"], opts["remote_port"], advertiser)
        self.lock = threading.Lock()
        self.status = {"connected": False, "decks": {}, "automix": [], "catalogue": 0,
                       "autopilot": opts["autopilot"], "last_error": None, "updated": None}
        self.catalogue, self.catalogue_at = [], 0
        self.played = {}  # path -> time last seen on a deck
        self.starved = False  # autopilot found nothing to add; warn once, not every tick

    # --- VirtualDJ side ---
    def run(self):
        while True:
            try:
                log.info("waiting for VirtualDJ to connect as %r", self.opts["remote_name"])
                self.vdj.accept()
                ids = {(d, k): self.vdj.watch(f"deck {d} {q}") for d in (1, 2) for k, q in DECK_QUERIES.items()}
            except Exception as e:
                self.error("connecting", e)
                time.sleep(5)
                continue
            failures = 0
            while self.vdj.connected:
                try:
                    self.tick(ids)
                    failures = 0
                except Exception as e:  # one slow answer is not a lost connection
                    failures += 1
                    self.error(f"tick ({failures} in a row)", e)
                    if failures >= MAX_FAILURES:
                        self.vdj.drop()
                time.sleep(3)
            with self.lock:
                self.status["connected"] = False

    def error(self, where, e):
        log.warning("%s: %s", where, e, exc_info=not isinstance(e, (TimeoutError, ConnectionError)))
        with self.lock:
            self.status["last_error"] = f"{time.strftime('%H:%M:%S')} {where}: {e}"

    def tick(self, ids):
        decks = {d: {k: self.vdj.values.get(ids[(d, k)]) for k in DECK_QUERIES} for d in (1, 2)}
        now = time.time()
        for d in decks.values():
            if d["loaded"] and d["path"]:
                self.played[d["path"]] = now
        if now - self.catalogue_at > 300 or not self.catalogue:
            self.catalogue, self.catalogue_at = self.vdj.folder(self.opts["catalogue"]), now
        automix = self.vdj.automix()
        log.debug("tick: catalogue %d, automix %d", len(self.catalogue), len(automix))
        with self.lock:
            self.status.update(connected=True, decks=decks, automix=automix[:12],
                               catalogue=len(self.catalogue), updated=time.strftime("%H:%M:%S"))
        if self.opts["autopilot"]:
            self.top_up(automix, now)

    def top_up(self, automix, now):
        start = 1
        short = planner.runway_short(automix, start, self.opts["runway"])
        if not short:
            return
        recent = {p for p, t in self.played.items() if now - t < self.opts["history_hours"] * 3600}
        exclude = recent | {s.get("path") for s in automix}
        last = automix[-1] if automix else None
        song = planner.next_fallback(last, self.catalogue, exclude)
        if song is None:
            if not self.starved:
                log.warning("runway short by %d but the catalogue has nothing left to add", short)
            self.starved = True
            return
        self.starved = False
        log.info("autopilot: adding %s - %s at %d (fit %s)", song.get("artist"), song.get("title"),
                 len(automix), flow.fit(last, song) if last else "-")
        self.vdj.add_to_automix(song, len(automix))

    # --- status page ---
    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.status))


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Studio 841 Jukebox</title>
<style>body{font:15px system-ui;margin:16px;background:#111;color:#eee}td{padding:2px 8px}
.ok{color:#6c6}.bad{color:#e66}h2{font-size:16px;margin-top:20px}</style>
<h1>Studio 841 Jukebox</h1><div id="s">loading…</div>
<script>
async function load(){const s=await (await fetch('api/status')).json();const e=x=>String(x??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let h=`<p class="${s.connected?'ok':'bad'}">${s.connected?'VirtualDJ connected':'VirtualDJ not connected'} · updated ${e(s.updated)} · autopilot ${s.autopilot?'on':'off'} · catalogue ${s.catalogue} songs</p>`;
if(s.last_error)h+=`<p class="bad">${e(s.last_error)}</p>`;
h+='<h2>Decks</h2><table>';for(const[d,v]of Object.entries(s.decks||{}))h+=`<tr><td>${d}${v.audible?' ▶':''}</td><td>${v.loaded?e(v.artist)+' - '+e(v.title):'empty'}</td><td>${v.loaded&&v.pos!=null?Math.round(v.pos*100)+'%':''}</td><td>${v.bpm?Math.round(v.bpm)+' BPM':''}</td></tr>`;
h+='</table><h2>Automix</h2><table>';(s.automix||[]).forEach((x,i)=>h+=`<tr><td>${i}</td><td>${e(x.artist)} - ${e(x.title)}</td></tr>`);
document.getElementById('s').innerHTML=h+'</table>';}
load();setInterval(load,3000);
</script>"""


def make_handler(jukebox):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0] not in INGRESS_PEERS:
                self.send_error(403)
                return
            if self.path.rstrip("/").endswith("/api/status") or self.path == "/api/status":
                body, ctype = json.dumps(jukebox.snapshot()).encode(), "application/json"
            else:
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return Handler


class StatusServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind does a reverse-DNS lookup of its own address, which took
        # 35 s on the house network (2026-10-25). The name is never used, so skip it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "jukebox", self.server_address[1]


def load_options(argv):
    path = argv[argv.index("--options") + 1] if "--options" in argv else "/data/options.json"
    opts = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            opts.update({k: v for k, v in json.load(f).items() if v not in (None, "")})
    return opts


def main(argv=sys.argv[1:]):
    # HA stops apps with SIGTERM; exit through `finally` so the Bonjour advert is withdrawn
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    opts = load_options(argv)
    logging.basicConfig(level=opts["log_level"].upper(), format="%(asctime)s %(levelname)s %(message)s")
    advertiser = DnsSdAdvertiser if sys.platform == "darwin" else ZeroconfAdvertiser
    jb = Jukebox(opts, advertiser)
    srv = StatusServer(("0.0.0.0", opts["status_port"]), make_handler(jb))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("status page on :%d (HA ingress)", opts["status_port"])
    try:
        jb.run()
    finally:
        jb.vdj.close()


if __name__ == "__main__":
    main()
