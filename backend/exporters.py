"""Simple MusicXML and MIDI exports from corrected note events."""
from __future__ import annotations

import io
import math
from xml.etree.ElementTree import Element, SubElement, tostring

PITCH_NAMES = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
ALTERS = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]


def _child(parent: Element, tag: str, value: object | None = None, **attrs: str) -> Element:
    node = SubElement(parent, tag, attrs)
    if value is not None:
        node.text = str(value)
    return node


def musicxml(notes: list[dict], tuning: list[int], title: str) -> bytes:
    root = Element("score-partwise", version="4.0")
    _child(_child(root, "work"), "work-title", title)
    _child(root, "movement-title", title)
    part_list = _child(root, "part-list")
    score_part = _child(part_list, "score-part", id="P1")
    _child(score_part, "part-name", "Guitar")
    instrument = _child(score_part, "midi-instrument", id="I1")
    _child(instrument, "midi-channel", 1)
    _child(instrument, "midi-program", 25)
    part = _child(root, "part", id="P1")
    ordered = sorted(notes, key=lambda n: (n["onset_seconds"], n["pitch"]))
    # 120 BPM, 4/4. Onsets are placed on a 16th-note grid; this is intentionally
    # a first-pass rhythm transcription, not a claim of exact meter detection.
    count = max(1, math.ceil(max((n["offset_seconds"] for n in ordered), default=0) / 2))
    for measure_idx in range(count):
        measure = _child(part, "measure", number=str(measure_idx + 1))
        if measure_idx == 0:
            attributes = _child(measure, "attributes")
            _child(attributes, "divisions", 480)
            time = _child(attributes, "time")
            _child(time, "beats", 4)
            _child(time, "beat-type", 4)
            clef = _child(attributes, "clef")
            _child(clef, "sign", "TAB")
            _child(clef, "line", 5)
            details = _child(attributes, "staff-details")
            _child(details, "staff-lines", 6)
            for i, midi in enumerate(tuning):
                staff_tuning = _child(details, "staff-tuning", line=str(6 - i))
                _child(staff_tuning, "tuning-step", PITCH_NAMES[midi % 12])
                if ALTERS[midi % 12]:
                    _child(staff_tuning, "tuning-alter", 1)
                _child(staff_tuning, "tuning-octave", midi // 12 - 1)
        measure_start = measure_idx * 1920
        measure_end = measure_start + 1920
        cursor = measure_start
        entries = [(round(item["onset_seconds"] * 8) * 120, item) for item in ordered]
        entries = [(onset, item) for onset, item in entries if measure_start <= onset < measure_end]
        groups: dict[int, list[dict]] = {}
        for onset, item in entries:
            groups.setdefault(onset, []).append(item)
        for onset, group in sorted(groups.items()):
            if onset > cursor:
                _child(_child(measure, "forward"), "duration", onset - cursor)
            elif onset < cursor:
                _child(_child(measure, "backup"), "duration", cursor - onset)
            length = min(measure_end - onset, max(120, round(max(item["offset_seconds"] - item["onset_seconds"] for item in group) * 8) * 120))
            duration_name = min([120, 240, 360, 480, 720, 960, 1440, 1920], key=lambda value: abs(value - length))
            type_name, dotted = {120: ("16th", False), 240: ("eighth", False), 360: ("eighth", True),
                                 480: ("quarter", False), 720: ("quarter", True), 960: ("half", False),
                                 1440: ("half", True), 1920: ("whole", False)}[duration_name]
            for index, item in enumerate(group):
                note = _child(measure, "note")
                if index:
                    _child(note, "chord")
                midi = int(item["pitch"])
                pitch = _child(note, "pitch")
                _child(pitch, "step", PITCH_NAMES[midi % 12])
                if ALTERS[midi % 12]:
                    _child(pitch, "alter", 1)
                _child(pitch, "octave", midi // 12 - 1)
                _child(note, "duration", duration_name)
                _child(note, "type", type_name)
                if dotted:
                    _child(note, "dot")
                if item.get("string", 0) > 0:
                    technical = _child(_child(note, "notations"), "technical")
                    _child(technical, "string", item["string"])
                    _child(technical, "fret", item["fret"])
            cursor = onset + duration_name
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + tostring(root, encoding="utf-8")


def _vlq(value: int) -> bytes:
    result = [value & 0x7F]
    while value >> 7:
        value >>= 7
        result.insert(0, (value & 0x7F) | 0x80)
    return bytes(result)


def midi(notes: list[dict]) -> bytes:
    events = []
    for note in notes:
        pitch = max(0, min(127, int(note["pitch"])))
        events.append((round(note["onset_seconds"] * 960), bytes([0x90, pitch, 80])))
        events.append((round(note["offset_seconds"] * 960), bytes([0x80, pitch, 0])))
    events.sort(key=lambda e: (e[0], e[1][0]))
    track = io.BytesIO()
    track.write(b"\x00\xff\x51\x03\x07\xa1\x20")
    previous = 0
    for tick, data in events:
        track.write(_vlq(max(0, tick - previous)))
        track.write(data)
        previous = tick
    track.write(b"\x00\xff\x2f\x00")
    content = track.getvalue()
    return b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0" + b"MTrk" + len(content).to_bytes(4, "big") + content
