# Neon Rack

A pattern-based music production studio for melodic house, progressive and
electronica — built with PyQt6, numpy and scipy. Step sequencer, piano roll,
arrangement playlist, mixer, and a full synthesis + effects engine.

Everything you hear is synthesised from scratch: there are no bundled samples,
so the project ships free of any third-party audio licensing. A Sampler
instrument is included for loading your own WAV files.

## Requirements

Python 3.10+, with `PyQt6`, `numpy` and `scipy`. Realtime audio uses Qt's own
`QAudioSink`, so no extra audio library is needed.

## Running

```bash
python -m neonrack
```

## Licence

MIT — see `LICENSE`.
