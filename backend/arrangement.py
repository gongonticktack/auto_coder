"""Turn a timed chord progression into a playable singing-accompaniment TAB."""
from __future__ import annotations

from bisect import bisect_right
from uuid import uuid4


def arrange_accompaniment(chart_events: list[dict], tuning: list[int], duration: float,
                          beat_times: list[float] | None = None, bpm: float | None = None) -> list[dict]:
    """Strum the active voicing on each beat, leaving N.C. and lyric-only spans empty."""
    chords = sorted((event for event in chart_events if event.get("chord")),
                    key=lambda event: event["time_seconds"])
    if not chords or duration <= 0:
        return []
    interval = 60 / bpm if bpm and bpm > 0 else .5
    beats = sorted({round(time, 3) for time in (beat_times or []) if 0 <= time < duration})
    if len(beats) < 2:
        beats = [round(i * interval, 3) for i in range(int(duration / interval) + 1)
                 if i * interval < duration]
    # Always play a newly entered chord, including an opening pickup before beat one.
    times = sorted({*beats, *(round(event["time_seconds"], 3) for event in chords
                              if 0 <= event["time_seconds"] < duration and event["chord"] != "N.C.")})
    starts = [event["time_seconds"] for event in chords]
    notes: list[dict] = []
    for index, time in enumerate(times):
        chord_index = bisect_right(starts, time + .001) - 1
        if chord_index < 0:
            continue
        chord = chords[chord_index]
        if chord["chord"] == "N.C.":
            continue
        frets = chord["frets"]
        played = [(string, fret) for string, fret in enumerate(frets) if 0 <= fret <= 24]
        if not played:
            continue
        # Strong beats use a downstroke; intervening beats use a lighter upstroke.
        direction = "strum-down" if index % 2 == 0 else "strum-up"
        end = min(duration, time + min(interval * .8, .7))
        if chord_index + 1 < len(chords):
            end = min(end, chords[chord_index + 1]["time_seconds"])
        if end <= time + .05:
            continue
        for string, fret in played:
            notes.append({
                "id": uuid4().hex, "pitch": tuning[5 - string] + fret,
                "onset_seconds": time, "offset_seconds": round(end, 3),
                "confidence": 1.0, "string": 6 - string, "fret": fret,
                "technique": direction, "source_model": "chord-arrangement",
            })
    return notes
