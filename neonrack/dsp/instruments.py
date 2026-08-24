"""Melodic instruments.

Every voice exposes the same tiny contract so the engine does not care what it
is playing:

    v = VoiceClass(params, pitch, velocity, sr)
    v.render(n) -> (n, 2) float32
    v.note_off()
    v.active -> bool
"""
from __future__ import annotations

import numpy as np

from ..core.theory import midi_to_hz
from .base import (ADSR, SR, DecayEnv, Oscillator, SuperSaw, equal_power_pan,
                   soft_clip)
from .filters import ModFilter
from .params import Param

_rng = np.random.default_rng()


# --------------------------------------------------------------------------
# base voice
# --------------------------------------------------------------------------
class Voice:
    """Common machinery: glide, vibrato, amp envelope, filter, panning."""

    is_drum = False

    def __init__(self, params: dict, pitch: int, velocity: float, sr: int = SR):
        self.p = params
        self.pitch = float(pitch)
        self.vel = float(velocity)
        self.sr = sr
        self.released = False
        self._freq = midi_to_hz(self.pitch)
        self._target = self._freq
        self._vib_phase = float(_rng.random())
        g = params.get("glide", 0.0)
        self._glide_coef = 0.0 if g <= 1e-4 else float(np.exp(-1.0 / (g * sr / 4.0)))
        self.amp = ADSR(params.get("attack", 0.005), params.get("decay", 0.3),
                        params.get("sustain", 0.7), params.get("release", 0.3), sr)
        self.amp.note_on()
        self._build()

    # -- hooks ---------------------------------------------------------------
    def _build(self) -> None:            # subclasses set up oscillators here
        pass

    def _oscillate(self, freq: np.ndarray, n: int) -> np.ndarray:
        """Return (n,2) pre-filter signal."""
        raise NotImplementedError

    # -- shared --------------------------------------------------------------
    def glide_to(self, pitch: int) -> None:
        self.pitch = float(pitch)
        self._target = midi_to_hz(pitch)
        if self._glide_coef == 0.0:
            self._freq = self._target

    def note_off(self) -> None:
        self.released = True
        self.amp.note_off()

    @property
    def active(self) -> bool:
        return self.amp.active

    def _freq_array(self, n: int) -> np.ndarray:
        p = self.p
        if self._glide_coef > 0.0:
            idx = np.arange(1, n + 1, dtype=np.float64)
            k = self._glide_coef ** idx
            f = self._target + (self._freq - self._target) * k
            self._freq = float(f[-1])
        else:
            self._freq = self._target
            f = np.full(n, self._target, dtype=np.float64)

        depth = p.get("vibrato", 0.0)
        if depth > 1e-4:
            rate = p.get("vib_rate", 5.2)
            ph = self._vib_phase + np.arange(n, dtype=np.float64) * (rate / self.sr)
            self._vib_phase = float(ph[-1] % 1.0)
            # gentle fade-in so held notes bloom rather than warble instantly
            f = f * (2.0 ** (np.sin(2 * np.pi * ph) * depth / 12.0))

        semis = p.get("transpose", 0.0) + p.get("fine", 0.0) / 100.0
        if abs(semis) > 1e-6:
            f = f * (2.0 ** (semis / 12.0))
        return f

    def _cutoff_array(self, n: int) -> np.ndarray | float:
        p = self.p
        base = p.get("cutoff", 8000.0)
        amt = p.get("env_amt", 0.0)
        if abs(amt) < 1e-4:
            return float(base)
        if not hasattr(self, "_fenv"):
            self._fenv = DecayEnv(max(p.get("f_decay", 0.25), 0.001), self.sr)
        env = self._fenv.render(n)
        # amount is in octaves
        return np.clip(base * (2.0 ** (env * amt)), 20.0, self.sr * 0.45)

    def render(self, n: int) -> np.ndarray:
        freq = self._freq_array(n)
        sig = self._oscillate(freq, n)
        if sig.ndim == 1:
            sig = np.stack((sig, sig), axis=-1)

        if not hasattr(self, "_filt"):
            self._filt = ModFilter(self.p.get("filt_type", "lp"),
                                   int(self.p.get("poles", 4)), self.sr, channels=2)
        cut = self._cutoff_array(n)
        sig = self._filt.process(sig, cut, self.p.get("resonance", 0.8))

        drive = self.p.get("drive", 0.0)
        if drive > 1e-3:
            sig = soft_clip(sig * (1.0 + drive * 4.0), 1.0 + drive * 3.0)

        env = self.amp.render(n)
        vel_curve = self.vel ** self.p.get("vel_curve", 1.0)
        gain = env * (self.p.get("level", 0.8) * vel_curve)
        sig = sig * gain[:, None]

        pan = self.p.get("pan", 0.0)
        if abs(pan) > 1e-4:
            gl, gr = equal_power_pan(pan)
            sig[:, 0] *= gl
            sig[:, 1] *= gr
        return sig.astype(np.float32, copy=False)


