"""Helpers for constructing musical patterns programmatically.

Used by the style templates and by the in-app generators (Chords, Arp, Bassline).
"""
from __future__ import annotations

import random

from ..core.project import Note, Pattern
from ..core.theory import (PROGRESSIONS, Progression, diatonic_chord,
                           progression_by_name, scale_degree_to_midi, voice_lead)

STEPS_PER_BAR = 16


# --------------------------------------------------------------------------
# drums
# --------------------------------------------------------------------------
def four_on_floor(pat: Pattern, cid: str, bars: int, vel: float = 1.0,
                  skip_last: int = 0) -> None:
    for b in range(bars):
        for beat in range(4):
            s = b * STEPS_PER_BAR + beat * 4
            if skip_last and b == bars - 1 and beat >= 4 - skip_last:
                continue
            pat.add_note(cid, Note(s, 48, 1, vel if beat == 0 else vel * 0.95))


def backbeat(pat: Pattern, cid: str, bars: int, vel: float = 0.9) -> None:
    """Clap/snare on beats 2 and 4."""
    for b in range(bars):
        for beat in (1, 3):
            pat.add_note(cid, Note(b * STEPS_PER_BAR + beat * 4, 48, 1, vel))


def offbeat(pat: Pattern, cid: str, bars: int, vel: float = 0.7) -> None:
    """Open hat on the '&' of every beat — the house lift."""
    for b in range(bars):
        for beat in range(4):
            pat.add_note(cid, Note(b * STEPS_PER_BAR + beat * 4 + 2, 48, 1, vel))


def sixteenths(pat: Pattern, cid: str, bars: int, vel: float = 0.45,
               accent: float = 0.75, humanise: float = 0.0,
               rng: random.Random | None = None) -> None:
    rng = rng or random.Random(0)
    for b in range(bars):
        for s in range(STEPS_PER_BAR):
            v = accent if s % 4 == 0 else vel
            if humanise:
                v *= 1.0 + rng.uniform(-humanise, humanise)
            pat.add_note(cid, Note(b * STEPS_PER_BAR + s, 48, 1, min(v, 1.0)))


def euclid(pat: Pattern, cid: str, bars: int, hits: int, steps: int = 16,
           pitch: int = 48, vel: float = 0.6, rotate: int = 0) -> None:
    """Euclidean rhythm — evenly spread `hits` across `steps`. Organic percussion."""
    pattern = []
    bucket = 0
    for i in range(steps):
        bucket += hits
        if bucket >= steps:
            bucket -= steps
            pattern.append(i)
    for b in range(bars):
        for i in pattern:
            s = b * STEPS_PER_BAR + ((i + rotate) % steps)
            pat.add_note(cid, Note(s, pitch, 1, vel))


def steps_at(pat: Pattern, cid: str, positions, bars: int = 1, pitch: int = 48,
             vel: float = 0.8) -> None:
    for b in range(bars):
        for s in positions:
            pat.add_note(cid, Note(b * STEPS_PER_BAR + s, pitch, 1, vel))


def fill(pat: Pattern, cid: str, bar: int, kind: str = "roll",
         pitch: int = 48) -> None:
    """A one-bar fill at the end of a section."""
    base = bar * STEPS_PER_BAR
    if kind == "roll":
        for i, s in enumerate((8, 10, 12, 13, 14, 15)):
            pat.add_note(cid, Note(base + s, pitch, 1, 0.5 + i * 0.08))
    elif kind == "build":
        for i in range(8):
            pat.add_note(cid, Note(base + 8 + i, pitch, 1, 0.45 + i * 0.07))


# --------------------------------------------------------------------------
# harmony
# --------------------------------------------------------------------------
def resolve_progression(name_or_prog, root: int, scale: str, bars: int,
                        octave: int = 3, seventh: bool = False,
                        extended: bool = False) -> list[list[int]]:
    """One voice-led chord per bar."""
    prog = (name_or_prog if isinstance(name_or_prog, Progression)
            else progression_by_name(name_or_prog) or PROGRESSIONS[0])
    raw = [diatonic_chord(root, scale, d, octave, seventh, extended)
           for d in prog.degrees]
    chords = []
    for i in range(bars):
        ch = raw[i % len(raw)]
        chords.append(voice_lead(ch, low=octave * 12 + 12, high=octave * 12 + 31))
    return chords


