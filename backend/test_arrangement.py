"""Checks that TAB generation follows the harmonic mix and chord timeline."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from .arrangement import arrange_accompaniment
from .beats import analyze_groove
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
            self.assertTrue(all(note["onset_seconds"] in beats or
                                any(abs(note["onset_seconds"] - beat - .25) < .001 for beat in beats)
                                for note in notes))
            self.assertTrue(all(note["pitch"] == TUNING[note["string"] - 1] + note["fret"]
                                for note in notes))
            self.assertTrue(all(note["source_model"] == "chord-arrangement" for note in notes))
            onsets = {note["onset_seconds"] for note in notes}
            self.assertEqual({round(time, 3) for time in (0, .5, 1.25, 1.5)},
                             {time for time in onsets if time < 2})
            self.assertFalse({.25, .75, 1, 1.75} & onsets)

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

    def test_chord_change_between_pattern_hits_replaces_nearby_stroke(self) -> None:
        events = [
            {"time_seconds": 0, "chord": "C", "frets": [-1, 3, 2, 0, 1, 0]},
            {"time_seconds": 1.22, "chord": "G", "frets": [3, 2, 0, 0, 0, 3]},
        ]
        notes = arrange_accompaniment(events, TUNING, 2, [0, .5, 1, 1.5], 120)
        onsets = {note["onset_seconds"] for note in notes}
        self.assertIn(1.22, onsets)
        self.assertNotIn(1.25, onsets)
        self.assertTrue(all(note["technique"] == "strum-down"
                            for note in notes if note["onset_seconds"] == 1.22))

    def test_groove_changes_playing_style_and_dynamics(self) -> None:
        events = [{"time_seconds": 0, "chord": "C", "frets": [-1, 3, 2, 0, 1, 0]}]
        beats = [i * .5 for i in range(16)]
        groove = [{"time_seconds": beat, "energy": .12 if i < 8 else .9,
                   "offbeat": i >= 8} for i, beat in enumerate(beats)]
        notes = arrange_accompaniment(events, TUNING, 8, beats, 120, groove)
        early = [note for note in notes if 0 < note["onset_seconds"] < 4]
        late = [note for note in notes if note["onset_seconds"] >= 4]
        self.assertIn("bass-pick", {note["technique"] for note in early})
        self.assertIn("treble-pick", {note["technique"] for note in early})
        self.assertIn("strum-up", {note["technique"] for note in late})
        self.assertIn("strum-muted", {note["technique"] for note in late})
        self.assertTrue(any(note["onset_seconds"] % .5 > .001 for note in late))
        self.assertGreater(min(note["velocity"] for note in late),
                           max(note["velocity"] for note in early))

    def test_audio_groove_detects_quiet_and_loud_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "groove.wav"
            rate = 22050
            samples = np.zeros(rate * 8, dtype=np.float64)
            pulse = np.hanning(round(rate * .05))
            for index in range(16):
                start = round(index * .5 * rate)
                samples[start:start + len(pulse)] += pulse * (.05 if index < 8 else .55)
                if index >= 8:
                    upbeat = start + round(.25 * rate)
                    samples[upbeat:upbeat + len(pulse)] += pulse * .35
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(rate)
                output.writeframes((samples * 28000).astype("<i2").tobytes())
            groove = analyze_groove(path, [i * .5 for i in range(16)], 8)
            self.assertEqual(len(groove), 16)
            self.assertLess(np.mean([item["energy"] for item in groove[:6]]),
                            np.mean([item["energy"] for item in groove[10:]]))
            self.assertTrue(any(item["offbeat"] for item in groove[8:]))


if __name__ == "__main__":
    unittest.main()