# --------------------------------------------------------------------------
# shared parameter blocks
# --------------------------------------------------------------------------
def _amp_params(a=0.005, d=0.3, s=0.7, r=0.3) -> tuple[Param, ...]:
    return (
        Param("attack", "Attack", 0.0005, 4.0, a, "ms", "log", "Amp Envelope"),
        Param("decay", "Decay", 0.005, 6.0, d, "ms", "log", "Amp Envelope"),
        Param("sustain", "Sustain", 0.0, 1.0, s, "%", "lin", "Amp Envelope"),
        Param("release", "Release", 0.005, 8.0, r, "ms", "log", "Amp Envelope"),
    )


def _filter_params(cut=8000.0, res=0.8, amt=0.0, fd=0.25) -> tuple[Param, ...]:
    return (
        Param("cutoff", "Cutoff", 30.0, 18000.0, cut, "hz", "log", "Filter"),
        Param("resonance", "Reso", 0.5, 14.0, res, "", "log", "Filter"),
        Param("env_amt", "Env Amt", -6.0, 6.0, amt, "", "lin", "Filter"),
        Param("f_decay", "Env Dec", 0.005, 4.0, fd, "ms", "log", "Filter"),
    )


def _out_params(level=0.8, drive=0.0) -> tuple[Param, ...]:
    return (
        Param("level", "Level", 0.0, 1.5, level, "%", "lin", "Output"),
        Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin", "Output"),
        Param("drive", "Drive", 0.0, 1.0, drive, "%", "lin", "Output"),
        Param("glide", "Glide", 0.0, 1.0, 0.0, "ms", "lin", "Output"),
        Param("transpose", "Transp", -24.0, 24.0, 0.0, "st", "lin", "Output"),
        Param("fine", "Fine", -100.0, 100.0, 0.0, "", "lin", "Output"),
    )


def _mod_params(vib=0.0) -> tuple[Param, ...]:
    return (
        Param("vibrato", "Vibrato", 0.0, 1.0, vib, "", "lin", "Mod"),
        Param("vib_rate", "Vib Rate", 0.1, 12.0, 5.2, "hz", "log", "Mod"),
    )


# --------------------------------------------------------------------------
# Supersaw lead / chords — Swedish House Mafia, Avicii
# --------------------------------------------------------------------------
class SupersawVoice(Voice):
    def _build(self) -> None:
        self.ss = SuperSaw(self.p.get("detune", 0.35), self.p.get("ss_mix", 0.75),
                           self.p.get("width", 1.0), _rng)
        self.sub = Oscillator("square", phase=float(_rng.random()), rng=_rng)

    def _oscillate(self, freq, n):
        out = self.ss.render(freq, self.sr)
        sub = self.p.get("sub", 0.0)
        if sub > 1e-3:
            s = self.sub.render(freq * 0.5, self.sr) * sub * 0.5
            out[:, 0] += s
            out[:, 1] += s
        return out


