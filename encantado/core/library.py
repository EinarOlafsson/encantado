"""Sample library: scan folders you own, classify what is in them, remember it.

Encantado never copies or redistributes your samples — the index stores paths.
Point it at wherever your packs already live.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from ..audio.wavio import AUDIO_EXTS, probe_duration

AUDIO_EXTS_HINT = AUDIO_EXTS

CATEGORIES = ("Kick", "Snare", "Clap", "Hat", "Cymbal", "Tom", "Perc",
              "Bass", "Lead", "Chord", "Pad", "Vocal", "FX", "Loop", "Other")

# Ordered: the first match wins, so put the specific words before the vague ones.
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Kick", ("kick", "bassdrum", "bass drum", "bd_", "_bd", "kck")),
    ("Snare", ("snare", "snr", "rimshot", "_sd", "sd_")),
    ("Clap", ("clap", "clp", "handclap")),
    ("Hat", ("hihat", "hi-hat", "hi hat", "hat", "_hh", "hh_", "openhat",
             "closedhat")),
    ("Cymbal", ("crash", "ride", "cymbal", "splash", "china")),
    ("Tom", ("tom", "floortom")),
    ("Perc", ("perc", "toploop", "top loop", "conga", "bongo", "shaker", "tamb", "rim", "wood",
              "clave", "cabasa", "triangle", "block", "cowbell", "click",
              "snap", "tick")),
    ("Bass", ("bass", "sub", "808", "reese")),
    ("Vocal", ("vocal", "vox", "acapella", "acappella", "chant", "phrase",
               "adlib", "hook")),
    ("FX", ("riser", "uplifter", "downlifter", "sweep", "impact", "whoosh",
            "transition", "reverse", "noise", "_fx", "fx_", "atmos", "foley",
            "drone", "boom")),
    ("Pad", ("pad", "string", "texture", "ambient", "swell")),
    ("Chord", ("chord", "stab", "piano", "keys", "rhodes", "organ", "harmony")),
    ("Lead", ("lead", "arp", "pluck", "melody", "synth")),
)

_LOOP_WORDS = ("loop", "groove", "beat", "riff", "seq")
_BPM_RE = re.compile(r"(?:^|[_\-. ])(\d{2,3})\s*(?:bpm)?(?:[_\-. ]|$)", re.I)
_BPM_TAGGED_RE = re.compile(r"(\d{2,3})\s*bpm", re.I)
_KEY_RE = re.compile(
    r"(?:^|[_\-. ])([A-G])(#|b|s(?:harp)?)?[ _\-]?(min(?:or)?|maj(?:or)?|m)?"
    r"(?:[_\-. ]|$)")
_NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass
class Sample:
    path: str
    name: str = ""
    category: str = "Other"
    duration: float = 0.0
    loop: bool = False
    bpm: float = 0.0
    root: int = -1                 # MIDI pitch class + 60, or -1 if unknown
    pack: str = ""                 # the folder it came from

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Sample":
        return Sample(**{k: v for k, v in d.items()
                         if k in Sample.__dataclass_fields__})


# --------------------------------------------------------------------------
def classify(path: str, duration: float = 0.0) -> tuple[str, bool]:
    """Guess (category, is_loop) from the filename, then the duration."""
    hay = (os.path.basename(path) + " " + os.path.basename(os.path.dirname(path))
           ).lower().replace("-", " ").replace("_", " ")
    padded = f" {hay} "
    is_loop = any(w in hay for w in _LOOP_WORDS) or duration >= 2.5

    for cat, words in _KEYWORDS:
        for w in words:
            probe = w.replace("_", " ").strip()
            if probe and (f" {probe}" in padded or f"{probe} " in padded
                          or probe in hay):
                return cat, is_loop

    # nothing recognisable in the name: fall back to what we can measure
    if is_loop:
        return "Loop", True
    if duration and duration < 0.25:
        return "Perc", False
    return "Other", False


def detect_bpm(name: str) -> float:
    m = _BPM_TAGGED_RE.search(name)
    if m:
        v = float(m.group(1))
        if 60 <= v <= 200:
            return v
    for m in _BPM_RE.finditer(name):
        v = float(m.group(1))
        if 70 <= v <= 190:
            return v
    return 0.0


def detect_root(name: str) -> int:
    """Return a MIDI note in octave 4 for a key found in the filename, else -1."""
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _KEY_RE.search(f" {stem} ")
    if not m:
        return -1
    letter, accidental, _quality = m.groups()
    pc = _NOTE_PC[letter.upper()]
    if accidental:
        pc += 1 if accidental.lower().startswith(("#", "s")) else -1
    return 60 + (pc % 12)


def describe(path: str, duration: float | None = None) -> Sample:
    name = os.path.basename(path)
    dur = probe_duration(path) if duration is None else duration
    cat, loop = classify(path, dur)
    return Sample(path=path, name=os.path.splitext(name)[0], category=cat,
                  duration=round(dur, 3), loop=loop, bpm=detect_bpm(name),
                  root=detect_root(name),
                  pack=os.path.basename(os.path.dirname(path)))


# --------------------------------------------------------------------------
def index_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "encantado")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "library.json")


class SampleLibrary:
    MAX_FILES = 60000

    def __init__(self) -> None:
        self.roots: list[str] = []
        self.samples: list[Sample] = []
        self.owned_packs: dict[str, str] = {}     # pack guide key -> folder

    # -- scanning ------------------------------------------------------------
    def add_root(self, path: str) -> None:
        path = os.path.abspath(path)
        if path not in self.roots:
            self.roots.append(path)

    def remove_root(self, path: str) -> None:
        self.roots = [r for r in self.roots if r != path]
        self.samples = [s for s in self.samples
                        if not s.path.startswith(path + os.sep)]

    def scan(self, root: str, progress=None) -> int:
        """Index every audio file under `root`. Returns how many were added."""
        root = os.path.abspath(root)
        known = {s.path for s in self.samples}
        found = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.lower().endswith(AUDIO_EXTS) or fn.startswith("."):
                    continue
                full = os.path.join(dirpath, fn)
                if full in known:
                    continue
                try:
                    if os.path.getsize(full) > 200 * 1024 * 1024:
                        continue
                except OSError:
                    continue
                # duration is only cheap for WAV; others resolve on first use
                dur = probe_duration(full) if fn.lower().endswith(
                    (".wav", ".wave")) else 0.0
                self.samples.append(describe(full, dur))
                known.add(full)
                found += 1
                if progress is not None and found % 40 == 0:
                    if not progress(found, full):
                        return found
                if len(self.samples) >= self.MAX_FILES:
                    return found
        self.add_root(root)
        return found

    def rescan(self, progress=None) -> int:
        self.samples = [s for s in self.samples if os.path.exists(s.path)]
        total = 0
        for r in list(self.roots):
            total += self.scan(r, progress)
        return total

    def forget_missing(self) -> int:
        n = len(self.samples)
        self.samples = [s for s in self.samples if os.path.exists(s.path)]
        return n - len(self.samples)

    # -- queries -------------------------------------------------------------
    def search(self, query: str = "", category: str = "",
               limit: int = 500) -> list[Sample]:
        q = query.strip().lower()
        terms = [t for t in q.split() if t]
        out = []
        for s in self.samples:
            if category and s.category != category:
                continue
            if terms:
                hay = f"{s.name} {s.pack} {s.category}".lower()
                if not all(t in hay for t in terms):
                    continue
            out.append(s)
            if len(out) >= limit:
                break
        return out

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.samples:
            out[s.category] = out.get(s.category, 0) + 1
        return out

    # -- persistence ---------------------------------------------------------
    def save(self, path: str | None = None) -> None:
        path = path or index_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "roots": self.roots,
                       "owned_packs": self.owned_packs,
                       "samples": [s.to_dict() for s in self.samples]}, fh)
        os.replace(tmp, path)

    @staticmethod
    def load(path: str | None = None) -> "SampleLibrary":
        lib = SampleLibrary()
        path = path or index_path()
        if not os.path.exists(path):
            return lib
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            return lib
        lib.roots = list(d.get("roots", []))
        lib.owned_packs = dict(d.get("owned_packs", {}))
        lib.samples = [Sample.from_dict(x) for x in d.get("samples", [])]
        return lib
