"""One-click sample kits, rendered locally by Encantado's own synthesis engine.

There is no download and no account, because there does not need to be: the app
already contains the instruments. Everything here is generated on your machine
from the same DSP the sequencer uses, so it carries no third-party licence and
arrives already named for the library's classifier to pick up.

Sources that genuinely cannot be automated — Spitfire LABS needs its own
installer, Cymatics and 99Sounds need an email signup, Freesound needs a
personal API key — stay as links in the Packs tab rather than being scraped.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ..audio.wavio import write_wav
from ..core.project import instrument_spec
from ..core.theory import note_name
from ..dsp.base import SR
from ..dsp.params import defaults_for

MAX_SECONDS = 6.0


@dataclass(frozen=True)
class KitVoice:
    role: str                                   # becomes the filename prefix
    instrument: str
    count: int = 4
    base: dict = field(default_factory=dict)
    vary: dict = field(default_factory=dict)    # param -> (low, high) absolute
    pitches: tuple[int, ...] = ()               # melodic voices only
    hold: float = 0.0                           # seconds before note-off


@dataclass(frozen=True)
class Kit:
    key: str
    name: str
    blurb: str
    voices: tuple[KitVoice, ...]

    @property
    def total(self) -> int:
        return sum(v.count * max(len(v.pitches), 1) for v in self.voices)


def _render_voice(instrument: str, params: dict, pitch: int, hold: float,
                  sr: int = SR) -> np.ndarray:
    spec = instrument_spec(instrument)
    if spec is None:
        return np.zeros(0, dtype=np.float32)
    voice = spec["cls"](dict(params), pitch, 1.0, sr)
    blocks: list[np.ndarray] = []
    n = 0
    limit = int(MAX_SECONDS * sr)
    hold_n = int(hold * sr)
    released = hold_n <= 0
    while n < limit:
        blocks.append(voice.render(512))
        n += 512
        if not released and n >= hold_n:
            voice.note_off()
            released = True
        if released and not voice.active:
            break
    if not blocks:
        return np.zeros(0, dtype=np.float32)
    audio = np.concatenate(blocks)
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-4:
        return np.zeros(0, dtype=np.float32)
    audio = audio / peak * 0.89
    # trim the silent tail, then fade so nothing clicks
    env = np.max(np.abs(audio), axis=1)
    live = np.where(env > 3e-4)[0]
    if live.size:
        audio = audio[: min(len(audio), live[-1] + 512)]
    fade = min(256, len(audio) // 8)
    if fade > 4:
        audio[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
    return audio.astype(np.float32)


def render_kit(kit: Kit, out_dir: str, progress=None, seed: int = 0,
               sr: int = SR) -> list[str]:
    """Render every sample in `kit` into `out_dir`. Returns the paths written."""
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    written: list[str] = []
    done = 0
    total = max(kit.total, 1)
    for voice in kit.voices:
        spec = instrument_spec(voice.instrument)
        if spec is None:
            continue
        pitches = voice.pitches or (48,)
        for pitch in pitches:
            for i in range(voice.count):
                params = defaults_for(spec["params"])
                params.update(voice.base)
                for key, (lo, hi) in voice.vary.items():
                    t = i / max(voice.count - 1, 1)
                    # sweep the range rather than sampling it, so a kit covers
                    # its span evenly instead of clustering by luck
                    jitter = float(rng.uniform(-0.06, 0.06))
                    params[key] = float(lo + (hi - lo) * min(max(t + jitter, 0.0), 1.0))
                audio = _render_voice(voice.instrument, params, pitch,
                                      voice.hold, sr)
                done += 1
                if audio.size == 0:
                    continue
                if voice.pitches:
                    # the octave has to be in the name: two pitches a class
                    # apart would otherwise write to the same file
                    note = note_name(pitch).replace("#", "s")
                    name = f"{voice.role}_{note}_{i + 1:02d}.wav"
                else:
                    name = f"{voice.role}_{i + 1:02d}.wav"
                path = os.path.join(out_dir, name)
                write_wav(path, audio, sr)
                written.append(path)
                if progress is not None and progress(done / total, name) is False:
                    return written
    return written


# --------------------------------------------------------------------------
# The kits. Ranges are chosen to sweep a musically useful span, not to be random.
# --------------------------------------------------------------------------
def _kick(count, start, end, decay, punch, click=(0.2, 0.45), drive=(0.1, 0.3)):
    return KitVoice("Kick", "kick", count,
                    base={},
                    vary={"start_hz": start, "end_hz": end, "decay": decay,
                          "punch": punch, "click": click, "drive": drive})


KITS: tuple[Kit, ...] = (
    Kit("melodic", "Melodic House Kit",
        "Rounded kicks, soft claps, tight hats, organic percussion and plucks — "
        "the Warakls / NTO / Joachim Pastor palette.",
        (
            _kick(5, (130, 175), (44, 50), (0.34, 0.5), (1.0, 1.8)),
            KitVoice("Clap", "clap", 4, vary={"tone": (1200, 1900),
                                              "decay": (0.16, 0.32),
                                              "tail": (0.3, 0.7)}),
            KitVoice("Hat", "hat", 5, vary={"decay": (0.025, 0.075),
                                            "hp": (6000, 9000),
                                            "metal": (0.3, 0.7)}),
            KitVoice("OpenHat", "hat", 3, vary={"decay": (0.18, 0.38),
                                                "hp": (6000, 8500),
                                                "metal": (0.35, 0.6)}),
            KitVoice("Perc", "perc", 5, vary={"hz": (260, 780),
                                              "decay": (0.05, 0.18),
                                              "noise": (0.15, 0.5)}),
            KitVoice("Shaker", "hat", 3, base={"metal": 0.1, "hp": 5200},
                     vary={"decay": (0.035, 0.07)}),
            KitVoice("Rim", "perc", 3, base={"noise": 0.55},
                     vary={"hz": (700, 1200), "decay": (0.02, 0.06)}),
            KitVoice("Pluck", "pluck", 3, pitches=(48, 60), hold=0.25,
                     vary={"cutoff": (700, 1600), "resonance": (3.0, 6.5),
                           "decay": (0.18, 0.4)}),
            KitVoice("Sub", "bass", 2, pitches=(33,), hold=0.5,
                     vary={"cutoff": (200, 420)}),
        )),
    Kit("progressive", "Progressive Anthem Kit",
        "Punchy kicks, wide claps, bright hats, crashes, risers and supersaw "
        "stabs — festival territory.",
        (
            _kick(5, (160, 210), (46, 54), (0.3, 0.46), (1.6, 2.8),
                  click=(0.3, 0.6), drive=(0.2, 0.45)),
            KitVoice("Clap", "clap", 4, vary={"tone": (1500, 2200),
                                              "decay": (0.2, 0.36),
                                              "spread": (0.006, 0.014)}),
            KitVoice("Snare", "snare", 3, vary={"body_hz": (170, 230),
                                                "decay": (0.14, 0.26),
                                                "snap": (0.7, 1.1)}),
            KitVoice("Hat", "hat", 4, vary={"decay": (0.02, 0.06),
                                            "hp": (7500, 10500)}),
            KitVoice("Crash", "cymbal", 3, vary={"decay": (1.0, 2.6),
                                                 "hp": (3500, 5500)}),
            KitVoice("Riser", "sweep", 3, vary={"dur": (1.5, 4.0),
                                                "to_hz": (7000, 12000)}),
            KitVoice("Stab", "supersaw", 3, pitches=(48,), hold=0.3,
                     vary={"detune": (0.2, 0.5), "cutoff": (4000, 10000)}),
        )),
    Kit("organic", "Deep Organic Kit",
        "Soft kicks, rims, congas, shakers and wood — the sparse, textural end.",
        (
            _kick(4, (105, 140), (42, 48), (0.4, 0.6), (0.8, 1.3),
                  click=(0.1, 0.28), drive=(0.05, 0.18)),
            KitVoice("Conga", "perc", 5, vary={"hz": (200, 480),
                                               "decay": (0.09, 0.24),
                                               "bend": (0.2, 0.6),
                                               "noise": (0.1, 0.3)}),
            KitVoice("Rim", "perc", 4, base={"noise": 0.6},
                     vary={"hz": (750, 1300), "decay": (0.02, 0.055)}),
            KitVoice("Shaker", "hat", 4, base={"metal": 0.08},
                     vary={"decay": (0.03, 0.08), "hp": (4500, 7000)}),
            KitVoice("Wood", "perc", 4, base={"noise": 0.35, "bend": 0.15},
                     vary={"hz": (500, 1000), "decay": (0.03, 0.09)}),
            KitVoice("Tom", "tom", 3, vary={"hz": (110, 260),
                                            "decay": (0.25, 0.55)}),
            KitVoice("Sub", "bass", 2, pitches=(31,), hold=0.7,
                     vary={"cutoff": (160, 300)}),
        )),
    Kit("tropical", "Tropical Deep Kit",
        "Soft kick, marimba hits, shakers, wood and airy plucks.",
        (
            _kick(4, (120, 155), (44, 50), (0.3, 0.42), (0.9, 1.5)),
            KitVoice("Clap", "clap", 3, vary={"tone": (1100, 1600),
                                              "decay": (0.14, 0.26)}),
            KitVoice("Shaker", "hat", 4, base={"metal": 0.12},
                     vary={"decay": (0.03, 0.07), "hp": (5500, 8000)}),
            KitVoice("Wood", "perc", 4, base={"noise": 0.3},
                     vary={"hz": (600, 1100), "decay": (0.03, 0.08)}),
            KitVoice("Marimba", "fm", 4, pitches=(60, 72), hold=0.1,
                     base={"ratio": 3.0}, vary={"index": (2.0, 4.5),
                                                "fm_decay": (0.05, 0.14),
                                                "decay": (0.3, 0.7)}),
            KitVoice("Flute", "pluck", 2, pitches=(72,), hold=0.6,
                     base={"sub": 0.0, "vibrato": 0.15},
                     vary={"cutoff": (2200, 4200)}),
        )),
    Kit("synthwave", "Cinematic Synth Kit",
        "Analogue kicks, gated snares, toms, reese basses and arp plucks.",
        (
            _kick(4, (175, 225), (48, 56), (0.24, 0.38), (1.8, 3.2),
                  click=(0.35, 0.65), drive=(0.25, 0.5)),
            KitVoice("Snare", "snare", 4, vary={"body_hz": (180, 260),
                                                "decay": (0.18, 0.34),
                                                "snap": (0.7, 1.0)}),
            KitVoice("Tom", "tom", 4, vary={"hz": (100, 300),
                                            "decay": (0.2, 0.5),
                                            "bend": (0.3, 0.9)}),
            KitVoice("Hat", "hat", 3, vary={"decay": (0.025, 0.07),
                                            "hp": (6500, 9500)}),
            KitVoice("Reese", "reese", 3, pitches=(36,), hold=0.6,
                     vary={"cutoff": (400, 900), "detune": (0.2, 0.5)}),
            KitVoice("Arp", "pluck", 3, pitches=(60,), hold=0.15,
                     vary={"cutoff": (1100, 2400), "resonance": (2.5, 5.5)}),
        )),
    Kit("fx", "FX & Transitions",
        "Risers, downlifters, impacts and noise sweeps for build-ups and drops.",
        (
            KitVoice("Riser", "sweep", 5, vary={"dur": (1.0, 4.0),
                                                "from_hz": (200, 600),
                                                "to_hz": (6000, 13000),
                                                "q": (0.8, 2.5)}),
            KitVoice("Downlifter", "sweep", 4, vary={"dur": (0.8, 2.5),
                                                     "from_hz": (8000, 12000),
                                                     "to_hz": (200, 600)}),
            KitVoice("Impact", "kick", 3, base={"click": 0.7, "drive": 0.6},
                     vary={"start_hz": (200, 380), "end_hz": (32, 44),
                           "decay": (0.7, 1.4), "punch": (2.0, 4.0)}),
            KitVoice("Sweep", "sweep", 3, base={"shape": 1.0},
                     vary={"dur": (2.0, 6.0), "q": (2.0, 6.0),
                           "from_hz": (400, 1500), "to_hz": (4000, 9000)}),
            KitVoice("Crash", "cymbal", 3, vary={"decay": (1.4, 4.0),
                                                 "hp": (2500, 5000)}),
        )),
)


def safe_dirname(name: str) -> str:
    """Folder name safe for shells and every filesystem we might land on."""
    keep = [c if (c.isalnum() or c in "-_") else "_" for c in name]
    out = "".join(keep)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_") or "Kit"


def kit(key: str) -> Kit | None:
    for k in KITS:
        if k.key == key:
            return k
    return None


def default_kit_root() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "encantado", "kits")
