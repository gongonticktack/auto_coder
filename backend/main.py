"""Local audio transcription API."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .exporters import midi, musicxml
from .beats import analyze_groove, estimate_beats
from .arrangement import arrange_accompaniment
from .chords import attach_lyrics, suggest_chords
from .lyrics import transcribe_lyrics

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "jobs"
DATA.mkdir(parents=True, exist_ok=True)
TUNINGS = {
    "Standard E": [64, 59, 55, 50, 45, 40],
    "Drop D": [64, 59, 55, 50, 45, 38],
    "Half step down": [63, 58, 54, 49, 44, 39],
    "Open G": [62, 59, 55, 50, 43, 38],
}
MAX_FILE_BYTES = 100 * 1024 * 1024
ALLOWED = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
SEPARATION_STEMS = ("vocals", "bass", "drums", "guitar", "piano", "other")
locks: dict[str, Lock] = {}

app = FastAPI(title="Fretlab API", version="0.1.0")


class NotePatch(BaseModel):
    pitch: int | None = Field(default=None, ge=0, le=127)
    onset_seconds: float | None = Field(default=None, ge=0)
    offset_seconds: float | None = Field(default=None, ge=0)
    string: int | None = Field(default=None, ge=0, le=6)
    fret: int | None = Field(default=None, ge=-1, le=24)
    technique: str | None = Field(default=None, max_length=40)


class NoteCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    pitch: int = Field(ge=0, le=127)
    onset_seconds: float = Field(ge=0)
    offset_seconds: float = Field(ge=0)
    confidence: float = Field(default=1, ge=0, le=1)
    string: int = Field(ge=0, le=6)
    fret: int = Field(ge=-1, le=24)
    technique: str = ""
    source_model: str = "manual"


class ChartEvent(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    time_seconds: float = Field(ge=0)
    chord: str = Field(default="", max_length=40)
    lyric: str = Field(default="", max_length=240)
    frets: list[int] = Field(min_length=6, max_length=6)


class ChartUpdate(BaseModel):
    events: list[ChartEvent] = Field(max_length=2000)


def _directory(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "ジョブが見つかりません。")
    path = DATA / job_id
    if not path.is_dir():
        raise HTTPException(404, "ジョブが見つかりません。")
    return path


def _load(job_id: str) -> dict:
    return json.loads((_directory(job_id) / "job.json").read_text(encoding="utf-8"))


def _save(job: dict) -> None:
    path = _directory(job["id"]) / "job.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _update(job_id: str, **changes: object) -> None:
    with locks[job_id]:
        job = _load(job_id)
        job.update(changes)
        _save(job)


def _run(args: list[str]) -> None:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "コマンドが失敗しました。")[-1200:])


def _ffmpeg_executable() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        executable = shutil.which("ffmpeg")
        if executable:
            return executable
        raise RuntimeError("FFmpeg が見つかりません。start.bat を再実行して依存関係をインストールしてください。")


def _make_backing(directory: Path) -> Path:
    """Mix the non-guitar instrumental stems into a reusable WAV."""
    destination = directory / "backing.wav"
    if destination.exists():
        return destination
    stems = [next(iter((directory / "stems").glob(f"**/{name}.wav")), None)
             for name in ("drums", "bass", "piano", "other")]
    if any(path is None for path in stems):
        raise FileNotFoundError("伴奏用ステムが見つかりません。")
    temporary = directory / "backing.tmp.wav"
    _run([_ffmpeg_executable(), "-y", "-hide_banner", "-loglevel", "error",
          *(item for path in stems for item in ("-i", str(path))),
          "-filter_complex", "[0:a][1:a][2:a][3:a]amix=inputs=4:duration=longest:normalize=0,alimiter=limit=0.95",
          "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(temporary)])
    temporary.replace(destination)
    return destination


def _make_harmony(directory: Path) -> Path:
    """Combine every pitched accompaniment stem, excluding drums and vocals."""
    destination = directory / "harmony.wav"
    if destination.exists():
        return destination
    stems = [next(iter((directory / "stems").glob(f"**/{name}.wav")), None)
             for name in ("bass", "guitar", "piano", "other")]
    if any(path is None for path in stems):
        raise FileNotFoundError("コード推定用の伴奏パートが見つかりません。")
    temporary = directory / "harmony.tmp.wav"
    _run([_ffmpeg_executable(), "-y", "-hide_banner", "-loglevel", "error",
          *(item for path in stems for item in ("-i", str(path))),
          "-filter_complex", "[0:a][1:a][2:a][3:a]amix=inputs=4:duration=longest:normalize=0,alimiter=limit=0.95",
          "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(temporary)])
    temporary.replace(destination)
    return destination


def _process(job_id: str) -> None:
    directory = _directory(job_id)
    job = _load(job_id)
    try:
        ffmpeg = _ffmpeg_executable()
        source = next(directory.glob("source.*"))
        normalized = directory / "normalized.wav"
        _update(job_id, status="running", stage="音源を準備", progress=8)
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        if job["segment_enabled"]:
            command += ["-ss", str(job["start_seconds"])]
        command += ["-i", str(source)]
        if job["segment_enabled"]:
            command += ["-t", str(job["end_seconds"] - job["start_seconds"])]
        # Keep stereo and Demucs's native 44.1 kHz bandwidth during separation.
        # Chord analysis gets its own mono 22.05 kHz conversion below.
        command += ["-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(normalized)]
        _run(command)
        if not normalized.exists() or normalized.stat().st_size < 500:
            raise RuntimeError("解析できる音声がありません。音源と区間指定を確認してください。")
        with wave.open(str(normalized), "rb") as audio_file:
            duration = audio_file.getnframes() / audio_file.getframerate()
        _update(job_id, duration_seconds=duration,
                end_seconds=job["start_seconds"] + duration)
        _update(job_id, stage="和声パートを分離", progress=25, audio_url=f"/api/jobs/{job_id}/audio/original")
        harmony = normalized
        beat_source = normalized
        if os.getenv("FRETLAB_SKIP_DEMUCS") != "1":
            output = directory / "stems"
            _run([sys.executable, "-m", "demucs", "-n", "htdemucs_6s",
                  "--shifts", "2", "--overlap", "0.5", "-o", str(output), str(normalized)])
            harmony = _make_harmony(directory)
            drum_candidates = list(output.glob("**/drums.wav"))
            if drum_candidates:
                beat_source = drum_candidates[0]
            _make_backing(directory)
            _update(job_id, stem_url=f"/api/jobs/{job_id}/audio/guitar",
                    harmony_url=f"/api/jobs/{job_id}/audio/harmony",
                    vocal_url=f"/api/jobs/{job_id}/audio/vocals",
                    backing_url=f"/api/jobs/{job_id}/audio/backing")
            vocal_candidates = list(output.glob("**/vocals.wav"))
            vocals = vocal_candidates[0] if vocal_candidates else normalized
        else:
            vocals = normalized
        _update(job_id, stage="BPM と拍を推定", progress=43)
        try:
            bpm, beat_times = estimate_beats(beat_source, duration)
        except Exception:
            bpm, beat_times = None, []
        if bpm is None and beat_source != normalized:
            try:
                bpm, beat_times = estimate_beats(normalized, duration)
            except Exception:
                pass
        _update(job_id, bpm=bpm, beat_times=beat_times)
        try:
            groove = analyze_groove(normalized, beat_times, duration)
        except Exception:
            groove = []
        _update(job_id, groove=groove)
        _update(job_id, stage="伴奏のコード進行を推定", progress=50)
        harmony_audio = directory / "harmony_input.wav"
        _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(harmony),
              "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(harmony_audio)])
        chart_events = suggest_chords([], job["tuning"], duration, harmony_audio, beat_times=beat_times)
        _update(job_id, stage="弾き語り伴奏を編曲", progress=76)
        notes = arrange_accompaniment(chart_events, job["tuning"], duration, beat_times, bpm, groove)
        _update(job_id, stage="歌詞を認識（初回はモデルを取得）", progress=88)
        lyrics = []
        lyrics_error = None
        try:
            lyrics = transcribe_lyrics(vocals, ROOT / ".runtime" / "whisper")
            chart_events = attach_lyrics(chart_events, lyrics)
        except Exception as exc:
            lyrics_error = str(exc)[:500]
        _update(job_id, stage="譜面を生成", progress=95)
        _update(job_id, notes=notes, chart_events=chart_events, lyrics=lyrics,
                lyrics_error=lyrics_error, status="completed", stage="完了", progress=100)
    except Exception as exc:
        _update(job_id, status="failed", stage="エラー", error=str(exc), progress=0)


def _process_separation(job_id: str) -> None:
    directory = _directory(job_id)
    try:
        ffmpeg = _ffmpeg_executable()
        source = next(directory.glob("source.*"))
        normalized = directory / "normalized.wav"
        _update(job_id, status="running", stage="音源を準備中", progress=5)
        _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
              "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(normalized)])
        if not normalized.exists() or normalized.stat().st_size < 500:
            raise RuntimeError("解析できる音声がありません。")
        _update(job_id, stage="6つのパートを分離中", progress=20)
        output = directory / "stems"
        _run([sys.executable, "-m", "demucs", "-n", "htdemucs_6s",
              "--shifts", "2", "--overlap", "0.5", "-o", str(output), str(normalized)])
        wavs = {}
        for stem in SEPARATION_STEMS:
            candidates = list(output.glob(f"**/{stem}.wav"))
            if not candidates:
                raise RuntimeError(f"{stem} の分離音声が生成されませんでした。")
            wavs[stem] = candidates[0]
        mp3_dir = directory / "mp3"
        mp3_dir.mkdir()
        for index, stem in enumerate(SEPARATION_STEMS):
            _update(job_id, stage=f"{stem} を MP3 に変換中", progress=70 + index * 5)
            destination = mp3_dir / f"{stem}.mp3"
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wavs[stem]),
                  "-codec:a", "libmp3lame", "-b:a", "192k", str(destination)])
            if not destination.exists() or destination.stat().st_size == 0:
                raise RuntimeError(f"{stem} の MP3 を生成できませんでした。")
        _update(job_id, status="completed", stage="完了", progress=100,
                stems={stem: f"/api/separations/{job_id}/stems/{stem}" for stem in SEPARATION_STEMS})
    except Exception as exc:
        _update(job_id, status="failed", stage="エラー", error=str(exc), progress=0)


@app.post("/api/separations", status_code=202)
async def create_separation(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(400, "対応する音声ファイルを選んでください。")
    job_id = uuid4().hex
    directory = DATA / job_id
    directory.mkdir()
    locks[job_id] = Lock()
    size = 0
    try:
        with (directory / f"source{extension}").open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, "音源は 100 MB 以下にしてください。")
                destination.write(chunk)
        if not size:
            raise HTTPException(400, "空のファイルです。")
    except Exception:
        shutil.rmtree(directory)
        locks.pop(job_id, None)
        raise
    job = {"id": job_id, "status": "queued", "stage": "待機中", "progress": 0,
           "error": None, "title": Path(file.filename or "audio").stem[:160], "stems": {}}
    _save(job)
    background_tasks.add_task(_process_separation, job_id)
    return job


@app.get("/api/separations/{job_id}")
def get_separation(job_id: str) -> dict:
    job = _load(job_id)
    if "stems" not in job:
        raise HTTPException(404, "分離ジョブが見つかりません。")
    return job


@app.get("/api/separations/{job_id}/stems/{stem}")
def get_separation_stem(job_id: str, stem: str) -> FileResponse:
    job = get_separation(job_id)
    if stem not in SEPARATION_STEMS or job["status"] != "completed":
        raise HTTPException(404, "分離音声が見つかりません。")
    path = _directory(job_id) / "mp3" / f"{stem}.mp3"
    if not path.is_file():
        raise HTTPException(404, "分離音声が見つかりません。")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/health")
def health() -> dict:
    try:
        ffmpeg = _ffmpeg_executable()
    except RuntimeError:
        ffmpeg = None
    return {"ok": True, "ffmpeg": bool(ffmpeg), "skip_demucs": os.getenv("FRETLAB_SKIP_DEMUCS") == "1"}


@app.post("/api/jobs", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form("Untitled"),
    segment_enabled: bool = Form(False),
    start_seconds: float = Form(0),
    end_seconds: float | None = Form(None),
    tuning: str = Form("Standard E"),
) -> dict:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(400, "対応する音声形式を選んでください。")
    if segment_enabled:
        if (end_seconds is None or not math.isfinite(start_seconds) or
                not math.isfinite(end_seconds) or not 0 <= start_seconds < end_seconds):
            raise HTTPException(400, "開始・終了位置を正しく指定してください。")
    else:
        start_seconds, end_seconds = 0, None
    if tuning not in TUNINGS:
        raise HTTPException(400, "チューニングが無効です。")
    job_id = uuid4().hex
    directory = DATA / job_id
    directory.mkdir()
    locks[job_id] = Lock()
    size = 0
    try:
        with (directory / f"source{extension}").open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, "音源は 100 MB 以下にしてください。")
                destination.write(chunk)
        if not size:
            raise HTTPException(400, "空のファイルです。")
    except Exception:
        shutil.rmtree(directory)
        locks.pop(job_id, None)
        raise
    job = {
        "id": job_id, "status": "queued", "stage": "待機中", "progress": 0, "error": None,
        "title": title[:160] or "Untitled", "duration_seconds": None,
        "segment_enabled": segment_enabled,
        "start_seconds": start_seconds, "end_seconds": end_seconds,
        "tuning": TUNINGS[tuning], "tuning_name": tuning, "part": "弾き語り伴奏", "generation_mode": "accompaniment",
        "notes": [], "bpm": None, "beat_times": [], "groove": [], "audio_url": None, "stem_url": None, "harmony_url": None, "vocal_url": None, "backing_url": None,
        "chart_events": [], "lyrics": [], "lyrics_error": None,
    }
    _save(job)
    background_tasks.add_task(_process, job_id)
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _load(job_id)


@app.get("/api/jobs/{job_id}/audio/{kind}")
def get_audio(job_id: str, kind: str) -> FileResponse:
    directory = _directory(job_id)
    if kind == "original":
        path = directory / "normalized.wav"
    elif kind == "guitar":
        candidates = list((directory / "stems").glob("**/guitar.wav"))
        path = candidates[0] if candidates else directory / "missing.wav"
    elif kind == "harmony":
        path = directory / "harmony.wav"
    elif kind == "vocals":
        candidates = list((directory / "stems").glob("**/vocals.wav"))
        path = candidates[0] if candidates else directory / "missing.wav"
    elif kind == "backing":
        with locks.setdefault(job_id, Lock()):
            try:
                path = _make_backing(directory)
            except FileNotFoundError:
                raise HTTPException(404, "伴奏音声が見つかりません。")
    else:
        raise HTTPException(404, "音声が見つかりません。")
    if not path.exists():
        raise HTTPException(404, "音声が見つかりません。")
    return FileResponse(path, media_type="audio/wav")


def _mutate(job_id: str, operation) -> dict:
    _directory(job_id)
    with locks.setdefault(job_id, Lock()):
        job = _load(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "解析完了後に編集できます。")
        operation(job)
        job["notes"].sort(key=lambda n: (n["onset_seconds"], n["pitch"]))
        _save(job)
        return job


@app.patch("/api/jobs/{job_id}/notes/{note_id}")
def patch_note(job_id: str, note_id: str, patch: NotePatch) -> dict:
    def operation(job: dict) -> None:
        note = next((n for n in job["notes"] if n["id"] == note_id), None)
        if note is None:
            raise HTTPException(404, "音が見つかりません。")
        note.update(patch.model_dump(exclude_none=True))
        if note["offset_seconds"] <= note["onset_seconds"]:
            raise HTTPException(400, "終了位置は開始位置より後にしてください。")
        if note["string"] and note["pitch"] != job["tuning"][note["string"] - 1] + note["fret"]:
            raise HTTPException(400, "弦・フレットと音高が一致しません。")
    return _mutate(job_id, operation)


@app.post("/api/jobs/{job_id}/notes")
def add_note(job_id: str, note: NoteCreate) -> dict:
    def operation(job: dict) -> None:
        if note.offset_seconds <= note.onset_seconds:
            raise HTTPException(400, "終了位置は開始位置より後にしてください。")
        if any(n["id"] == note.id for n in job["notes"]):
            raise HTTPException(409, "同じ ID の音が存在します。")
        if note.string and note.pitch != job["tuning"][note.string - 1] + note.fret:
            raise HTTPException(400, "弦・フレットと音高が一致しません。")
        job["notes"].append(note.model_dump())
    return _mutate(job_id, operation)


@app.delete("/api/jobs/{job_id}/notes/{note_id}")
def delete_note(job_id: str, note_id: str) -> dict:
    def operation(job: dict) -> None:
        old_length = len(job["notes"])
        job["notes"] = [note for note in job["notes"] if note["id"] != note_id]
        if len(job["notes"]) == old_length:
            raise HTTPException(404, "音が見つかりません。")
    return _mutate(job_id, operation)


@app.put("/api/jobs/{job_id}/chart")
def update_chart(job_id: str, update: ChartUpdate) -> dict:
    if any(any(fret < -1 or fret > 24 for fret in event.frets) for event in update.events):
        raise HTTPException(400, "フレットは -1（ミュート）から 24 の範囲にしてください。")
    if len({event.id for event in update.events}) != len(update.events):
        raise HTTPException(400, "同じ図の ID が重複しています。")
    def operation(job: dict) -> None:
        duration = job.get("duration_seconds")
        if any(event.time_seconds > duration for event in update.events):
            raise HTTPException(400, "配置時刻が音源の長さを超えています。")
        job["chart_events"] = [event.model_dump() for event in sorted(update.events, key=lambda item: item.time_seconds)]
        if job.get("generation_mode") == "accompaniment":
            job["notes"] = arrange_accompaniment(job["chart_events"], job["tuning"], duration,
                                                   job.get("beat_times"), job.get("bpm"), job.get("groove"))
    return _mutate(job_id, operation)


@app.get("/api/jobs/{job_id}/export/{kind}")
def export(job_id: str, kind: str) -> Response:
    job = _load(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, "解析完了後に書き出せます。")
    if kind == "musicxml":
        data = musicxml(job["notes"], job["tuning"], job["title"], job.get("bpm"))
        media_type = "application/vnd.recordare.musicxml+xml"
        suffix = "musicxml"
    elif kind == "midi":
        data = midi(job["notes"], job.get("bpm"))
        media_type = "audio/midi"
        suffix = "mid"
    else:
        raise HTTPException(404, "書き出し形式が見つかりません。")
    return Response(data, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="fretlab-{job_id[:8]}.{suffix}"'})
