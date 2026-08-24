"""Pulling a mix apart: stems, individual hits, and what each hit is.

This is classical DSP — harmonic/percussive median filtering, band splitting,
NMF and onset slicing. It is not a trained stem separator: it will not lift a
clean vocal out of a finished master. What it does do well is split drums from
tone, isolate the low end, and cut the percussion into individual one-shots you
can actually reuse.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import butter, sosfilt

from .features import (HOP, N_FFT, SR, hpss, istft, nmf, onset_strength,
                       pick_onsets, spectral_centroid, spectral_flatness, stft)

ROLES = ("Kick", "Snare", "Clap", "Hat", "Cymbal", "Tom", "Perc")


def _band(x: np.ndarray, sr: int, lo: float | None, hi: float | None) -> np.ndarray:
    if lo and hi:
        sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    elif lo:
        sos = butter(4, lo, btype="highpass", fs=sr, output="sos")
    elif hi:
        sos = butter(4, hi, btype="lowpass", fs=sr, output="sos")
    else:
        return x
    return sosfilt(sos, x).astype(np.float32)


@dataclass
class Stems:
    drums: np.ndarray            # percussive + low body: good to slice from
    bass: np.ndarray
    harmonic: np.ndarray
    full: np.ndarray
    percussive: np.ndarray = None   # transients only: good to find onsets in
    sr: int = SR

    def as_dict(self) -> dict[str, np.ndarray]:
        return {"Drums": self.drums, "Bass": self.bass, "Melodic": self.harmonic}


def separate(x: np.ndarray, sr: int = SR,
             bass_cutoff: float = 180.0) -> Stems:
    """Split into percussive, low-end and melodic layers."""
    S = stft(x)
    H, P = hpss(S)
    n = len(x)
    perc = istft(P, length=n)
    harm = istft(H, length=n)
    bass = _band(harm, sr, None, bass_cutoff)
    mel = _band(harm, sr, bass_cutoff, None)
    # A kick's body is a decaying sine, so HPSS files it as *harmonic* and the
    # percussive layer keeps only the click. Fold the low band back in or the
    # drum layer has no kick in it at all.
    drums = (perc + _band(harm, sr, None, 160.0)).astype(np.float32)
    return Stems(drums=drums, bass=bass, harmonic=mel, full=x,
                 percussive=perc, sr=sr)


def nmf_components(x: np.ndarray, n_components: int = 5, sr: int = SR,
                   iters: int = 90) -> list[np.ndarray]:
    """Unsupervised split into recurring spectral templates."""
    S = stft(x)
    V = np.abs(S)
    W, Hm = nmf(V, n_components, iters)
    out = []
    total = (W @ Hm) + 1e-9
    for k in range(n_components):
        mask = np.outer(W[:, k], Hm[k]) / total
        out.append(istft((S * mask).astype(np.complex64), length=len(x)))
    # loudest first
    out.sort(key=lambda a: -float(np.sqrt(np.mean(a ** 2))))
    return out


# --------------------------------------------------------------------------
@dataclass
class Hit:
    start: int                  # sample index in the source
    audio: np.ndarray
    role: str = "Perc"
    centroid: float = 0.0
    low_ratio: float = 0.0
    duration: float = 0.0
    step: int = -1              # position on the 16th grid
    cluster: int = -1

    @property
    def peak(self) -> float:
        return float(np.max(np.abs(self.audio))) if self.audio.size else 0.0


def _describe_hit(a: np.ndarray, sr: int) -> tuple[float, float, float, float, float]:
    """(centroid, low_ratio, body_ratio, flatness, duration)."""
    if a.size < 256:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    n = min(len(a), 8192)
    mag = np.abs(np.fft.rfft(a[:n] * np.hanning(n)))
    f = np.fft.rfftfreq(n, 1 / sr)
    tot = mag.sum() + 1e-9
    centroid = float((mag * f).sum() / tot)
    low_ratio = float(mag[f < 200].sum() / tot)
    body_ratio = float(mag[(f >= 150) & (f < 450)].sum() / tot)
    m = np.maximum(mag, 1e-9)
    flatness = float(np.exp(np.log(m).mean()) / m.mean())
    env = np.abs(a)
    thr = env.max() * 0.06 if env.size else 0.0
    nz = np.where(env > thr)[0]
    dur = float((nz[-1] - nz[0]) / sr) if nz.size > 1 else 0.0
    return centroid, low_ratio, body_ratio, flatness, dur


def classify_hit(centroid: float, low_ratio: float, body_ratio: float,
                 flatness: float, duration: float) -> str:
    """Rules fitted to measured features of real drum sounds.

    Spectral flatness does most of the work: kicks and toms are near-sinusoidal
    (flatness ~0.005), snares and claps are noise (0.4-0.5), and the split
    between those two is that a snare is flatter and brighter than a clap.
    """
    if flatness < 0.06:                      # strongly tonal -> a drum with pitch
        if centroid < 260 and low_ratio > 0.45:
            return "Kick"
        if centroid < 800:
            return "Tom"
        return "Perc"
    if low_ratio > 0.5 and centroid < 400:
        return "Kick"
    if centroid > 9000:
        return "Cymbal" if (duration > 0.45 or flatness > 0.55) else "Hat"
    if centroid > 3000:
        if body_ratio > 0.2:
            return "Perc"
        return "Snare" if flatness >= 0.44 else "Clap"
    if centroid > 1200:
        if body_ratio > 0.18:
            return "Perc"
        return "Snare" if flatness > 0.42 else "Perc"
    if low_ratio > 0.35:
        return "Kick" if duration > 0.15 else "Tom"
    return "Perc"


def extract_hits(perc: np.ndarray, sr: int = SR, max_hits: int = 400,
                 max_len: float = 0.6) -> list[Hit]:
    """Slice the percussive layer at its onsets into individual one-shots."""
    S = np.abs(stft(perc))
    env = onset_strength(S)
    onsets = pick_onsets(env, sr, HOP, delta=0.12, min_gap_s=0.045)
    if onsets.size == 0:
        return []
    starts = (onsets * HOP).astype(int)
    hits: list[Hit] = []
    limit = int(max_len * sr)
    for i, s0 in enumerate(starts[:max_hits]):
        s0 = max(int(s0) - int(0.004 * sr), 0)          # small pre-roll
        s1 = int(starts[i + 1]) if i + 1 < len(starts) else len(perc)
        s1 = min(max(s1, s0 + 1024), s0 + limit, len(perc))
        a = perc[s0:s1].copy()
        if a.size < 512 or float(np.max(np.abs(a))) < 1e-4:
            continue
        # short fade so slices do not click
        fade = min(256, a.size // 8)
        if fade > 4:
            a[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        c, lr, br, fl, d = _describe_hit(a, sr)
        hits.append(Hit(start=s0, audio=a,
                        role=classify_hit(c, lr, br, fl, d),
                        centroid=c, low_ratio=lr, duration=d))
    return hits


def cluster_hits(hits: list[Hit], per_role: int = 3) -> dict[str, list[Hit]]:
    """Group near-identical hits and keep the cleanest few per role.

    A four-minute track has hundreds of kicks; you want two or three good ones.
    """
    out: dict[str, list[Hit]] = {}
    by_role: dict[str, list[Hit]] = {}
    for h in hits:
        by_role.setdefault(h.role, []).append(h)
    for role, group in by_role.items():
        if len(group) <= per_role:
            out[role] = sorted(group, key=lambda h: -h.peak)
            continue
        feats = np.array([[np.log10(max(h.centroid, 20.0)), h.low_ratio,
                           np.log10(max(h.duration, 1e-3))] for h in group])
        feats = (feats - feats.mean(0)) / (feats.std(0) + 1e-9)
        k = min(per_role, len(group))
        try:
            from sklearn.cluster import KMeans
            labels = KMeans(n_clusters=k, n_init=4,
                            random_state=0).fit_predict(feats)
        except Exception:
            labels = np.zeros(len(group), dtype=int)
        picked = []
        for c in range(k):
            members = [h for h, l in zip(group, labels) if l == c]
            if members:
                best = max(members, key=lambda h: h.peak)
                best.cluster = c
                picked.append(best)
        out[role] = sorted(picked, key=lambda h: -h.peak)
    return out


def drum_pattern(hits: list[Hit], n_bars: int,
                 steps_per_bar: int = 16,
                 min_fraction: float = 0.35) -> dict[str, list[int]]:
    """Which 16th steps each role lands on, as a fraction of the bars analysed.

    Thresholding on bar count rather than on the peak is what stops a long
    track from reporting that every drum plays on every step.
    """
    counts: dict[str, np.ndarray] = {}
    for h in hits:
        if h.step < 0:
            continue
        counts.setdefault(h.role, np.zeros(steps_per_bar))[h.step % steps_per_bar] += 1
    n_bars = max(int(n_bars), 1)
    pattern: dict[str, list[int]] = {}
    for role, arr in counts.items():
        keep = np.where(arr >= max(min_fraction * n_bars, 2))[0]
        if keep.size:
            pattern[role] = sorted(int(v) for v in keep)
    return pattern


def pattern_velocities(hits: list[Hit], n_bars: int,
                       steps_per_bar: int = 16) -> dict[str, dict[int, float]]:
    """Average relative loudness per role per step, for accents."""
    acc: dict[str, dict[int, list[float]]] = {}
    for h in hits:
        if h.step < 0:
            continue
        acc.setdefault(h.role, {}).setdefault(h.step % steps_per_bar, []).append(h.peak)
    out: dict[str, dict[int, float]] = {}
    for role, steps in acc.items():
        peak = max((max(v) for v in steps.values()), default=1.0) or 1.0
        out[role] = {s: float(np.clip(np.mean(v) / peak, 0.2, 1.0))
                     for s, v in steps.items()}
    return out


# --------------------------------------------------------------------------
# Band-limited onset detection
# --------------------------------------------------------------------------
# Classifying a slice of a finished mix does not work: a slice at beat 1 holds
# a kick, a hat and part of the bass at once. Detecting onsets separately in the
# band each drum occupies sidesteps the overlap entirely.
ROLE_BANDS: dict[str, tuple[float, float]] = {
    "Kick":  (30.0, 140.0),
    "Tom":   (140.0, 350.0),
    "Perc":  (350.0, 1500.0),
    "Snare": (1800.0, 6000.0),
    "Hat":   (8000.0, 16000.0),
}


def band_onset_envelope(mag: np.ndarray, lo: float, hi: float, sr: int = SR,
                        n_fft: int = N_FFT) -> np.ndarray:
    from .features import freqs, onset_strength
    f = freqs(n_fft, sr)
    sel = (f >= lo) & (f < hi)
    if not sel.any():
        return np.zeros(mag.shape[1], dtype=np.float32)
    return onset_strength(mag[sel], sr)


def role_onsets(x: np.ndarray, sr: int = SR,
                delta: float = 0.28) -> dict[str, np.ndarray]:
    """Onset frames per drum role, found in that role's own frequency band."""
    mag = np.abs(stft(x))
    out: dict[str, np.ndarray] = {}
    for role, (lo, hi) in ROLE_BANDS.items():
        env = band_onset_envelope(mag, lo, hi, sr)
        gap = 0.09 if role == "Kick" else 0.05
        out[role] = pick_onsets(env, sr, HOP, delta=delta, min_gap_s=gap)
    return out


