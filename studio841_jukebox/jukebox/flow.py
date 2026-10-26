"""
How well one song flows into the next: tempo and key.

VirtualDJ's folder XML gives both, in its own encodings (worked out 2026-10-25 against songs
whose keys VirtualDJ also shows as text):
- bpm: seconds per beat (0.488 = 123 BPM); 0 when not analysed.
- key: 1-12 minor and 13-24 major, both starting at A - Cm = 4, G = 23, A = 13, and
  Ab = 24 (Rick Astley, 2026-10-26: a 24 ruled out the 0-23 reading of 2026-10-25).
  0 means not analysed.

Keys are compared on the Camelot wheel: same number, a neighbour (+-1), or the relative
major/minor (same number, other letter) mix cleanly.
"""
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

TEMPO_EASY = 0.03    # within 3%: no audible stretch
TEMPO_LIMIT = 0.06   # beyond 6%: needs a bridge


def bpm(song):
    spb = float(song.get("bpm") or 0)
    return round(60 / spb, 1) if spb > 0 else None


def key(song):
    """(pitch class 0-11 with C = 0, is_major), or None when not analysed."""
    code = int(song.get("key") or 0)
    if not 1 <= code <= 24:
        return None
    return (code % 12 - 4) % 12, code >= 13


def key_name(song):
    k = key(song)
    return None if k is None else NAMES[k[0]] + ("" if k[1] else "m")


def camelot(song):
    """(number 1-12, 'A' minor / 'B' major), e.g. Cm -> (5, 'A'), G -> (9, 'B')."""
    k = key(song)
    if k is None:
        return None
    pc, major = k
    return ((pc - (11 if major else 8)) * 7) % 12 + 1, "B" if major else "A"


def key_score(a, b):
    ca, cb = camelot(a), camelot(b)
    if ca is None or cb is None:
        return None
    step = min((ca[0] - cb[0]) % 12, (cb[0] - ca[0]) % 12)
    if step == 0:
        return 1.0 if ca[1] == cb[1] else 0.8
    if step == 1 and ca[1] == cb[1]:
        return 0.9
    if step == 2 and ca[1] == cb[1]:
        return 0.4
    return 0.0


def tempo_score(a, b):
    ta, tb = bpm(a), bpm(b)
    if ta is None or tb is None:
        return None
    drift = min(abs(tb * f / ta - 1) for f in (0.5, 1, 2))  # half and double time mix too
    if drift <= TEMPO_EASY:
        return 1.0
    return max(0.0, 1 - (drift - TEMPO_EASY) / (TEMPO_LIMIT - TEMPO_EASY))


def score(a, b):
    """0..1 for playing b straight after a. Unknown halves count as neutral (0.5)."""
    t, k = tempo_score(a, b), key_score(a, b)
    return 0.6 * (0.5 if t is None else t) + 0.4 * (0.5 if k is None else k)


def fit(a, b):
    """'green' fits, 'amber' needs care, 'red' a jump - for the approve notification."""
    s = score(a, b)
    return "green" if s >= 0.75 else "amber" if s >= 0.45 else "red"
