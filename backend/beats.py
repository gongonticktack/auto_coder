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


def analyze_groove(path: str | Path, beats: list[float], duration: float) -> list[dict]:
    """Measure phrase energy and offbeat attacks on an established beat grid."""
    if len(beats) < 2:
        return []
    import librosa

    audio, rate = librosa.load(str(path), sr=22050, mono=True)
    if audio.size < rate or float(np.max(np.abs(audio))) < .002:
        return []
    hop = 256
    onset = librosa.onset.onset_strength(y=audio, sr=rate, hop_length=hop)
    if not onset.size:
        return []
    onset_times = librosa.frames_to_time(np.arange(len(onset)), sr=rate, hop_length=hop)
    positive = onset[onset > 0]
    attack_floor = float(np.percentile(positive, 55)) if positive.size else 0
    raw_energy = []
    offbeats = []
    for index, beat in enumerate(beats):
        period = beats[index + 1] - beat if index + 1 < len(beats) else beats[index] - beats[index - 1]
        period = max(.15, period)
        begin = max(0, round(beat * rate))
        end = min(audio.size, round(min(duration, beat + period) * rate))
        segment = audio[begin:end]
        raw_energy.append(float(np.sqrt(np.mean(segment ** 2))) if segment.size else 0)
        window = onset[(onset_times >= beat + .39 * period) &
                       (onset_times <= beat + .65 * period)]
        offbeats.append(bool(window.size and float(window.max()) > attack_floor * 1.35
                             and float(window.max()) > .06))

    # Smooth across a short phrase so a single kick does not change the playing style.
    padded = np.pad(np.asarray(raw_energy), (1, 2), mode="edge")
    energy = np.convolve(padded, np.ones(4) / 4, mode="valid")
    low, high = np.percentile(energy, [15, 85])
    if high - low < max(high * .12, 1e-5):
        levels = np.full(len(beats), .5)
    else:
        levels = np.clip((energy - low) / (high - low), 0, 1)
    return [{"time_seconds": round(beat, 3), "energy": round(float(level), 3),
             "offbeat": offbeat} for beat, level, offbeat in zip(beats, levels, offbeats)]


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
