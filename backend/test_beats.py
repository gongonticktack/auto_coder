"""Focused checks for beat-aware timing and exported tempo."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from .beats import estimate_beats, quantize_notes
from .chords import suggest_chords
from .exporters import midi, musicxml


class BeatTimingTests(unittest.TestCase):
    def test_detects_click_track_and_ignores_silence(self) -> None:
        rate = 22050
        samples = np.zeros(rate * 12, dtype="<i2")
        click = np.linspace(22000, 0, 100, dtype="<i2")
        for time in np.arange(.25, 12, .5):
            start = round(time * rate)
            samples[start:start + len(click)] = click
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clicks.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(rate)
                output.writeframes(samples.tobytes())
            bpm, beats = estimate_beats(path, 12)
            self.assertIsNotNone(bpm)
            self.assertAlmostEqual(bpm, 120, delta=3)
            self.assertGreaterEqual(len(beats), 20)
            self.assertAlmostEqual(beats[0], .25, delta=.06)
            path.write_bytes(path.read_bytes()[:44] + b"\x00" * (len(samples) * 2))
            self.assertEqual(estimate_beats(path, 12), (None, []))

    def test_notes_and_chords_follow_beats(self) -> None:
        beats = [.25 + i * .5 for i in range(16)]
        notes = [{"pitch": 60, "onset_seconds": .29, "offset_seconds": .78, "confidence": 1},
                 {"pitch": 64, "onset_seconds": 1.28, "offset_seconds": 1.73, "confidence": 1}]
        quantize_notes(notes, beats, 8)
        self.assertAlmostEqual(notes[0]["onset_seconds"], .25)
        self.assertAlmostEqual(notes[0]["offset_seconds"], .75)
        events = suggest_chords(notes, [64, 59, 55, 50, 45, 40], 8, beat_times=beats)
        self.assertTrue(events)
        self.assertTrue(all(event["time_seconds"] in [0, *beats] for event in events))

    def test_exports_use_detected_tempo(self) -> None:
        notes = [{"pitch": 64, "onset_seconds": .5, "offset_seconds": 1.0, "string": 1, "fret": 0}]
        score = ElementTree.fromstring(musicxml(notes, [64, 59, 55, 50, 45, 40], "test", 90))
        self.assertEqual(score.findtext(".//per-minute"), "90")
        self.assertIn(b"\xff\x51\x03" + round(60_000_000 / 90).to_bytes(3, "big"), midi(notes, 90))


if __name__ == "__main__":
    unittest.main()