SUPERSAW_PARAMS = (
    Param("detune", "Detune", 0.0, 1.0, 0.35, "%", "lin", "Osc"),
    Param("ss_mix", "Spread", 0.0, 1.0, 0.75, "%", "lin", "Osc"),
    Param("width", "Width", 0.0, 1.0, 1.0, "%", "lin", "Osc"),
    Param("sub", "Sub", 0.0, 1.0, 0.0, "%", "lin", "Osc"),
) + _filter_params(9000.0, 0.8, 0.0) + _amp_params(0.01, 0.4, 0.85, 0.35) \
  + _mod_params() + _out_params(0.55)


# --------------------------------------------------------------------------
# Pluck — Warakls, Joachim Pastor, NTO
# --------------------------------------------------------------------------
class PluckVoice(Voice):
    def _build(self) -> None:
        self.o1 = Oscillator(self.p.get("wave1", "saw") if isinstance(
            self.p.get("wave1"), str) else "saw", float(_rng.random()), rng=_rng)
        self.o2 = Oscillator("square", float(_rng.random()), rng=_rng)
        self.o2.pw = self.p.get("pw", 0.42)
        self.detune = self.p.get("detune", 0.06)

    def _oscillate(self, freq, n):
        a = self.o1.render(freq, self.sr)
        mix2 = self.p.get("osc2", 0.4)
        if mix2 > 1e-3:
            b = self.o2.render(freq * (1.0 + self.detune * 0.02), self.sr)
            a = a * (1.0 - mix2 * 0.5) + b * mix2
        sub = self.p.get("sub", 0.25)
        if sub > 1e-3:
            if not hasattr(self, "_subosc"):
                self._subosc = Oscillator("sine", rng=_rng)
            a = a + self._subosc.render(freq * 0.5, self.sr) * sub
        # slight stereo life from a haas-free phase-offset copy
        w = self.p.get("width", 0.25)
        if w > 1e-3:
            return np.stack((a, np.roll(a, 3) * (1 - w) + a * w), axis=-1)
        return a


PLUCK_PARAMS = (
    Param("osc2", "Osc 2", 0.0, 1.0, 0.4, "%", "lin", "Osc"),
    Param("pw", "Pulse W", 0.05, 0.95, 0.42, "%", "lin", "Osc"),
    Param("sub", "Sub", 0.0, 1.0, 0.25, "%", "lin", "Osc"),
    Param("detune", "Detune", 0.0, 1.0, 0.06, "%", "lin", "Osc"),
    Param("width", "Width", 0.0, 1.0, 0.25, "%", "lin", "Osc"),
) + _filter_params(1200.0, 4.5, 3.2, 0.16) + _amp_params(0.002, 0.28, 0.0, 0.18) \
  + _mod_params() + _out_params(0.7)


# --------------------------------------------------------------------------
# Bass — sub sine + saw layer
# --------------------------------------------------------------------------
class BassVoice(Voice):
    def _build(self) -> None:
        self.sine = Oscillator("sine", rng=_rng)
        self.saw = Oscillator("saw", float(_rng.random()), rng=_rng)
        self.saw2 = Oscillator("saw", float(_rng.random()), rng=_rng)

    def _oscillate(self, freq, n):
        sub = self.sine.render(freq, self.sr) * self.p.get("sub", 0.9)
        top = self.p.get("saw", 0.35)
        out = sub
        if top > 1e-3:
            d = self.p.get("detune", 0.1) * 0.01
            s = (self.saw.render(freq * (1 + d), self.sr) +
                 self.saw2.render(freq * (1 - d), self.sr)) * 0.5
            out = out + s * top
        return out


BASS_PARAMS = (
    Param("sub", "Sub Sine", 0.0, 1.5, 0.9, "%", "lin", "Osc"),
    Param("saw", "Saw", 0.0, 1.0, 0.35, "%", "lin", "Osc"),
    Param("detune", "Detune", 0.0, 1.0, 0.1, "%", "lin", "Osc"),
) + _filter_params(320.0, 1.6, 1.4, 0.12) + _amp_params(0.004, 0.5, 0.85, 0.09) \
  + _mod_params() + _out_params(0.85, 0.15)


