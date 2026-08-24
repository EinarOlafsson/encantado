"""Realtime audio output via Qt Multimedia.

Pull mode: Qt asks a QIODevice for samples from its own audio thread, and we
render straight from the engine. No extra audio library, and one code path
shared with the offline exporter.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtMultimedia import (QAudioFormat, QAudioSink, QMediaDevices)

BYTES_PER_FRAME = 8          # float32 stereo
MAX_FRAMES = 8192


class _EngineDevice(QIODevice):
    """Adapts the engine to the QIODevice interface Qt pulls from."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.underruns = 0

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        return MAX_FRAMES * BYTES_PER_FRAME + super().bytesAvailable()

    def readData(self, maxlen: int) -> bytes:
        frames = int(maxlen) // BYTES_PER_FRAME
        if frames <= 0:
            return b""
        frames = min(frames, MAX_FRAMES)
        try:
            block = self.engine.render(frames)
        except Exception:
            self.underruns += 1
            block = np.zeros((frames, 2), dtype=np.float32)
        if block.shape[0] != frames:
            pad = np.zeros((frames, 2), dtype=np.float32)
            k = min(frames, block.shape[0])
            pad[:k] = block[:k]
            block = pad
        return np.ascontiguousarray(block, dtype=np.float32).tobytes()

    def writeData(self, data) -> int:
        return 0


class AudioBackend(QObject):
    """Owns the QAudioSink and keeps it fed."""

    state_changed = pyqtSignal(str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.sink: QAudioSink | None = None
        self.device_obj: _EngineDevice | None = None
        self._device = None
        self.buffer_frames = 2048
        self.last_error = ""

    # -- devices -------------------------------------------------------------
    @staticmethod
    def output_devices() -> list:
        return list(QMediaDevices.audioOutputs())

    @staticmethod
    def device_names() -> list[str]:
        return [d.description() for d in QMediaDevices.audioOutputs()]

    def _format(self) -> QAudioFormat:
        fmt = QAudioFormat()
        fmt.setSampleRate(self.engine.sr)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        return fmt

    # -- lifecycle -----------------------------------------------------------
    def start(self, device=None, buffer_frames: int | None = None) -> bool:
        self.stop()
        if buffer_frames:
            self.buffer_frames = int(buffer_frames)
        dev = device or QMediaDevices.defaultAudioOutput()
        if dev is None or dev.isNull():
            self.last_error = "No audio output device found."
            self.state_changed.emit("error")
            return False
        fmt = self._format()
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
            if fmt.channelCount() != 2:
                fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
            if not dev.isFormatSupported(fmt):
                self.last_error = f"{dev.description()} cannot play 44.1 kHz stereo float."
                self.state_changed.emit("error")
                return False
        self._device = dev
        self.sink = QAudioSink(dev, fmt, self)
        self.sink.setBufferSize(self.buffer_frames * BYTES_PER_FRAME)
        self.device_obj = _EngineDevice(self.engine, self)
        self.device_obj.open(QIODevice.OpenModeFlag.ReadOnly)
        self.sink.start(self.device_obj)
        ok = self.sink.error().name in ("NoError",)
        self.last_error = "" if ok else self.sink.error().name
        self.state_changed.emit("running" if ok else "error")
        return ok

    def stop(self) -> None:
        if self.sink is not None:
            try:
                self.sink.stop()
            except RuntimeError:
                pass
            self.sink = None
        if self.device_obj is not None:
            try:
                self.device_obj.close()
            except RuntimeError:
                pass
            self.device_obj = None
        self.state_changed.emit("stopped")

    def restart(self) -> bool:
        return self.start(self._device, self.buffer_frames)

    @property
    def running(self) -> bool:
        return self.sink is not None

    def set_volume(self, v: float) -> None:
        if self.sink is not None:
            self.sink.setVolume(float(max(0.0, min(1.0, v))))

    def latency_ms(self) -> float:
        return self.buffer_frames / self.engine.sr * 1000.0
