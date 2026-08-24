"""Synthesised drums — 909/808 lineage, tuned for modern house and techno.

Each drum is a one-shot voice with the same contract as a melodic Voice. They
are tunable: `pitch` shifts the whole drum in semitones relative to C3 (MIDI 48),
so you can tune the kick to the key of the track.
"""
from __future__ import annotations

import numpy as np

from .base import SR, DecayEnv, equal_power_pan, soft_clip
from .filters import ModFilter
from .params import Param

_rng = np.random.default_rng()
REF_NOTE = 48.0          # C3 = "as designed"

# TR-808 style inharmonic partial ratios — what makes metal sound like metal
METAL_RATIOS = (1.0, 1.4471, 1.6170, 1.9265, 2.5028, 2.6637)


class DrumVoice:
    """Base one-shot percussion voice."""

    is_drum = True

    def __init__(self, params: dict, pitch: int = 48, velocity: float = 1.0,
                 sr: int = SR):
        self.p = params
        self.sr = sr
        self.vel = float(velocity)
        self.tune = 2.0 ** ((float(pitch) - REF_NOTE + params.get("tune", 0.0)) / 12.0)
        self.t = 0                       # samples elapsed
        self.dead = False
        self._build()

    def _build(self) -> None:
        pass

    def note_off(self) -> None:          # one-shots ignore note-off
        pass

    @property
    def active(self) -> bool:
        return not self.dead

    def _time(self, n: int) -> np.ndarray:
        t = (self.t + np.arange(n, dtype=np.float64)) / self.sr
        self.t += n
        return t

    def _finish(self, mono: np.ndarray, n: int) -> np.ndarray:
        drive = self.p.get("drive", 0.0)
        if drive > 1e-3:
            mono = soft_clip(mono * (1.0 + drive * 5.0), 1.0 + drive * 6.0)
        mono = mono * (self.p.get("level", 0.9) * self.vel)
        gl, gr = equal_power_pan(self.p.get("pan", 0.0))
        return np.stack((mono * gl, mono * gr), axis=-1).astype(np.float32)

    def _noise(self, n: int) -> np.ndarray:
        return _rng.standard_normal(n).astype(np.float32)


def _exp_env(t: np.ndarray, decay: float, curve: float = 1.0) -> np.ndarray:
    """Exponential decay from 1 -> 0 over roughly `decay` seconds."""
    return np.exp(-t / max(decay / 5.0, 1e-5)) ** curve


def _attack_shape(t: np.ndarray, attack: float = 0.0008) -> np.ndarray:
    """Tiny attack ramp so nothing clicks on sample 0."""
    return np.minimum(t / max(attack, 1e-6), 1.0)


# --------------------------------------------------------------------------
class Kick(DrumVoice):
    """Pitch-swept sine with a click transient. The centre of the record."""

    def _build(self) -> None:
        self._ph = 0.0
        self._hp = ModFilter("hp", 2, self.sr, 1)

    def render(self, n):
        p = self.p
        t = self._time(n)
        total = p.get("decay", 0.42) + 0.05
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)

        f_start = p.get("start_hz", 160.0) * self.tune
        f_end = p.get("end_hz", 48.0) * self.tune
        pdec = max(p.get("pitch_decay", 0.028), 1e-4)
        freq = f_end + (f_start - f_end) * np.exp(-t / pdec)

        self._ph += float(np.sum(freq)) / self.sr
        ph = np.cumsum(freq) / self.sr + (self._ph - float(np.sum(freq)) / self.sr)
        body = np.sin(2 * np.pi * ph)

        amp = _exp_env(t, p.get("decay", 0.42), p.get("curve", 1.0))
        amp *= _attack_shape(t, 0.0006)
        out = body * amp

        click = p.get("click", 0.35)
        if click > 1e-3:
            cl = self._noise(n) * np.exp(-t / 0.0016) * click
            out = out + self._hp.process(cl, 1800.0, 0.7)

        out = np.tanh(out * (1.0 + p.get("punch", 1.4)))
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


