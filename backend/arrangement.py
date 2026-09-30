"""Turn a timed chord progression and groove into a singing-accompaniment TAB."""
from __future__ import annotations

from bisect import bisect_right
from uuid import uuid4


def arrange_accompaniment(chart_events: list[dict], tuning: list[int], duration: float,
                          beat_times: list[float] | None = None, bpm: float | None = None,
                          groove: list[dict] | None = None) -> list[dict]:
    """Choose bass picks, treble picks and strums from phrase energy and attacks."""
    chords = sorted((event for event in chart_events if event.get("chord")),
                    key=lambda event: event["time_seconds"])
    if not chords or duration <= 0:
        return []
    interval = 60 / bpm if bpm and bpm > 0 else .5
    beats = sorted({round(time, 3) for time in (beat_times or []) if 0 <= time < duration})
    if len(beats) < 2:
        beats = [round(i * interval, 3) for i in range(int(duration / interval) + 1)
                 if i * interval < duration]
    starts = [event["time_seconds"] for event in chords]
    groove_by_time = {round(item["time_seconds"], 3): item for item in groove or []}
    # Eighth-note slots in a bar: D - d u - u D (u).  The gaps are as
    # important as the strokes; quiet phrases leave the extra upbeats out.
    schedule: dict[float, tuple[int, int]] = {}
    for index, beat in enumerate(beats):
        period = beats[index + 1] - beat if index + 1 < len(beats) else interval
        if period <= 0:
            continue
        scene = groove_by_time.get(beat, {})
        energy = float(scene.get("energy", .5))
        slot = (index % 4) * 2
        bar = index // 4
        # A quieter bar has a downbeat, a small answer on 2, and an upbeat
        # before 4.  Busier bars gain the conventional 2-and / 4-and.
        if slot == 0 or slot == 2 or slot == 6 and energy >= .28:
            schedule[beat] = (index, slot)
        if slot == 4 and energy < .28 and bar % 2:
            schedule[beat] = (index, slot)
        upbeat = (slot == 4 and energy < .28 or slot == 4 and energy >= .28
                  or slot == 2 and energy >= .55
                  or slot == 6 and energy >= .72 and bool(scene.get("offbeat")))
        if upbeat:
            time = round(beat + period / 2, 3)
            if time < duration and (index + 1 >= len(beats) or time < beats[index + 1]):
                schedule[time] = (index, slot + 1)
    # A chord entering between beats must sound at its actual change time.
    for chord in chords:
        time = round(chord["time_seconds"], 3)
        if 0 <= time < duration and chord["chord"] != "N.C." and time not in schedule:
            index = max(0, bisect_right(beats, time) - 1)
            # Do not flam a newly changed chord against a nearby pattern hit.
            for nearby in list(schedule):
                if abs(nearby - time) < min(.09, interval * .18):
                    del schedule[nearby]
            schedule[time] = (index, (index % 4) * 2)

    notes: list[dict] = []
    ordered_times = sorted(schedule)
    for position, time in enumerate(ordered_times):
        beat_index, slot = schedule[time]
        chord_index = bisect_right(starts, time + .001) - 1
        if chord_index < 0:
            continue
        chord = chords[chord_index]
        if chord["chord"] == "N.C.":
            continue
        played = [(string, fret) for string, fret in enumerate(chord["frets"])
                  if 0 <= fret <= 24]
        if not played:
            continue
        scene = groove_by_time.get(beats[beat_index], {})
        energy = float(scene.get("energy", .5))
        change = abs(time - chord["time_seconds"]) < .003
        if change:
            technique, velocity = "strum-down", round(72 + energy * 20)
        elif energy < .28:
            technique = "strum-up" if slot == 5 else "treble-pick" if slot == 2 else "bass-pick"
            velocity = round((43 if slot == 5 else 38) + energy * 20)
        elif slot % 2:
            technique = "strum-muted" if slot == 3 and energy >= .72 and groove_by_time.get(beats[beat_index], {}).get("offbeat") else "strum-up"
            velocity = round(45 + energy * 18)
        elif slot == 2:
            technique, velocity = "treble-pick" if energy < .55 else "strum-down", round(48 + energy * 19)
        else:
            technique, velocity = "strum-down", round((65 if slot == 0 else 55) + energy * 19)
        if technique == "bass-pick":
            selected = played[:1]
        elif technique == "treble-pick":
            selected = played[-2:]
        elif technique == "strum-muted":
            selected = played[-3:]
        elif technique == "strum-up":
            selected = played[-4:]
        elif slot != 0 and not change:
            selected = played[1:]
        else:
            selected = played
        next_time = ordered_times[position + 1] if position + 1 < len(ordered_times) else duration
        next_chord = starts[chord_index + 1] if chord_index + 1 < len(chords) else duration
        nominal = .16 if technique == "strum-muted" else min(interval * .78, .7)
        end = min(duration, time + nominal, next_time, next_chord)
        if end <= time + .05:
            continue
        for string, fret in selected:
            notes.append({
                "id": uuid4().hex, "pitch": tuning[5 - string] + fret,
                "onset_seconds": time, "offset_seconds": round(end, 3),
                "confidence": 1.0, "string": 6 - string, "fret": fret,
                "technique": technique, "velocity": velocity,
                "source_model": "chord-arrangement",
            })
    return notes
