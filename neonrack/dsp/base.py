"""Core DSP primitives: band-limited oscillators, noise, envelopes, pan.

Everything is block-based and vectorised with numpy. A "block" is a 1-D float32
array of `n` samples; stereo blocks are shape (n, 2).
"""
from __future__ import annotations

import numpy as np

SR = 44100
TWO_PI = 2.0 * np.pi


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def db_to_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def lin_to_db(x: float) -> float:
    return float(20.0 * np.log10(max(x, 1e-9)))


def soft_clip(x: np.ndarray, drive: float = 1.0) -> np.ndarray:
    """tanh saturation — the 'analogue glue' on basses and drums."""
    if drive <= 1.0001:
        return np.tanh(x)
    return np.tanh(x * drive) / np.tanh(drive)


def equal_power_pan(pan: float) -> tuple[float, float]:
    """pan in [-1, 1] -> (left gain, right gain), constant perceived loudness."""
    p = (float(np.clip(pan, -1.0, 1.0)) + 1.0) * 0.25 * np.pi
    return float(np.cos(p)), float(np.sin(p))


def to_stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    gl, gr = equal_power_pan(pan)
    return np.stack((mono * gl, mono * gr), axis=-1)


def fast_rand(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.random(n, dtype=np.float32) * 2.0 - 1.0


# --------------------------------------------------------------------------
# PolyBLEP band-limited oscillator
# --------------------------------------------------------------------------
def _poly_blep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """Polynomial band-limited step correction for a discontinuity at t=0."""
    out = np.zeros_like(t)
    # just after the jump
    m = t < dt
    if m.any():
        x = t[m] / np.maximum(dt[m], 1e-12)
        out[m] = x + x - x * x - 1.0
    # just before the jump
    m = t > 1.0 - dt
    if m.any():
        x = (t[m] - 1.0) / np.maximum(dt[m], 1e-12)
        out[m] = x * x + x + x + 1.0
    return out


class Oscillator:
    """Single band-limited oscillator with a persistent phase.

    shape: 'saw' | 'square' | 'sine' | 'triangle' | 'noise'
    """

    __slots__ = ("phase", "shape", "pw", "_rng")

    def __init__(self, shape: str = "saw", phase: float = 0.0, pw: float = 0.5,
                 rng: np.random.Generator | None = None):
        self.phase = float(phase)
        self.shape = shape
        self.pw = float(pw)
        self._rng = rng or np.random.default_rng()

    def render(self, freq: np.ndarray, sr: int = SR) -> np.ndarray:
        n = freq.shape[0]
        if self.shape == "noise":
            return fast_rand(n, self._rng)

        dt = np.abs(freq) / sr
        np.clip(dt, 0.0, 0.45, out=dt)
        phase = self.phase + np.cumsum(dt, dtype=np.float64)
        # keep the running phase in [0,1) for the *next* block
        self.phase = float(phase[-1] % 1.0)
        phase = np.mod(phase, 1.0).astype(np.float32)
        dt32 = dt.astype(np.float32)

        if self.shape == "sine":
            return np.sin(TWO_PI * phase, dtype=np.float32)

        if self.shape == "saw":
            out = 2.0 * phase - 1.0
            out -= _poly_blep(phase, dt32)
            return out.astype(np.float32)

        if self.shape == "square":
            pw = np.float32(np.clip(self.pw, 0.02, 0.98))
            out = np.where(phase < pw, np.float32(1.0), np.float32(-1.0))
            out += _poly_blep(phase, dt32)
            out -= _poly_blep(np.mod(phase + (1.0 - pw), 1.0), dt32)
            return out.astype(np.float32)

        if self.shape == "triangle":
            # integrate a band-limited square -> alias-free triangle
            pw = np.float32(0.5)
            sq = np.where(phase < pw, np.float32(1.0), np.float32(-1.0))
            sq += _poly_blep(phase, dt32)
            sq -= _poly_blep(np.mod(phase + 0.5, 1.0), dt32)
            tri = np.cumsum(sq * dt32 * 4.0, dtype=np.float32)
            return (tri - np.mean(tri)).astype(np.float32)

        raise ValueError(f"unknown oscillator shape {self.shape!r}")


# --------------------------------------------------------------------------
# Supersaw — 7 detuned saws, the sound of the genre
# --------------------------------------------------------------------------
# JP-8000 style detune curve: musical, non-linear spread.
_SS_OFFSETS = np.array([-0.11002313, -0.06288439, -0.01952356,
                        0.0,
                        0.01991221, 0.06216538, 0.10745242], dtype=np.float64)
_SS_PAN = np.array([-1.0, 0.62, -0.35, 0.0, 0.35, -0.62, 1.0], dtype=np.float32)


class SuperSaw:
    """7 saws, detuned and spread across the stereo field."""

    __slots__ = ("oscs", "detune", "mix", "stereo")

    def __init__(self, detune: float = 0.35, mix: float = 0.75,
                 stereo: float = 1.0, rng: np.random.Generator | None = None):
        rng = rng or np.random.default_rng()
        # random start phases stop the stack from clicking in unison
        self.oscs = [Oscillator("saw", phase=float(rng.random()), rng=rng)
                     for _ in range(7)]
        self.detune = float(detune)
        self.mix = float(mix)
        self.stereo = float(stereo)

    def render(self, freq: np.ndarray, sr: int = SR) -> np.ndarray:
        n = freq.shape[0]
        out = np.zeros((n, 2), dtype=np.float32)
        d = self.detune
        centre_gain = np.float32(1.0 - self.mix * 0.5)
        side_gain = np.float32(self.mix * 0.55)
        for i, osc in enumerate(self.oscs):
            f = freq * (1.0 + _SS_OFFSETS[i] * d)
            sig = osc.render(f, sr)
            g = centre_gain if i == 3 else side_gain
            pan = _SS_PAN[i] * self.stereo
            gl, gr = equal_power_pan(pan)
            out[:, 0] += sig * (g * gl)
            out[:, 1] += sig * (g * gr)
        return out * np.float32(0.55)


# --------------------------------------------------------------------------
# Envelopes
# --------------------------------------------------------------------------
class ADSR:
    """Sample-accurate ADSR with exponential-ish curves, rendered per block."""

    IDLE, ATTACK, DECAY, SUSTAIN, RELEASE = range(5)

    __slots__ = ("a", "d", "s", "r", "stage", "level", "sr", "_rel_from")

    def __init__(self, a: float = 0.005, d: float = 0.2, s: float = 0.7,
                 r: float = 0.3, sr: int = SR):
        self.a, self.d, self.s, self.r = max(a, 1e-4), max(d, 1e-4), s, max(r, 1e-4)
        self.sr = sr
        self.stage = self.IDLE
        self.level = 0.0
        self._rel_from = 0.0

    def note_on(self) -> None:
        self.stage = self.ATTACK

    def note_off(self) -> None:
        if self.stage not in (self.IDLE, self.RELEASE):
            self._rel_from = self.level
            self.stage = self.RELEASE

    @property
    def active(self) -> bool:
        return self.stage != self.IDLE

    def render(self, n: int) -> np.ndarray:
        out = np.empty(n, dtype=np.float32)
        i = 0
        while i < n:
            if self.stage == self.IDLE:
                out[i:] = 0.0
                break

            if self.stage == self.ATTACK:
                rate = 1.0 / (self.a * self.sr)
                need = int(np.ceil((1.0 - self.level) / rate))
                k = min(max(need, 1), n - i)
                seg = self.level + rate * np.arange(1, k + 1, dtype=np.float32)
                np.clip(seg, 0.0, 1.0, out=seg)
                out[i:i + k] = seg
                self.level = float(seg[-1])
                i += k
                if self.level >= 0.9999:
                    self.level = 1.0
                    self.stage = self.DECAY

            elif self.stage == self.DECAY:
                # exponential approach to sustain
                tau = max(self.d * self.sr / 4.0, 1.0)
                coef = float(np.exp(-1.0 / tau))
                k = n - i
                idx = np.arange(1, k + 1, dtype=np.float32)
                decay = coef ** idx
                seg = self.s + (self.level - self.s) * decay
                out[i:i + k] = seg
                self.level = float(seg[-1])
                i += k
                if abs(self.level - self.s) < 1e-4:
                    self.level = self.s
                    self.stage = self.SUSTAIN

            elif self.stage == self.SUSTAIN:
                out[i:] = self.s
                self.level = self.s
                break

            else:  # RELEASE
                tau = max(self.r * self.sr / 4.0, 1.0)
                coef = float(np.exp(-1.0 / tau))
                k = n - i
                idx = np.arange(1, k + 1, dtype=np.float32)
                seg = self.level * (coef ** idx)
                out[i:i + k] = seg
                self.level = float(seg[-1])
                i += k
                if self.level < 1e-4:
                    self.level = 0.0
                    self.stage = self.IDLE
                    out[i:] = 0.0
                    break
        return out


class DecayEnv:
    """One-shot exponential decay — percussion, plucks, pitch sweeps."""

    __slots__ = ("level", "coef", "sr", "floor")

    def __init__(self, decay: float = 0.2, sr: int = SR, floor: float = 1e-4):
        self.sr = sr
        self.floor = floor
        self.level = 1.0
        self.set_decay(decay)

    def set_decay(self, decay: float) -> None:
        tau = max(decay * self.sr / 5.0, 1.0)
        self.coef = float(np.exp(-1.0 / tau))

    @property
    def active(self) -> bool:
        return self.level > self.floor

    def render(self, n: int) -> np.ndarray:
        idx = np.arange(1, n + 1, dtype=np.float32)
        seg = self.level * (self.coef ** idx)
        self.level = float(seg[-1]) if n else self.level
        return seg
