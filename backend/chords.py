"""Suggest easy guitar chords from the audio's pitch classes."""
from __future__ import annotations

import math
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np

PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
# Frets are ordered from the sixth (lowest) to the first (highest) string.
EASY_SHAPES = (
    (-1, 3, 2, 0, 1, 0),  # C
    (-1, -1, 0, 2, 3, 2),  # D
    (0, 2, 2, 1, 0, 0),  # E
    (3, 2, 0, 0, 0, 3),  # G
    (-1, 0, 2, 2, 2, 0),  # A
    (0, 2, 2, 0, 0, 0),  # Em
    (-1, 0, 2, 2, 1, 0),  # Am
    (-1, -1, 0, 2, 3, 1),  # Dm
    (-1, -1, 3, 2, 1, 1),  # F
    (-1, 2, 4, 4, 3, 2),  # Bm
)
OPEN_G_SHAPES = (
    (0, 0, 0, 0, 0, 0),  # G
    (-1, 0, 2, 0, 1, 2),  # C
    (-1, 2, 0, 2, 3, 4),  # D
    (-1, 0, 2, 0, 0, 2),  # Em
    (-1, 2, 2, 2, 1, 2),  # Am
)
DROP_D_SHAPES = (
    (-1, 2, 2, 1, 0, 0),  # E
    (-1, 2, 2, 0, 0, 0),  # Em
)


def _candidates(tuning: list[int]) -> list[tuple[str, tuple[int, ...], set[int], int, float]]:
    result = []
    shapes = EASY_SHAPES
    if tuning == [62, 59, 55, 50, 43, 38]:
        shapes += OPEN_G_SHAPES
    if tuning == [64, 59, 55, 50, 45, 38]:
        shapes += DROP_D_SHAPES
    for shape in shapes:
        pitches = {(open_pitch + fret) % 12 for open_pitch, fret in zip(reversed(tuning), shape) if fret >= 0}
        for root in range(12):
            for suffix, third in (("", 4), ("m", 3)):
                triad = {root, (root + third) % 12, (root + 7) % 12}
                if pitches == triad:
                    positive = [fret for fret in shape if fret > 0]
                    difficulty = (max(positive, default=0) * .015 +
                                  (max(positive) - min(positive) if positive else 0) * .025 +
                                  sum(fret > 2 for fret in shape) * .015)
                    result.append((PITCH_NAMES[root] + suffix, shape, pitches, root, difficulty))
    return result


def _audio_profiles(path: str | Path, count: int, window_seconds: float) -> np.ndarray:
    with wave.open(str(path), "rb") as audio_file:
        rate = audio_file.getframerate()
        samples = np.frombuffer(audio_file.readframes(audio_file.getnframes()), dtype="<i2").astype(np.float32)
    profiles = np.zeros((count, 12), dtype=np.float64)
    if not samples.size:
        return profiles
    size = 8192
    hop = rate // 2
    window = np.hanning(size)
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    bins = [(midi % 12, np.flatnonzero(abs(frequencies - 440 * 2 ** ((midi - 69) / 12)) < rate / size * 1.5))
            for midi in range(40, 85)]
    for position in range(0, max(1, len(samples) - size + 1), hop):
        frame = samples[position:position + size]
        if len(frame) < size:
            frame = np.pad(frame, (0, size - len(frame)))
        spectrum = abs(np.fft.rfft(frame * window))
        index = min(count - 1, int(position / rate / window_seconds))
        for pitch_class, nearby in bins:
            if nearby.size:
                profiles[index, pitch_class] += float(np.max(spectrum[nearby]))
    return profiles


def suggest_chords(notes: list[dict], tuning: list[int], duration: float,
                   audio_path: str | Path | None = None, window_seconds: float = 4) -> list[dict]:
    candidates = _candidates(tuning)
    if not candidates or duration <= 0:
        return []
    count = math.ceil(duration / window_seconds)
    profiles = _audio_profiles(audio_path, count, window_seconds) if audio_path else np.zeros((count, 12))
    for note in notes:
        start = max(0, int(note["onset_seconds"] // window_seconds))
        end = min(count, int(note["offset_seconds"] // window_seconds) + 1)
        for index in range(start, end):
            overlap = max(0, min(note["offset_seconds"], (index + 1) * window_seconds) -
                          max(note["onset_seconds"], index * window_seconds))
            profiles[index, note["pitch"] % 12] += overlap * note.get("confidence", 1) * 5000

    events = []
    previous_name = None
    for index, profile in enumerate(profiles):
        total = profile.sum()
        if total <= 0:
            continue
        profile = profile / total
        name, shape, _, _, _ = max(
            candidates,
            key=lambda item: (sum(profile[pitch] for pitch in item[2]) + profile[item[3]] * .08 -
                              item[4] - (.09 if previous_name and item[0] != previous_name else 0)),
        )
        events.append({"id": uuid4().hex, "time_seconds": round(index * window_seconds, 2),
                       "chord": name, "lyric": "", "frets": list(shape)})
        previous_name = name
    return events


def attach_lyrics(events: list[dict], phrases: list[dict]) -> list[dict]:
    for phrase in phrases:
        if not events or events[0]["time_seconds"] > phrase["start_seconds"]:
            events.append({"id": uuid4().hex, "time_seconds": phrase["start_seconds"],
                           "chord": "N.C.", "lyric": "", "frets": [-1] * 6})
            events.sort(key=lambda event: event["time_seconds"])
        index = max(i for i, event in enumerate(events)
                    if event["time_seconds"] <= phrase["start_seconds"])
        event = events[index]
        if event["chord"] == "N.C." and event["lyric"] and phrase["start_seconds"] - event["time_seconds"] >= 4:
            event = {"id": uuid4().hex, "time_seconds": phrase["start_seconds"],
                     "chord": "N.C.", "lyric": "", "frets": [-1] * 6}
            events.insert(index + 1, event)
        if event["lyric"] and len(event["lyric"]) + len(phrase["text"]) + 1 > 240:
            event = {"id": uuid4().hex, "time_seconds": phrase["start_seconds"],
                     "chord": events[index]["chord"], "lyric": "",
                     "frets": events[index]["frets"][:]}
            events.insert(index + 1, event)
        event["lyric"] = (event["lyric"] + " " + phrase["text"]).strip()[:240]
    return sorted(events, key=lambda event: event["time_seconds"])
