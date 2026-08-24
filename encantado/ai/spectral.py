"""Spectral representation used by the model, and phase reconstruction."""
from __future__ import annotations

import numpy as np

from ..analysis.features import istft, stft

N_FFT = 1024
HOP = 256
BINS = 512                 # drop the Nyquist bin so the size is a power of two
FRAMES = 128               # ~0.74 s at 44.1 kHz
EPS = 1e-5
FLOOR_DB = -80.0


def to_patch(x: np.ndarray) -> np.ndarray:
    """Audio -> (BINS, FRAMES) log-magnitude in [0, 1].

    Each patch is normalised by its own peak before the dB conversion. Real
    STFT magnitudes run well above 1.0, so without this every loud partial
    saturates at the top of the range and the spectrum shape is destroyed.
    Normalising also makes the representation gain-invariant, which is what we
    want: the model should learn timbre, not how loud the file was.
    """
    S = np.abs(stft(x, n_fft=N_FFT, hop=HOP))[:BINS]
    if S.shape[1] < FRAMES:
        S = np.pad(S, ((0, 0), (0, FRAMES - S.shape[1])))
    S = S[:, :FRAMES]
    peak = float(S.max())
    if peak > 0:
        S = S / peak
    db = 20.0 * np.log10(np.maximum(S, EPS))
    return np.clip((db - FLOOR_DB) / (-FLOOR_DB), 0.0, 1.0).astype(np.float32)


def from_patch(p: np.ndarray) -> np.ndarray:
    """(BINS, FRAMES) in [0,1] -> linear magnitude spectrogram."""
    db = np.clip(p, 0.0, 1.0) * (-FLOOR_DB) + FLOOR_DB
    mag = 10.0 ** (db / 20.0)
    mag[mag <= EPS * 1.5] = 0.0
    full = np.zeros((N_FFT // 2 + 1, mag.shape[1]), dtype=np.float32)
    full[:BINS] = mag
    return full


def griffin_lim(mag: np.ndarray, n_iter: int = 48, seed: int = 0) -> np.ndarray:
    """Recover a waveform from a magnitude spectrogram (Griffin & Lim)."""
    rng = np.random.default_rng(seed)
    angle = np.exp(2j * np.pi * rng.random(mag.shape)).astype(np.complex64)
    S = (mag * angle).astype(np.complex64)
    x = istft(S, hop=HOP)
    for _ in range(n_iter):
        est = stft(x, n_fft=N_FFT, hop=HOP)
        n = min(est.shape[1], mag.shape[1])
        ang = est[:, :n] / np.maximum(np.abs(est[:, :n]), 1e-8)
        S = (mag[:, :n] * ang).astype(np.complex64)
        x = istft(S, hop=HOP)
    # Fade before normalising. Griffin-Lim leaves a large artifact at the very
    # first sample; normalising to that spike and then fading it away scales the
    # entire grain down to nothing.
    x = np.array(x, dtype=np.float32, copy=True)
    fade = min(128, max(x.size // 16, 0))
    if fade > 2:
        x[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        x[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak > 0:
        x = x / peak * 0.9
    return x.astype(np.float32)


def patch_to_audio(p: np.ndarray, n_iter: int = 48, seed: int = 0) -> np.ndarray:
    return griffin_lim(from_patch(p), n_iter, seed)


def patch_features(p: np.ndarray, sr: int = 44100) -> np.ndarray:
    """Descriptors used to build the macro controls: brightness, length, weight, noisiness."""
    mag = from_patch(p)
    f = np.fft.rfftfreq(N_FFT, 1.0 / sr)[:mag.shape[0]]
    energy = mag.sum(axis=0) + 1e-9
    total = energy.sum()
    centroid = float(((mag * f[:, None]).sum(axis=0) / energy * energy).sum() / total)
    env = energy / energy.max()
    length = float((env > 0.15).sum() / len(env))
    low = float(mag[f < 250].sum() / (mag.sum() + 1e-9))
    m = np.maximum(mag, 1e-9)
    flat = float(np.exp(np.log(m).mean()) / m.mean())
    return np.array([centroid / 8000.0, length, low, flat], dtype=np.float32)


FEATURE_NAMES = ("Brightness", "Length", "Weight", "Noisiness")
