"""
Talk to VirtualDJ by posing as a VirtualDJ Remote.

VirtualDJ has no "add this song to Automix" command in VDJScript, but its Remote protocol
does. The protocol is undocumented; everything here was read off the wire on 2026-10-25
(design and evidence: worthingtony/basement-sound, jukebox/README.md):

- The Remote advertises Bonjour `_vdjremote8._tcp` and listens; VirtualDJ connects to it,
  if the advertised name is on its Remote accept list. VirtualDJ retries every ~2 s.
- Every message is b"8JDV" + uint32 LE total length + uint16 LE type + body.
- The Remote speaks first (HELLO), then registers VDJScript queries; VirtualDJ pushes each
  query's value whenever it changes (VALUE). Registrations are numbered from 0 in order.
- Folders and searches are read by path (FOLDER_REQ -> FOLDER, plain XML or a zip holding
  data.xml); a song is added to the Automix list by path at an exact position
  (FOLDER_UPDATE with a <filedrop>).

Registered scripts are evaluated as queries (VDJScript's "LED" context), so registering one
never runs it. A Remote "press" (type 2) would run an action; nothing here sends one.
"""
import html, io, logging, re, socket, struct, subprocess, threading, time, zipfile
from xml.sax.saxutils import quoteattr

log = logging.getLogger(__name__)

MAGIC = b"8JDV"
SERVICE = "_vdjremote8._tcp"

T_REGISTER, T_SUBSCRIBE, T_VALUE = 1, 3, 5
T_BYE = 20
T_FOLDER_REQ, T_FOLDER = 36, 37
T_HELLO = 39
T_FOLDER_UPDATE = 50
T_INFO = 64

AUTOMIX = "playlist"  # the Automix list's folder path


def frame(mtype, body=b""):
    return MAGIC + struct.pack("<IH", 10 + len(body), mtype) + body


class Framer:
    """Split a byte stream into (type, body) messages."""

    def __init__(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        out = []
        while len(self.buf) >= 10:
            if self.buf[:4] != MAGIC:
                j = self.buf.find(MAGIC, 1)
                self.buf = self.buf[j:] if j > 0 else b""
                continue
            n = struct.unpack("<I", self.buf[4:8])[0]
            if len(self.buf) < n:
                break
            out.append((struct.unpack("<H", self.buf[8:10])[0], self.buf[10:n]))
            self.buf = self.buf[n:]
        return out


def register_body(qid, script, deck=None):
    # deck is the skin's 4-letter deck tag ("left", "righ"), stored reversed; None for global
    tag = deck[:4].encode()[::-1].ljust(4, b"\0") if deck else b"\0\0\0\0"
    return struct.pack("<H", qid) + tag + script.encode()


def parse_value(body):
    """VALUE body -> (id, value). bool -> bool, val -> float, txt -> str, fail -> None."""
    qid = struct.unpack("<H", body[:2])[0]
    tag = body[2:6][::-1].strip(b"\0").decode("latin1")
    if tag == "bool":
        return qid, bool(struct.unpack("<I", body[6:10])[0])
    if tag == "val":
        return qid, struct.unpack("<f", body[6:10])[0]
    if tag == "txt":
        n = struct.unpack("<I", body[6:10])[0]
        return qid, body[10:10 + n].decode("utf-8", "replace")
    return qid, None


def folder_body_xml(body):
    """FOLDER body: uint16 flag, uint32 encoding (1 XML, 2 zip holding data.xml)."""
    if struct.unpack("<I", body[2:6])[0] == 2:
        return zipfile.ZipFile(io.BytesIO(body[6:])).read("data.xml").decode("utf-8", "replace")
    return body[6:].decode("utf-8", "replace")


def xml_files(xml):
    return [{k: html.unescape(v) for k, v in re.findall(r'(\w+)="([^"]*)"', m)}
            for m in re.findall(r"<file (.*?)/?>", xml)]


def songs(files):
    """Drop source headers such as separator://AppleMusic that searches interleave."""
    return [f for f in files if not f.get("path", "").startswith("separator://")]


def folder_path(xml):
    m = re.search(r'<folder(?:content|children) path="([^"]*)"', xml)
    return html.unescape(m.group(1)) if m else None


def filedrop_body(song, position, folder=AUTOMIX):
    attrs = " ".join(f"{k}={quoteattr(song[k])}" for k in
                     ("path", "artist", "title", "remix", "bpm", "key", "length") if song.get(k))
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\r\n<folderupdate path={quoteattr(folder)} '
           f'name={quoteattr(folder)}>\r\n\t<filedrop {attrs} position="{int(position)}" />\r\n'
           "</folderupdate>\r\n")
    return struct.pack("<HI", 0, 1) + xml.encode()


