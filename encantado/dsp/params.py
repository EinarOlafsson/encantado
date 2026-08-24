"""Parameter descriptors — the UI builds its knobs straight from these."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    lo: float
    hi: float
    default: float
    unit: str = ""
    curve: str = "lin"           # 'lin' | 'log' | 'switch'
    group: str = "Main"
    choices: tuple[str, ...] = field(default_factory=tuple)

    # --- normalised <-> real ------------------------------------------------
    def to_norm(self, value: float) -> float:
        v = float(np.clip(value, self.lo, self.hi))
        if self.curve == "log":
            lo = max(self.lo, 1e-6)
            return float(np.log(max(v, lo) / lo) / np.log(self.hi / lo))
        return (v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def from_norm(self, norm: float) -> float:
        t = float(np.clip(norm, 0.0, 1.0))
        if self.curve == "log":
            lo = max(self.lo, 1e-6)
            return float(lo * (self.hi / lo) ** t)
        return self.lo + t * (self.hi - self.lo)

    def format(self, value: float) -> str:
        if self.curve == "switch":
            i = int(round(value))
            if self.choices and 0 <= i < len(self.choices):
                return self.choices[i]
            return str(i)
        if self.unit == "hz":
            return f"{value:.0f} Hz" if value >= 1000 else f"{value:.1f} Hz"
        if self.unit == "ms":
            return f"{value * 1000:.0f} ms" if value < 1 else f"{value:.2f} s"
        if self.unit == "%":
            return f"{value * 100:.0f}%"
        if self.unit == "db":
            return f"{value:+.1f} dB"
        if self.unit == "st":
            return f"{value:+.0f} st"
        return f"{value:.2f}"


def defaults_for(specs: tuple[Param, ...]) -> dict[str, float]:
    return {p.key: p.default for p in specs}
