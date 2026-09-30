"""Estimate chord changes from a mix of pitched accompaniment instruments."""
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
SEVENTH_SHAPES = (
    (0, 2, 0, 1, 0, 0),  # E7
    (-1, 0, 2, 0, 2, 0),  # A7
    (-1, -1, 0, 2, 1, 2),  # D7
    (3, 2, 0, 0, 0, 1),  # G7
    (0, 2, 0, 0, 0, 0),  # Em7
    (-1, 0, 2, 0, 1, 0),  # Am7
    (-1, -1, 0, 2, 1, 1),  # Dm7
)
STANDARD_LOW_TO_HIGH = (40, 45, 50, 55, 59, 64)
def _candidates(tuning: list[int]) -> list[tuple[str, tuple[int, ...], set[int], int, float]]:
    """Transpose familiar voicings, retaining only valid shapes in this tuning."""
    result = []
    source_shapes = EASY_SHAPES + SEVENTH_SHAPES
    for shape in source_shapes:
        source_pcs = {(pitch + fret) % 12 for pitch, fret in zip(STANDARD_LOW_TO_HIGH, shape) if fret >= 0}
        for root in range(12):
            for suffix, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7)),
                                      ("7", (0, 4, 7, 10)), ("m7", (0, 3, 7, 10))):
                if source_pcs != {(root + interval) % 12 for interval in intervals}:
                    continue
                for shift in range(12):
                    for octave in (0, 12):
                        frets = tuple(-1 if fret < 0 else pitch + fret + shift + octave - open_pitch
                                      for pitch, fret, open_pitch in zip(STANDARD_LOW_TO_HIGH, shape, reversed(tuning)))
                        played = [fret for fret in frets if fret >= 0]
                        if (not played or any(fret < 0 for original, fret in zip(shape, frets) if original >= 0)
                                or max(played) > 20):
                            continue
                        positive = [fret for fret in played if fret > 0]
                        span = max(positive) - min(positive) if positive else 0
                        if span > 5:
                            continue
                        pitches = {(pitch + fret) % 12 for pitch, fret in zip(reversed(tuning), frets) if fret >= 0}
                        bass = next((pitch + fret) % 12 for pitch, fret in zip(reversed(tuning), frets) if fret >= 0)
                        shifted_root = (root + shift) % 12
                        if bass != shifted_root:
                            continue
                        difficulty = min(positive, default=0) * .012 + span * .02 + sum(f > 4 for f in played) * .015
                        result.append((PITCH_NAMES[shifted_root] + suffix, frets, pitches, shifted_root, difficulty))
    best = {}
    for candidate in result:
        name = candidate[0]
        if name not in best or candidate[4] < best[name][4]:
            best[name] = candidate
    return list(best.values())


