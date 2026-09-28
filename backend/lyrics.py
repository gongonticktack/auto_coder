"""Transcribe the local vocal stem into timed lyric phrases."""
from __future__ import annotations

from pathlib import Path


def transcribe_lyrics(path: str | Path, model_dir: str | Path) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8",
                         download_root=str(model_dir))
    segments, _ = model.transcribe(str(path), beam_size=3, vad_filter=True,
                                   condition_on_previous_text=False)
    phrases = []
    for segment in segments:
        text = segment.text.strip()
        if text and segment.no_speech_prob < 0.6:
            phrases.append({"start_seconds": round(segment.start, 2),
                            "end_seconds": round(segment.end, 2), "text": text})
    return phrases
