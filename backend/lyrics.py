"""Transcribe the local vocal stem into timed lyric phrases."""
from __future__ import annotations

from pathlib import Path


def transcribe_lyrics(path: str | Path, model_dir: str | Path) -> list[dict]:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8",
                         download_root=str(model_dir))
    segments, _ = model.transcribe(str(path), beam_size=3, vad_filter=True,
                                   word_timestamps=True, condition_on_previous_text=False)
    return phrases_from_segments(segments)


def phrases_from_segments(segments) -> list[dict]:
    """Keep lyric chunks near the spoken word onsets, including after VAD gaps."""
    phrases = []
    for segment in segments:
        if segment.no_speech_prob >= 0.6:
            continue
        words = [word for word in (segment.words or []) if word.word.strip() and word.start is not None and word.end is not None]
        if not words:
            text = segment.text.strip()
            if text:
                phrases.append({"start_seconds": round(segment.start, 2),
                                "end_seconds": round(segment.end, 2), "text": text})
            continue
        group = []
        for word in words:
            if group and (word.start - group[-1].end > .4 or word.end - group[0].start > 1.8
                          or sum(len(part.word) for part in group) + len(word.word) > 28):
                phrases.append({"start_seconds": round(group[0].start, 2),
                                "end_seconds": round(group[-1].end, 2),
                                "text": "".join(part.word for part in group).strip()})
                group = []
            group.append(word)
        if group:
            phrases.append({"start_seconds": round(group[0].start, 2),
                            "end_seconds": round(group[-1].end, 2),
                            "text": "".join(part.word for part in group).strip()})
    return phrases
