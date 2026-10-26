"""
Where a guest's pick goes in the Automix list, and what fills the gaps.

Fairness comes first, flow second:
- Turns are round-robin by guest, in layers: every guest's 1st pending pick plays before
  anyone's 2nd, and so on. A pick never jumps ahead of a pick from an earlier-or-equal layer.
- Within what fairness allows, a pick may move up to MAX_SHIFT slots later to sit where it
  flows best (flow.score with both neighbours).
- Fallback songs from the curated catalogue keep a runway of songs queued, each chosen to
  flow from the one before; nothing repeats within the history window.

All pure functions over song dicts (from VdjRemote.folder) so they test without VirtualDJ.
`guest_of` maps a pending pick's path to its guest's name; anything else is a fallback.
"""
import random
from . import flow

MAX_SHIFT = 2


def _layers(automix, start, guest_of):
    """index -> (guest, layer) for each pending guest pick at or after start."""
    seen, out = {}, {}
    for i in range(start, len(automix)):
        g = guest_of.get(automix[i].get("path"))
        if g is not None:
            out[i] = (g, seen.get(g, 0))
            seen[g] = seen.get(g, 0) + 1
    return out


def insert_position(automix, pick, guest, guest_of, start=1, max_shift=MAX_SHIFT):
    """Index to drop `pick` at. `start` is the first index that may change (1 = right after the
    song now playing; 2 if Automix has already loaded index 1 on the other deck)."""
    layers = _layers(automix, start, guest_of)
    layer = sum(1 for g, _ in layers.values() if g == guest)
    earliest = max([i + 1 for i, (_, l) in layers.items() if l <= layer], default=start)
    latest = min([i for i, (_, l) in layers.items() if l > layer], default=len(automix))
    earliest = max(earliest, start)
    best, best_gain = earliest, None
    for p in range(earliest, min(latest, earliest + max_shift) + 1):
        prev = automix[p - 1] if p > 0 else None
        nxt = automix[p] if p < len(automix) else None
        gain = ((flow.score(prev, pick) if prev else 0.5) + (flow.score(pick, nxt) if nxt else 0.5)
                - (flow.score(prev, nxt) if prev and nxt else 0.5))
        if best_gain is None or gain > best_gain + 1e-9:
            best, best_gain = p, gain
    return best


def runway_short(automix, start, runway):
    """How many songs to add so `runway` songs are queued after the one playing."""
    return max(0, runway - (len(automix) - start))


def next_fallback(last, catalogue, exclude, rng=random, top=3):
    """A catalogue song that flows well from `last`, not in `exclude` (paths queued or played
    recently). Picks among the best `top` so the night doesn't run on rails."""
    pool = [s for s in catalogue if s.get("path") not in exclude]
    if not pool:
        return None
    if last is None:
        return rng.choice(pool)
    ranked = sorted(pool, key=lambda s: flow.score(last, s), reverse=True)
    return rng.choice(ranked[:top])
