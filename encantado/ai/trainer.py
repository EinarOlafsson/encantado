"""Training a grain model on the audio you provide."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from .model import LATENT, TORCH, GrainVAE, device, vae_loss
from .spectral import BINS, FEATURE_NAMES, FRAMES, patch_features, patch_to_audio

if TORCH:
    import torch


@dataclass
class TrainConfig:
    epochs: int = 140
    batch: int = 32
    lr: float = 5e-4
    beta: float = 6e-5
    max_seconds: float = 240.0
    seed: int = 0


class GrainModel:
    """A trained VAE plus everything needed to use it musically."""

    def __init__(self, latent: int = LATENT):
        if not TORCH:
            raise RuntimeError("PyTorch is required for the generation studio.")
        self.latent = latent
        self.net: GrainVAE | None = None
        self.dev = device()
        self.macro: np.ndarray | None = None          # (4, latent) unit vectors
        self.macro_scale: np.ndarray | None = None    # spread of the data along each
        self.active_dims = 0
        self.z_mean: np.ndarray | None = None
        self.z_std: np.ndarray | None = None
        self.train_latents: np.ndarray | None = None
        self.sources: list[str] = []
        self.history: list[float] = []
        self.n_grains = 0

    # -- training ------------------------------------------------------------
    def fit(self, patches: np.ndarray, cfg: TrainConfig | None = None,
            progress=None) -> None:
        cfg = cfg or TrainConfig()
        if patches.size == 0:
            raise ValueError("No usable audio was found in those files.")
        if patches.shape[0] < 16:
            raise ValueError(
                f"Only {patches.shape[0]} usable grains — that is too few to "
                "learn anything. Add more audio, or longer files.")
        torch.manual_seed(cfg.seed)
        self.net = GrainVAE(self.latent).to(self.dev)
        opt = torch.optim.Adam(self.net.parameters(), lr=cfg.lr)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, cfg.epochs)
        X = torch.from_numpy(patches).unsqueeze(1)
        n = X.shape[0]
        self.n_grains = int(n)
        # a small set still trains, it just needs more passes
        batch = int(np.clip(min(cfg.batch, max(n // 4, 4)), 2, max(n, 2)))
        start = time.time()
        self.history = []
        self.net.train()
        for ep in range(cfg.epochs):
            perm = torch.randperm(n)
            total = 0.0
            for i in range(0, n, batch):
                idx = perm[i:i + batch]
                if len(idx) < 2:
                    continue          # batch-norm needs more than one sample
                xb = X[idx].to(self.dev, non_blocking=True)
                recon, mu, lv = self.net(xb)
                loss, rec, kl = vae_loss(recon, xb, mu, lv, cfg.beta)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 5.0)
                opt.step()
                total += float(rec) * len(idx)
            sched.step()
            mean_rec = total / max(n, 1)
            if not np.isfinite(mean_rec):
                raise RuntimeError(
                    "Training became unstable (loss went to NaN). Try fewer "
                    "epochs or a different set of source files.")
            self.history.append(mean_rec)
            if progress is not None:
                frac = (ep + 1) / cfg.epochs
                msg = f"epoch {ep + 1}/{cfg.epochs}   reconstruction {self.history[-1]:.1f}"
                if progress(frac, msg) is False:
                    break
            if time.time() - start > cfg.max_seconds:
                if progress is not None:
                    progress(1.0, "time budget reached — stopping early")
                break
        self.net.eval()

    # -- latent space --------------------------------------------------------
    @torch.no_grad() if TORCH else (lambda f: f)
    def encode(self, patches: np.ndarray) -> np.ndarray:
        out = []
        X = torch.from_numpy(patches).unsqueeze(1)
        for i in range(0, X.shape[0], 64):
            mu, _ = self.net.encode(X[i:i + 64].to(self.dev))
            out.append(mu.cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.latent), np.float32)

    @torch.no_grad() if TORCH else (lambda f: f)
    def decode(self, z: np.ndarray) -> np.ndarray:
        z = np.atleast_2d(np.asarray(z, dtype=np.float32))
        out = []
        for i in range(0, len(z), 32):
            zb = torch.from_numpy(z[i:i + 32]).to(self.dev)
            out.append(self.net.decode(zb).squeeze(1).cpu().numpy())
        return np.concatenate(out)

    def calibrate(self, patches: np.ndarray, feats: np.ndarray) -> None:
        """Learn the latent statistics and the macro-control directions.

        The regression is done inside the *active* subspace only. A VAE
        typically leaves most latent dimensions unused, and an unconstrained
        least-squares fit will happily put the control direction in that dead
        space: it scores a near-perfect R-squared and changes nothing you can
        hear. Projecting onto the leading principal components first keeps each
        macro in the part of the space the decoder actually responds to.
        """
        Z = self.encode(patches)
        if not np.all(np.isfinite(Z)):
            raise RuntimeError("The trained model produced invalid latents.")
        self.train_latents = Z
        self.z_mean = Z.mean(0)
        self.z_std = Z.std(0) + 1e-6
        Zc = Z - self.z_mean

        U, S, Vt = np.linalg.svd(Zc, full_matrices=False)
        var = S ** 2
        keep = int(np.searchsorted(np.cumsum(var) / max(var.sum(), 1e-9), 0.98) + 1)
        keep = int(np.clip(keep, 2, min(16, Vt.shape[0])))
        V = Vt[:keep]                      # (keep, latent)
        T = Zc @ V.T                       # coordinates in the active subspace
        self.active_dims = keep

        dirs, scales = [], []
        ridge = float(np.mean(np.sum(T ** 2, axis=0))) * 1e-3 + 1e-9
        for j in range(feats.shape[1]):
            y = feats[:, j] - feats[:, j].mean()
            A = T.T @ T + ridge * np.eye(keep)
            c = np.linalg.solve(A, T.T @ y)
            w = c @ V
            n = np.linalg.norm(w)
            w = w / n if n > 1e-9 else np.zeros_like(w)
            dirs.append(w)
            scales.append(float(np.std(Zc @ w)) or 1.0)
        self.macro = np.stack(dirs).astype(np.float32)
        self.macro_scale = np.array(scales, dtype=np.float32)

    def sample(self, n: int, spread: float = 1.0,
               rng: np.random.Generator | None = None) -> np.ndarray:
        rng = rng or np.random.default_rng()
        if self.z_mean is None:
            return rng.standard_normal((n, self.latent)).astype(np.float32) * spread
        return (self.z_mean + rng.standard_normal((n, self.latent))
                * self.z_std * spread).astype(np.float32)

    def seed_from_training(self, n: int,
                           rng: np.random.Generator | None = None) -> np.ndarray:
        """Start from real grains rather than from noise — usually more musical."""
        rng = rng or np.random.default_rng()
        if self.train_latents is None or len(self.train_latents) == 0:
            return self.sample(n, 1.0, rng)
        idx = rng.choice(len(self.train_latents), n,
                         replace=len(self.train_latents) < n)
        return self.train_latents[idx].astype(np.float32)

    def render(self, z: np.ndarray, n_iter: int = 40, seed: int = 0) -> np.ndarray:
        patch = self.decode(np.atleast_2d(z))[0]
        return patch_to_audio(patch, n_iter=n_iter, seed=seed)

    # -- persistence ---------------------------------------------------------
    def save(self, path: str) -> None:
        torch.save({"latent": self.latent,
                    "state": self.net.state_dict(),
                    "macro": self.macro, "macro_scale": self.macro_scale,
                    "z_mean": self.z_mean, "z_std": self.z_std,
                    "train_latents": self.train_latents,
                    "sources": self.sources, "history": self.history,
                    "n_grains": self.n_grains,
                    "active_dims": self.active_dims}, path)

    @staticmethod
    def load(path: str) -> "GrainModel":
        d = torch.load(path, map_location="cpu", weights_only=False)
        m = GrainModel(int(d.get("latent", LATENT)))
        m.net = GrainVAE(m.latent)
        m.net.load_state_dict(d["state"])
        m.net.to(m.dev).eval()
        m.macro = d.get("macro")
        m.macro_scale = d.get("macro_scale")
        m.z_mean = d.get("z_mean")
        m.z_std = d.get("z_std")
        m.train_latents = d.get("train_latents")
        m.sources = list(d.get("sources", []))
        m.history = list(d.get("history", []))
        m.n_grains = int(d.get("n_grains", 0))
        m.active_dims = int(d.get("active_dims", 0))
        return m
