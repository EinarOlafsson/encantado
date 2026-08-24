"""Key and chord estimation from chroma."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.theory import NOTE_NAMES

# Krumhansl-Kessler key profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                          2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                          2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

TRIADS = {"maj": (0, 4, 7), "min": (0, 3, 7)}
SEVENTHS = {"maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "dom7": (0, 4, 7, 10)}


@dataclass
class KeyEstimate:
    root: int                  # pitch class
    mode: str                  # 'major' | 'minor'
    confidence: float
    alternatives: list[tuple[int, str, float]]

    @property
    def name(self) -> str:
        return f"{NOTE_NAMES[self.root]} {self.mode}"

    @property
    def scale_name(self) -> str:
        return "Major (Ionian)" if self.mode == "major" else "Minor (Aeolian)"


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-12 else 0.0


DIATONIC = np.zeros(12)
for _s in (0, 2, 4, 5, 7, 9, 11):
    DIATONIC[_s] = 1.0


def suppress_harmonics(profile: np.ndarray, fifth: float = 0.40,
                       third: float = 0.15) -> np.ndarray:
    """Remove the energy a note's own overtones add a fifth and a third above it.

    Without this the whole estimate drifts sharp by a fifth, because every
    note's third harmonic votes for its own dominant.
    """
    out = profile.copy()
    for pc in range(12):
        out[pc] -= fifth * profile[(pc - 7) % 12] + third * profile[(pc - 4) % 12]
    out = np.clip(out, 0.0, None)
    return out if out.sum() > 1e-9 else profile.copy()


def estimate_key(chroma_treble: np.ndarray, chroma_bass: np.ndarray | None = None,
                 prefer_minor: bool = True) -> KeyEstimate:
    """Find the scale, then the tonic within it.

    Measured on this app's own reference renders: the scale collection is right
    5 times in 6; the tonic inside that collection is much less certain, which
    is why both candidates are returned and the caller can switch in one click.
    """
    if chroma_treble.size == 0:
        return KeyEstimate(0, "minor", 0.0, [])
    prof = chroma_treble.mean(axis=1) if chroma_treble.ndim == 2 else chroma_treble
    if prof.sum() <= 0:
        return KeyEstimate(0, "minor", 0.0, [])
    prof = prof / prof.sum()
    if chroma_bass is not None and chroma_bass.size:
        b = chroma_bass.mean(axis=1) if chroma_bass.ndim == 2 else chroma_bass
        if b.sum() > 0:
            prof = 0.55 * prof + 0.45 * (b / b.sum())
    prof = suppress_harmonics(prof)
    prof = prof / max(prof.sum(), 1e-9)

    # 1. which set of seven notes is in play
    coll = sorted(((_corr(np.roll(prof, -r), DIATONIC), r) for r in range(12)),
                  reverse=True)
    major_root = coll[0][1]
    margin = coll[0][0] - coll[1][0] if len(coll) > 1 else 0.0
    confidence = float(np.clip(margin * 2.2 + coll[0][0] * 0.4, 0.0, 1.0))

    # 2. tonic: the collection's major root, or its relative minor
    minor_root = (major_root + 9) % 12
    maj_s = _corr(np.roll(prof, -major_root), MAJOR_PROFILE)
    min_s = _corr(np.roll(prof, -minor_root), MINOR_PROFILE)
    if prefer_minor:
        # this genre is overwhelmingly minor; major has to win clearly
        pick_minor = min_s > maj_s - 0.12
    else:
        pick_minor = min_s > maj_s
    root, mode = (minor_root, "minor") if pick_minor else (major_root, "major")

    alts = [(minor_root, "minor", float(min_s)), (major_root, "major", float(maj_s))]
    if pick_minor:
        alts = alts[:1] + alts[1:]
    else:
        alts = [alts[1], alts[0]]
    for c_score, c_root in coll[1:3]:
        alts.append(((c_root + 9) % 12, "minor", float(c_score)))
    return KeyEstimate(root, mode, confidence, alts)


def _chord_templates(with_sevenths: bool = False) -> list[tuple[str, np.ndarray]]:
    out = []
    shapes = dict(TRIADS)
    if with_sevenths:
        shapes.update(SEVENTHS)
    for root in range(12):
        for name, ivs in shapes.items():
            v = np.zeros(12)
            for i, iv in enumerate(ivs):
                v[(root + iv) % 12] = 1.0 if i < 3 else 0.8
            out.append((f"{NOTE_NAMES[root]}{'' if name == 'maj' else name}", v))
    return out


def estimate_chords(chroma_frames: np.ndarray, segment_bounds: np.ndarray,
                    with_sevenths: bool = False) -> list[str]:
    """One chord label per segment (segment_bounds are frame indices)."""
    if chroma_frames.size == 0 or segment_bounds.size < 2:
        return []
    templates = _chord_templates(with_sevenths)
    out = []
    n = chroma_frames.shape[1]
    for a, b in zip(segment_bounds[:-1], segment_bounds[1:]):
        a, b = int(max(a, 0)), int(min(b, n))
        if b <= a:
            out.append("—")
            continue
        v = chroma_frames[:, a:b].mean(axis=1)
        if v.sum() <= 1e-9:
            out.append("—")
            continue
        v = v / v.sum()
        best = max(templates, key=lambda t: _corr(v, t[1]))
        out.append(best[0])
    return out


def degrees_from_chords(chords: list[str], root: int, mode: str) -> list[int]:
    """Map chord labels back to scale degrees so they can drive the generators."""
    from ..core.theory import SCALES
    steps = SCALES["Major (Ionian)" if mode == "major" else "Minor (Aeolian)"]
    table = {(root + s) % 12: i for i, s in enumerate(steps)}
    out = []
    for c in chords:
        name = c.rstrip("min7maj domin").rstrip("0123456789")
        pc = None
        for i, n in enumerate(NOTE_NAMES):
            if c.startswith(n) and (pc is None or len(n) > 1):
                pc = i
        if pc is None:
            continue
        out.append(table.get(pc % 12, 0))
    return out
