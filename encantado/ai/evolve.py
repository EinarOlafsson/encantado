"""The refinement loop: generate, judge, breed, repeat.

This is what makes the studio a process rather than a button. You never get one
opaque render — you get a population, you say what you like, and the next
population is bred from that. Locked variations survive untouched.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .spectral import FEATURE_NAMES


@dataclass(eq=False)          # identity comparison: the fields are numpy arrays
class Variation:
    latent: np.ndarray
    audio: np.ndarray | None = None
    patch: np.ndarray | None = None
    rating: int = 0                 # -1 rejected, 0 unheard, +1 kept
    locked: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    generation: int = 0
    label: str = ""

    @property
    def liked(self) -> bool:
        return self.rating > 0 or self.locked


class Studio:
    """Holds the population and the breeding rules."""

    def __init__(self, model, size: int = 8, seed: int = 0):
        self.model = model
        self.size = size
        self.rng = np.random.default_rng(seed)
        self.population: list[Variation] = []
        self.generation = 0
        self.spread = 1.0
        self.mutation = 0.35
        self.macro_offset = np.zeros(len(FEATURE_NAMES), dtype=np.float32)

    # -- population ----------------------------------------------------------
    def seed(self, from_training: bool = True) -> None:
        z = (self.model.seed_from_training(self.size, self.rng) if from_training
             else self.model.sample(self.size, self.spread, self.rng))
        self.generation = 0
        self.population = [Variation(latent=z[i], generation=0,
                                     label=f"v{i + 1}") for i in range(self.size)]

    def _macro_vector(self) -> np.ndarray:
        if self.model.macro is None:
            return np.zeros(self.model.latent, dtype=np.float32)
        scale = getattr(self.model, "macro_scale", None)
        if scale is None:
            scale = np.ones(len(self.macro_offset), dtype=np.float32)
        return ((self.macro_offset * scale)[:, None] * self.model.macro
                ).sum(0).astype(np.float32)

    def latent_of(self, v: Variation) -> np.ndarray:
        return (v.latent + self._macro_vector()).astype(np.float32)

    def set_macro(self, index: int, value: float) -> None:
        if 0 <= index < len(self.macro_offset):
            self.macro_offset[index] = float(value)

    # -- breeding ------------------------------------------------------------
    def evolve(self) -> None:
        """Next generation: keep what you locked, breed from what you liked."""
        parents = [v for v in self.population if v.liked]
        keep = [v for v in self.population if v.locked]
        if not parents:
            # nothing chosen yet — explore instead of exploiting
            self.seed(from_training=self.generation == 0)
            self.generation += 1
            for v in self.population:
                v.generation = self.generation
            return

        self.generation += 1
        nxt: list[Variation] = []
        for v in keep:
            v.generation = self.generation
            nxt.append(v)
        # the best parents carry forward unchanged so progress is never lost
        kept_ids = {id(v) for v in nxt}
        for v in parents:
            if id(v) not in kept_ids and len(nxt) < max(self.size // 3, 1):
                nxt.append(Variation(latent=v.latent.copy(), rating=1,
                                     generation=self.generation,
                                     label=v.label + "'"))
        P = np.stack([v.latent for v in parents])
        rejected = [v.latent for v in self.population if v.rating < 0]
        R = np.stack(rejected) if rejected else None
        i = 0
        while len(nxt) < self.size:
            if len(P) >= 2:
                a, b = self.rng.choice(len(P), 2, replace=False)
                t = self.rng.random()
                z = P[a] * t + P[b] * (1 - t)
            else:
                z = P[0].copy()
            z = z + self.rng.standard_normal(z.shape).astype(np.float32) \
                * self.mutation * (self.model.z_std if self.model.z_std is not None else 1.0)
            if R is not None and len(R):
                # push away from what you rejected
                d = z - R[self.rng.integers(len(R))]
                nrm = np.linalg.norm(d)
                if nrm > 1e-6:
                    z = z + (d / nrm) * self.mutation * 0.5
            i += 1
            nxt.append(Variation(latent=z.astype(np.float32),
                                 generation=self.generation,
                                 label=f"g{self.generation}.{i}"))
        self.population = nxt[:self.size]

    def refresh(self) -> None:
        """Throw the unliked ones away and draw new ones."""
        z = self.model.seed_from_training(self.size, self.rng)
        j = 0
        for i, v in enumerate(self.population):
            if v.liked:
                continue
            self.population[i] = Variation(latent=z[j % len(z)],
                                           generation=self.generation,
                                           label=f"n{self.generation}.{i + 1}")
            j += 1

    def render(self, v: Variation, n_iter: int = 40) -> np.ndarray:
        v.audio = self.model.render(self.latent_of(v), n_iter=n_iter)
        return v.audio

    def decode_all(self) -> None:
        """Latents -> spectrogram patches. Touches the GPU, so the caller must
        run this on the main thread; CUDA in a Qt worker thread crashes."""
        if not self.population:
            return
        Z = np.stack([self.latent_of(v) for v in self.population])
        patches = self.model.decode(Z)
        for v, p in zip(self.population, patches):
            v.patch = p

    def vocode_all(self, n_iter: int = 32, progress=None) -> None:
        """Patches -> audio. Pure numpy, so this is safe in a worker thread."""
        from .spectral import patch_to_audio
        for i, v in enumerate(self.population):
            if v.patch is None:
                continue
            v.audio = patch_to_audio(v.patch, n_iter=n_iter)
            if progress is not None and progress(
                    (i + 1) / len(self.population), v.label) is False:
                return

    def render_all(self, n_iter: int = 32, progress=None) -> None:
        self.decode_all()
        self.vocode_all(n_iter, progress)
