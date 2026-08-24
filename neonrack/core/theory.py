"""Music theory helpers: notes, scales, chords, progressions.

Everything here is pure data + pure functions so the UI and the sequencer can
share one notion of "what is in key".
"""
from __future__ import annotations

from dataclasses import dataclass

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

A4_MIDI = 69
A4_HZ = 440.0


def midi_to_hz(midi: float) -> float:
    return A4_HZ * (2.0 ** ((midi - A4_MIDI) / 12.0))


def note_name(midi: int, flats: bool = False) -> str:
    names = FLAT_NAMES if flats else NOTE_NAMES
    return f"{names[midi % 12]}{midi // 12 - 1}"


def is_black_key(midi: int) -> bool:
    return (midi % 12) in (1, 3, 6, 8, 10)


# --------------------------------------------------------------------------
# Scales
# --------------------------------------------------------------------------
SCALES: dict[str, tuple[int, ...]] = {
    "Minor (Aeolian)": (0, 2, 3, 5, 7, 8, 10),
    "Major (Ionian)": (0, 2, 4, 5, 7, 9, 11),
    "Harmonic Minor": (0, 2, 3, 5, 7, 8, 11),
    "Melodic Minor": (0, 2, 3, 5, 7, 9, 11),
    "Dorian": (0, 2, 3, 5, 7, 9, 10),
    "Phrygian": (0, 1, 3, 5, 7, 8, 10),
    "Lydian": (0, 2, 4, 6, 7, 9, 11),
    "Mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "Minor Pentatonic": (0, 3, 5, 7, 10),
    "Major Pentatonic": (0, 2, 4, 7, 9),
    "Chromatic": tuple(range(12)),
}

DEFAULT_SCALE = "Minor (Aeolian)"


def scale_pitches(root: int, scale: str) -> set[int]:
    """Pitch classes (0-11) belonging to the scale."""
    steps = SCALES.get(scale, SCALES[DEFAULT_SCALE])
    return {(root + s) % 12 for s in steps}


def in_scale(midi: int, root: int, scale: str) -> bool:
    return (midi % 12) in scale_pitches(root, scale)


def snap_to_scale(midi: int, root: int, scale: str) -> int:
    """Move a note to the nearest scale tone (ties go up)."""
    allowed = scale_pitches(root, scale)
    if midi % 12 in allowed:
        return midi
    for delta in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6):
        if (midi + delta) % 12 in allowed:
            return midi + delta
    return midi


def scale_degree_to_midi(root: int, scale: str, degree: int, octave: int = 4) -> int:
    """Degree 0 = tonic. Degrees beyond the scale wrap into higher octaves."""
    steps = SCALES.get(scale, SCALES[DEFAULT_SCALE])
    n = len(steps)
    octave_shift, idx = divmod(degree, n)
    return root + 12 * (octave + 1 + octave_shift) + steps[idx]


# --------------------------------------------------------------------------
# Chords
# --------------------------------------------------------------------------
CHORD_SHAPES: dict[str, tuple[int, ...]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "min9": (0, 3, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "add9": (0, 4, 7, 14),
    "minadd9": (0, 3, 7, 14),
    "sus2add9": (0, 2, 7, 14),
    "min11": (0, 3, 7, 10, 14, 17),
    "6": (0, 4, 7, 9),
    "min6": (0, 3, 7, 9),
}

# Diatonic triad quality for each degree of the major and natural-minor scales.
MAJOR_QUALITIES = ("maj", "min", "min", "maj", "maj", "min", "dim")
MINOR_QUALITIES = ("min", "dim", "maj", "min", "min", "maj", "maj")


def diatonic_chord(root: int, scale: str, degree: int, octave: int = 3,
                   seventh: bool = False, extended: bool = False) -> list[int]:
    """Build the diatonic chord on `degree` (0-indexed) of the given key."""
    steps = SCALES.get(scale, SCALES[DEFAULT_SCALE])
    if len(steps) != 7:
        steps = SCALES[DEFAULT_SCALE]
    base = scale_degree_to_midi(root, scale, degree, octave)
    third = scale_degree_to_midi(root, scale, degree + 2, octave)
    fifth = scale_degree_to_midi(root, scale, degree + 4, octave)
    notes = [base, third, fifth]
    if seventh or extended:
        notes.append(scale_degree_to_midi(root, scale, degree + 6, octave))
    if extended:
        notes.append(scale_degree_to_midi(root, scale, degree + 8, octave))
    return notes


def chord_notes(root_midi: int, shape: str) -> list[int]:
    return [root_midi + i for i in CHORD_SHAPES.get(shape, CHORD_SHAPES["min"])]


def voice_lead(chord: list[int], low: int = 48, high: int = 72) -> list[int]:
    """Fold a chord into a comfortable register without changing its identity."""
    out = []
    for n in chord:
        while n < low:
            n += 12
        while n > high:
            n -= 12
        out.append(n)
    return sorted(set(out))


def spread_voicing(chord: list[int], octaves: int = 2) -> list[int]:
    """Big open voicing: root in the bass, the rest stacked upward."""
    if not chord:
        return []
    base = sorted(chord)
    out = list(base)
    for o in range(1, octaves):
        out.extend(n + 12 * o for n in base[1:])
    return sorted(set(out))


# --------------------------------------------------------------------------
# Progressions — the harmonic backbone of the genre
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Progression:
    name: str
    degrees: tuple[int, ...]          # 0-indexed scale degrees
    scale: str                        # scale it is designed for
    note: str = ""                    # what it evokes

    def chords(self, root: int, octave: int = 3, seventh: bool = False,
               extended: bool = False) -> list[list[int]]:
        return [diatonic_chord(root, self.scale, d, octave, seventh, extended)
                for d in self.degrees]


PROGRESSIONS: tuple[Progression, ...] = (
    Progression("i - VI - III - VII", (0, 5, 2, 6), "Minor (Aeolian)",
                "The melodic-house workhorse. Warakls, Joachim Pastor."),
    Progression("i - VII - VI - VII", (0, 6, 5, 6), "Minor (Aeolian)",
                "Driving and circular. Great under an arp."),
    Progression("VI - VII - i - i", (5, 6, 0, 0), "Minor (Aeolian)",
                "Lifts into the tonic. Classic big-room drop."),
    Progression("i - III - VII - VI", (0, 2, 6, 5), "Minor (Aeolian)",
                "Anthemic. Swedish House Mafia territory."),
    Progression("VI - III - VII - i", (5, 2, 6, 0), "Minor (Aeolian)",
                "Suspended, cinematic. NTO / deep organic."),
    Progression("i - iv - VI - V", (0, 3, 5, 4), "Harmonic Minor",
                "Darker pull, strong resolution."),
    Progression("I - V - vi - IV", (0, 4, 5, 3), "Major (Ionian)",
                "The pop axis. Avicii piano house."),
    Progression("vi - IV - I - V", (5, 3, 0, 4), "Major (Ionian)",
                "Same axis, wistful start. Robin Schulz / MEDUZA."),
    Progression("I - vi - IV - V", (0, 5, 3, 4), "Major (Ionian)",
                "Warm and classic, 50s changes."),
    Progression("i - VI - VII - v", (0, 5, 6, 4), "Dorian",
                "Floating, modal. French 79."),
)


def progression_by_name(name: str) -> Progression | None:
    for p in PROGRESSIONS:
        if p.name == name:
            return p
    return None
