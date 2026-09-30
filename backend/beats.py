"""Estimate a stable beat grid and gently align detected note timings."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def estimate_beats(path: str | Path, duration: float) -> tuple[float | None, list[float]]:
    """Return BPM and beat times only when a reasonably regular pulse is present."""
    import librosa

    audio, rate = librosa.load(str(path), sr=22050, mono=True)
    if audio.size < rate * 4 or float(np.max(np.abs(audio))) < 0.002:
        return None, []
    hop = 512
    envelope = librosa.onset.onset_strength(y=audio, sr=rate, hop_length=hop)
    if not envelope.size or float(np.max(envelope)) < 0.05:
        return None, []
    _, frames = librosa.beat.beat_track(onset_envelope=envelope, sr=rate, hop_length=hop,
                                       start_bpm=120, trim=False)
    times = librosa.frames_to_time(frames, sr=rate, hop_length=hop)
    if len(times) < 4:
        return None, []
    intervals = np.diff(times)
    median = float(np.median(intervals))
    if not 0.3 <= median <= 1.0 or float(np.median(np.abs(intervals - median))) > median * 0.16:
        return None, []
    period = float((times[-1] - times[0]) / (len(times) - 1))
    # Keep detected beats for tempo drift, and extend the steady pulse to the audio edges.
    grid = [float(t) for t in times if 0 <= t < duration]
    if not grid:
        return None, []
    while grid[0] - period >= 0:
        grid.insert(0, grid[0] - period)
    while grid[-1] + period < duration:
        grid.append(grid[-1] + period)
    return round(60 / period, 1), [round(t, 3) for t in grid]


def quantize_notes(notes: list[dict], beats: list[float], duration: float) -> list[dict]:
    """Move nearby onsets/offsets to 16th-note positions without erasing off-grid phrasing."""
    if len(beats) < 2:
        return notes
    grid = []
    for left, right in zip(beats, beats[1:]):
        grid.extend(left + (right - left) * step / 4 for step in range(4))
    grid.append(beats[-1])
    positions = np.asarray(grid)
    beat_length = float(np.median(np.diff(beats)))
    tolerance = min(0.065, beat_length * 0.13)

    def snap(value: float) -> float:
        index = int(np.argmin(np.abs(positions - value)))
        candidate = float(positions[index])
        return candidate if abs(candidate - value) <= tolerance else value

    for note in notes:
        onset = snap(note["onset_seconds"])
        offset = snap(note["offset_seconds"])
        if offset <= onset + 0.05:
            offset = max(note["offset_seconds"], onset + 0.08)
        note["onset_seconds"] = round(max(0, min(onset, duration)), 3)
        note["offset_seconds"] = round(min(duration, offset), 3)
    return notes
