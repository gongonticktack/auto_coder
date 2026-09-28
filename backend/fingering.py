"""Small phrase-level constrained search for playable string/fret assignments."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    assignments: list[tuple[int, int]]
    center: float
    cost: float


def assign_fingerings(events: list[dict], tuning: list[int], max_fret: int = 24) -> list[dict]:
    if not events:
        return events
    ordered = sorted(events, key=lambda n: (n["onset_seconds"], n["pitch"]))
    groups: list[list[dict]] = []
    for event in ordered:
        if groups and abs(event["onset_seconds"] - groups[-1][0]["onset_seconds"]) <= 0.045:
            groups[-1].append(event)
        else:
            groups.append([event])

    previous: list[Candidate] = [Candidate([], 3, 0)]
    backtracks: list[list[tuple[Candidate, int]]] = []
    for group in groups:
        placements = _candidate_groups(group, tuning, max_fret)
        if not placements:
            for event in group:
                event["string"] = 0
                event["fret"] = -1
            backtracks.append([(Candidate([(0, -1)] * len(group), 3, 20), 0)])
            previous = [Candidate([(0, -1)] * len(group), 3, 20)]
            continue
        scored: list[tuple[Candidate, int]] = []
        for placement in placements:
            scores = [old.cost + placement.cost + abs(old.center - placement.center) * 0.7 for old in previous]
            best_idx = min(range(len(scores)), key=scores.__getitem__)
            scored.append((Candidate(placement.assignments, placement.center, scores[best_idx]), best_idx))
        scored.sort(key=lambda pair: pair[0].cost)
        backtracks.append(scored[:40])
        previous = [pair[0] for pair in scored[:40]]

    index = min(range(len(previous)), key=lambda i: previous[i].cost)
    for group, choices in zip(reversed(groups), reversed(backtracks)):
        candidate, index = choices[index]
        for event, (string, fret) in zip(group, candidate.assignments):
            event["string"] = string
            event["fret"] = fret
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
            if span > 5:
                return
            center = sum(frets) / len(frets) if frets else 0
            string_jump = sum(abs(picked[i][0] - picked[i - 1][0]) for i in range(1, len(picked)))
            cost = span * 1.6 + center * .08 + string_jump * .15 - sum(fret == 0 for _, fret in picked) * .2
            results.append(Candidate(picked[:], center, cost))
            return
        for position in per_note[idx]:
            if position[0] not in [used[0] for used in picked]:
                visit(idx + 1, picked + [position])

    visit(0, [])
    return sorted(results, key=lambda c: c.cost)[:80]