def _audio_profiles(path: str | Path, boundaries: list[float]) -> np.ndarray:
    with wave.open(str(path), "rb") as audio_file:
        rate = audio_file.getframerate()
        channels = audio_file.getnchannels()
        if audio_file.getsampwidth() != 2:
            raise ValueError("コード解析には16-bit PCM WAV が必要です。")
        samples = np.frombuffer(audio_file.readframes(audio_file.getnframes()), dtype="<i2").astype(np.float32)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
    profiles = np.zeros((len(boundaries) - 1, 12), dtype=np.float64)
    if not samples.size:
        return profiles
    size = 8192
    hop = max(1, rate // 8)
    window = np.hanning(size)
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    bins = [(midi % 12, np.flatnonzero(abs(frequencies - 440 * 2 ** ((midi - 69) / 12)) < rate / size * 1.5))
            for midi in range(40, 85)]
    for position in range(0, max(1, len(samples) - size + 1), hop):
        frame = samples[position:position + size]
        if len(frame) < size:
            frame = np.pad(frame, (0, size - len(frame)))
        spectrum = abs(np.fft.rfft(frame * window))
        index = min(len(profiles) - 1, max(0, int(np.searchsorted(boundaries, position / rate + size / rate / 2, side="right") - 1)))
        for pitch_class, nearby in bins:
            if nearby.size:
                profiles[index, pitch_class] += float(np.max(spectrum[nearby])) ** .7
    return profiles


def suggest_chords(notes: list[dict], tuning: list[int], duration: float,
                   audio_path: str | Path | None = None, window_seconds: float = 1.0,
                   beat_times: list[float] | None = None) -> list[dict]:
    candidates = _candidates(tuning)
    if not candidates or duration <= 0:
        return []
    if beat_times and len(beat_times) >= 2:
        boundaries = sorted({0.0, duration, *(time for time in beat_times if 0 < time < duration)})
    else:
        boundaries = [min(duration, index * window_seconds) for index in range(math.ceil(duration / window_seconds) + 1)]
        if boundaries[-1] < duration:
            boundaries.append(duration)
    count = len(boundaries) - 1
    profiles = _audio_profiles(audio_path, boundaries) if audio_path else np.zeros((count, 12))
    note_profiles = np.zeros_like(profiles)
    for note in notes:
        start = max(0, int(np.searchsorted(boundaries, note["onset_seconds"], side="right") - 1))
        end = min(count, int(np.searchsorted(boundaries, note["offset_seconds"], side="left") + 1))
        for index in range(start, end):
            overlap = max(0, min(note["offset_seconds"], boundaries[index + 1]) -
                          max(note["onset_seconds"], boundaries[index]))
            note_profiles[index, note["pitch"] % 12] += overlap * note.get("confidence", 1)

    # Keep a pre-normalization reference for genuinely silent harmonic windows.
    audio_energy = profiles.sum(axis=1).copy()
    note_energy = note_profiles.sum(axis=1).copy()
    silence_floor = float(audio_energy.max(initial=0)) * .035
    silent = (audio_energy < silence_floor) & (note_energy < .06)
    # Normalize the two evidence sources separately so recording level does not decide the chord.
    profiles /= np.maximum(profiles.sum(axis=1, keepdims=True), 1e-9)
    note_profiles /= np.maximum(note_profiles.sum(axis=1, keepdims=True), 1e-9)
    profiles = profiles * .65 + note_profiles * .35 if note_energy.max(initial=0) > 0 else profiles

    # Dynamic programming keeps an entire progression coherent instead of deciding
    # each window independently. A clear new chord still wins over the change cost.
    scores = np.zeros(len(candidates))
    backtrack = []
    change_cost = np.array([[0 if old[0] == new[0] else (.16 if old[3] == new[3] else .24)
                             for new in candidates] for old in candidates])
    for profile in profiles:
        emission = np.array([
            1.5 * sum(profile[pitch] for pitch in pitches)
            - .9 * sum(profile[pitch] for pitch in range(12) if pitch not in pitches)
            + .25 * profile[root]
            + .4 * profile[(root + (3 if name.endswith(('m', 'm7')) else 4)) % 12]
            - difficulty - (.08 if name.endswith('7') else 0)
            - (.25 * max(0, .12 - profile[(root + 10) % 12]) / .12 if name.endswith('7') else 0)
            for name, _, pitches, root, difficulty in candidates
        ])
        transitions = scores[:, None] - change_cost
        previous = transitions.argmax(axis=0)
        scores = transitions[previous, np.arange(len(candidates))] + emission
        backtrack.append(previous)
    state = int(scores.argmax())
    chosen = [state]
    for previous in reversed(backtrack[1:]):
        state = int(previous[state])
        chosen.append(state)
    chosen.reverse()
    events = []
    for index, state in enumerate(chosen):
        if silent[index] or profiles[index].sum() < .03:
            if not events or events[-1]["chord"] != "N.C.":
                events.append({"id": uuid4().hex, "time_seconds": round(boundaries[index], 3),
                               "chord": "N.C.", "lyric": "", "frets": [-1] * 6})
            continue
        name, shape, _, _, _ = candidates[state]
        if events and events[-1]["chord"] == name:
            continue
        events.append({"id": uuid4().hex, "time_seconds": round(boundaries[index], 3),
                       "chord": name, "lyric": "", "frets": list(shape)})
    return events


def attach_lyrics(events: list[dict], phrases: list[dict]) -> list[dict]:
    """Put each lyric at its own recognized onset, independent of chord changes."""
    for phrase in phrases:
        text = phrase.get("text", "").strip()
        if text:
            events.append({"id": uuid4().hex, "time_seconds": round(phrase["start_seconds"], 2),
                           "chord": "", "lyric": text[:240], "frets": [-1] * 6})
    return sorted(events, key=lambda event: event["time_seconds"])