KICK_PARAMS = (
    Param("start_hz", "Punch Hz", 60.0, 400.0, 160.0, "hz", "log", "Tone"),
    Param("end_hz", "Body Hz", 30.0, 120.0, 48.0, "hz", "log", "Tone"),
    Param("pitch_decay", "Pitch Dec", 0.003, 0.2, 0.028, "ms", "log", "Tone"),
    Param("decay", "Decay", 0.05, 1.6, 0.42, "ms", "log", "Tone"),
    Param("curve", "Curve", 0.3, 3.0, 1.0, "", "lin", "Tone"),
    Param("click", "Click", 0.0, 1.0, 0.35, "%", "lin", "Tone"),
    Param("punch", "Punch", 0.0, 6.0, 1.4, "", "lin", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.15, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.95, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Snare(DrumVoice):
    def _build(self) -> None:
        self._bp = ModFilter("bp", 2, self.sr, 1)
        self._hp = ModFilter("hp", 2, self.sr, 1)

    def render(self, n):
        p = self.p
        t = self._time(n)
        total = max(p.get("decay", 0.18), p.get("body_decay", 0.09)) + 0.05
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)

        f1 = p.get("body_hz", 185.0) * self.tune
        body = (np.sin(2 * np.pi * f1 * t) * 0.6
                + np.sin(2 * np.pi * f1 * 1.78 * t) * 0.4)
        body *= _exp_env(t, p.get("body_decay", 0.09)) * p.get("body", 0.5)

        nz = self._noise(n)
        nz = self._bp.process(nz, p.get("tone", 2400.0), 0.9)
        nz = self._hp.process(nz, 700.0, 0.7)
        nz *= _exp_env(t, p.get("decay", 0.18), p.get("curve", 1.0)) * p.get("snap", 0.85)

        out = (body + nz) * _attack_shape(t, 0.0004)
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


SNARE_PARAMS = (
    Param("body_hz", "Body Hz", 90.0, 400.0, 185.0, "hz", "log", "Tone"),
    Param("body", "Body", 0.0, 1.5, 0.5, "%", "lin", "Tone"),
    Param("body_decay", "Body Dec", 0.01, 0.6, 0.09, "ms", "log", "Tone"),
    Param("tone", "Noise Tone", 600.0, 9000.0, 2400.0, "hz", "log", "Tone"),
    Param("snap", "Snap", 0.0, 1.5, 0.85, "%", "lin", "Tone"),
    Param("decay", "Decay", 0.02, 1.2, 0.18, "ms", "log", "Tone"),
    Param("curve", "Curve", 0.3, 3.0, 1.0, "", "lin", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.1, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.8, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Clap(DrumVoice):
    """Four offset noise bursts + a tail. The 'hands' in house music."""

    def _build(self) -> None:
        self._bp = ModFilter("bp", 2, self.sr, 1)
        self._hp = ModFilter("hp", 2, self.sr, 1)

    def render(self, n):
        p = self.p
        t = self._time(n)
        total = p.get("decay", 0.24) + 0.08
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)

        spread = p.get("spread", 0.009)
        env = np.zeros(n, dtype=np.float32)
        for i, g in enumerate((1.0, 0.85, 0.7, 0.55)):
            off = t - i * spread
            m = off >= 0
            env[m] += (np.exp(-off[m] / 0.0042) * g).astype(np.float32)
        tail_start = t - 3 * spread
        m = tail_start >= 0
        env[m] += np.exp(-tail_start[m] / max(p.get("decay", 0.24) / 5.0, 1e-4)) \
            .astype(np.float32) * p.get("tail", 0.5)

        nz = self._noise(n)
        nz = self._bp.process(nz, p.get("tone", 1500.0), p.get("q", 1.1))
        nz = self._hp.process(nz, 700.0, 0.7)
        out = nz * env
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


CLAP_PARAMS = (
    Param("tone", "Tone", 500.0, 5000.0, 1500.0, "hz", "log", "Tone"),
    Param("q", "Width", 0.3, 6.0, 1.1, "", "log", "Tone"),
    Param("spread", "Spread", 0.002, 0.03, 0.009, "ms", "log", "Tone"),
    Param("tail", "Tail", 0.0, 1.5, 0.5, "%", "lin", "Tone"),
    Param("decay", "Decay", 0.03, 1.0, 0.24, "ms", "log", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.0, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.7, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Hat(DrumVoice):
    """Noise + inharmonic metal partials. Closed and open share one engine."""

    def _build(self) -> None:
        self._hp = ModFilter("hp", 4, self.sr, 1)
        self._bp = ModFilter("bp", 2, self.sr, 1)
        self._phases = _rng.random(len(METAL_RATIOS))

    def render(self, n):
        p = self.p
        t = self._time(n)
        dec = p.get("decay", 0.055)
        total = dec + 0.03
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)

        env = _exp_env(t, dec, p.get("curve", 1.0)) * _attack_shape(t, 0.0003)

        metal = np.zeros(n, dtype=np.float32)
        base = p.get("metal_hz", 1150.0) * self.tune
        for i, r in enumerate(METAL_RATIOS):
            f = base * r
            ph = self._phases[i] + f * t
            metal += np.sign(np.sin(2 * np.pi * ph)).astype(np.float32)
        metal /= len(METAL_RATIOS)
        self._phases = (self._phases + base * np.array(METAL_RATIOS) * (n / self.sr)) % 1.0

        mix = p.get("metal", 0.55)
        src = self._noise(n) * (1.0 - mix) + metal * mix
        src = self._hp.process(src, p.get("hp", 7200.0), 0.7)
        sizzle = self._bp.process(src, p.get("sizzle_hz", 9500.0), 2.0)
        out = (src + sizzle * 0.5) * env
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


HAT_PARAMS = (
    Param("decay", "Decay", 0.008, 1.2, 0.055, "ms", "log", "Tone"),
    Param("curve", "Curve", 0.3, 3.0, 1.0, "", "lin", "Tone"),
    Param("hp", "HP Cut", 2000.0, 12000.0, 7200.0, "hz", "log", "Tone"),
    Param("metal", "Metal", 0.0, 1.0, 0.55, "%", "lin", "Tone"),
    Param("metal_hz", "Metal Hz", 300.0, 3000.0, 1150.0, "hz", "log", "Tone"),
    Param("sizzle_hz", "Sizzle", 5000.0, 15000.0, 9500.0, "hz", "log", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.0, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.45, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Tom(DrumVoice):
    def _build(self) -> None:
        self._ph = 0.0

    def render(self, n):
        p = self.p
        t = self._time(n)
        total = p.get("decay", 0.4) + 0.05
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)
        f0 = p.get("hz", 180.0) * self.tune
        freq = f0 * (1.0 + p.get("bend", 0.6) * np.exp(-t / 0.05))
        ph = np.cumsum(freq) / self.sr + self._ph
        self._ph = float(ph[-1] % 1.0)
        env = _exp_env(t, p.get("decay", 0.4)) * _attack_shape(t, 0.0008)
        out = np.sin(2 * np.pi * ph) * env
        out += self._noise(n) * np.exp(-t / 0.004) * p.get("attack_noise", 0.15)
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


TOM_PARAMS = (
    Param("hz", "Pitch", 60.0, 500.0, 180.0, "hz", "log", "Tone"),
    Param("bend", "Bend", 0.0, 2.0, 0.6, "%", "lin", "Tone"),
    Param("decay", "Decay", 0.05, 1.5, 0.4, "ms", "log", "Tone"),
    Param("attack_noise", "Attack", 0.0, 1.0, 0.15, "%", "lin", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.05, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.7, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Perc(DrumVoice):
    """Conga / rim / wood — the organic layer in NTO and Warakls records."""

    def _build(self) -> None:
        self._bp = ModFilter("bp", 2, self.sr, 1)
        self._ph = 0.0

    def render(self, n):
        p = self.p
        t = self._time(n)
        total = p.get("decay", 0.12) + 0.04
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)
        f0 = p.get("hz", 420.0) * self.tune
        freq = f0 * (1.0 + p.get("bend", 0.25) * np.exp(-t / 0.012))
        ph = np.cumsum(freq) / self.sr + self._ph
        self._ph = float(ph[-1] % 1.0)
        env = _exp_env(t, p.get("decay", 0.12)) * _attack_shape(t, 0.0004)
        tone = np.sin(2 * np.pi * ph) * (1.0 - p.get("noise", 0.3))
        nz = self._bp.process(self._noise(n), p.get("hz", 420.0) * 3.5 * self.tune,
                              p.get("q", 2.0)) * p.get("noise", 0.3)
        out = (tone + nz) * env
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


PERC_PARAMS = (
    Param("hz", "Pitch", 100.0, 2000.0, 420.0, "hz", "log", "Tone"),
    Param("bend", "Bend", 0.0, 2.0, 0.25, "%", "lin", "Tone"),
    Param("noise", "Noise", 0.0, 1.0, 0.3, "%", "lin", "Tone"),
    Param("q", "Noise Q", 0.3, 8.0, 2.0, "", "log", "Tone"),
    Param("decay", "Decay", 0.01, 1.0, 0.12, "ms", "log", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.0, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.6, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class Cymbal(DrumVoice):
    """Crash / ride — long metallic wash, usually on the drop."""

    def _build(self) -> None:
        self._hp = ModFilter("hp", 2, self.sr, 1)
        self._phases = _rng.random(len(METAL_RATIOS))

    def render(self, n):
        p = self.p
        t = self._time(n)
        dec = p.get("decay", 1.6)
        total = dec + 0.1
        if t[0] > total:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)
        env = _exp_env(t, dec, p.get("curve", 1.2)) * _attack_shape(t, 0.001)
        metal = np.zeros(n, dtype=np.float32)
        base = p.get("metal_hz", 620.0) * self.tune
        for i, r in enumerate(METAL_RATIOS):
            metal += np.sign(np.sin(2 * np.pi * (self._phases[i] + base * r * t)))
        self._phases = (self._phases + base * np.array(METAL_RATIOS) * (n / self.sr)) % 1.0
        metal /= len(METAL_RATIOS)
        src = self._noise(n) * 0.55 + metal * 0.45
        out = self._hp.process(src, p.get("hp", 4200.0), 0.7) * env
        if t[-1] > total:
            self.dead = True
        return self._finish(out, n)


CYMBAL_PARAMS = (
    Param("decay", "Decay", 0.1, 6.0, 1.6, "ms", "log", "Tone"),
    Param("curve", "Curve", 0.3, 3.0, 1.2, "", "lin", "Tone"),
    Param("hp", "HP Cut", 1000.0, 10000.0, 4200.0, "hz", "log", "Tone"),
    Param("metal_hz", "Metal Hz", 200.0, 2000.0, 620.0, "hz", "log", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.0, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.5, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


# --------------------------------------------------------------------------
class NoiseSweep(DrumVoice):
    """Riser / downlifter / white-noise sweep — the glue of every build-up."""

    def _build(self) -> None:
        self._f = ModFilter("bp", 2, self.sr, 1)

    def render(self, n):
        p = self.p
        t = self._time(n)
        dur = p.get("dur", 2.0)
        if t[0] > dur:
            self.dead = True
            return np.zeros((n, 2), dtype=np.float32)
        frac = np.clip(t / dur, 0.0, 1.0)
        f_lo, f_hi = p.get("from_hz", 300.0), p.get("to_hz", 9000.0)
        cut = f_lo * (f_hi / max(f_lo, 1.0)) ** frac
        env = np.where(frac < 1.0, frac ** p.get("shape", 2.0), 0.0)
        env *= np.minimum((1.0 - frac) / 0.02, 1.0)         # avoid a hard cut
        out = self._f.process(self._noise(n), cut, p.get("q", 1.2)) * env
        if t[-1] > dur:
            self.dead = True
        return self._finish(out, n)


SWEEP_PARAMS = (
    Param("dur", "Length", 0.2, 16.0, 2.0, "ms", "log", "Tone"),
    Param("from_hz", "From", 100.0, 12000.0, 300.0, "hz", "log", "Tone"),
    Param("to_hz", "To", 200.0, 16000.0, 9000.0, "hz", "log", "Tone"),
    Param("q", "Q", 0.3, 8.0, 1.2, "", "log", "Tone"),
    Param("shape", "Shape", 0.3, 5.0, 2.0, "", "lin", "Tone"),
    Param("tune", "Tune", -24.0, 24.0, 0.0, "st", "lin", "Out"),
    Param("drive", "Drive", 0.0, 1.0, 0.0, "%", "lin", "Out"),
    Param("level", "Level", 0.0, 1.5, 0.4, "%", "lin", "Out"),
    Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Out"),
)


DRUMS: dict[str, dict] = {
    "kick":   {"name": "Kick", "cls": Kick, "params": KICK_PARAMS,
               "category": "Drums", "poly": 2, "blurb": "Pitch-swept sine with click."},
    "snare":  {"name": "Snare", "cls": Snare, "params": SNARE_PARAMS,
               "category": "Drums", "poly": 3, "blurb": "Tuned body plus noise snap."},
    "clap":   {"name": "Clap", "cls": Clap, "params": CLAP_PARAMS,
               "category": "Drums", "poly": 3, "blurb": "Four offset bursts and a tail."},
    "hat":    {"name": "Hi-Hat", "cls": Hat, "params": HAT_PARAMS,
               "category": "Drums", "poly": 4, "blurb": "Metal partials + noise."},
    "tom":    {"name": "Tom", "cls": Tom, "params": TOM_PARAMS,
               "category": "Drums", "poly": 3, "blurb": "Bending sine drum."},
    "perc":   {"name": "Perc", "cls": Perc, "params": PERC_PARAMS,
               "category": "Drums", "poly": 4, "blurb": "Conga, rim and wood hits."},
    "cymbal": {"name": "Cymbal", "cls": Cymbal, "params": CYMBAL_PARAMS,
               "category": "Drums", "poly": 3, "blurb": "Crash and ride wash."},
    "sweep":  {"name": "Riser", "cls": NoiseSweep, "params": SWEEP_PARAMS,
               "category": "FX", "poly": 2, "blurb": "Noise sweep for build-ups."},
}