# --------------------------------------------------------------------------
# Reese / growl bass
# --------------------------------------------------------------------------
class ReeseVoice(Voice):
    def _build(self) -> None:
        self.a = Oscillator("saw", float(_rng.random()), rng=_rng)
        self.b = Oscillator("saw", float(_rng.random()), rng=_rng)
        self.c = Oscillator("saw", float(_rng.random()), rng=_rng)
        self._lfo = float(_rng.random())

    def _oscillate(self, freq, n):
        d = self.p.get("detune", 0.35) * 0.03
        s = (self.a.render(freq, self.sr)
             + self.b.render(freq * (1 + d), self.sr)
             + self.c.render(freq * (1 - d * 0.7), self.sr)) / 3.0
        return s


REESE_PARAMS = (
    Param("detune", "Detune", 0.0, 1.0, 0.35, "%", "lin", "Osc"),
) + _filter_params(700.0, 3.0, 1.0, 0.4) + _amp_params(0.01, 0.6, 0.9, 0.15) \
  + _mod_params() + _out_params(0.7, 0.3)


# --------------------------------------------------------------------------
# Pad — French 79, NTO, breakdown texture
# --------------------------------------------------------------------------
class PadVoice(Voice):
    def _build(self) -> None:
        self.n_osc = 5
        self.oscs = [Oscillator("saw", float(_rng.random()), rng=_rng)
                     for _ in range(self.n_osc)]
        self.pans = np.linspace(-1.0, 1.0, self.n_osc)
        self.offs = np.linspace(-1.0, 1.0, self.n_osc)
        self._lfo_ph = float(_rng.random())

    def _oscillate(self, freq, n):
        out = np.zeros((n, 2), dtype=np.float32)
        d = self.p.get("detune", 0.25) * 0.012
        # slow independent drift keeps the pad alive
        rate = self.p.get("drift", 0.15)
        ph = self._lfo_ph + np.arange(n) * (rate / self.sr)
        self._lfo_ph = float(ph[-1] % 1.0)
        for i, o in enumerate(self.oscs):
            drift = 1.0 + 0.0016 * np.sin(2 * np.pi * (ph + i / self.n_osc))
            sig = o.render(freq * (1 + self.offs[i] * d) * drift, self.sr)
            gl, gr = equal_power_pan(self.pans[i] * self.p.get("width", 0.9))
            out[:, 0] += sig * gl
            out[:, 1] += sig * gr
        return out * np.float32(0.42)


PAD_PARAMS = (
    Param("detune", "Detune", 0.0, 1.0, 0.25, "%", "lin", "Osc"),
    Param("width", "Width", 0.0, 1.0, 0.9, "%", "lin", "Osc"),
    Param("drift", "Drift", 0.0, 1.0, 0.15, "hz", "lin", "Osc"),
) + _filter_params(2600.0, 1.0, 0.9, 2.5) + _amp_params(0.9, 2.0, 0.8, 1.8) \
  + _mod_params() + _out_params(0.45)


# --------------------------------------------------------------------------
# FM electric piano / bell / marimba — Avicii keys, tropical plucks
# --------------------------------------------------------------------------
class FMVoice(Voice):
    def _build(self) -> None:
        self.cph = float(_rng.random())
        self.mph = float(_rng.random())
        self.idx_env = DecayEnv(self.p.get("fm_decay", 0.35), self.sr)
        self.fb = 0.0

    def _oscillate(self, freq, n):
        ratio = self.p.get("ratio", 1.0)
        index = self.p.get("index", 3.0)
        env = self.idx_env.render(n)

        mstep = freq * ratio / self.sr
        mph = self.mph + np.cumsum(mstep)
        self.mph = float(mph[-1] % 1.0)
        mod = np.sin(2 * np.pi * mph) * (index * env)

        cstep = freq / self.sr
        cph = self.cph + np.cumsum(cstep)
        self.cph = float(cph[-1] % 1.0)
        car = np.sin(2 * np.pi * cph + mod)

        second = self.p.get("second", 0.0)
        if second > 1e-3:
            car = car + np.sin(2 * np.pi * cph * 2.0) * second * 0.4
        return car.astype(np.float32)


