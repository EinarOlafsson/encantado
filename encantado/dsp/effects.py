"""Effects: reverb, delay, chorus, phaser, drive, DJ filter, comp, limiter,
and the sidechain ducker that gives this genre its pump.

Every effect exposes `process(x)` where x is (n, 2) float32, plus a `params`
dict and a class-level PARAMS spec so the UI can build controls automatically.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from .base import SR, soft_clip
from .filters import ModFilter, StaticEQ, _rbj
from .params import Param


# --------------------------------------------------------------------------
# delay-line building blocks (handle delays shorter than the audio block)
# --------------------------------------------------------------------------
class _Line:
    """Circular delay line with correct feedback for any delay length."""

    __slots__ = ("buf", "idx", "size")

    def __init__(self, size: int):
        self.size = int(max(size, 1))
        self.buf = np.zeros(self.size, dtype=np.float32)
        self.idx = 0

    def comb(self, x: np.ndarray, fb: float, damp: float, state: list) -> np.ndarray:
        """Lowpass-damped feedback comb (Schroeder/Freeverb style)."""
        n = x.shape[0]
        out = np.empty(n, dtype=np.float32)
        i = 0
        d = state[0]
        while i < n:
            k = min(self.size - self.idx, n - i)
            seg = self.buf[self.idx:self.idx + k].copy()
            out[i:i + k] = seg
            # one-pole damping inside the feedback path
            if damp > 1e-4:
                y, zf = lfilter([1.0 - damp], [1.0, -damp], seg, zi=[d * damp])
                d = float(y[-1])
                seg = y.astype(np.float32)
            self.buf[self.idx:self.idx + k] = x[i:i + k] + seg * fb
            self.idx = (self.idx + k) % self.size
            i += k
        state[0] = d
        return out

    def allpass(self, x: np.ndarray, g: float) -> np.ndarray:
        n = x.shape[0]
        out = np.empty(n, dtype=np.float32)
        i = 0
        while i < n:
            k = min(self.size - self.idx, n - i)
            buf = self.buf[self.idx:self.idx + k]
            xin = x[i:i + k]
            out[i:i + k] = -xin + buf
            self.buf[self.idx:self.idx + k] = xin + buf * g
            self.idx = (self.idx + k) % self.size
            i += k
        return out

    def read_write(self, x: np.ndarray, fb_signal: np.ndarray | None = None) -> np.ndarray:
        """Plain delay: read the old content, write new content."""
        n = x.shape[0]
        out = np.empty(n, dtype=np.float32)
        i = 0
        while i < n:
            k = min(self.size - self.idx, n - i)
            out[i:i + k] = self.buf[self.idx:self.idx + k]
            self.buf[self.idx:self.idx + k] = x[i:i + k]
            self.idx = (self.idx + k) % self.size
            i += k
        return out

    def read_interp(self, positions: np.ndarray,
                    start: int | None = None) -> np.ndarray:
        """Fractional read, `positions[i]` samples behind the head at sample i.

        The read head advances one sample per output sample -- forgetting that
        makes a delay line output a single frozen sample instead of an echo.
        `start` overrides the head position (used when the block was already
        written, e.g. by the chorus).
        """
        n = positions.shape[0]
        head = self.idx if start is None else start
        base = head + np.arange(n, dtype=np.float64) - positions
        i0 = np.floor(base).astype(np.int64)
        frac = (base - i0).astype(np.float32)
        a = self.buf[i0 % self.size]
        b = self.buf[(i0 + 1) % self.size]
        return a * (1 - frac) + b * frac

    def write_block(self, x: np.ndarray) -> None:
        n = x.shape[0]
        i = 0
        while i < n:
            k = min(self.size - self.idx, n - i)
            self.buf[self.idx:self.idx + k] = x[i:i + k]
            self.idx = (self.idx + k) % self.size
            i += k


class Effect:
    NAME = "Effect"
    PARAMS: tuple[Param, ...] = ()

    def __init__(self, params: dict | None = None, sr: int = SR):
        self.sr = sr
        self.p = {q.key: q.default for q in self.PARAMS}
        if params:
            self.p.update(params)
        self.enabled = True
        self.wet_only = False        # send-bus mode: return only the wet signal
        self._build()

    def _build(self) -> None:
        pass

    def set(self, key: str, value: float) -> None:
        self.p[key] = value
        self._on_change(key)

    def _on_change(self, key: str) -> None:
        pass

    def process(self, x: np.ndarray) -> np.ndarray:
        return x

    def reset(self) -> None:
        self._build()


# --------------------------------------------------------------------------
# Reverb — Freeverb-derived, with a high-pass so the low end stays tight
# --------------------------------------------------------------------------
_COMBS = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)
_ALLPASS = (556, 441, 341, 225)
_STEREO_SPREAD = 23


class Reverb(Effect):
    NAME = "Reverb"
    PARAMS = (
        Param("mix", "Mix", 0.0, 1.0, 0.3, "%", "lin", "Reverb"),
        Param("size", "Size", 0.0, 1.0, 0.72, "%", "lin", "Reverb"),
        Param("damp", "Damp", 0.0, 1.0, 0.45, "%", "lin", "Reverb"),
        Param("width", "Width", 0.0, 1.0, 1.0, "%", "lin", "Reverb"),
        Param("hp", "Low Cut", 20.0, 1200.0, 260.0, "hz", "log", "Reverb"),
        Param("predelay", "Pre-dly", 0.0, 0.25, 0.02, "ms", "lin", "Reverb"),
    )

    def _build(self) -> None:
        sc = self.sr / 44100.0
        self.combs = [[_Line(int(d * sc)) for d in _COMBS],
                      [_Line(int((d + _STEREO_SPREAD) * sc)) for d in _COMBS]]
        self.aps = [[_Line(int(d * sc)) for d in _ALLPASS],
                    [_Line(int((d + _STEREO_SPREAD) * sc)) for d in _ALLPASS]]
        self.damp_state = [[[0.0] for _ in _COMBS], [[0.0] for _ in _COMBS]]
        self.hp = ModFilter("hp", 2, self.sr, 2)
        pd = int(max(self.p.get("predelay", 0.02), 0.0) * self.sr) + 1
        self.pre = [_Line(pd), _Line(pd)]
        self._pd_len = pd

    def _on_change(self, key: str) -> None:
        if key == "predelay":
            pd = int(max(self.p.get("predelay", 0.02), 0.0) * self.sr) + 1
            if pd != self._pd_len:
                self.pre = [_Line(pd), _Line(pd)]
                self._pd_len = pd

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return x
        mix = self.p["mix"]
        if mix <= 1e-4:
            return x
        fb = 0.7 + self.p["size"] * 0.28
        damp = self.p["damp"] * 0.4
        src = self.hp.process(x, self.p["hp"], 0.707)
        wet = np.zeros_like(x)
        for ch in range(2):
            s = self.pre[ch].read_write(src[:, ch] * 0.15)
            acc = np.zeros_like(s)
            for i, line in enumerate(self.combs[ch]):
                acc += line.comb(s, fb, damp, self.damp_state[ch][i])
            acc /= len(_COMBS)
            for line in self.aps[ch]:
                acc = line.allpass(acc, 0.5)
            wet[:, ch] = acc
        w = self.p["width"]
        if w < 0.999:
            mid = (wet[:, 0] + wet[:, 1]) * 0.5
            side = (wet[:, 0] - wet[:, 1]) * 0.5 * w
            wet = np.stack((mid + side, mid - side), axis=-1)
        if self.wet_only:
            return (wet * (mix * 3.2)).astype(np.float32)
        return (x * (1.0 - mix * 0.35) + wet * (mix * 3.2)).astype(np.float32)


# --------------------------------------------------------------------------
# Delay — tempo-synced, optional ping-pong
# --------------------------------------------------------------------------
DIVISIONS = ("1/16", "1/8T", "1/8", "1/8D", "1/4", "1/4D", "1/2", "1/1")
_DIV_BEATS = (0.25, 1 / 3, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0)


class Delay(Effect):
    NAME = "Delay"
    PARAMS = (
        Param("mix", "Mix", 0.0, 1.0, 0.22, "%", "lin", "Delay"),
        Param("division", "Time", 0, len(DIVISIONS) - 1, 3, "", "switch",
              "Delay", DIVISIONS),
        Param("feedback", "Feedback", 0.0, 0.95, 0.42, "%", "lin", "Delay"),
        Param("pingpong", "Ping-Pong", 0.0, 1.0, 1.0, "", "switch", "Delay",
              ("Off", "On")),
        Param("lp", "Tone", 400.0, 18000.0, 5000.0, "hz", "log", "Delay"),
        Param("hp", "Low Cut", 20.0, 2000.0, 300.0, "hz", "log", "Delay"),
    )
    MAX_SEC = 4.0

    def _build(self) -> None:
        n = int(self.MAX_SEC * self.sr)
        self.lines = [_Line(n), _Line(n)]
        self.lp = ModFilter("lp", 2, self.sr, 2)
        self.hp = ModFilter("hp", 2, self.sr, 2)
        self.bpm = 124.0

    def set_tempo(self, bpm: float) -> None:
        self.bpm = max(float(bpm), 20.0)

    def _delay_samples(self) -> int:
        beats = _DIV_BEATS[int(np.clip(round(self.p["division"]), 0,
                                       len(_DIV_BEATS) - 1))]
        return int(np.clip(beats * 60.0 / self.bpm * self.sr, 8,
                           self.MAX_SEC * self.sr - 2))

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled or self.p["mix"] <= 1e-4:
            return x
        n = x.shape[0]
        d = max(self._delay_samples(), n + 2)
        pos = np.full(n, float(d), dtype=np.float64)
        taps = np.stack((self.lines[0].read_interp(pos),
                         self.lines[1].read_interp(pos)), axis=-1)
        taps = self.lp.process(taps, self.p["lp"], 0.707)
        taps = self.hp.process(taps, self.p["hp"], 0.707)
        fb = self.p["feedback"]
        if self.p["pingpong"] > 0.5:
            wr_l = x[:, 0] * 0.7 + taps[:, 1] * fb
            wr_r = x[:, 1] * 0.7 + taps[:, 0] * fb
        else:
            wr_l = x[:, 0] * 0.7 + taps[:, 0] * fb
            wr_r = x[:, 1] * 0.7 + taps[:, 1] * fb
        self.lines[0].write_block(np.clip(wr_l, -8, 8).astype(np.float32))
        self.lines[1].write_block(np.clip(wr_r, -8, 8).astype(np.float32))
        if self.wet_only:
            return (taps * self.p["mix"] * 1.4).astype(np.float32)
        return (x + taps * self.p["mix"] * 1.4).astype(np.float32)


# --------------------------------------------------------------------------
# Chorus / Phaser — width and movement
# --------------------------------------------------------------------------
class Chorus(Effect):
    NAME = "Chorus"
    PARAMS = (
        Param("mix", "Mix", 0.0, 1.0, 0.35, "%", "lin", "Chorus"),
        Param("rate", "Rate", 0.02, 6.0, 0.45, "hz", "log", "Chorus"),
        Param("depth", "Depth", 0.0, 1.0, 0.45, "%", "lin", "Chorus"),
        Param("spread", "Spread", 0.0, 1.0, 0.8, "%", "lin", "Chorus"),
    )

    def _build(self) -> None:
        self.lines = [_Line(int(0.06 * self.sr)), _Line(int(0.06 * self.sr))]
        self.ph = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled or self.p["mix"] <= 1e-4:
            return x
        n = x.shape[0]
        rate = self.p["rate"]
        ph = self.ph + np.arange(n) * (rate / self.sr)
        self.ph = float(ph[-1] % 1.0)
        base = 0.011 * self.sr
        depth = self.p["depth"] * 0.006 * self.sr
        off = self.p["spread"] * 0.5
        pl = base + depth * (0.5 + 0.5 * np.sin(2 * np.pi * ph))
        pr = base + depth * (0.5 + 0.5 * np.sin(2 * np.pi * (ph + off)))
        head_l, head_r = self.lines[0].idx, self.lines[1].idx
        self.lines[0].write_block(x[:, 0].copy())
        self.lines[1].write_block(x[:, 1].copy())
        wl = self.lines[0].read_interp(pl, start=head_l)
        wr = self.lines[1].read_interp(pr, start=head_r)
        wet = np.stack((wl, wr), axis=-1)
        m = self.p["mix"]
        return (x * (1 - m * 0.5) + wet * m).astype(np.float32)


class Phaser(Effect):
    NAME = "Phaser"
    PARAMS = (
        Param("mix", "Mix", 0.0, 1.0, 0.4, "%", "lin", "Phaser"),
        Param("rate", "Rate", 0.02, 8.0, 0.3, "hz", "log", "Phaser"),
        Param("depth", "Depth", 0.0, 1.0, 0.7, "%", "lin", "Phaser"),
        Param("feedback", "Feedback", 0.0, 0.9, 0.35, "%", "lin", "Phaser"),
        Param("stages", "Stages", 2, 8, 6, "", "lin", "Phaser"),
    )

    def _build(self) -> None:
        self.ph = 0.0
        self.filters = [ModFilter("notch", 2, self.sr, 2) for _ in range(4)]
        self._fb = np.zeros((1, 2), dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled or self.p["mix"] <= 1e-4:
            return x
        n = x.shape[0]
        ph = self.ph + np.arange(n) * (self.p["rate"] / self.sr)
        self.ph = float(ph[-1] % 1.0)
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * ph)
        depth = self.p["depth"]
        y = x.copy()
        n_st = int(np.clip(round(self.p["stages"] / 2), 1, 4))
        for i in range(n_st):
            cut = 220.0 * (2.0 ** ((lfo * 4.0 * depth) + i * 0.7))
            y = self.filters[i].process(y, cut, 0.7)
        m = self.p["mix"]
        return (x * (1 - m * 0.5) + y * m).astype(np.float32)


# --------------------------------------------------------------------------
# Drive and DJ filter
# --------------------------------------------------------------------------
class Drive(Effect):
    NAME = "Drive"
    PARAMS = (
        Param("amount", "Drive", 0.0, 1.0, 0.3, "%", "lin", "Drive"),
        Param("tone", "Tone", 500.0, 18000.0, 9000.0, "hz", "log", "Drive"),
        Param("mix", "Mix", 0.0, 1.0, 1.0, "%", "lin", "Drive"),
        Param("out", "Output", 0.0, 1.5, 1.0, "%", "lin", "Drive"),
    )

    def _build(self) -> None:
        self.lp = ModFilter("lp", 2, self.sr, 2)

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled or self.p["amount"] <= 1e-4:
            return x
        a = self.p["amount"]
        wet = soft_clip(x * (1.0 + a * 12.0), 1.0 + a * 8.0)
        wet = self.lp.process(wet, self.p["tone"], 0.707)
        m = self.p["mix"]
        return ((x * (1 - m) + wet * m) * self.p["out"]).astype(np.float32)


class DJFilter(Effect):
    """One knob: centre = off, left = lowpass sweep, right = highpass sweep."""

    NAME = "DJ Filter"
    PARAMS = (
        Param("cut", "Filter", -1.0, 1.0, 0.0, "", "lin", "Filter"),
        Param("reso", "Reso", 0.5, 8.0, 1.2, "", "log", "Filter"),
    )

    def _build(self) -> None:
        self.lp = ModFilter("lp", 4, self.sr, 2)
        self.hp = ModFilter("hp", 4, self.sr, 2)

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return x
        c = float(self.p["cut"])
        if abs(c) < 0.02:
            return x
        q = self.p["reso"]
        if c < 0:
            cut = 18000.0 * (40.0 / 18000.0) ** (-c)
            return self.lp.process(x, cut, q)
        cut = 20.0 * (12000.0 / 20.0) ** c
        return self.hp.process(x, cut, q)


# --------------------------------------------------------------------------
# Dynamics
# --------------------------------------------------------------------------
class Compressor(Effect):
    NAME = "Compressor"
    PARAMS = (
        Param("threshold", "Thresh", -48.0, 0.0, -18.0, "db", "lin", "Comp"),
        Param("ratio", "Ratio", 1.0, 20.0, 3.0, "", "log", "Comp"),
        Param("attack", "Attack", 0.0005, 0.2, 0.008, "ms", "log", "Comp"),
        Param("release", "Release", 0.01, 1.5, 0.14, "ms", "log", "Comp"),
        Param("makeup", "Makeup", 0.0, 4.0, 1.0, "%", "lin", "Comp"),
        Param("mix", "Mix", 0.0, 1.0, 1.0, "%", "lin", "Comp"),
    )

    def _build(self) -> None:
        self.env = 0.0
        self.gr_db = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return x
        det = np.max(np.abs(x), axis=1)
        ta = float(np.exp(-1.0 / max(self.p["attack"] * self.sr, 1.0)))
        tr = float(np.exp(-1.0 / max(self.p["release"] * self.sr, 1.0)))
        # attack is fast, release is slow: a release-time one-pole over a
        # running peak is a good, cheap approximation of a real detector.
        env, _ = lfilter([1.0 - tr], [1.0, -tr], det, zi=[self.env * tr])
        env = np.maximum(env, det * (1.0 - ta))
        self.env = float(env[-1])

        env_db = 20.0 * np.log10(np.maximum(env, 1e-7))
        thr, ratio = self.p["threshold"], max(self.p["ratio"], 1.0)
        over = np.maximum(env_db - thr, 0.0)
        gr_db = -over * (1.0 - 1.0 / ratio)
        self.gr_db = float(gr_db[-1])
        g = (10.0 ** (gr_db / 20.0)).astype(np.float32)[:, None]
        wet = x * g * self.p["makeup"]
        m = self.p["mix"]
        return (x * (1 - m) + wet * m).astype(np.float32)


class Limiter(Effect):
    NAME = "Limiter"
    PARAMS = (
        Param("ceiling", "Ceiling", -12.0, 0.0, -0.8, "db", "lin", "Limiter"),
        Param("drive", "Push", 1.0, 6.0, 1.0, "%", "lin", "Limiter"),
        Param("release", "Release", 0.01, 1.0, 0.09, "ms", "log", "Limiter"),
    )

    def _build(self) -> None:
        self.env = 1.0
        self.gr_db = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled:
            return x
        ceil = 10.0 ** (self.p["ceiling"] / 20.0)
        y = x * self.p["drive"]
        peak = np.max(np.abs(y), axis=1)
        tr = float(np.exp(-1.0 / max(self.p["release"] * self.sr, 1.0)))
        env, _ = lfilter([1.0 - tr], [1.0, -tr], peak, zi=[self.env * tr])
        env = np.maximum(env, peak)
        self.env = float(env[-1])
        gain = np.minimum(1.0, ceil / np.maximum(env, 1e-6)).astype(np.float32)
        self.gr_db = float(20.0 * np.log10(max(gain[-1], 1e-6)))
        out = y * gain[:, None]
        # final safety: nothing ever leaves above the ceiling
        return np.tanh(out / ceil).astype(np.float32) * ceil


class EQ3(Effect):
    NAME = "EQ"
    PARAMS = (
        Param("low", "Low", -18.0, 18.0, 0.0, "db", "lin", "EQ"),
        Param("low_hz", "Low Hz", 40.0, 400.0, 120.0, "hz", "log", "EQ"),
        Param("mid", "Mid", -18.0, 18.0, 0.0, "db", "lin", "EQ"),
        Param("mid_hz", "Mid Hz", 200.0, 6000.0, 1200.0, "hz", "log", "EQ"),
        Param("mid_q", "Mid Q", 0.2, 6.0, 0.9, "", "log", "EQ"),
        Param("high", "High", -18.0, 18.0, 0.0, "db", "lin", "EQ"),
        Param("high_hz", "High Hz", 2000.0, 16000.0, 7000.0, "hz", "log", "EQ"),
    )

    def _build(self) -> None:
        self._rebuild()

    def _on_change(self, key: str) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        p = self.p
        bands = []
        if abs(p["low"]) > 0.05:
            bands.append(("lowshelf", p["low_hz"], 0.707, p["low"]))
        if abs(p["mid"]) > 0.05:
            bands.append(("peak", p["mid_hz"], p["mid_q"], p["mid"]))
        if abs(p["high"]) > 0.05:
            bands.append(("highshelf", p["high_hz"], 0.707, p["high"]))
        self.eq = StaticEQ(bands, self.sr, 2) if bands else None

    def process(self, x: np.ndarray) -> np.ndarray:
        if not self.enabled or self.eq is None:
            return x
        return self.eq.process(x)


# --------------------------------------------------------------------------
# Sidechain ducker — the pump
# --------------------------------------------------------------------------
class Sidechain:
    """Volume ducking triggered by the kick.

    This is the 'ghost kick' technique: rather than following an audio detector,
    it fires a shaped gain curve on every trigger, which is exactly how the
    pumping in modern house records is made — tight, predictable, musical.
    """

    __slots__ = ("sr", "amount", "release", "shape", "_pos", "_active")

    def __init__(self, sr: int = SR, amount: float = 0.0,
                 release: float = 0.28, shape: float = 1.8):
        self.sr = sr
        self.amount = float(amount)
        self.release = float(release)
        self.shape = float(shape)
        self._pos = 10 ** 9        # samples since last trigger
        self._active = False

    def trigger(self, offset: int = 0) -> None:
        self._pos = -int(offset)
        self._active = True

    def gain(self, n: int) -> np.ndarray | None:
        """Return an (n,) gain curve, or None when there is nothing to do."""
        if self.amount <= 1e-4 or not self._active:
            self._pos += n
            return None
        rel = max(self.release * self.sr, 1.0)
        t = self._pos + np.arange(n, dtype=np.float32)
        self._pos += n
        frac = np.clip(t / rel, 0.0, 1.0)
        # 0 -> fully ducked, 1 -> fully recovered, with a curved recovery
        duck = 1.0 - self.amount * (1.0 - frac) ** self.shape
        duck[t < 0] = 1.0
        if self._pos > rel:
            self._active = False
        return duck.astype(np.float32)


SIDECHAIN_PARAMS = (
    Param("sc_amount", "Amount", 0.0, 1.0, 0.0, "%", "lin", "Sidechain"),
    Param("sc_release", "Release", 0.02, 1.2, 0.28, "ms", "log", "Sidechain"),
    Param("sc_shape", "Shape", 0.3, 5.0, 1.8, "", "lin", "Sidechain"),
)


EFFECTS: dict[str, type[Effect]] = {
    "eq": EQ3,
    "drive": Drive,
    "djfilter": DJFilter,
    "chorus": Chorus,
    "phaser": Phaser,
    "delay": Delay,
    "reverb": Reverb,
    "comp": Compressor,
    "limiter": Limiter,
}
