"""Biquad filters with block-rate coefficient updates.

The recursive part runs in scipy's C `sosfilt`, so we keep coefficients constant
over short sub-blocks (default 128 samples ~ 2.9 ms) and step them. That is fine
for filter envelopes and LFOs while staying fast enough for a lot of voices.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt, sosfilt_zi

from .base import SR

SUB_BLOCK = 128
MIN_HZ = 20.0
MAX_HZ_FRAC = 0.45          # of sample rate


def _rbj(kind: str, f0: float, q: float, sr: int, gain_db: float = 0.0) -> np.ndarray:
    """One RBJ biquad as a (6,) second-order-section row."""
    f0 = float(np.clip(f0, MIN_HZ, sr * MAX_HZ_FRAC))
    q = float(max(q, 0.05))
    w0 = 2.0 * np.pi * f0 / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)

    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "bp":
        b0, b1, b2 = alpha, 0.0, -alpha
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "notch":
        b0, b1, b2 = 1.0, -2 * cw, 1.0
        a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
    elif kind == "peak":
        A = 10 ** (gain_db / 40.0)
        b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
        a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
    elif kind == "lowshelf":
        A = 10 ** (gain_db / 40.0)
        s = 2.0 * np.sqrt(A) * alpha
        b0 = A * ((A + 1) - (A - 1) * cw + s)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - s)
        a0 = (A + 1) + (A - 1) * cw + s
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - s
    elif kind == "highshelf":
        A = 10 ** (gain_db / 40.0)
        s = 2.0 * np.sqrt(A) * alpha
        b0 = A * ((A + 1) + (A - 1) * cw + s)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - s)
        a0 = (A + 1) - (A - 1) * cw + s
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - s
    else:
        raise ValueError(f"unknown filter kind {kind!r}")

    return np.array([b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0],
                    dtype=np.float64)


class ModFilter:
    """Resonant filter (1 or 2 cascaded biquads) with a per-sample cutoff array.

    poles=2 -> 12 dB/oct, poles=4 -> 24 dB/oct (ladder-ish, resonance on the
    first section so it sings rather than just ringing).
    """

    __slots__ = ("kind", "poles", "sr", "channels", "_zi", "_last_key", "_sos")

    def __init__(self, kind: str = "lp", poles: int = 4, sr: int = SR,
                 channels: int = 1):
        self.kind = kind
        self.poles = 4 if poles >= 4 else 2
        self.sr = sr
        self.channels = channels
        self._zi = None
        self._last_key: tuple | None = None
        self._sos = None

    def reset(self) -> None:
        self._zi = None

    def _build(self, cutoff: float, res: float) -> np.ndarray:
        key = (round(cutoff, 1), round(res, 3))
        if key == self._last_key and self._sos is not None:
            return self._sos
        if self.poles == 2:
            sos = _rbj(self.kind, cutoff, res, self.sr)[None, :]
        else:
            sos = np.stack((_rbj(self.kind, cutoff, res, self.sr),
                            _rbj(self.kind, cutoff, 0.707, self.sr)))
        self._last_key = key
        self._sos = sos
        return sos

    def _ensure_zi(self, sos: np.ndarray, x0) -> None:
        if self._zi is None or self._zi.shape[0] != sos.shape[0]:
            base = sosfilt_zi(sos)                      # (n_sections, 2)
            if self.channels == 1:
                self._zi = base * 0.0
            else:
                self._zi = np.zeros((sos.shape[0], 2, self.channels))

    def process(self, x: np.ndarray, cutoff, res: float = 0.9) -> np.ndarray:
        """x: (n,) mono or (n, ch). cutoff: scalar or (n,) array in Hz."""
        n = x.shape[0]
        if n == 0:
            return x
        axis = 0
        scalar_cut = np.isscalar(cutoff) or np.ndim(cutoff) == 0

        if scalar_cut:
            spans = [(0, n, float(cutoff))]
        else:
            cut = np.asarray(cutoff, dtype=np.float64)
            lo, hi = float(cut.min()), float(cut.max())
            if hi <= lo * 1.02:                          # effectively static
                spans = [(0, n, 0.5 * (lo + hi))]
            else:
                spans = []
                for s in range(0, n, SUB_BLOCK):
                    e = min(s + SUB_BLOCK, n)
                    spans.append((s, e, float(cut[s:e].mean())))

        out = np.empty_like(x)
        for s, e, c in spans:
            sos = self._build(c, res)
            self._ensure_zi(sos, x)
            y, self._zi = sosfilt(sos, x[s:e], axis=axis, zi=self._zi)
            out[s:e] = y
        return out.astype(np.float32, copy=False)


class StaticEQ:
    """Fixed multi-band EQ used on the master bus and drum sends."""

    __slots__ = ("_sos", "_zi", "channels")

    def __init__(self, bands: list[tuple[str, float, float, float]],
                 sr: int = SR, channels: int = 2):
        rows = [_rbj(kind, f, q, sr, g) for kind, f, q, g in bands]
        self._sos = np.stack(rows) if rows else None
        self.channels = channels
        self._zi = (np.zeros((len(rows), 2, channels)) if rows else None)

    def process(self, x: np.ndarray) -> np.ndarray:
        if self._sos is None:
            return x
        y, self._zi = sosfilt(self._sos, x, axis=0, zi=self._zi)
        return y.astype(np.float32, copy=False)


class DCBlocker:
    """Removes DC offset that pitch-swept sines and saturation leave behind."""

    __slots__ = ("x1", "y1", "r", "ch")

    def __init__(self, channels: int = 2, r: float = 0.9995):
        self.ch = channels
        self.r = r
        self.x1 = np.zeros(channels, dtype=np.float64)
        self.y1 = np.zeros(channels, dtype=np.float64)

    def process(self, x: np.ndarray) -> np.ndarray:
        # y[n] = x[n] - x[n-1] + r*y[n-1]  — done with lfilter for speed
        from scipy.signal import lfilter
        b = np.array([1.0, -1.0])
        a = np.array([1.0, -self.r])
        if x.ndim == 1:
            zi = np.array([self.r * self.y1[0] - self.x1[0]])
            y, zf = lfilter(b, a, x, zi=zi)
            self.x1[0], self.y1[0] = x[-1], y[-1]
            return y.astype(np.float32, copy=False)
        out = np.empty_like(x)
        for c in range(x.shape[1]):
            zi = np.array([self.r * self.y1[c] - self.x1[c]])
            y, _ = lfilter(b, a, x[:, c], zi=zi)
            self.x1[c], self.y1[c] = x[-1, c], y[-1]
            out[:, c] = y
        return out.astype(np.float32, copy=False)