def pattern_from_role_onsets(onsets: dict[str, np.ndarray], beats,
                             steps_per_bar: int = 16,
                             min_fraction: float = 0.4) -> dict[str, list[int]]:
    """Quantise each role's onsets onto the 16th grid and keep the steady steps."""
    from .tempo import quantise
    n_bars = max(len(beats.bar_times) - 1, 1)
    pattern: dict[str, list[int]] = {}
    for role, frames in onsets.items():
        if frames.size == 0:
            continue
        steps = quantise(frames.astype(float), beats)
        if steps.size == 0:
            continue
        hist = np.bincount(steps % steps_per_bar, minlength=steps_per_bar)
        keep = np.where(hist >= max(min_fraction * n_bars, 2))[0]
        if keep.size:
            pattern[role] = sorted(int(v) for v in keep)
    return pattern


def role_velocities(x: np.ndarray, onsets: dict[str, np.ndarray], beats,
                    sr: int = SR, steps_per_bar: int = 16
                    ) -> dict[str, dict[int, float]]:
    """Relative loudness per role per step, so accents survive the round trip."""
    from .tempo import quantise
    mag = np.abs(stft(x))
    out: dict[str, dict[int, float]] = {}
    for role, (lo, hi) in ROLE_BANDS.items():
        frames = onsets.get(role, np.array([], dtype=int))
        if frames.size == 0:
            continue
        env = band_onset_envelope(mag, lo, hi, sr)
        steps = quantise(frames.astype(float), beats)
        n = min(len(steps), len(frames))
        acc: dict[int, list[float]] = {}
        for i in range(n):
            fr = int(np.clip(frames[i], 0, len(env) - 1))
            acc.setdefault(int(steps[i]) % steps_per_bar, []).append(float(env[fr]))
        if not acc:
            continue
        top = max(max(v) for v in acc.values()) or 1.0
        out[role] = {s: float(np.clip(np.mean(v) / top, 0.25, 1.0))
                     for s, v in acc.items()}
    return out