def chord_track(pat: Pattern, cid: str, chords: list[list[int]],
                vel: float = 0.75, sustain_bars: int = 1,
                stab_steps: tuple[int, ...] | None = None) -> None:
    """Sustained chords, or rhythmic stabs when `stab_steps` is given."""
    for b, chord in enumerate(chords):
        base = b * STEPS_PER_BAR
        if stab_steps is None:
            for p in chord:
                pat.add_note(cid, Note(base, p, STEPS_PER_BAR * sustain_bars, vel))
        else:
            for s in stab_steps:
                for p in chord:
                    pat.add_note(cid, Note(base + s, p, 2, vel))


def bass_track(pat: Pattern, cid: str, chords: list[list[int]],
               rhythm: str = "offbeat", octave_shift: int = -24,
               vel: float = 1.0) -> None:
    """Root-note bass following the progression."""
    for b, chord in enumerate(chords):
        root = min(chord) + octave_shift
        # keep the bass in the register where a sub actually reads on a system
        while root < 28:
            root += 12
        while root > 43:
            root -= 12
        base = b * STEPS_PER_BAR
        if rhythm == "offbeat":                 # the classic house '&' bass
            for beat in range(4):
                pat.add_note(cid, Note(base + beat * 4 + 2, root, 2, vel))
        elif rhythm == "sustain":
            pat.add_note(cid, Note(base, root, STEPS_PER_BAR, vel))
        elif rhythm == "eighths":
            for i in range(8):
                pat.add_note(cid, Note(base + i * 2, root, 2, vel * (1.0 if i % 2 == 0 else 0.8)))
        elif rhythm == "rolling":               # 16ths with a gap on the kick
            for s in range(STEPS_PER_BAR):
                if s % 4 == 0:
                    continue
                pat.add_note(cid, Note(base + s, root, 1, vel * 0.9))
        elif rhythm == "octave":
            for i in range(8):
                p = root if i % 2 == 0 else root + 12
                pat.add_note(cid, Note(base + i * 2, p, 2, vel))
        elif rhythm == "downbeat":
            pat.add_note(cid, Note(base, root, 6, vel))
            pat.add_note(cid, Note(base + 8, root, 6, vel * 0.9))


ARP_SHAPES = {
    "up": (0, 1, 2, 3, 4, 5, 6, 7),
    "updown": (0, 1, 2, 3, 4, 3, 2, 1),
    "cascade": (0, 2, 1, 3, 2, 4, 3, 5),
    "rolling": (0, 1, 2, 4, 3, 2, 1, 2),
    "wide": (0, 3, 1, 4, 2, 5, 3, 6),
    "pulse": (0, 0, 2, 2, 1, 1, 3, 3),
}


def arp_track(pat: Pattern, cid: str, chords: list[list[int]],
              shape: str = "cascade", octaves: int = 2, rate: int = 1,
              vel: float = 0.8, length: int = 1, accent_every: int = 4) -> None:
    """16th-note arpeggio over the chord tones."""
    seq = ARP_SHAPES.get(shape, ARP_SHAPES["cascade"])
    for b, chord in enumerate(chords):
        pool = sorted({p + 12 * o for o in range(octaves) for p in chord})
        base = b * STEPS_PER_BAR
        i = 0
        for s in range(0, STEPS_PER_BAR, rate):
            idx = seq[i % len(seq)]
            note = pool[idx % len(pool)]
            v = vel * (1.0 if (s // rate) % accent_every == 0 else 0.82)
            pat.add_note(cid, Note(base + s, note, length, min(v, 1.0)))
            i += 1


def melody_track(pat: Pattern, cid: str, root: int, scale: str,
                 degrees: list[tuple[int, int, int]], octave: int = 5,
                 vel: float = 0.85) -> None:
    """degrees: (start_step, scale_degree, length_steps)."""
    for start, deg, ln in degrees:
        pat.add_note(cid, Note(start, scale_degree_to_midi(root, scale, deg, octave),
                               ln, vel))


def riser(pat: Pattern, cid: str, bars: int, start_bar: int = 0) -> None:
    pat.add_note(cid, Note(start_bar * STEPS_PER_BAR, 48, bars * STEPS_PER_BAR, 0.9))
