"""Checks that TAB generation follows the harmonic mix and chord timeline."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from .arrangement import arrange_accompaniment
from .chords import suggest_chords
from .main import _make_harmony

TUNING = [64, 59, 55, 50, 45, 40]


def write_tones(path: Path, pitches: tuple[int, ...], seconds: float = 1.0) -> None:
    rate = 44100
    time = np.arange(round(rate * seconds)) / rate
    signal = sum(np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * time) for pitch in pitches)
    signal = np.asarray(signal * (2500 / max(1, len(pitches))), dtype="<i2")
    stereo = np.repeat(signal[:, None], 2, axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(stereo.tobytes())


class ArrangementTests(unittest.TestCase):
    def test_harmony_mix_includes_all_pitched_stems_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            stems = directory / "stems" / "model" / "song"
            for name, pitches in {"bass": (45,), "guitar": (57,), "piano": (64,),
                                  "other": (69,), "vocals": (81,), "drums": (76,)}.items():
                write_tones(stems / f"{name}.wav", pitches)
            with wave.open(str(_make_harmony(directory)), "rb") as audio:
                samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")[::2]
                rate = audio.getframerate()
            spectrum = np.abs(np.fft.rfft(samples.astype(float)))
            frequencies = np.fft.rfftfreq(len(samples), 1 / rate)
            def energy(pitch: int) -> float:
                hz = 440 * 2 ** ((pitch - 69) / 12)
                return float(spectrum[np.argmin(abs(frequencies - hz))])
            for pitch in (45, 57, 64, 69):
                self.assertGreater(energy(pitch), energy(81) * 5)
            self.assertLess(energy(76), energy(69) / 5)

    def test_chord_progression_becomes_beat_aligned_playable_strums(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progression.wav"
            rate = 44100
            time = np.arange(rate * 4) / rate
            chords = ((48, 52, 55, 60, 64), (43, 47, 50, 55, 59))
            halves = [sum(np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * time)
                          for pitch in chord) for chord in chords]
            mono = np.concatenate(halves) * 1000
            stereo = np.repeat(mono.astype("<i2")[:, None], 2, axis=1)
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                audio.writeframes(stereo.tobytes())
            beats = [i * .5 for i in range(16)]
            events = suggest_chords([], TUNING, 8, path, beat_times=beats)
            self.assertEqual([(event["time_seconds"], event["chord"]) for event in events],
                             [(0, "C"), (4, "G")])
            notes = arrange_accompaniment(events, TUNING, 8, beats, 120)
            self.assertTrue(notes)
            self.assertTrue(all(note["onset_seconds"] in beats for note in notes))
            self.assertTrue(all(note["pitch"] == TUNING[note["string"] - 1] + note["fret"]
                                for note in notes))
            self.assertTrue(all(note["source_model"] == "chord-arrangement" for note in notes))
            self.assertEqual({note["onset_seconds"] for note in notes}, set(beats))

    def test_no_chord_and_edited_voicing_update_arrangement(self) -> None:
        events = [
            {"time_seconds": 0, "chord": "C", "frets": [-1, 3, 2, 0, 1, 0]},
            {"time_seconds": 1, "chord": "N.C.", "frets": [-1] * 6},
            {"time_seconds": 2, "chord": "G", "frets": [3, 2, 0, 0, 0, 3]},
        ]
        beats = [i * .5 for i in range(8)]
        notes = arrange_accompaniment(events, TUNING, 4, beats, 120)
        self.assertFalse(any(1 <= note["onset_seconds"] < 2 for note in notes))
        edited = [dict(event) for event in events]
        edited[2]["frets"] = [3, 2, 0, 0, 3, 3]
        changed = arrange_accompaniment(edited, TUNING, 4, beats, 120)
        self.assertIn(3, {note["fret"] for note in changed if note["string"] == 2})


if __name__ == "__main__":
    unittest.main()
