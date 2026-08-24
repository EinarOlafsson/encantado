"""Low-level analysis: STFT, onset strength, chroma, spectral descriptors.

Written directly on numpy/scipy so the app keeps its three-dependency footprint.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d

SR = 44100
N_FFT = 2048
HOP = 512


def to_mono(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return x.astype(np.float32)
    return x.mean(axis=1).astype(np.float32)


def frame_rate(sr: int = SR, hop: int = HOP) -> float:
    return sr / hop


def stft(x: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    """Magnitude-and-phase STFT, shape (bins, frames), complex64."""
    x = np.asarray(x, dtype=np.float32)
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = x[idx] * win
    return np.fft.rfft(frames, axis=1).astype(np.complex64).T


def istft(S: np.ndarray, hop: int = HOP, length: int | None = None) -> np.ndarray:
    """Overlap-add inverse with Hann analysis+synthesis (COLA at 75% overlap)."""
    n_fft = 2 * (S.shape[0] - 1)
    win = np.hanning(n_fft).astype(np.float32)
    frames = np.fft.irfft(S.T, n=n_fft, axis=1).astype(np.float32) * win
    n = (frames.shape[0] - 1) * hop + n_fft
    out = np.zeros(n, dtype=np.float32)
    norm = np.zeros(n, dtype=np.float32)
    for i in range(frames.shape[0]):
        s = i * hop
        out[s:s + n_fft] += frames[i]
        norm[s:s + n_fft] += win ** 2
    out /= np.maximum(norm, 1e-8)
    return out[:length] if length else out


def freqs(n_fft: int = N_FFT, sr: int = SR) -> np.ndarray:
    return np.fft.rfftfreq(n_fft, 1.0 / sr)


# --------------------------------------------------------------------------
def onset_strength(mag: np.ndarray, sr: int = SR, hop: int = HOP,
                   lag: int = 1) -> np.ndarray:
    """Spectral flux on a log-compressed magnitude spectrogram."""
    logm = np.log1p(mag * 8.0)
    diff = np.diff(logm, n=lag, axis=1)
    flux = np.maximum(diff, 0.0).sum(axis=0)
    flux = np.concatenate([np.zeros(lag, dtype=np.float32), flux])
    # subtract a moving average so slow level changes do not read as onsets
    base = uniform_filter1d(flux, size=int(frame_rate(sr, hop) * 0.35) | 1)
    env = np.maximum(flux - base, 0.0)
    # scale by a high percentile, not the max: one huge transient must not
    # squash the rest of the envelope into noise
    ref = float(np.percentile(env, 99)) if env.size else 0.0
    if ref <= 1e-9:
        return env.astype(np.float32)
    return np.clip(env / ref, 0.0, 4.0).astype(np.float32)


def pick_onsets(env: np.ndarray, sr: int = SR, hop: int = HOP,
                delta: float = 0.06, min_gap_s: float = 0.035) -> np.ndarray:
    """Peak positions (in frames) of the onset envelope."""
    if env.size < 3:
        return np.array([], dtype=int)
    gap = max(int(min_gap_s * frame_rate(sr, hop)), 1)
    cand = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:])
                    & (env[1:-1] > delta))[0] + 1
    if cand.size == 0:
        return cand
    keep = [cand[0]]
    for c in cand[1:]:
        if c - keep[-1] >= gap:
            keep.append(c)
        elif env[c] > env[keep[-1]]:
            keep[-1] = c
    return np.array(keep, dtype=int)


# --------------------------------------------------------------------------
def chroma(mag: np.ndarray, sr: int = SR, n_fft: int = N_FFT,
           fmin: float = 110.0, fmax: float = 3520.0,
           whiten: bool = True) -> np.ndarray:
    """(12, frames) pitch-class energy.

    The spectrum is whitened first — divided by its own smoothed envelope — so
    that the bass and kick, which carry most of the energy in dance music, do
    not simply decide the answer.
    """
    f = freqs(n_fft, sr)
    valid = (f >= fmin) & (f <= fmax)
    if not valid.any():
        return np.zeros((12, mag.shape[1]), dtype=np.float32)
    m = mag[valid]
    if whiten:
        env = median_filter(m, size=(max(m.shape[0] // 24 | 1, 3), 1),
                            mode="nearest")
        m = m / np.maximum(env, 1e-6)
        m = np.log1p(m)
    fv = f[valid]
    pc = np.round(12 * np.log2(np.maximum(fv, 1e-6) / 440.0) + 69).astype(int) % 12
    M = np.zeros((12, fv.size), dtype=np.float32)
    M[pc, np.arange(fv.size)] = 1.0
    C = M @ m
    norm = C.sum(axis=0, keepdims=True)
    return (C / np.maximum(norm, 1e-9)).astype(np.float32)


def chroma_hires(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """Chroma from a long window — low notes need the frequency resolution."""
    S = stft(x, n_fft=8192, hop=2048)
    return chroma(np.abs(S), sr=sr, n_fft=8192)


def spectral_centroid(mag: np.ndarray, sr: int = SR,
                      n_fft: int = N_FFT) -> np.ndarray:
    f = freqs(n_fft, sr)[:, None]
    tot = mag.sum(axis=0, keepdims=True)
    return ((mag * f).sum(axis=0) / np.maximum(tot[0], 1e-9)).astype(np.float32)


def spectral_flatness(mag: np.ndarray) -> np.ndarray:
    m = np.maximum(mag, 1e-9)
    gm = np.exp(np.log(m).mean(axis=0))
    am = m.mean(axis=0)
    return (gm / np.maximum(am, 1e-9)).astype(np.float32)


def spectral_rolloff(mag: np.ndarray, sr: int = SR, n_fft: int = N_FFT,
                     frac: float = 0.85) -> np.ndarray:
    f = freqs(n_fft, sr)
    c = np.cumsum(mag, axis=0)
    total = np.maximum(c[-1], 1e-9)
    idx = (c >= frac * total).argmax(axis=0)
    return f[idx].astype(np.float32)


def rms(x: np.ndarray, hop: int = HOP, n_fft: int = N_FFT) -> np.ndarray:
    n_frames = 1 + max(len(x) - n_fft, 0) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
    idx = np.clip(idx, 0, len(x) - 1)
    return np.sqrt((x[idx] ** 2).mean(axis=1)).astype(np.float32)


# --------------------------------------------------------------------------
def hpss(S: np.ndarray, kernel_time: int = 31, kernel_freq: int = 31,
         power: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Harmonic/percussive split by median filtering (Fitzgerald's method).

    Horizontal structure (sustained tones) survives a time-median; vertical
    structure (transients) survives a frequency-median. Soft Wiener masks then
    divide the original spectrum between the two.
    """
    mag = np.abs(S).astype(np.float32)
    H = median_filter(mag, size=(1, kernel_time), mode="nearest")
    P = median_filter(mag, size=(kernel_freq, 1), mode="nearest")
    Hp, Pp = H ** power, P ** power
    tot = Hp + Pp + 1e-9
    return (S * (Hp / tot)).astype(np.complex64), (S * (Pp / tot)).astype(np.complex64)


def nmf(V: np.ndarray, n_components: int = 6, iters: int = 120,
        seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Non-negative matrix factorisation, V ~= W @ H (multiplicative updates).

    W holds `n_components` spectral templates, H when each one is active — an
    unsupervised way of pulling recurring sounds apart.
    """
    rng = np.random.default_rng(seed)
    V = np.maximum(V.astype(np.float32), 1e-9)
    n, m = V.shape
    W = rng.random((n, n_components), dtype=np.float32) + 0.1
    H = rng.random((n_components, m), dtype=np.float32) + 0.1
    for _ in range(iters):
        WH = W @ H + 1e-9
        H *= (W.T @ (V / WH)) / np.maximum(W.T.sum(axis=1)[:, None], 1e-9)
        WH = W @ H + 1e-9
        W *= ((V / WH) @ H.T) / np.maximum(H.sum(axis=1)[None, :], 1e-9)
        scale = np.maximum(W.sum(axis=0, keepdims=True), 1e-9)
        W /= scale
        H *= scale.T
    return W, H
