"""Turn the files you give it into training grains."""
from __future__ import annotations

import os

import numpy as np

from ..analysis.features import onset_strength, pick_onsets, stft, to_mono
from ..audio.wavio import read_audio
from .spectral import FRAMES, HOP, N_FFT, patch_features, to_patch

GRAIN_LEN = FRAMES * HOP + N_FFT          # samples covered by one patch


def grains_from_audio(x: np.ndarray, sr: int = 44100, max_grains: int = 3000,
                      use_onsets: bool = True, seed: int = 0) -> list[np.ndarray]:
    """Cut audio into overlapping grains, favouring note starts."""
    x = to_mono(x)
    if x.size < GRAIN_LEN:
        x = np.pad(x, (0, GRAIN_LEN - x.size))
    starts: list[int] = []
    if use_onsets:
        env = onset_strength(np.abs(stft(x)))
        on = pick_onsets(env, delta=0.12, min_gap_s=0.04)
        starts.extend(int(max(o * 512 - int(0.005 * sr), 0)) for o in on)
    # plus a regular sweep so sustained material is represented too
    step = max(GRAIN_LEN // 3, 1)
    starts.extend(range(0, max(len(x) - GRAIN_LEN, 1), step))
    rng = np.random.default_rng(seed)
    starts = sorted(set(s for s in starts if s + GRAIN_LEN <= len(x)))
    if len(starts) > max_grains:
        starts = list(rng.choice(starts, max_grains, replace=False))
    out = []
    for s in starts:
        g = x[s:s + GRAIN_LEN]
        peak = float(np.max(np.abs(g)))
        if peak < 1e-3:
            continue
        out.append((g / peak * 0.9).astype(np.float32))
    return out


MIN_GRAINS = 96


def augment(grains: list[np.ndarray], target: int, sr: int = 44100,
            seed: int = 0) -> list[np.ndarray]:
    """Grow a small set of grains by shifting and resampling them.

    A folder of one-shots yields one grain per file, which is far too few to
    train on. Offsetting in time and resampling gives genuine variety without
    inventing anything that is not in the source material.
    """
    if not grains or len(grains) >= target:
        return grains
    rng = np.random.default_rng(seed)
    out = list(grains)
    n = len(grains)
    i = 0
    while len(out) < target:
        g = grains[i % n]
        i += 1
        rate = float(rng.uniform(0.82, 1.22))
        idx = np.arange(0, len(g) - 1, rate)
        i0 = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        y = g[i0] * (1 - frac) + g[np.minimum(i0 + 1, len(g) - 1)] * frac
        shift = int(rng.integers(0, max(GRAIN_LEN // 4, 1)))
        y = np.concatenate([np.zeros(shift, dtype=np.float32), y])
        if len(y) < GRAIN_LEN:
            y = np.pad(y, (0, GRAIN_LEN - len(y)))
        y = y[:GRAIN_LEN]
        peak = float(np.max(np.abs(y)))
        if peak < 1e-4:
            continue
        out.append((y / peak * 0.9).astype(np.float32))
    return out


def build_dataset(paths: list[str], progress=None, max_grains: int = 4000
                  ) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Returns (patches (n,BINS,FRAMES), features (n,4), raw grains)."""
    grains: list[np.ndarray] = []
    per_file = max(max_grains // max(len(paths), 1), 64)
    for i, p in enumerate(paths):
        if progress is not None:
            progress(i / max(len(paths), 1), f"Reading {os.path.basename(p)}…")
        try:
            audio, sr = read_audio(p)
        except Exception:
            continue
        grains.extend(grains_from_audio(audio, sr, per_file, seed=i))
    if not grains:
        return np.zeros((0, 0, 0), np.float32), np.zeros((0, 4), np.float32), []
    if len(grains) < MIN_GRAINS:
        if progress is not None:
            progress(0.9, f"only {len(grains)} grains — augmenting…")
        grains = augment(grains, MIN_GRAINS)
    patches = np.stack([to_patch(g) for g in grains])
    feats = np.stack([patch_features(p) for p in patches])
    return patches, feats, grains
