"""A small convolutional VAE over spectrogram grains.

Deliberately modest. Trained on a handful of files it learns the *timbre* of
that material — drum hits, stabs, textures — well enough to generate new grains
in the same character. It is not a music model and will not write you a track;
the musical structure comes from the analysis engine and the sequencer.
"""
from __future__ import annotations

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH = True
except Exception:                                      # pragma: no cover
    TORCH = False
    torch = None
    nn = object

from .spectral import BINS, FRAMES

LATENT = 96


def device() -> "torch.device":
    if TORCH and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu") if TORCH else None


if TORCH:
    class GrainVAE(nn.Module):
        def __init__(self, latent: int = LATENT):
            super().__init__()
            ch = (1, 32, 64, 96, 128, 160)
            enc = []
            for i in range(len(ch) - 1):
                enc += [nn.Conv2d(ch[i], ch[i + 1], 4, 2, 1),
                        nn.BatchNorm2d(ch[i + 1]),
                        nn.SiLU()]
            self.enc = nn.Sequential(*enc)
            self.fh, self.fw = BINS // 32, FRAMES // 32       # 8 x 4
            flat = ch[-1] * self.fh * self.fw
            self.to_mu = nn.Linear(flat, latent)
            self.to_lv = nn.Linear(flat, latent)
            self.from_z = nn.Linear(latent, flat)
            dec = []
            rch = list(reversed(ch))
            for i in range(len(rch) - 1):
                last = i == len(rch) - 2
                dec += [nn.ConvTranspose2d(rch[i], rch[i + 1], 4, 2, 1)]
                if not last:
                    dec += [nn.BatchNorm2d(rch[i + 1]), nn.SiLU()]
            self.dec = nn.Sequential(*dec)
            self.latent = latent
            self._ch = ch

        def encode(self, x):
            h = self.enc(x).flatten(1)
            # clamp here, not just where std is taken: an unclamped log-variance
            # makes exp(lv) overflow inside the KL term and the loss goes NaN
            return self.to_mu(h), self.to_lv(h).clamp(-8.0, 8.0)

        def decode(self, z):
            h = self.from_z(z).view(-1, self._ch[-1], self.fh, self.fw)
            return torch.sigmoid(self.dec(h))

        def forward(self, x):
            mu, lv = self.encode(x)
            std = torch.exp(0.5 * lv)
            z = mu + std * torch.randn_like(std)
            return self.decode(z), mu, lv

    def vae_loss(recon, x, mu, lv, beta: float = 2e-4):
        rec = F.mse_loss(recon, x, reduction="none").flatten(1).sum(1).mean()
        kl = (-0.5 * (1 + lv - mu.pow(2) - lv.exp())).flatten(1).sum(1).mean()
        return rec + beta * kl, rec.detach(), kl.detach()
else:                                                   # pragma: no cover
    GrainVAE = None

    def vae_loss(*_a, **_k):
        raise RuntimeError("PyTorch is not installed")
