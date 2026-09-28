"""Run the bundled Basic Pitch TensorFlow model without Numba native extensions."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
HOP = 256
FRAMES_PER_SECOND = SAMPLE_RATE // HOP
WINDOW_SAMPLES = SAMPLE_RATE * 2 - HOP
OVERLAP_FRAMES = 30
OVERLAP_SAMPLES = OVERLAP_FRAMES * HOP


def predict_notes(path: str | Path) -> list[tuple[float, float, int, float]]:
    """Return onset, offset, MIDI pitch, confidence from Basic Pitch activations."""
    import tensorflow as tf
    from basic_pitch import ICASSP_2022_MODEL_PATH

    with wave.open(str(path), "rb") as audio_file:
        if audio_file.getnchannels() != 1 or audio_file.getframerate() != SAMPLE_RATE or audio_file.getsampwidth() != 2:
            raise ValueError("Expected 22,050 Hz mono, 16-bit WAV")
        samples = np.frombuffer(audio_file.readframes(audio_file.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    if not samples.size:
        return []

    model = tf.saved_model.load(str(ICASSP_2022_MODEL_PATH))
    infer = model.signatures["serving_default"]
    padded = np.pad(samples, (OVERLAP_SAMPLES // 2, 0))
    step = WINDOW_SAMPLES - OVERLAP_SAMPLES
    activations: dict[str, list[np.ndarray]] = {"note": [], "onset": []}
    for position in range(0, len(padded), step):
        window = padded[position:position + WINDOW_SAMPLES]
        if len(window) < WINDOW_SAMPLES:
            window = np.pad(window, (0, WINDOW_SAMPLES - len(window)))
        output = infer(input_2=tf.convert_to_tensor(window.reshape(1, WINDOW_SAMPLES, 1)))
        for name in activations:
            activations[name].append(output[name].numpy()[0, OVERLAP_FRAMES // 2:-OVERLAP_FRAMES // 2])

    frame_count = int(np.floor(len(samples) * FRAMES_PER_SECOND / SAMPLE_RATE))
    notes = np.concatenate(activations["note"], axis=0)[:frame_count]
    onsets = np.concatenate(activations["onset"], axis=0)[:frame_count]
    result: list[tuple[float, float, int, float]] = []
    for pitch_index in range(notes.shape[1]):
        active = notes[:, pitch_index] >= 0.3
        start: int | None = None
        for frame in range(len(active) + 1):
            is_active = frame < len(active) and bool(active[frame])
            new_onset = (is_active and frame > 0 and start is not None and
                         onsets[frame, pitch_index] >= 0.5 and onsets[frame - 1, pitch_index] < 0.5)
            if start is not None and (not is_active or new_onset):
                if frame - start >= 7:
                    confidence = float(np.max(notes[start:frame, pitch_index]))
                    result.append((start / FRAMES_PER_SECOND, frame / FRAMES_PER_SECOND,
                                   pitch_index + 21, confidence))
                start = None
            if is_active and start is None:
                start = frame
    return sorted(result, key=lambda note: (note[0], note[2]))
