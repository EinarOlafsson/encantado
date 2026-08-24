"""The audio engine: transport, step scheduler, voices, buses, master chain.

`render(n)` is the only entry point. The realtime backend and the offline WAV
exporter both drive it the same way, so what you export is exactly what you
heard.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from ..core.project import Channel, Project, instrument_spec
from .base import SR, equal_power_pan
from .effects import (EFFECTS, Compressor, Delay, DJFilter, EQ3, Limiter,
                      Reverb, Sidechain)

MAX_VOICES_TOTAL = 96
PREVIEW_CID = "__preview__"


class _LiveVoice:
    """A sounding voice plus the bookkeeping the scheduler needs."""

    __slots__ = ("voice", "cid", "offset", "off_at", "pitch", "released", "preview")

    def __init__(self, voice, cid, offset=0, off_at=None, pitch=48, preview=False):
        self.voice = voice
        self.cid = cid
        self.offset = offset          # samples to wait inside the first block
        self.off_at = off_at          # absolute sample at which to release
        self.pitch = pitch
        self.released = False
        self.preview = preview


class Engine:
    def __init__(self, project: Project, sr: int = SR, block: int = 1024):
        self.sr = sr
        self.block = block
        self.project = project
        self.lock = threading.RLock()

        self.playing = False
        self.mode = "pattern"                # 'pattern' | 'song'
        self.pos = 0                         # samples since transport start
        self.current_pattern: str = (project.patterns[0].id
                                     if project.patterns else "")
        self.loop = True
        self.metronome = False

        self._voices: list[_LiveVoice] = []
        self._sidechains: dict[str, Sidechain] = {}
        self._chan_fx: dict[str, list] = {}
        self._fx_sig: dict[str, tuple] = {}

        self.reverb_bus = Reverb(project.master.get("reverb"), sr)
        self.reverb_bus.wet_only = True
        self.delay_bus = Delay(project.master.get("delay"), sr)
        self.delay_bus.wet_only = True
        self.dj = DJFilter(project.master.get("djfilter"), sr)
        self.eq = EQ3(project.master.get("eq"), sr)
        self.comp = Compressor(project.master.get("comp"), sr)
        self.limiter = Limiter(project.master.get("limiter"), sr)
        self.delay_bus.set_tempo(project.bpm)

        self.meters: dict[str, float] = {}
        self.master_peak = np.zeros(2, dtype=np.float32)
        self.cpu = 0.0
        self._step_cache: int = -1
        self._metro_ph = 0.0

    # -- transport -----------------------------------------------------------
    @property
    def samples_per_step(self) -> float:
        return self.sr * 60.0 / max(self.project.bpm, 20.0) / 4.0

    @property
    def current_step(self) -> int:
        return int(self.pos // self.samples_per_step)

    def loop_length_steps(self) -> int:
        if self.mode == "song":
            return max(self.project.arrangement_length, 16)
        pat = self.project.pattern(self.current_pattern)
        return pat.length if pat else 16

    def play(self) -> None:
        with self.lock:
            self.playing = True

    def stop(self) -> None:
        with self.lock:
            self.playing = False
            self.pos = 0
            self._all_notes_off(kill=True)
            self._step_cache = -1

    def pause(self) -> None:
        with self.lock:
            self.playing = False
            self._all_notes_off()

    def seek_step(self, step: int) -> None:
        with self.lock:
            self.pos = int(max(step, 0) * self.samples_per_step)
            self._step_cache = self.current_step - 1
            self._all_notes_off()

    def set_mode(self, mode: str) -> None:
        with self.lock:
            if mode != self.mode:
                self.mode = mode
                self.pos = 0
                self._all_notes_off(kill=True)
                self._step_cache = -1

    def _all_notes_off(self, kill: bool = False) -> None:
        if kill:
            self._voices.clear()
        else:
            for lv in self._voices:
                if not lv.released:
                    lv.voice.note_off()
                    lv.released = True

    # -- live preview from the UI -------------------------------------------
    def preview_note(self, cid: str, pitch: int, velocity: float = 0.9) -> None:
        with self.lock:
            ch = self.project.channel(cid)
            if ch is None:
                return
            self._spawn(ch, pitch, velocity, offset=0, off_at=None, preview=True)

    def preview_buffer(self, buf, level: float = 0.9) -> None:
        """Audition a decoded sample without giving it a channel."""
        from .instruments import SAMPLER_PARAMS, SamplerVoice
        from .params import defaults_for
        if buf is None or len(buf) == 0:
            return
        params = defaults_for(SAMPLER_PARAMS)
        params.update({"_buffer": buf, "level": level, "root_note": 60.0})
        with self.lock:
            self._voices = [lv for lv in self._voices if lv.cid != PREVIEW_CID]
            self._voices.append(_LiveVoice(
                SamplerVoice(params, 60, 1.0, self.sr), PREVIEW_CID, 0, None,
                60, True))

    def stop_preview(self) -> None:
        with self.lock:
            self._voices = [lv for lv in self._voices if lv.cid != PREVIEW_CID]

    def preview_off(self, cid: str, pitch: int) -> None:
        with self.lock:
            for lv in self._voices:
                if lv.preview and lv.cid == cid and lv.pitch == pitch and not lv.released:
                    lv.voice.note_off()
                    lv.released = True

    # -- scheduling ----------------------------------------------------------
    def _notes_at(self, gstep: int) -> list[tuple[Channel, object]]:
        pr = self.project
        out = []
        if self.mode == "song":
            for clip in pr.arrangement:
                if not (clip.start <= gstep < clip.end):
                    continue
                pat = pr.pattern(clip.pattern_id)
                if pat is None or pat.length <= 0:
                    continue
                local = (gstep - clip.start) % pat.length
                for cid, notes in pat.notes.items():
                    ch = pr.channel(cid)
                    if ch is None or not pr.audible(ch):
                        continue
                    for nt in notes:
                        if nt.step == local:
                            out.append((ch, nt))
        else:
            pat = pr.pattern(self.current_pattern)
            if pat is None or pat.length <= 0:
                return out
            local = gstep % pat.length
            for cid, notes in pat.notes.items():
                ch = pr.channel(cid)
                if ch is None or not pr.audible(ch):
                    continue
                for nt in notes:
                    if nt.step == local:
                        out.append((ch, nt))
        return out

    def _step_onset(self, k: int) -> float:
        sps = self.samples_per_step
        base = k * sps
        sw = self.project.swing
        if sw > 1e-3 and k % 2 == 1:
            base += sw * sps * 0.66
        return base

    def _spawn(self, ch: Channel, pitch: int, velocity: float, offset: int,
               off_at: int | None, preview: bool = False) -> None:
        spec = instrument_spec(ch.instrument)
        if spec is None:
            return
        # the live dict, not a copy: turning a knob then changes the sound of
        # notes that are already ringing, the way a hardware synth would
        params = ch.params
        same = [lv for lv in self._voices if lv.cid == ch.id]
        poly = int(spec.get("poly", 8))
        if len(same) >= poly:
            oldest = same[0]
            self._voices.remove(oldest)
        if len(self._voices) >= MAX_VOICES_TOTAL:
            self._voices.pop(0)
        try:
            v = spec["cls"](params, pitch, velocity, self.sr)
        except Exception:
            return
        self._voices.append(_LiveVoice(v, ch.id, offset, off_at, pitch, preview))

    def _fire_step(self, k: int, offset: int) -> None:
        sps = self.samples_per_step
        for ch, nt in self._notes_at(k):
            off_at = None
            if not ch.drum:
                off_at = int(self.pos + offset + max(nt.length, 1) * sps)
            self._spawn(ch, nt.pitch, nt.velocity, offset, off_at)
            if ch.is_kick_source:
                for sc in self._sidechains.values():
                    sc.trigger(offset)

    # -- per-channel effect chain -------------------------------------------
    def _chain_for(self, ch: Channel) -> list:
        sig = tuple((f.get("type"), f.get("enabled", True)) for f in ch.fx)
        if self._fx_sig.get(ch.id) != sig:
            chain = []
            for spec in ch.fx:
                cls = EFFECTS.get(spec.get("type", ""))
                if cls is None:
                    continue
                fx = cls(spec.get("params"), self.sr)
                fx.enabled = bool(spec.get("enabled", True))
                if isinstance(fx, Delay):
                    fx.set_tempo(self.project.bpm)
                chain.append(fx)
            self._chan_fx[ch.id] = chain
            self._fx_sig[ch.id] = sig
        else:
            chain = self._chan_fx.get(ch.id, [])
            for fx, spec in zip(chain, ch.fx):
                for k, v in (spec.get("params") or {}).items():
                    if fx.p.get(k) != v:
                        fx.set(k, v)
        return chain

    def _sidechain_for(self, ch: Channel) -> Sidechain:
        sc = self._sidechains.get(ch.id)
        if sc is None:
            sc = Sidechain(self.sr)
            self._sidechains[ch.id] = sc
        sc.amount = ch.sc_amount
        sc.release = ch.sc_release
        sc.shape = ch.sc_shape
        return sc

    # -- render --------------------------------------------------------------
    def render(self, n: int | None = None) -> np.ndarray:
        n = n or self.block
        t_start = time.perf_counter()
        with self.lock:
            out = self._render_locked(n)
        dt = time.perf_counter() - t_start
        self.cpu = 0.9 * self.cpu + 0.1 * (dt / (n / self.sr) * 100.0)
        return out

    def _render_locked(self, n: int) -> np.ndarray:
        pr = self.project
        self.delay_bus.set_tempo(pr.bpm)

        # 1. schedule any steps starting inside this block
        if self.playing:
            sps = self.samples_per_step
            loop_steps = self.loop_length_steps()
            loop_samples = loop_steps * sps
            start, end = float(self.pos), float(self.pos + n)
            k = int(start // sps) - 1
            guard = 0
            while guard < 512:
                guard += 1
                onset = self._step_onset(k)
                if onset >= end:
                    break
                if onset >= start and k > self._step_cache:
                    self._fire_step(k, int(onset - start))
                    self._step_cache = k
                k += 1
            self.pos += n
            if self.loop and loop_samples > 0 and self.pos >= loop_samples:
                self.pos -= loop_samples
                self._step_cache = -1

        # 2. mix voices into their channels
        master = np.zeros((n, 2), dtype=np.float32)
        rev_send = np.zeros((n, 2), dtype=np.float32)
        dly_send = np.zeros((n, 2), dtype=np.float32)

        by_chan: dict[str, np.ndarray] = {}
        dead = []
        for lv in self._voices:
            if lv.off_at is not None and not lv.released and self.pos >= lv.off_at:
                lv.voice.note_off()
                lv.released = True
            k = n - lv.offset
            if k <= 0:
                lv.offset -= n
                continue
            try:
                sig = lv.voice.render(k)
            except Exception:
                dead.append(lv)
                continue
            buf = by_chan.get(lv.cid)
            if buf is None:
                buf = np.zeros((n, 2), dtype=np.float32)
                by_chan[lv.cid] = buf
            buf[lv.offset:] += sig
            lv.offset = 0
            if not lv.voice.active:
                dead.append(lv)
        for lv in dead:
            if lv in self._voices:
                self._voices.remove(lv)

        # 3. per-channel processing
        self.meters = {}
        for ch in pr.channels:
            buf = by_chan.get(ch.id)
            sc = self._sidechain_for(ch)
            duck = sc.gain(n)
            if buf is None:
                self.meters[ch.id] = 0.0
                continue
            for fx in self._chain_for(ch):
                buf = fx.process(buf)
            if duck is not None:
                buf = buf * duck[:, None]
            gl, gr = equal_power_pan(ch.pan)
            vol = ch.volume if pr.audible(ch) else 0.0
            buf = buf * np.array([gl * vol, gr * vol], dtype=np.float32)
            self.meters[ch.id] = float(np.max(np.abs(buf))) if buf.size else 0.0
            master += buf
            if ch.sends.reverb > 1e-4:
                rev_send += buf * ch.sends.reverb
            if ch.sends.delay > 1e-4:
                dly_send += buf * ch.sends.delay

        # voices with no channel of their own (sample auditions) go straight out
        for cid, buf in by_chan.items():
            if pr.channel(cid) is None:
                master += buf

        # 4. send buses
        master += self.reverb_bus.process(rev_send)
        master += self.delay_bus.process(dly_send)

        # 5. master chain
        master = self.dj.process(master)
        master = self.eq.process(master)
        master = self.comp.process(master)
        master = master * float(pr.master.get("volume", 0.85))
        master = self.limiter.process(master)

        self.master_peak = np.max(np.abs(master), axis=0) if master.size else \
            np.zeros(2, dtype=np.float32)
        return np.nan_to_num(master, copy=False)

    # -- master parameter sync ----------------------------------------------
    def sync_master(self) -> None:
        with self.lock:
            m = self.project.master
            for key, fx in (("reverb", self.reverb_bus), ("delay", self.delay_bus),
                            ("djfilter", self.dj), ("eq", self.eq),
                            ("comp", self.comp), ("limiter", self.limiter)):
                for k, v in (m.get(key) or {}).items():
                    if fx.p.get(k) != v:
                        fx.set(k, v)
            self.delay_bus.set_tempo(self.project.bpm)

    def reset_audio_state(self) -> None:
        with self.lock:
            self._voices.clear()
            for fx in (self.reverb_bus, self.delay_bus, self.dj, self.eq,
                       self.comp, self.limiter):
                fx.reset()
            self._chan_fx.clear()
            self._fx_sig.clear()

    def load_project(self, project: Project) -> None:
        """Swap in a different project without disturbing the audio stream."""
        with self.lock:
            self.project = project
            self.playing = False
            self.pos = 0
            self._step_cache = -1
            self.mode = "pattern"
            self.current_pattern = (project.patterns[0].id
                                    if project.patterns else "")
            self._voices.clear()
            self._sidechains.clear()
            self._chan_fx.clear()
            self._fx_sig.clear()
            self.meters = {}
            for key, fx in (("reverb", self.reverb_bus), ("delay", self.delay_bus),
                            ("djfilter", self.dj), ("eq", self.eq),
                            ("comp", self.comp), ("limiter", self.limiter)):
                fx.p.update(project.master.get(key) or {})
                fx.reset()
            self.delay_bus.set_tempo(project.bpm)

    # -- offline render ------------------------------------------------------
    def render_span(self, steps: int, tail: float = 3.0,
                    progress=None) -> np.ndarray:
        """Render `steps` steps from the top plus a tail, for WAV export."""
        with self.lock:
            saved = (self.playing, self.pos, self.loop, self._step_cache)
            self.playing, self.pos, self.loop = True, 0, False
            self._step_cache = -1
            self.reset_audio_state()
        total = int(steps * self.samples_per_step) + int(tail * self.sr)
        chunks, done = [], 0
        blk = 2048
        while done < total:
            k = min(blk, total - done)
            chunks.append(self.render(k))
            done += k
            if progress is not None and not progress(done / total):
                break
        with self.lock:
            self.playing, self.pos, self.loop, self._step_cache = saved
            self.reset_audio_state()
        return np.concatenate(chunks) if chunks else np.zeros((0, 2), np.float32)