def local_ip(probe="172.16.0.1"):
    """The address this host uses on the house LAN (no packet is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((probe, 9))
        return s.getsockname()[0]


class DnsSdAdvertiser:
    """Bonjour advert with macOS's built-in dns-sd - for running from a Mac."""

    def __init__(self, name, port):
        self.proc = subprocess.Popen(["dns-sd", "-R", name, SERVICE, "local.", str(port)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self):
        self.proc.terminate()


class ZeroconfAdvertiser:
    """Bonjour advert with python-zeroconf - for the HA app (host network, Linux)."""

    def __init__(self, name, port, ip=None):
        from zeroconf import ServiceInfo, Zeroconf
        ip = ip or local_ip()
        self.zc = Zeroconf(interfaces=[ip])
        host = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
        self.info = ServiceInfo(f"{SERVICE}.local.", f"{name}.{SERVICE}.local.",
                                addresses=[socket.inet_aton(ip)], port=port, server=f"{host}.local.")
        self.zc.register_service(self.info)
        log.info("advertising %r as %s on %s:%d", name, SERVICE, ip, port)

    def stop(self):
        self.zc.unregister_service(self.info)
        self.zc.close()


class VdjRemote:
    """Listens and advertises once; accept() waits for VirtualDJ, and can be called again after
    a disconnect. Registered queries are per connection - re-register after each accept()."""

    def __init__(self, name, port, advertiser=DnsSdAdvertiser):
        self.name, self.port = name, port
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("0.0.0.0", port))
        self.srv.listen(1)
        self.adv = advertiser(name, port)
        self.conn = None
        self.cond = threading.Condition()
        self._reset()

    def _reset(self):
        self.values = {}       # query id -> latest value
        self.queries = {}      # query id -> script
        self.folders = {}      # folder path -> (time, xml)
        self.next_id = 0       # VirtualDJ numbers registrations from 0, in order

    @property
    def connected(self):
        return self.conn is not None

    # --- connection ---
    def accept(self, timeout=None):
        self.srv.settimeout(timeout)
        try:
            conn, peer = self.srv.accept()
        except socket.timeout:
            raise TimeoutError(f"VirtualDJ did not connect - is {self.name!r} on its Remote accept list?")
        conn.settimeout(None)
        with self.cond:
            self._reset()
            self.conn = conn
        log.info("VirtualDJ connected from %s", peer[0])
        self._send(T_HELLO, b"\x49\x03")
        self._send(T_INFO, struct.pack("<HI", 0, 1) +
                   b'<?xml version="1.0" encoding="UTF-8"?>\r\n<info build="9618" skin="Default:4x3T" '
                   b'width="1000" height="1000" dpi="1.0" />\r\n')
        threading.Thread(target=self._read, args=(conn,), daemon=True).start()

    def close(self):
        try:
            if self.conn:
                self._send(T_BYE)
                self.conn.close()
        except OSError:
            pass
        finally:
            self.adv.stop()
            self.srv.close()

    def _send(self, mtype, body=b""):
        conn = self.conn
        if conn is None:
            raise ConnectionError("VirtualDJ is not connected")
        conn.sendall(frame(mtype, body))

    def _read(self, conn):
        framer = Framer()
        while True:
            try:
                data = conn.recv(1 << 16)
            except OSError:
                data = b""
            with self.cond:
                if not data:
                    if self.conn is conn:
                        self.conn = None
                        log.warning("VirtualDJ disconnected")
                    self.cond.notify_all()
                    return
                for t, body in framer.feed(data):
                    self._handle(t, body)
                self.cond.notify_all()

    def _handle(self, t, body):
        if t == T_VALUE:
            qid, v = parse_value(body)
            self.values[qid] = v
        elif t == T_FOLDER:
            xml = folder_body_xml(body)
            p = folder_path(xml)
            if p is not None:
                self.folders[p] = (time.time(), xml)

    def _wait(self, pred, timeout):
        end = time.time() + timeout
        with self.cond:
            while not pred():
                left = end - time.time()
                if left <= 0 or self.conn is None:
                    return False
                self.cond.wait(left)
            return True

    # --- API ---
    def watch(self, script):
        """Register a query; its value then arrives in self.values[id] whenever it changes."""
        with self.cond:
            qid = self.next_id
            self.next_id += 1
            self.queries[qid] = script
        self._send(T_REGISTER, register_body(qid, script))
        self._send(T_SUBSCRIBE, struct.pack("<HI", 2, qid))
        return qid

    def folder(self, path, timeout=5, settle=1.0):
        """Songs in a folder or search (e.g. 'search://claude'), as a list of attribute dicts.
        Searches fill in waves as online sources answer (0 -> 26 -> 127 -> 402 over ~2 s on
        2026-10-25), so wait until no update has come for `settle` seconds."""
        asked = time.time()
        self._send(T_FOLDER_REQ, struct.pack("<H", 1) + path.encode())
        if not self._wait(lambda: self.folders.get(path, (0,))[0] >= asked, timeout):
            raise TimeoutError(f"no listing for {path!r}")
        end = asked + timeout
        while time.time() < end and time.time() - self.folders[path][0] < settle:
            time.sleep(0.1)
        return songs(xml_files(self.folders[path][1]))

    def automix(self):
        return self.folder(AUTOMIX, settle=0.3)

    def add_to_automix(self, song, position, timeout=5):
        """Drop `song` (a dict from folder()) into the Automix list at `position`, then read back.
        Returns the new list. Raises if the song isn't at that position afterwards."""
        self._send(T_FOLDER_UPDATE, filedrop_body(song, position))
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.5)
            after = self.automix()
            if position < len(after) and after[position].get("path") == song["path"]:
                return after
        raise RuntimeError(f"{song.get('path')} is not at position {position} after the drop")
