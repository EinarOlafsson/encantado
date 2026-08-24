"""WAV import/export using only the standard library."""
from __future__ import annotations

import wave

import numpy as np


def write_wav(path: str, audio: np.ndarray, sr: int = 44100,
              bits: int = 16) -> None:
    """audio: (n, 2) float32 in roughly [-1, 1]."""
    a = np.asarray(audio, dtype=np.float64)
    if a.ndim == 1:
        a = np.stack((a, a), axis=-1)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 1.0:
        a = a / peak                      # never clip on the way out
    with wave.open(path, "wb") as fh:
        fh.setnchannels(a.shape[1])
        fh.setsampwidth(bits // 8)
        fh.setframerate(sr)
        if bits == 24:
            q = np.clip(a * 8388607.0, -8388608, 8388607).astype(np.int32)
            b = q.astype("<i4").tobytes()
            fh.writeframes(b"".join(b[i:i + 3] for i in range(0, len(b), 4)))
        else:
            q = np.clip(a * 32767.0, -32768, 32767).astype("<i2")
            fh.writeframes(q.tobytes())


def read_wav(path: str, target_sr: int = 44100) -> tuple[np.ndarray, int]:
    """Returns (n, 2) float32. Resamples linearly if the rate differs."""
    with wave.open(path, "rb") as fh:
        n_ch, width, sr, n_frames = (fh.getnchannels(), fh.getsampwidth(),
                                     fh.getframerate(), fh.getnframes())
        raw = fh.readframes(n_frames)
    if width == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        q = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int32) << 16))
        q = np.where(q & 0x800000, q - 0x1000000, q)
        a = q.astype(np.float32) / 8388608.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {width}")

    a = a.reshape(-1, n_ch)
    if n_ch == 1:
        a = np.repeat(a, 2, axis=1)
    elif n_ch > 2:
        a = a[:, :2]

    if sr != target_sr and len(a):
        ratio = target_sr / sr
        idx = np.arange(int(len(a) * ratio)) / ratio
        i0 = np.clip(idx.astype(np.int64), 0, len(a) - 1)
        i1 = np.clip(i0 + 1, 0, len(a) - 1)
        frac = (idx - i0).astype(np.float32)[:, None]
        a = a[i0] * (1 - frac) + a[i1] * frac
    return np.ascontiguousarray(a, dtype=np.float32), target_sr


# --------------------------------------------------------------------------
# Anything that is not a WAV goes through ffmpeg, when it is available
# --------------------------------------------------------------------------
import os
import shutil
import subprocess
import tempfile

AUDIO_EXTS = (".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".ogg",
              ".m4a", ".aac", ".wma", ".opus")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def read_audio(path: str, target_sr: int = 44100) -> tuple[np.ndarray, int]:
    """Read any common audio file. WAV is decoded directly; everything else is
    converted with ffmpeg if it is installed."""
    if os.path.splitext(path)[1].lower() in (".wav", ".wave"):
        try:
            return read_wav(path, target_sr)
        except Exception:
            pass                      # fall through: some 'wav' files are not
    if not ffmpeg_available():
        raise RuntimeError(
            f"{os.path.splitext(path)[1] or 'This format'} needs ffmpeg to import. "
            "Install ffmpeg, or convert the file to WAV.")
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path,
             "-ac", "2", "-ar", str(target_sr), "-c:a", "pcm_s16le", tmp],
            capture_output=True, timeout=120)
        if proc.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:300]
                               or "ffmpeg could not decode this file")
        return read_wav(tmp, target_sr)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def probe_duration(path: str) -> float:
    """Cheap duration read for the library scanner (WAV without full decode)."""
    if os.path.splitext(path)[1].lower() in (".wav", ".wave"):
        try:
            with wave.open(path, "rb") as fh:
                return fh.getnframes() / float(fh.getframerate() or 44100)
        except Exception:
            return 0.0
    if not shutil.which("ffprobe"):
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, timeout=20)
        return float(out.stdout.decode().strip() or 0.0)
    except Exception:
        return 0.0