FM_PARAMS = (
    Param("ratio", "Ratio", 0.25, 12.0, 1.0, "", "log", "FM"),
    Param("index", "Index", 0.0, 12.0, 3.0, "", "lin", "FM"),
    Param("fm_decay", "FM Decay", 0.005, 4.0, 0.35, "ms", "log", "FM"),
    Param("second", "2nd Harm", 0.0, 1.0, 0.0, "%", "lin", "FM"),
) + _filter_params(12000.0, 0.7, 0.0) + _amp_params(0.002, 1.2, 0.0, 0.5) \
  + _mod_params() + _out_params(0.7)


# --------------------------------------------------------------------------
# Organ / drawbar-ish additive — house stabs
# --------------------------------------------------------------------------
class OrganVoice(Voice):
    HARMS = (1.0, 2.0, 3.0, 4.0, 6.0, 8.0)

    def _build(self) -> None:
        self.oscs = [Oscillator("sine", float(_rng.random()), rng=_rng)
                     for _ in self.HARMS]

    def _oscillate(self, freq, n):
        bars = [self.p.get(f"bar{i}", d) for i, d in
                enumerate((1.0, 0.6, 0.35, 0.2, 0.12, 0.08))]
        out = np.zeros(n, dtype=np.float32)
        for o, h, g in zip(self.oscs, self.HARMS, bars):
            if g > 1e-3:
                out += o.render(freq * h, self.sr) * g
        return out * np.float32(0.4)


ORGAN_PARAMS = tuple(
    Param(f"bar{i}", lbl, 0.0, 1.0, d, "%", "lin", "Drawbars")
    for i, (lbl, d) in enumerate((("16'", 1.0), ("8'", 0.6), ("5⅓'", 0.35),
                                  ("4'", 0.2), ("2⅔'", 0.12), ("2'", 0.08)))
) + _filter_params(7000.0, 0.7, 0.0) + _amp_params(0.008, 0.4, 0.9, 0.12) \
  + _mod_params() + _out_params(0.6, 0.2)


# --------------------------------------------------------------------------
# Choir / vox pad — formant-shaped saws
# --------------------------------------------------------------------------
class ChoirVoice(Voice):
    def _build(self) -> None:
        self.oscs = [Oscillator("saw", float(_rng.random()), rng=_rng)
                     for _ in range(4)]
        self.offs = (-1.0, -0.33, 0.33, 1.0)
        self._f1 = ModFilter("bp", 2, self.sr, 2)
        self._f2 = ModFilter("bp", 2, self.sr, 2)
        self._vph = float(_rng.random())

    def _oscillate(self, freq, n):
        d = self.p.get("detune", 0.3) * 0.01
        out = np.zeros((n, 2), dtype=np.float32)
        for i, o in enumerate(self.oscs):
            sig = o.render(freq * (1 + self.offs[i] * d), self.sr)
            gl, gr = equal_power_pan(self.offs[i] * 0.8)
            out[:, 0] += sig * gl
            out[:, 1] += sig * gr
        out *= np.float32(0.4)
        # two formant bands = a vowel-ish 'aah'
        f1 = self.p.get("formant1", 700.0)
        f2 = self.p.get("formant2", 1150.0)
        v = self._f1.process(out, f1, 3.0) + self._f2.process(out, f2, 3.0) * 0.7
        return out * 0.35 + v * 0.9


CHOIR_PARAMS = (
    Param("detune", "Detune", 0.0, 1.0, 0.3, "%", "lin", "Osc"),
    Param("formant1", "Formant 1", 250.0, 1200.0, 700.0, "hz", "log", "Voice"),
    Param("formant2", "Formant 2", 700.0, 3200.0, 1150.0, "hz", "log", "Voice"),
) + _filter_params(5000.0, 0.7, 0.0) + _amp_params(0.35, 1.5, 0.75, 1.2) \
  + _mod_params(0.25) + _out_params(0.5)


