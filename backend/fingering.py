"""Small phrase-level constrained search for playable string/fret assignments."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    assignments: list[tuple[int, int]]
    center: float
    cost: float
    occupied_until: tuple[float, ...]


def assign_fingerings(events: list[dict], tuning: list[int], max_fret: int = 20) -> list[dict]:
    if not events:
        return events
    ordered = sorted(events, key=lambda n: (n["onset_seconds"], n["pitch"]))
    groups: list[list[dict]] = []
    for event in ordered:
        if groups and abs(event["onset_seconds"] - groups[-1][0]["onset_seconds"]) <= 0.045:
            groups[-1].append(event)
        else:
            groups.append([event])
    for group in groups:
        if len(group) > 6:
            kept = set(id(note) for note in sorted(group, key=lambda note: note["confidence"], reverse=True)[:6])
            for note in group:
                if id(note) not in kept:
                    note["string"], note["fret"] = 0, -1
            group[:] = [note for note in group if id(note) in kept]

    previous: list[Candidate] = [Candidate([], 3, 0, (0.0,) * 6)]
    backtracks: list[list[tuple[Candidate, int]]] = []
    for group in groups:
        placements = _candidate_groups(group, tuning, max_fret)
        while not placements and len(group) > 1:
            omitted = min(group, key=lambda note: note["confidence"])
            omitted["string"], omitted["fret"] = 0, -1
            group.remove(omitted)
            placements = _candidate_groups(group, tuning, max_fret)
        if not placements:
            for event in group:
                event["string"] = 0
                event["fret"] = -1
            scored = [(Candidate([(0, -1)] * len(group), old.center, old.cost + 20,
                                 old.occupied_until), index) for index, old in enumerate(previous)]
            backtracks.append(scored)
            previous = [pair[0] for pair in scored]
            continue
        scored: list[tuple[Candidate, int]] = []
        for placement in placements:
            onset = group[0]["onset_seconds"]
            scores = [old.cost + placement.cost + abs(old.center - placement.center) * 1.1 +
                      sum(min(1, max(0, old.occupied_until[string - 1] - onset)) * 4
                          for string, _ in placement.assignments) for old in previous]
            best_idx = min(range(len(scores)), key=scores.__getitem__)
            occupied = list(previous[best_idx].occupied_until)
            for event, (string, _) in zip(group, placement.assignments):
                occupied[string - 1] = event["offset_seconds"]
            scored.append((Candidate(placement.assignments, placement.center,
                                     scores[best_idx], tuple(occupied)), best_idx))
        scored.sort(key=lambda pair: pair[0].cost)
        backtracks.append(scored[:40])
        previous = [pair[0] for pair in scored[:40]]

    index = min(range(len(previous)), key=lambda i: previous[i].cost)
    for group, choices in zip(reversed(groups), reversed(backtracks)):
        candidate, index = choices[index]
        for event, (string, fret) in zip(group, candidate.assignments):
            event["string"] = string
            event["fret"] = fret
    for string in range(1, 7):
        played = sorted((note for note in ordered if note.get("string") == string),
                        key=lambda note: note["onset_seconds"])
        for earlier, later in zip(played, played[1:]):
            if earlier["offset_seconds"] > later["onset_seconds"]:
                if later["onset_seconds"] - earlier["onset_seconds"] < .08:
                    earlier["string"], earlier["fret"] = 0, -1
                else:
                    earlier["offset_seconds"] = later["onset_seconds"]
    active: list[dict] = []
    for note in ordered:
        if not note.get("string"):
            continue
        onset = note["onset_seconds"]
        active = [held for held in active if held["offset_seconds"] > onset and held.get("string")]
        while True:
            frets = [held["fret"] for held in [*active, note] if held["fret"] > 0]
            if not frets or max(frets) - min(frets) <= 4:
                break
            older = [held for held in active if held["onset_seconds"] < onset - .045]
            if not older:
                note["string"], note["fret"] = 0, -1
                break
            released = min(older, key=lambda held: (held["onset_seconds"], held["confidence"]))
            if onset - released["onset_seconds"] < .08:
                released["string"], released["fret"] = 0, -1
            else:
                released["offset_seconds"] = onset
            active.remove(released)
        if note["string"]:
            active.append(note)
    return ordered


def _candidate_groups(group: list[dict], tuning: list[int], max_fret: int) -> list[Candidate]:
    per_note = []
    for note in group:
        positions = [(string + 1, note["pitch"] - open_pitch) for string, open_pitch in enumerate(tuning)]
        positions = [(string, fret) for string, fret in positions if 0 <= fret <= max_fret]
        if not positions:
            return []
        per_note.append(positions)
    results: list[Candidate] = []

    def visit(idx: int, picked: list[tuple[int, int]]) -> None:
        if idx == len(per_note):
            frets = [fret for _, fret in picked if fret > 0]
            span = max(frets) - min(frets) if frets else 0
            if span > 4:
                return
            center = sum(frets) / len(frets) if frets else 0
            string_jump = sum(abs(picked[i][0] - picked[i - 1][0]) for i in range(1, len(picked)))
            cost = span * 1.8 + center * .16 + string_jump * .15 - sum(fret == 0 for _, fret in picked) * .25
            results.append(Candidate(picked[:], center, cost, (0.0,) * 6))
            return
        for position in per_note[idx]:
            if position[0] not in [used[0] for used in picked]:
                visit(idx + 1, picked + [position])

    visit(0, [])
    return sorted(results, key=lambda c: c.cost)[:80]
