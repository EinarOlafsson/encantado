"""Style templates — complete starter songs.

Each one builds a full project: channels with tuned presets, section patterns and
an arrangement. Load one, hit play, then change whatever you like. They are
written in the idiom of a genre, not copies of any particular record.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from ..core.project import Clip, Project
from ..core.theory import scale_degree_to_midi
from . import builder as B

SPB = B.STEPS_PER_BAR
BARS = 4
PLEN = SPB * BARS                       # every section pattern is 4 bars


def _arrange(pr: Project, order: list[tuple[str, int]]) -> None:
    """order: list of (pattern name, repeat count), laid out end to end."""
    by_name = {p.name: p for p in pr.patterns}
    at = 0
    for name, reps in order:
        pat = by_name.get(name)
        if pat is None:
            continue
        for _ in range(reps):
            pr.arrangement.append(Clip(pat.id, at, PLEN, 0))
            at += PLEN


# --------------------------------------------------------------------------
# 1. Melodic house — cinematic, arp-led
# --------------------------------------------------------------------------
def melodic_house() -> Project:
    pr = Project(name="Melodic House", bpm=122, root=9, scale="Minor (Aeolian)")
    rng = random.Random(7)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 150, "end_hz": 47,
                                           "decay": 0.44, "punch": 1.6, "drive": 0.2})
    clap = pr.add_channel("clap", "Clap", {"tone": 1600, "decay": 0.28, "tail": 0.55})
    ohat = pr.add_channel("hat", "Open Hat", {"decay": 0.3, "metal": 0.45, "level": 0.32})
    chat = pr.add_channel("hat", "Closed Hat", {"decay": 0.04, "level": 0.3})
    perc = pr.add_channel("perc", "Perc", {"hz": 520, "decay": 0.09, "noise": 0.45})
    bass = pr.add_channel("bass", "Sub Bass", {"cutoff": 420, "sub": 1.0, "saw": 0.3,
                                               "decay": 0.35, "sustain": 0.8})
    arp = pr.add_channel("pluck", "Arp", {"cutoff": 900, "resonance": 5.0,
                                          "env_amt": 3.4, "f_decay": 0.14,
                                          "decay": 0.24, "level": 0.62})
    pad = pr.add_channel("pad", "Pad", {"cutoff": 2200, "attack": 1.2,
                                        "release": 2.4, "level": 0.4})
    lead = pr.add_channel("pluck", "Lead", {"cutoff": 2400, "resonance": 2.4,
                                            "env_amt": 2.0, "decay": 0.5,
                                            "sustain": 0.25, "release": 0.5,
                                            "level": 0.5, "sub": 0.0})
    rise = pr.add_channel("sweep", "Riser", {"dur": 4.0, "from_hz": 400,
                                             "to_hz": 11000, "level": 0.3})

    for c, amt in ((bass, 0.85), (arp, 0.6), (pad, 0.5), (lead, 0.45)):
        c.sc_amount, c.sc_release = amt, 0.3
    arp.sends.reverb, arp.sends.delay = 0.3, 0.28
    pad.sends.reverb = 0.5
    lead.sends.reverb, lead.sends.delay = 0.35, 0.3
    perc.sends.reverb = 0.25
    clap.sends.reverb = 0.2
    pr.master["delay"]["division"] = 3          # 1/8 dotted

    chords = B.resolve_progression("i - VI - III - VII", pr.root, pr.scale, BARS, 3)

    def drums(pat, full=True, hats=True):
        B.four_on_floor(pat, kick.id, BARS)
        if full:
            B.backbeat(pat, clap.id, BARS, 0.85)
        if hats:
            B.offbeat(pat, ohat.id, BARS, 0.6)
            B.sixteenths(pat, chat.id, BARS, 0.28, 0.42, 0.12, rng)
        if full:
            B.euclid(pat, perc.id, BARS, 5, 16, 48, 0.5, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.four_on_floor(intro, kick.id, BARS)
    B.offbeat(intro, ohat.id, BARS, 0.5)
    B.arp_track(intro, arp.id, chords, "cascade", 2, 1, 0.6)

    groove = pr.add_pattern("Groove", PLEN)
    drums(groove)
    B.bass_track(groove, bass.id, chords, "offbeat", -24)
    B.arp_track(groove, arp.id, chords, "cascade", 2, 1, 0.75)
    B.chord_track(groove, pad.id, chords, 0.5)

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, pad.id, chords, 0.62)
    B.arp_track(brk, arp.id, chords, "updown", 2, 2, 0.6, 2)
    B.euclid(brk, perc.id, BARS, 3, 16, 48, 0.4)

    build = pr.add_pattern("Build", PLEN)
    B.four_on_floor(build, kick.id, BARS, 1.0, skip_last=2)
    B.sixteenths(build, chat.id, BARS, 0.3, 0.5, 0.1, rng)
    B.chord_track(build, pad.id, chords, 0.6)
    B.arp_track(build, arp.id, chords, "cascade", 2, 1, 0.8)
    B.riser(build, rise.id, BARS)

    drop = pr.add_pattern("Drop", PLEN)
    drums(drop)
    B.bass_track(drop, bass.id, chords, "offbeat", -24)
    B.arp_track(drop, arp.id, chords, "cascade", 2, 1, 0.85)
    B.chord_track(drop, pad.id, chords, 0.55)
    B.melody_track(drop, lead.id, pr.root, pr.scale,
                   [(0, 4, 6), (8, 2, 4), (16, 3, 6), (24, 4, 4),
                    (32, 5, 8), (48, 4, 6), (56, 2, 6)], 5, 0.8)

    outro = pr.add_pattern("Outro", PLEN)
    B.four_on_floor(outro, kick.id, BARS)
    B.offbeat(outro, ohat.id, BARS, 0.5)
    B.chord_track(outro, pad.id, chords, 0.45)

    _arrange(pr, [("Intro", 2), ("Groove", 2), ("Break", 2), ("Build", 1),
                  ("Drop", 4), ("Break", 1), ("Drop", 2), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
# 2. Progressive anthem — big supersaw drop
# --------------------------------------------------------------------------
def progressive_anthem() -> Project:
    pr = Project(name="Progressive Anthem", bpm=126, root=6, scale="Minor (Aeolian)")
    rng = random.Random(3)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 190, "end_hz": 50,
                                           "decay": 0.4, "punch": 2.2, "drive": 0.3})
    clap = pr.add_channel("clap", "Clap", {"tone": 1800, "decay": 0.3, "tail": 0.6})
    ohat = pr.add_channel("hat", "Open Hat", {"decay": 0.26, "level": 0.34})
    chat = pr.add_channel("hat", "Closed Hat", {"decay": 0.035, "level": 0.28})
    crash = pr.add_channel("cymbal", "Crash", {"decay": 2.2, "level": 0.4})
    bass = pr.add_channel("bass", "Bass", {"cutoff": 500, "sub": 1.0, "saw": 0.45,
                                           "drive": 0.25})
    saws = pr.add_channel("supersaw", "Big Chords", {"detune": 0.42, "cutoff": 7000,
                                                     "attack": 0.02, "release": 0.4,
                                                     "level": 0.34})
    lead = pr.add_channel("supersaw", "Lead", {"detune": 0.3, "cutoff": 9000,
                                               "attack": 0.008, "sustain": 0.8,
                                               "release": 0.3, "level": 0.3,
                                               "sub": 0.2})
    keys = pr.add_channel("fm", "Piano", {"ratio": 1.0, "index": 2.2,
                                          "fm_decay": 0.4, "decay": 1.4,
                                          "level": 0.5})
    rise = pr.add_channel("sweep", "Riser", {"dur": 4.0, "from_hz": 500,
                                             "to_hz": 12000, "level": 0.34})

    for c, amt in ((bass, 0.9), (saws, 0.8), (lead, 0.6), (keys, 0.4)):
        c.sc_amount, c.sc_release = amt, 0.32
    saws.sends.reverb, saws.sends.delay = 0.3, 0.2
    lead.sends.reverb, lead.sends.delay = 0.32, 0.3
    keys.sends.reverb = 0.4
    pr.master["delay"]["division"] = 3

    chords = B.resolve_progression("i - III - VII - VI", pr.root, pr.scale, BARS, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.chord_track(intro, keys.id, chords, 0.6, stab_steps=(0, 6, 8, 14))
    B.four_on_floor(intro, kick.id, BARS)
    B.offbeat(intro, ohat.id, BARS, 0.45)

    groove = pr.add_pattern("Groove", PLEN)
    B.four_on_floor(groove, kick.id, BARS)
    B.backbeat(groove, clap.id, BARS, 0.9)
    B.offbeat(groove, ohat.id, BARS, 0.6)
    B.sixteenths(groove, chat.id, BARS, 0.26, 0.4, 0.1, rng)
    B.bass_track(groove, bass.id, chords, "offbeat", -24)
    B.chord_track(groove, keys.id, chords, 0.55, stab_steps=(0, 6, 8, 14))

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, keys.id, chords, 0.65, stab_steps=(0, 6, 8, 14))
    B.chord_track(brk, saws.id, chords, 0.35)
    B.steps_at(brk, crash.id, (0,), 1, 48, 0.5)

    build = pr.add_pattern("Build", PLEN)
    B.four_on_floor(build, kick.id, BARS, 1.0, skip_last=2)
    B.sixteenths(build, chat.id, BARS, 0.3, 0.55, 0.08, rng)
    B.chord_track(build, saws.id, chords, 0.4)
    B.riser(build, rise.id, BARS)
    B.fill(build, clap.id, BARS - 1, "build")

    drop = pr.add_pattern("Drop", PLEN)
    B.four_on_floor(drop, kick.id, BARS)
    B.backbeat(drop, clap.id, BARS, 0.95)
    B.offbeat(drop, ohat.id, BARS, 0.65)
    B.sixteenths(drop, chat.id, BARS, 0.26, 0.42, 0.1, rng)
    B.bass_track(drop, bass.id, chords, "offbeat", -24)
    B.chord_track(drop, saws.id, chords, 0.45)
    B.steps_at(drop, crash.id, (0,), 1, 48, 0.55)
    B.melody_track(drop, lead.id, pr.root, pr.scale,
                   [(0, 7, 8), (8, 6, 8), (16, 4, 8), (24, 5, 8),
                    (32, 7, 8), (40, 9, 8), (48, 7, 12), (60, 6, 4)], 5, 0.8)

    outro = pr.add_pattern("Outro", PLEN)
    B.four_on_floor(outro, kick.id, BARS)
    B.chord_track(outro, keys.id, chords, 0.5, stab_steps=(0, 8))

    _arrange(pr, [("Intro", 2), ("Groove", 2), ("Break", 2), ("Build", 1),
                  ("Drop", 4), ("Break", 1), ("Build", 1), ("Drop", 4), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
# 3. Piano house
# --------------------------------------------------------------------------
def piano_house() -> Project:
    pr = Project(name="Piano House", bpm=126, root=1, scale="Major (Ionian)")
    rng = random.Random(11)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 170, "end_hz": 49,
                                           "decay": 0.38, "punch": 1.9, "drive": 0.25})
    clap = pr.add_channel("clap", "Clap", {"tone": 1700, "decay": 0.26})
    ohat = pr.add_channel("hat", "Open Hat", {"decay": 0.28, "level": 0.33})
    chat = pr.add_channel("hat", "Closed Hat", {"decay": 0.038, "level": 0.27})
    bass = pr.add_channel("bass", "Bass", {"cutoff": 460, "sub": 0.95, "saw": 0.4})
    piano = pr.add_channel("fm", "Piano", {"ratio": 1.0, "index": 2.6,
                                           "fm_decay": 0.35, "decay": 1.6,
                                           "release": 0.4, "level": 0.55,
                                           "second": 0.25})
    organ = pr.add_channel("organ", "Organ Stab", {"cutoff": 5000, "decay": 0.3,
                                                   "sustain": 0.0, "level": 0.4})
    lead = pr.add_channel("supersaw", "Lead", {"detune": 0.28, "cutoff": 9500,
                                               "sustain": 0.85, "level": 0.28})

    for c, amt in ((bass, 0.85), (piano, 0.5), (organ, 0.6), (lead, 0.55)):
        c.sc_amount = amt
    piano.sends.reverb, piano.sends.delay = 0.35, 0.25
    lead.sends.reverb = 0.3
    organ.sends.delay = 0.2

    chords = B.resolve_progression("I - V - vi - IV", pr.root, pr.scale, BARS, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.chord_track(intro, piano.id, chords, 0.7, stab_steps=(0, 3, 6, 8, 11, 14))
    B.four_on_floor(intro, kick.id, BARS)

    groove = pr.add_pattern("Groove", PLEN)
    B.four_on_floor(groove, kick.id, BARS)
    B.backbeat(groove, clap.id, BARS, 0.85)
    B.offbeat(groove, ohat.id, BARS, 0.6)
    B.sixteenths(groove, chat.id, BARS, 0.25, 0.4, 0.1, rng)
    B.bass_track(groove, bass.id, chords, "offbeat", -24)
    B.chord_track(groove, piano.id, chords, 0.65, stab_steps=(0, 3, 6, 8, 11, 14))

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, piano.id, chords, 0.72, stab_steps=(0, 3, 6, 8, 11, 14))
    B.chord_track(brk, organ.id, chords, 0.3, stab_steps=(2, 10))

    build = pr.add_pattern("Build", PLEN)
    B.four_on_floor(build, kick.id, BARS, 1.0, skip_last=2)
    B.sixteenths(build, chat.id, BARS, 0.3, 0.5, 0.08, rng)
    B.chord_track(build, piano.id, chords, 0.7, stab_steps=(0, 3, 6, 8, 11, 14))

    drop = pr.add_pattern("Drop", PLEN)
    B.four_on_floor(drop, kick.id, BARS)
    B.backbeat(drop, clap.id, BARS, 0.9)
    B.offbeat(drop, ohat.id, BARS, 0.62)
    B.sixteenths(drop, chat.id, BARS, 0.25, 0.42, 0.1, rng)
    B.bass_track(drop, bass.id, chords, "offbeat", -24)
    B.chord_track(drop, piano.id, chords, 0.62, stab_steps=(0, 3, 6, 8, 11, 14))
    B.chord_track(drop, organ.id, chords, 0.28, stab_steps=(2, 6, 10, 14))
    B.melody_track(drop, lead.id, pr.root, pr.scale,
                   [(0, 4, 8), (8, 5, 8), (16, 4, 4), (20, 2, 12),
                    (32, 4, 8), (40, 7, 8), (48, 5, 16)], 5, 0.75)

    outro = pr.add_pattern("Outro", PLEN)
    B.four_on_floor(outro, kick.id, BARS)
    B.chord_track(outro, piano.id, chords, 0.55, stab_steps=(0, 8))

    _arrange(pr, [("Intro", 2), ("Groove", 2), ("Break", 2), ("Build", 1),
                  ("Drop", 4), ("Break", 1), ("Drop", 2), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
# 4. Deep organic — sparse, textural
# --------------------------------------------------------------------------
def deep_organic() -> Project:
    pr = Project(name="Deep Organic", bpm=120, root=2, scale="Minor (Aeolian)",
                 swing=0.12)
    rng = random.Random(5)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 120, "end_hz": 44,
                                           "decay": 0.5, "punch": 1.1,
                                           "click": 0.18, "drive": 0.1})
    rim = pr.add_channel("perc", "Rim", {"hz": 900, "decay": 0.04, "noise": 0.55,
                                         "level": 0.4})
    shk = pr.add_channel("hat", "Shaker", {"decay": 0.05, "metal": 0.1,
                                           "hp": 5200, "level": 0.22})
    cga = pr.add_channel("perc", "Conga", {"hz": 300, "decay": 0.16, "noise": 0.2,
                                           "bend": 0.4, "level": 0.42})
    bass = pr.add_channel("bass", "Deep Sub", {"cutoff": 260, "sub": 1.1,
                                               "saw": 0.15, "decay": 0.6,
                                               "sustain": 0.9})
    stab = pr.add_channel("pluck", "Stab", {"cutoff": 700, "resonance": 6.0,
                                            "env_amt": 2.6, "f_decay": 0.2,
                                            "decay": 0.35, "level": 0.5})
    pad = pr.add_channel("pad", "Texture", {"cutoff": 1500, "attack": 2.0,
                                            "release": 3.0, "level": 0.42,
                                            "drift": 0.25})
    choir = pr.add_channel("choir", "Voices", {"level": 0.3, "attack": 0.8})

    for c, amt in ((bass, 0.8), (stab, 0.55), (pad, 0.5), (choir, 0.45)):
        c.sc_amount, c.sc_release = amt, 0.34
    stab.sends.reverb, stab.sends.delay = 0.42, 0.35
    pad.sends.reverb = 0.6
    choir.sends.reverb = 0.55
    cga.sends.reverb = 0.3
    pr.master["reverb"]["size"] = 0.85
    pr.master["delay"]["division"] = 3

    chords = B.resolve_progression("VI - III - VII - i", pr.root, pr.scale, BARS, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.four_on_floor(intro, kick.id, BARS, 0.9)
    B.euclid(intro, shk.id, BARS, 7, 16, 48, 0.3, 1)
    B.chord_track(intro, pad.id, chords, 0.45)

    groove = pr.add_pattern("Groove", PLEN)
    B.four_on_floor(groove, kick.id, BARS, 0.95)
    B.euclid(groove, shk.id, BARS, 9, 16, 48, 0.3, 1)
    B.euclid(groove, cga.id, BARS, 5, 16, 48, 0.5, 2)
    B.steps_at(groove, rim.id, (4, 12), BARS, 48, 0.45)
    B.bass_track(groove, bass.id, chords, "offbeat", -24)
    B.arp_track(groove, stab.id, chords, "wide", 2, 2, 0.6, 2, 2)
    B.chord_track(groove, pad.id, chords, 0.42)

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, pad.id, chords, 0.55)
    B.chord_track(brk, choir.id, chords, 0.4)
    B.euclid(brk, shk.id, BARS, 5, 16, 48, 0.25, 1)

    drop = pr.add_pattern("Drop", PLEN)
    B.four_on_floor(drop, kick.id, BARS)
    B.euclid(drop, shk.id, BARS, 11, 16, 48, 0.32, 1)
    B.euclid(drop, cga.id, BARS, 7, 16, 48, 0.5, 2)
    B.steps_at(drop, rim.id, (4, 12), BARS, 48, 0.5)
    B.bass_track(drop, bass.id, chords, "rolling", -24, 0.9)
    B.arp_track(drop, stab.id, chords, "wide", 2, 2, 0.7, 2, 2)
    B.chord_track(drop, pad.id, chords, 0.45)
    B.chord_track(drop, choir.id, chords, 0.3)

    outro = pr.add_pattern("Outro", PLEN)
    B.four_on_floor(outro, kick.id, BARS, 0.85)
    B.chord_track(outro, pad.id, chords, 0.4)

    _arrange(pr, [("Intro", 2), ("Groove", 3), ("Break", 2), ("Drop", 4),
                  ("Break", 1), ("Drop", 2), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
# 5. Tropical / deep melodic
# --------------------------------------------------------------------------
def tropical_deep() -> Project:
    pr = Project(name="Tropical Deep", bpm=122, root=4, scale="Minor (Aeolian)")
    rng = random.Random(13)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 140, "end_hz": 48,
                                           "decay": 0.36, "punch": 1.2,
                                           "click": 0.25})
    clap = pr.add_channel("clap", "Clap", {"tone": 1400, "decay": 0.2, "level": 0.55})
    shk = pr.add_channel("hat", "Shaker", {"decay": 0.045, "metal": 0.15,
                                           "hp": 6000, "level": 0.24})
    ohat = pr.add_channel("hat", "Open Hat", {"decay": 0.22, "level": 0.26})
    perc = pr.add_channel("perc", "Wood", {"hz": 780, "decay": 0.06, "noise": 0.3,
                                           "level": 0.38})
    bass = pr.add_channel("bass", "Bass", {"cutoff": 400, "sub": 1.0, "saw": 0.25})
    mar = pr.add_channel("fm", "Marimba", {"ratio": 3.0, "index": 3.4,
                                           "fm_decay": 0.08, "decay": 0.5,
                                           "release": 0.3, "level": 0.55})
    pad = pr.add_channel("pad", "Air Pad", {"cutoff": 3000, "attack": 1.4,
                                            "level": 0.34})
    lead = pr.add_channel("pluck", "Flute Lead", {"cutoff": 3200, "resonance": 1.6,
                                                  "env_amt": 1.2, "attack": 0.03,
                                                  "decay": 0.6, "sustain": 0.4,
                                                  "release": 0.4, "sub": 0.0,
                                                  "level": 0.42, "vibrato": 0.15})

    for c, amt in ((bass, 0.8), (mar, 0.55), (pad, 0.45), (lead, 0.4)):
        c.sc_amount = amt
    mar.sends.reverb, mar.sends.delay = 0.32, 0.3
    pad.sends.reverb = 0.5
    lead.sends.reverb, lead.sends.delay = 0.35, 0.25
    perc.sends.reverb = 0.3

    chords = B.resolve_progression("VI - VII - i - i", pr.root, pr.scale, BARS, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.arp_track(intro, mar.id, chords, "pulse", 2, 2, 0.6, 2, 2)
    B.euclid(intro, shk.id, BARS, 7, 16, 48, 0.28, 1)

    groove = pr.add_pattern("Groove", PLEN)
    B.four_on_floor(groove, kick.id, BARS)
    B.backbeat(groove, clap.id, BARS, 0.75)
    B.euclid(groove, shk.id, BARS, 11, 16, 48, 0.3, 1)
    B.offbeat(groove, ohat.id, BARS, 0.45)
    B.euclid(groove, perc.id, BARS, 5, 16, 48, 0.4, 3)
    B.bass_track(groove, bass.id, chords, "offbeat", -24)
    B.arp_track(groove, mar.id, chords, "pulse", 2, 2, 0.7, 2, 2)
    B.chord_track(groove, pad.id, chords, 0.4)

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, pad.id, chords, 0.5)
    B.arp_track(brk, mar.id, chords, "updown", 2, 2, 0.55, 2, 2)
    B.euclid(brk, shk.id, BARS, 5, 16, 48, 0.25, 1)

    drop = pr.add_pattern("Drop", PLEN)
    B.four_on_floor(drop, kick.id, BARS)
    B.backbeat(drop, clap.id, BARS, 0.8)
    B.euclid(drop, shk.id, BARS, 11, 16, 48, 0.32, 1)
    B.offbeat(drop, ohat.id, BARS, 0.48)
    B.euclid(drop, perc.id, BARS, 7, 16, 48, 0.42, 3)
    B.bass_track(drop, bass.id, chords, "offbeat", -24)
    B.arp_track(drop, mar.id, chords, "pulse", 2, 2, 0.75, 2, 2)
    B.chord_track(drop, pad.id, chords, 0.42)
    B.melody_track(drop, lead.id, pr.root, pr.scale,
                   [(0, 4, 8), (8, 3, 4), (12, 2, 4), (16, 4, 12),
                    (32, 5, 8), (40, 4, 8), (48, 2, 16)], 5, 0.7)

    outro = pr.add_pattern("Outro", PLEN)
    B.four_on_floor(outro, kick.id, BARS, 0.9)
    B.arp_track(outro, mar.id, chords, "pulse", 2, 2, 0.5, 2, 2)

    _arrange(pr, [("Intro", 2), ("Groove", 3), ("Break", 2), ("Drop", 4),
                  ("Break", 1), ("Drop", 2), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
# 6. Cinematic synthwave — slower, analogue
# --------------------------------------------------------------------------
def cinematic_synth() -> Project:
    pr = Project(name="Cinematic Synth", bpm=105, root=7, scale="Dorian")
    rng = random.Random(17)

    kick = pr.add_channel("kick", "Kick", {"start_hz": 200, "end_hz": 52,
                                           "decay": 0.3, "punch": 2.4,
                                           "click": 0.5, "drive": 0.35})
    snare = pr.add_channel("snare", "Snare", {"body_hz": 200, "decay": 0.26,
                                              "snap": 0.9, "level": 0.6})
    chat = pr.add_channel("hat", "Hat", {"decay": 0.05, "level": 0.24})
    bass = pr.add_channel("reese", "Analog Bass", {"cutoff": 620, "resonance": 3.2,
                                                   "env_amt": 1.4, "f_decay": 0.18,
                                                   "detune": 0.2, "level": 0.55,
                                                   "drive": 0.3})
    arp = pr.add_channel("pluck", "Arp", {"cutoff": 1500, "resonance": 4.0,
                                          "env_amt": 2.4, "f_decay": 0.1,
                                          "decay": 0.18, "level": 0.5})
    pad = pr.add_channel("pad", "Strings", {"cutoff": 2400, "attack": 1.0,
                                            "release": 2.6, "level": 0.42})
    lead = pr.add_channel("supersaw", "Lead", {"detune": 0.22, "cutoff": 6000,
                                               "attack": 0.05, "sustain": 0.8,
                                               "release": 0.5, "level": 0.26,
                                               "vibrato": 0.2})

    for c, amt in ((bass, 0.55), (arp, 0.4), (pad, 0.4), (lead, 0.35)):
        c.sc_amount, c.sc_release = amt, 0.26
    arp.sends.reverb, arp.sends.delay = 0.35, 0.4
    pad.sends.reverb = 0.6
    lead.sends.reverb, lead.sends.delay = 0.4, 0.3
    snare.sends.reverb = 0.35
    pr.master["delay"]["division"] = 2
    pr.master["reverb"]["size"] = 0.82

    chords = B.resolve_progression("i - VI - VII - v", pr.root, pr.scale, BARS, 3)

    intro = pr.add_pattern("Intro", PLEN)
    B.arp_track(intro, arp.id, chords, "up", 2, 2, 0.6, 1, 2)
    B.chord_track(intro, pad.id, chords, 0.45)

    groove = pr.add_pattern("Groove", PLEN)
    B.steps_at(groove, kick.id, (0, 6, 10), BARS, 48, 0.95)
    B.backbeat(groove, snare.id, BARS, 0.8)
    B.sixteenths(groove, chat.id, BARS, 0.22, 0.36, 0.1, rng)
    B.bass_track(groove, bass.id, chords, "eighths", -24)
    B.arp_track(groove, arp.id, chords, "up", 2, 2, 0.7, 1, 2)
    B.chord_track(groove, pad.id, chords, 0.45)

    brk = pr.add_pattern("Break", PLEN)
    B.chord_track(brk, pad.id, chords, 0.6)
    B.arp_track(brk, arp.id, chords, "updown", 2, 2, 0.55, 1, 2)

    drop = pr.add_pattern("Drop", PLEN)
    B.steps_at(drop, kick.id, (0, 6, 10), BARS, 48, 1.0)
    B.backbeat(drop, snare.id, BARS, 0.85)
    B.sixteenths(drop, chat.id, BARS, 0.22, 0.38, 0.1, rng)
    B.bass_track(drop, bass.id, chords, "eighths", -24)
    B.arp_track(drop, arp.id, chords, "up", 2, 2, 0.75, 1, 2)
    B.chord_track(drop, pad.id, chords, 0.45)
    B.melody_track(drop, lead.id, pr.root, pr.scale,
                   [(0, 4, 12), (16, 3, 8), (24, 4, 8), (32, 6, 12),
                    (48, 4, 16)], 5, 0.7)

    outro = pr.add_pattern("Outro", PLEN)
    B.chord_track(outro, pad.id, chords, 0.4)
    B.arp_track(outro, arp.id, chords, "up", 2, 2, 0.45, 1, 2)

    _arrange(pr, [("Intro", 2), ("Groove", 3), ("Break", 2), ("Drop", 4),
                  ("Break", 1), ("Drop", 2), ("Outro", 1)])
    return pr


# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Template:
    key: str
    name: str
    bpm: int
    blurb: str
    build: Callable[[], Project]


TEMPLATES: tuple[Template, ...] = (
    Template("melodic", "Melodic House", 122,
             "Arp-led and cinematic. Rolling plucks, deep sub, wide pads.",
             melodic_house),
    Template("progressive", "Progressive Anthem", 126,
             "Big supersaw chords, piano break, festival drop.",
             progressive_anthem),
    Template("piano", "Piano House", 126,
             "Bright piano riff over a driving four-to-the-floor groove.",
             piano_house),
    Template("organic", "Deep Organic", 120,
             "Sparse and textural. Swung percussion, deep sub, evolving pad.",
             deep_organic),
    Template("tropical", "Tropical Deep", 122,
             "Marimba plucks, soft kick, airy pad and a flute lead.",
             tropical_deep),
    Template("synthwave", "Cinematic Synth", 105,
             "Slower and analogue. Reese bass, gated strings, wide arp.",
             cinematic_synth),
)


def empty_project() -> Project:
    """A blank slate with a sensible starter kit."""
    pr = Project(name="Untitled", bpm=124)
    for key, name in (("kick", "Kick"), ("clap", "Clap"), ("hat", "Hat"),
                      ("bass", "Bass"), ("pluck", "Pluck"), ("pad", "Pad")):
        pr.add_channel(key, name)
    pr.add_pattern("Pattern 1", 16)
    return pr


def by_key(key: str) -> Template | None:
    for t in TEMPLATES:
        if t.key == key:
            return t
    return None