# --------------------------------------------------------------------------
# Sampler — drop in your own one-shots and loops
# --------------------------------------------------------------------------
class SamplerVoice(Voice):
    def _build(self) -> None:
        self.buf = self.p.get("_buffer")
        self.pos = 0.0
        self.root = self.p.get("root_note", 60.0)

    def _oscillate(self, freq, n):
        buf = self.buf
        if buf is None or len(buf) == 0:
            self.amp.stage = ADSR.IDLE
            return np.zeros((n, 2), dtype=np.float32)
        rate = float(2.0 ** ((self.pitch - self.root) / 12.0))
        rate *= 2.0 ** (self.p.get("transpose", 0.0) / 12.0)
        idx = self.pos + np.arange(n, dtype=np.float64) * rate
        self.pos = float(idx[-1] + rate)
        last = len(buf) - 1
        if self.p.get("loop", 0.0) > 0.5:
            idx = np.mod(idx, last)
        else:
            if idx[0] >= last:
                self.amp.note_off()
                return np.zeros((n, 2), dtype=np.float32)
            idx = np.clip(idx, 0, last)
        i0 = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)[:, None]
        i1 = np.minimum(i0 + 1, last)
        return (buf[i0] * (1 - frac) + buf[i1] * frac).astype(np.float32)


SAMPLER_PARAMS = (
    Param("root_note", "Root", 24.0, 96.0, 60.0, "", "lin", "Sample"),
    Param("loop", "Loop", 0.0, 1.0, 0.0, "", "switch", "Sample", ("Off", "On")),
) + _filter_params(18000.0, 0.7, 0.0) + _amp_params(0.001, 2.0, 1.0, 0.2) \
  + _mod_params() + _out_params(0.8)


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
INSTRUMENTS: dict[str, dict] = {
    "supersaw": {"name": "Supersaw", "cls": SupersawVoice, "params": SUPERSAW_PARAMS,
                 "category": "Lead", "poly": 12,
                 "blurb": "7 detuned saws. Big-room chords and anthemic leads."},
    "pluck":    {"name": "Pluck", "cls": PluckVoice, "params": PLUCK_PARAMS,
                 "category": "Lead", "poly": 12,
                 "blurb": "Short filtered stab. The melodic-house arp sound."},
    "bass":     {"name": "Bass", "cls": BassVoice, "params": BASS_PARAMS,
                 "category": "Bass", "poly": 3,
                 "blurb": "Sub sine with a saw layer. Sits under the kick."},
    "reese":    {"name": "Reese Bass", "cls": ReeseVoice, "params": REESE_PARAMS,
                 "category": "Bass", "poly": 3,
                 "blurb": "Detuned saw growl for darker, driving basslines."},
    "pad":      {"name": "Pad", "cls": PadVoice, "params": PAD_PARAMS,
                 "category": "Keys", "poly": 10,
                 "blurb": "Wide evolving strings for breakdowns."},
    "fm":       {"name": "FM Keys", "cls": FMVoice, "params": FM_PARAMS,
                 "category": "Keys", "poly": 12,
                 "blurb": "2-operator FM: e-piano, bells, marimba, plucks."},
    "organ":    {"name": "Organ", "cls": OrganVoice, "params": ORGAN_PARAMS,
                 "category": "Keys", "poly": 10,
                 "blurb": "Drawbar additive tone for house stabs."},
    "choir":    {"name": "Choir", "cls": ChoirVoice, "params": CHOIR_PARAMS,
                 "category": "Keys", "poly": 8,
                 "blurb": "Formant-filtered voices. Cinematic breakdowns."},
    "sampler":  {"name": "Sampler", "cls": SamplerVoice, "params": SAMPLER_PARAMS,
                 "category": "Sampler", "poly": 8,
                 "blurb": "Load your own WAV one-shots and loops."},
}
