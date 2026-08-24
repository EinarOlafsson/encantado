# Encantado

A pattern-based music studio for melodic house, progressive and electronica —
built with PyQt6, numpy and scipy. Step sequencer, piano roll, arrangement
playlist, mixer, and a complete synthesis and effects engine.

Named for the shapeshifter of Amazonian folklore who turns up at the party and
enchants everyone with music.

Everything you hear is synthesised from scratch — there are no bundled samples,
so the project carries no third-party audio licensing. A Sampler instrument is
included for loading your own WAV files.

## Requirements

Python 3.10+ with `PyQt6`, `numpy` and `scipy`. Realtime audio goes through Qt's
own `QAudioSink`, so no extra audio library is needed.

## Running

```bash
python -m encantado
```

## Project files

Projects are saved as `.ecp` (JSON). Renders export to 16- or 24-bit WAV.

## Licence

MIT — see `LICENSE`.
