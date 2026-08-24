"""Tempo, beat grid, downbeats and groove."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .features import HOP, SR, frame_rate

MIN_BPM = 60.0
MAX_BPM = 200.0
PRIOR_CENTRE = 122.0        # this app's home territory
PRIOR_WIDTH = 0.9           # in octaves


@dataclass
class Beats:
    bpm: float
    confidence: float
    beat_frames: np.ndarray = field(default_factory=lambda: np.array([]))
    downbeat_offset: int = 0            # which beat index starts a bar
    swing: float = 0.0                  # 0 = straight, 1 = full triplet
    onset_frames: np.ndarray = field(default_factory=lambda: np.array([]))
    sr: int = SR
    hop: int = HOP

    @property
    def beat_times(self) -> np.ndarray:
        return self.beat_frames * self.hop / self.sr

    @property
    def period_frames(self) -> float:
        return 60.0 * frame_rate(self.sr, self.hop) / max(self.bpm, 1e-6)

    @property
    def bar_times(self) -> np.ndarray:
        if self.beat_frames.size == 0:
            return np.array([])
        idx = np.arange(self.downbeat_offset, len(self.beat_frames), 4)
        return self.beat_frames[idx] * self.hop / self.sr


def _autocorr(env: np.ndarray) -> np.ndarray:
    n = int(2 ** np.ceil(np.log2(max(len(env) * 2, 2))))
    f = np.fft.rfft(env - env.mean(), n=n)
    ac = np.fft.irfft(f * np.conj(f), n=n)[:len(env)]
    return ac / max(ac[0], 1e-9)


def _comb_score(env: np.ndarray, period: float) -> tuple[float, int]:
    """Best phase for a pulse train, scored as onset energy at the pulses
    relative to the overall mean. The ratio is what makes scores at different
    periods comparable — an absolute sum quietly favours longer periods."""
    p = int(round(period))
    if p < 2 or p >= len(env):
        return 0.0, 0
    n_pulses = len(env) // p
    if n_pulses < 3:
        return 0.0, 0
    grid = (np.arange(n_pulses) * p)[None, :] + np.arange(p)[:, None]
    grid = np.clip(grid, 0, len(env) - 1)
    means = env[grid].mean(axis=1)
    phase = int(np.argmax(means))
    baseline = max(float(env.mean()), 1e-9)
    return float(means[phase] / baseline), phase


def estimate_tempo(env: np.ndarray, sr: int = SR, hop: int = HOP) -> tuple[float, float]:
    """Returns (bpm, confidence 0-1)."""
    fr = frame_rate(sr, hop)
    if env.size < fr * 4:
        return PRIOR_CENTRE, 0.0
    ac = _autocorr(env)
    lag_min = max(int(60.0 * fr / MAX_BPM), 2)
    lag_max = min(int(60.0 * fr / MIN_BPM), len(ac) - 1)
    if lag_max <= lag_min:
        return PRIOR_CENTRE, 0.0
    lags = np.arange(lag_min, lag_max + 1)
    bpms = 60.0 * fr / lags
    prior = np.exp(-0.5 * (np.log2(bpms / PRIOR_CENTRE) / PRIOR_WIDTH) ** 2)
    score = ac[lags] * prior
    if not np.any(score > 0):
        return PRIOR_CENTRE, 0.0

    best_lag = int(lags[int(np.argmax(score))])
    bpm = 60.0 * fr / best_lag

    # only genuine metrical relatives are considered, and only to settle which
    # octave the pulse sits in -- admitting ratios like 5/4 invents tempos
    cands = []
    for mult in (0.5, 1.0, 2.0):
        c = bpm * mult
        if MIN_BPM <= c <= MAX_BPM:
            s_c, _ = _comb_score(env, 60.0 * fr / c)
            s_c *= np.exp(-0.5 * (np.log2(c / PRIOR_CENTRE) / PRIOR_WIDTH) ** 2)
            cands.append((s_c, c))
    if not cands:
        return float(bpm), 0.0
    cands.sort(reverse=True)
    best_score, best_bpm = cands[0]
    runner = cands[1][0] if len(cands) > 1 else 0.0
    conf = float(np.clip((best_score - 1.0) / 1.5, 0.0, 1.0))
    if runner > 0:
        conf *= float(np.clip(best_score / max(runner, 1e-9) - 1.0, 0.15, 1.0))
    return float(best_bpm), float(np.clip(conf, 0.0, 1.0))


def track_beats(env: np.ndarray, bpm: float, sr: int = SR,
                hop: int = HOP) -> np.ndarray:
    """Follow the beat, predicting each one from the last beat actually found.

    A grid laid down from a single origin drifts: a 1 BPM tempo error is a whole
    beat adrift after a minute, which smears every extracted pattern across all
    sixteen steps. Tracking forward from each accepted beat keeps the grid
    locked to the audio even when the tempo estimate is slightly off.
    """
    fr = frame_rate(sr, hop)
    period = 60.0 * fr / max(bpm, 1e-6)
    if period < 2 or env.size < period * 2:
        return np.array([], dtype=int)
    _s, phase = _comb_score(env, period)

    win = max(int(period * 0.14), 1)
    beats = [int(phase)]
    predicted = phase + period
    while predicted < len(env) - 1:
        lo = int(max(predicted - win, beats[-1] + period * 0.5))
        hi = int(min(predicted + win + 1, len(env)))
        if hi <= lo:
            pos = int(predicted)
        else:
            seg = env[lo:hi]
            pos = lo + int(np.argmax(seg)) if float(seg.max()) > 1e-6 else int(predicted)
        beats.append(pos)
        # let the grid follow real drift, but only a little per beat
        predicted = pos + period
    return np.array(beats, dtype=int)


def refine_tempo(beats: np.ndarray, sr: int = SR, hop: int = HOP) -> float:
    """Tempo implied by the beats we actually found."""
    if beats.size < 4:
        return 0.0
    d = np.diff(beats.astype(float))
    d = d[(d > 0)]
    if d.size == 0:
        return 0.0
    med = float(np.median(d))
    keep = d[np.abs(d - med) < med * 0.25]
    period = float(np.mean(keep)) if keep.size else med
    return 60.0 * frame_rate(sr, hop) / max(period, 1e-6)


def find_downbeat(env: np.ndarray, beats: np.ndarray) -> int:
    """Which of the first four beats carries the most weight."""
    if beats.size < 8:
        return 0
    best, best_i = -1.0, 0
    for off in range(4):
        idx = beats[off::4]
        if idx.size == 0:
            continue
        v = float(env[np.clip(idx, 0, len(env) - 1)].mean())
        if v > best:
            best, best_i = v, off
    return best_i


def estimate_swing(env: np.ndarray, beats: np.ndarray,
                   onsets: np.ndarray) -> float:
    """How late the off-8ths sit: 0 straight, ~1 triplet."""
    if beats.size < 4 or onsets.size < 8:
        return 0.0
    period = float(np.mean(np.diff(beats)))
    if period <= 0:
        return 0.0
    ratios = []
    for b0, b1 in zip(beats[:-1], beats[1:]):
        mid_lo, mid_hi = b0 + period * 0.25, b0 + period * 0.85
        cand = onsets[(onsets > mid_lo) & (onsets < mid_hi)]
        if cand.size:
            pos = (cand[np.argmin(np.abs(cand - (b0 + period * 0.5)))] - b0) / period
            ratios.append(pos)
    if not ratios:
        return 0.0
    med = float(np.median(ratios))
    # 0.5 = straight, 0.667 = triplet swing
    return float(np.clip((med - 0.5) / (2 / 3 - 0.5), 0.0, 1.5))


def analyse_beats(env: np.ndarray, onsets: np.ndarray, sr: int = SR,
                  hop: int = HOP) -> Beats:
    bpm, conf = estimate_tempo(env, sr, hop)
    beats = track_beats(env, bpm, sr, hop)
    # one refinement pass: retrack at the tempo the beats themselves imply
    refined = refine_tempo(beats, sr, hop)
    if refined > 0 and abs(refined - bpm) < bpm * 0.06:
        bpm = refined
        beats = track_beats(env, bpm, sr, hop)
    down = find_downbeat(env, beats)
    swing = estimate_swing(env, beats, onsets)
    return Beats(bpm=bpm, confidence=conf, beat_frames=beats,
                 downbeat_offset=down, swing=swing, onset_frames=onsets,
                 sr=sr, hop=hop)


def quantise(onsets: np.ndarray, beats: Beats, subdiv: int = 4) -> np.ndarray:
    """Map onset frames onto a 16th grid using the tracked beats themselves.

    Interpolating inside each real beat interval, rather than off one fixed
    period, is what makes this survive tempo drift and human timing.
    """
    bf = beats.beat_frames.astype(float)
    if bf.size < 2 or onsets.size == 0:
        return np.array([], dtype=int)
    on = np.asarray(onsets, dtype=float)
    idx = np.clip(np.searchsorted(bf, on) - 1, 0, bf.size - 2)
    span = np.maximum(bf[idx + 1] - bf[idx], 1e-6)
    frac = np.clip((on - bf[idx]) / span, 0.0, 1.0)
    steps = (idx - beats.downbeat_offset) * subdiv + np.round(frac * subdiv)
    return steps.astype(int)
