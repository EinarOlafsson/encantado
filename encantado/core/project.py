"""Project data model: channels, patterns, notes, arrangement.

A pattern holds notes per channel on a 16th-note grid. Drum channels simply use
notes at a fixed pitch, so the step sequencer and the piano roll are two views of
exactly the same data.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

from ..dsp.drums import DRUMS
from ..dsp.instruments import INSTRUMENTS
from ..dsp.params import defaults_for

STEPS_PER_BEAT = 4
STEPS_PER_BAR = 16

CHANNEL_COLORS = [
    "#ff5c7a", "#ff9f45", "#ffd93d", "#7ee787", "#4dd4c1",
    "#4db8ff", "#8b7cff", "#d47cff", "#ff7cc4", "#a0a8b8",
]


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def instrument_spec(key: str) -> dict | None:
    return INSTRUMENTS.get(key) or DRUMS.get(key)


def is_drum(key: str) -> bool:
    return key in DRUMS


# --------------------------------------------------------------------------
@dataclass
class Note:
    step: int
    pitch: int = 48
    length: int = 1
    velocity: float = 0.9

    def to_dict(self) -> dict:
        return {"s": self.step, "p": self.pitch, "l": self.length,
                "v": round(self.velocity, 4)}

    @staticmethod
    def from_dict(d: dict) -> "Note":
        return Note(int(d["s"]), int(d.get("p", 48)), int(d.get("l", 1)),
                    float(d.get("v", 0.9)))


@dataclass
class Send:
    reverb: float = 0.0
    delay: float = 0.0


@dataclass
class Channel:
    id: str = field(default_factory=new_id)
    name: str = "Channel"
    instrument: str = "pluck"
    params: dict[str, float] = field(default_factory=dict)
    volume: float = 0.8
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    color: str = "#4db8ff"
    sends: Send = field(default_factory=Send)
    sc_amount: float = 0.0
    sc_release: float = 0.28
    sc_shape: float = 1.8
    is_kick_source: bool = False      # this channel fires the sidechain
    fx: list[dict] = field(default_factory=list)
    sample_path: str = ""

    def __post_init__(self) -> None:
        spec = instrument_spec(self.instrument)
        if spec:
            base = defaults_for(spec["params"])
            base.update(self.params)
            self.params = base

    @property
    def drum(self) -> bool:
        return is_drum(self.instrument)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sends"] = asdict(self.sends)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Channel":
        d = dict(d)
        sends = d.pop("sends", {}) or {}
        ch = Channel(**{k: v for k, v in d.items()
                        if k in Channel.__dataclass_fields__ and k != "sends"})
        ch.sends = Send(float(sends.get("reverb", 0.0)),
                        float(sends.get("delay", 0.0)))
        return ch


@dataclass
class Pattern:
    id: str = field(default_factory=new_id)
    name: str = "Pattern"
    length: int = 16                                   # in steps
    notes: dict[str, list[Note]] = field(default_factory=dict)

    def channel_notes(self, cid: str) -> list[Note]:
        return self.notes.setdefault(cid, [])

    def note_at(self, cid: str, step: int) -> Note | None:
        for nt in self.notes.get(cid, ()):
            if nt.step == step:
                return nt
        return None

    def toggle_step(self, cid: str, step: int, pitch: int = 48,
                    velocity: float = 0.9) -> bool:
        """Returns True if a note was added, False if one was removed."""
        lst = self.channel_notes(cid)
        for i, nt in enumerate(lst):
            if nt.step == step:
                lst.pop(i)
                return False
        lst.append(Note(step, pitch, 1, velocity))
        lst.sort(key=lambda n: (n.step, n.pitch))
        return True

    def add_note(self, cid: str, note: Note) -> None:
        lst = self.channel_notes(cid)
        lst.append(note)
        lst.sort(key=lambda n: (n.step, n.pitch))

    def remove_note(self, cid: str, note: Note) -> None:
        lst = self.channel_notes(cid)
        if note in lst:
            lst.remove(note)

    def clear_channel(self, cid: str) -> None:
        self.notes[cid] = []

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "length": self.length,
                "notes": {k: [n.to_dict() for n in v]
                          for k, v in self.notes.items() if v}}

    @staticmethod
    def from_dict(d: dict) -> "Pattern":
        p = Pattern(d.get("id", new_id()), d.get("name", "Pattern"),
                    int(d.get("length", 16)))
        p.notes = {k: [Note.from_dict(x) for x in v]
                   for k, v in d.get("notes", {}).items()}
        return p


@dataclass
class Clip:
    """A pattern placed on the arrangement timeline."""
    pattern_id: str
    start: int                    # in steps
    length: int                   # in steps
    lane: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Clip":
        return Clip(d["pattern_id"], int(d["start"]), int(d["length"]),
                    int(d.get("lane", 0)))

    @property
    def end(self) -> int:
        return self.start + self.length


# --------------------------------------------------------------------------
@dataclass
class Project:
    name: str = "Untitled"
    bpm: float = 124.0
    root: int = 9                   # pitch class; 9 = A
    scale: str = "Minor (Aeolian)"
    swing: float = 0.0
    channels: list[Channel] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    arrangement: list[Clip] = field(default_factory=list)
    master: dict[str, Any] = field(default_factory=lambda: {
        "volume": 0.85,
        "limiter": {"ceiling": -0.8, "drive": 1.0, "release": 0.09},
        "eq": {"low": 0.0, "mid": 0.0, "high": 0.0},
        "reverb": {"mix": 1.0, "size": 0.76, "damp": 0.42, "hp": 300.0,
                   "width": 1.0, "predelay": 0.018},
        "delay": {"mix": 1.0, "division": 3, "feedback": 0.4,
                  "pingpong": 1.0, "lp": 5200.0, "hp": 320.0},
        "djfilter": {"cut": 0.0, "reso": 1.2},
        "comp": {"threshold": -14.0, "ratio": 2.4, "attack": 0.012,
                 "release": 0.16, "makeup": 1.15, "mix": 1.0},
    })
    n_lanes: int = 8

    # -- lookup --------------------------------------------------------------
    def channel(self, cid: str) -> Channel | None:
        for c in self.channels:
            if c.id == cid:
                return c
        return None

    def pattern(self, pid: str) -> Pattern | None:
        for p in self.patterns:
            if p.id == pid:
                return p
        return None

    def channel_index(self, cid: str) -> int:
        for i, c in enumerate(self.channels):
            if c.id == cid:
                return i
        return -1

    @property
    def any_solo(self) -> bool:
        return any(c.solo for c in self.channels)

    def audible(self, ch: Channel) -> bool:
        if self.any_solo:
            return ch.solo
        return not ch.mute

    def kick_channels(self) -> list[Channel]:
        return [c for c in self.channels if c.is_kick_source]

    # -- editing -------------------------------------------------------------
    def add_channel(self, instrument: str, name: str | None = None,
                    params: dict | None = None) -> Channel:
        spec = instrument_spec(instrument)
        if spec is None:
            raise KeyError(instrument)
        ch = Channel(
            name=name or spec["name"],
            instrument=instrument,
            params=dict(params or {}),
            color=CHANNEL_COLORS[len(self.channels) % len(CHANNEL_COLORS)],
        )
        if instrument == "kick" and not self.kick_channels():
            ch.is_kick_source = True
        self.channels.append(ch)
        return ch

    def remove_channel(self, cid: str) -> None:
        self.channels = [c for c in self.channels if c.id != cid]
        for p in self.patterns:
            p.notes.pop(cid, None)

    def move_channel(self, cid: str, delta: int) -> None:
        i = self.channel_index(cid)
        j = i + delta
        if i < 0 or not (0 <= j < len(self.channels)):
            return
        self.channels[i], self.channels[j] = self.channels[j], self.channels[i]

    def add_pattern(self, name: str | None = None, length: int = 16) -> Pattern:
        p = Pattern(name=name or f"Pattern {len(self.patterns) + 1}", length=length)
        self.patterns.append(p)
        return p

    def duplicate_pattern(self, pid: str) -> Pattern | None:
        src = self.pattern(pid)
        if src is None:
            return None
        p = Pattern.from_dict(src.to_dict())
        p.id = new_id()
        p.name = f"{src.name} copy"
        self.patterns.append(p)
        return p

    def remove_pattern(self, pid: str) -> None:
        if len(self.patterns) <= 1:
            return
        self.patterns = [p for p in self.patterns if p.id != pid]
        self.arrangement = [c for c in self.arrangement if c.pattern_id != pid]

    @property
    def arrangement_length(self) -> int:
        return max((c.end for c in self.arrangement), default=0)

    # -- persistence ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": "encantado-project",
            "version": 1,
            "name": self.name,
            "bpm": self.bpm,
            "root": self.root,
            "scale": self.scale,
            "swing": self.swing,
            "n_lanes": self.n_lanes,
            "channels": [c.to_dict() for c in self.channels],
            "patterns": [p.to_dict() for p in self.patterns],
            "arrangement": [c.to_dict() for c in self.arrangement],
            "master": self.master,
        }

    @staticmethod
    def from_dict(d: dict) -> "Project":
        pr = Project(
            name=d.get("name", "Untitled"),
            bpm=float(d.get("bpm", 124.0)),
            root=int(d.get("root", 9)),
            scale=d.get("scale", "Minor (Aeolian)"),
            swing=float(d.get("swing", 0.0)),
            n_lanes=int(d.get("n_lanes", 8)),
        )
        pr.channels = [Channel.from_dict(c) for c in d.get("channels", [])]
        pr.patterns = [Pattern.from_dict(p) for p in d.get("patterns", [])]
        pr.arrangement = [Clip.from_dict(c) for c in d.get("arrangement", [])]
        master = Project().master
        for k, v in (d.get("master") or {}).items():
            if isinstance(v, dict) and isinstance(master.get(k), dict):
                master[k].update(v)
            else:
                master[k] = v
        pr.master = master
        if not pr.patterns:
            pr.add_pattern()
        return pr

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1)

    @staticmethod
    def load(path: str) -> "Project":
        with open(path, encoding="utf-8") as fh:
            return Project.from_dict(json.load(fh))

    def clone(self) -> "Project":
        return Project.from_dict(self.to_dict())
