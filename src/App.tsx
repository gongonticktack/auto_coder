import { useEffect, useRef, useState } from 'react'
import { Activity, ArrowDownToLine, ArrowRight, AudioLines, Check, ChevronDown, CircleHelp, Clock3, CloudUpload, FileAudio, FileMusic, FileUp, Guitar, Headphones, LayoutGrid, LoaderCircle, MoreHorizontal, Music2, Pause, Play, Plus, RotateCcw, Settings2, SlidersHorizontal, Sparkles, Trash2, WandSparkles, Waves, X } from 'lucide-react'
import type { ChartEvent, Job, Note } from './types'
import { pitchName, TUNINGS, TUNING_LABELS } from './types'
import { ChartEditor, ChordSheet, shapeFor } from './ChordChart'

const demoNotes: Note[] = [
  [0, .44, 64, 1, 0], [.5, .92, 67, 1, 3], [1, 1.45, 69, 1, 5], [1.5, 1.94, 67, 1, 3],
  [2, 2.45, 64, 1, 0], [2.5, 2.94, 62, 2, 3], [3, 3.43, 59, 2, 0], [3.5, 3.94, 62, 2, 3],
  [4, 4.45, 64, 1, 0], [4.5, 4.95, 67, 1, 3], [5, 5.45, 69, 1, 5], [5.5, 5.95, 71, 1, 7],
  [6, 6.45, 69, 1, 5], [6.5, 6.95, 67, 1, 3], [7, 7.45, 64, 1, 0], [7.5, 7.95, 62, 2, 3],
  [8, 8.45, 59, 2, 0], [8.5, 8.95, 62, 2, 3], [9, 9.45, 64, 1, 0], [9.5, 9.95, 67, 1, 3],
  [10, 10.45, 64, 1, 0], [10.5, 10.95, 62, 2, 3], [11, 11.45, 59, 2, 0], [11.5, 11.95, 55, 3, 0],
].map(([onset, offset, pitch, string, fret], i) => ({
  id: `demo-${i}`, onset_seconds: onset, offset_seconds: offset, pitch, string, fret,
  confidence: .92 - (i % 7) * .035, technique: '', source_model: 'demo',
}))

const demoChart: ChartEvent[] = [
  [0, 'G', '夜の風に'], [1.5, 'G/B', '耳をすませ'], [3, 'C', '街を抜け'],
  [4.5, 'D', '走りだす'], [6, 'Em', '小さな光'], [7.5, 'C', '見つけたら'],
  [9, 'A7', '新しい朝へ'], [10.5, 'D7', 'つなげよう'],
].map(([time, chord, lyric], index) => ({ id: `demo-chart-${index}`, time_seconds: Number(time), chord: String(chord), lyric: String(lyric), frets: shapeFor(String(chord)) }))

const demoJob: Job = {
  id: 'demo', status: 'completed', stage: '完了', progress: 100, error: null,
  title: 'Midnight Drive — Lead Guitar', duration_seconds: 12, start_seconds: 0, end_seconds: 12,
  tuning: TUNINGS['Standard E'], notes: demoNotes, chart_events: demoChart, audio_url: null, stem_url: null,
}

const stages = ['音源を準備', 'ギターとボーカルを分離', '音符を推定', 'コードを推定', '歌詞を認識', '譜面を生成']
const bars = Array.from({ length: 88 }, (_, i) => {
  const shape = Math.abs(Math.sin(i * 1.913) * Math.cos(i * .371) + Math.sin(i * .73) * .35)
  return Math.round(12 + Math.min(1, shape) * 38)
})

function formatTime(value: number) {
  return `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60).toString().padStart(2, '0')}`
}

function download(data: BlobPart, type: string, name: string) {
  const url = URL.createObjectURL(new Blob([data], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 500)
}

function App() {
  const [job, setJob] = useState<Job>(demoJob)
  const [file, setFile] = useState<File | null>(null)
  const [localAudio, setLocalAudio] = useState<string | null>(null)
  const [segmentEnabled, setSegmentEnabled] = useState(false)
  const [sourceDuration, setSourceDuration] = useState<number | null>(null)
  const [tuningName, setTuningName] = useState('Standard E')
  const [part, setPart] = useState('Lead guitar')
  const [start, setStart] = useState(0)
  const [end, setEnd] = useState(30)
  const [activeTab, setActiveTab] = useState<'tab' | 'notes' | 'chart'>('chart')
  const [chartRevision, setChartRevision] = useState(0)
  const [audioMode, setAudioMode] = useState<'original' | 'guitar'>('original')
  const [selectedId, setSelectedId] = useState<string | null>(demoNotes[2].id)
  const [playing, setPlaying] = useState(false)
  const [playhead, setPlayhead] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const [showScore, setShowScore] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const audioContext = useRef<AudioContext | null>(null)
  const notes = job.notes
  const selected = notes.find(n => n.id === selectedId) || null
  const duration = job.duration_seconds ?? (segmentEnabled ? end - start : sourceDuration || 12)
  const measureCount = Math.max(6, Math.ceil(duration / 2))
  const tabLength = measureCount * 2
  const jobTuningName = Object.keys(TUNINGS).find(name => TUNINGS[name].every((value, i) => value === job.tuning[i])) || 'Standard E'
  const isDemo = job.id === 'demo'
  const isWorking = job.status === 'queued' || job.status === 'running'
  const toneTimer = useRef<number | null>(null)

  useEffect(() => {
    if (!localAudio) return
    return () => URL.revokeObjectURL(localAudio)
  }, [localAudio])

  useEffect(() => {
    if (!isWorking || isDemo) return
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/jobs/${job.id}`)
        if (!response.ok) throw new Error('ジョブの状態を取得できませんでした。')
        const updated = await response.json() as Job
        setJob(updated)
        if (updated.status === 'completed') {
          setSelectedId(updated.notes[0]?.id || null)
          setPlayhead(0)
          setMessage(updated.lyrics_error
            ? `TAB とコードが完成しました。歌詞の認識は失敗しました: ${updated.lyrics_error}`
            : updated.lyrics?.length
              ? 'TAB、コード、歌詞の候補が完成しました。音を聴きながら修正できます。'
              : 'TAB とコードが完成しました。歌詞は検出されませんでした。')
        }
      } catch (error) { setMessage((error as Error).message) }
    }, 1500)
    return () => clearInterval(timer)
  }, [job.id, isWorking, isDemo])

  useEffect(() => {
    if (!playing) return
    const tick = setInterval(() => {
      if (audioRef.current && !isDemo && (job.audio_url || localAudio)) {
        setPlayhead(audioRef.current.currentTime)
      } else {
        setPlayhead(value => {
          if (value >= duration) { setPlaying(false); return 0 }
          return Math.min(duration, value + .05)
        })
      }
    }, 50)
    return () => clearInterval(tick)
  }, [playing, duration, localAudio, job.audio_url, isDemo])

  useEffect(() => {
    if (!playing || !isDemo) return
    const note = notes.find(n => playhead >= n.onset_seconds && playhead < n.onset_seconds + .06)
    if (!note || toneTimer.current === Math.floor(note.onset_seconds * 10)) return
    toneTimer.current = Math.floor(note.onset_seconds * 10)
    const context = audioContext.current || new AudioContext()
    audioContext.current = context
    const osc = context.createOscillator()
    const gain = context.createGain()
    osc.type = 'triangle'
    osc.frequency.value = 440 * Math.pow(2, (note.pitch - 69) / 12)
    gain.gain.setValueAtTime(.0001, context.currentTime)
    gain.gain.exponentialRampToValueAtTime(.095, context.currentTime + .012)
    gain.gain.exponentialRampToValueAtTime(.0001, context.currentTime + .32)
    osc.connect(gain).connect(context.destination)
    osc.start()
    osc.stop(context.currentTime + .34)
  }, [playhead, playing, isDemo, notes])

  function chooseFile(chosen: File | null) {
    if (!chosen) return
    if (!chosen.type.startsWith('audio/') && !/\.(wav|mp3|m4a|flac|ogg|aac)$/i.test(chosen.name)) {
      setMessage('音声ファイルを選んでください（WAV、MP3、M4A、FLAC など）。')
      return
    }
    setFile(chosen)
    setSourceDuration(null)
    setLocalAudio(URL.createObjectURL(chosen))
    setMessage(null)
  }

  async function startJob() {
    if (!file) { fileInput.current?.click(); return }
    if (segmentEnabled && (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start)) {
      setMessage('開始・終了位置を正しく指定してください。'); return
    }
    setSubmitting(true)
    setMessage(null)
    const form = new FormData()
    form.append('file', file)
    form.append('title', file.name.replace(/\.[^.]+$/, ''))
    if (segmentEnabled) {
      form.append('segment_enabled', 'true')
      form.append('start_seconds', String(start))
      form.append('end_seconds', String(end))
    }
    form.append('tuning', tuningName)
    form.append('part', part)
    try {
      const response = await fetch('/api/jobs', { method: 'POST', body: form })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || '解析を開始できませんでした。')
      setJob(body as Job)
      setSelectedId(null)
      setPlayhead(0)
    } catch (error) {
      setMessage(`API に接続できません。${(error as Error).message} README の手順でサーバーを起動してください。`)
    } finally { setSubmitting(false) }
  }

  async function updateNote(changes: Partial<Note>) {
    if (!selected) return
    const updated = notes.map(n => n.id === selected.id ? { ...n, ...changes } : n)
    setJob(current => ({ ...current, notes: updated }))
    if (!isDemo) {
      try {
        const response = await fetch(`/api/jobs/${job.id}/notes/${selected.id}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
        })
        if (!response.ok) throw new Error('変更を保存できませんでした。')
      } catch (error) { setMessage((error as Error).message) }
    }
  }

  async function deleteNote() {
    if (!selected) return
    const id = selected.id
    setJob(current => ({ ...current, notes: current.notes.filter(n => n.id !== id) }))
    setSelectedId(null)
    if (!isDemo) {
      const response = await fetch(`/api/jobs/${job.id}/notes/${id}`, { method: 'DELETE' })
      if (!response.ok) setMessage('ノートの削除を保存できませんでした。')
    }
  }

  async function addNote() {
    const onset = Math.min(duration - .5, Math.floor(playhead * 2) / 2)
    const note: Note = { id: crypto.randomUUID(), pitch: job.tuning[0], onset_seconds: onset,
      offset_seconds: Math.min(duration, onset + .5), confidence: 1, string: 1, fret: 0,
      technique: '', source_model: 'manual' }
    setJob(current => ({ ...current, notes: [...current.notes, note].sort((a, b) => a.onset_seconds - b.onset_seconds) }))
    setSelectedId(note.id)
    if (!isDemo) {
      const response = await fetch(`/api/jobs/${job.id}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(note) })
      if (!response.ok) setMessage('ノートの追加を保存できませんでした。')
    }
  }

  async function saveChart(events: ChartEvent[]) {
    if (!isDemo) {
      const response = await fetch(`/api/jobs/${job.id}/chart`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ events }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(typeof body.detail === 'string' ? body.detail : '歌詞とコードを保存できませんでした。')
      }
    }
    setJob(current => ({ ...current, chart_events: events }))
    setMessage('歌詞とコード図を保存しました。')
  }

  function togglePlay() {
    if (playing) { audioRef.current?.pause(); setPlaying(false); return }
    if (playhead >= duration) setPlayhead(0)
    if (audioRef.current && !isDemo && (job.audio_url || localAudio)) {
      audioRef.current.currentTime = playhead
      void audioRef.current.play().catch(() => setMessage('音声を再生できませんでした。'))
    }
    setPlaying(true)
  }

  async function exportFile(type: 'musicxml' | 'midi') {
    if (isDemo) {
      if (type === 'musicxml') download(createMusicXml(notes, job.tuning, job.title), 'application/vnd.recordare.musicxml+xml', 'fretlab-demo.musicxml')
      else download(createMidi(notes), 'audio/midi', 'fretlab-demo.mid')
      return
    }
    try {
      const response = await fetch(`/api/jobs/${job.id}/export/${type}`)
      if (!response.ok) throw new Error('書き出しに失敗しました。')
      download(await response.blob(), type === 'midi' ? 'audio/midi' : 'application/vnd.recordare.musicxml+xml', `${job.title}.${type === 'midi' ? 'mid' : 'musicxml'}`)
    } catch (error) { setMessage((error as Error).message) }
  }

  function resetDemo() {
    setJob(demoJob)
    setChartRevision(value => value + 1)
    setActiveTab('chart')
    setSelectedId(demoNotes[2].id)
    setPlayhead(0)
    setPlaying(false)
    setMessage('デモセッションを開きました。')
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><Activity size={23} strokeWidth={2.4} /></div><span>fret<span className="brand-accent">lab</span><sup> BETA</sup></span></div>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="sidebar-nav">
        <button className="nav-item active"><LayoutGrid size={18} /> Studio <span className="active-dot" /></button>
        <button className="nav-item" onClick={resetDemo}><Music2 size={18} /> Demo session</button>
        <button className="nav-item" onClick={() => document.getElementById('new-project')?.scrollIntoView({ behavior: 'smooth' })}><FileUp size={18} /> New transcription</button>
      </nav>
      <div className="sidebar-section-label recent-label">YOUR SESSIONS <button title="新しいセッション" onClick={() => document.getElementById('new-project')?.scrollIntoView({ behavior: 'smooth' })}><Plus size={16} /></button></div>
      <button className="recent-item" onClick={resetDemo}><span className="recent-icon"><AudioLines size={17} /></span><span><strong>Midnight Drive</strong><small>Demo · Lead guitar</small></span><span className="recent-indicator" /></button>
      {!isDemo && <button className="recent-item current"><span className="recent-icon"><FileAudio size={17} /></span><span><strong>{job.title}</strong><small>{job.status === 'completed' ? 'Ready to edit' : job.stage}</small></span></button>}
      <div className="sidebar-bottom"><div className="tip-card"><div className="tip-icon"><Sparkles size={17} /></div><strong>Make it yours.</strong><p>自動生成した TAB を、耳で確かめながら仕上げましょう。</p><span>弦・フレットを直接編集 <ArrowRight size={13} /></span></div><div className="sidebar-footer"><CircleHelp size={16} /> About fretlab <span>v0.1</span></div></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <strong>Studio</strong></div><div className="top-actions"><span className="system-status"><span /> LOCAL STUDIO</span><button className="avatar" title="Fretlab">F</button></div></header>
      <div className="content">
        <div className="page-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR CREATIVE WORKSPACE</div><h1>Turn sound into <em>something playable.</em></h1><p>音を聴いて、弾ける形に。ギターのためのスマートな TAB スタジオ。</p></div><div className="intro-art" aria-hidden="true"><div className="orbit orbit-1"/><div className="orbit orbit-2"/><div className="orb"><Activity size={43} strokeWidth={1.15}/></div><span className="art-star one">✦</span><span className="art-star two">✦</span></div></div>

        <section className="create-panel" id="new-project"><div className="panel-heading"><div className="heading-icon"><WandSparkles size={18}/></div><div><h2>新しい TAB を作成</h2><p>音源を追加して、解析したいパートを設定します</p></div><span className="step-pill">01 / SETUP</span></div>
          <div className="source-grid"><div className={`upload-zone ${file ? 'has-file' : ''}`} onClick={() => fileInput.current?.click()} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]) }} role="button" tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') fileInput.current?.click() }}><input ref={fileInput} type="file" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg,.aac" hidden onChange={event => chooseFile(event.target.files?.[0] || null)}/><span className="upload-icon">{file ? <FileAudio size={23}/> : <CloudUpload size={23}/>}</span><div><strong>{file ? file.name : '音源ファイルをドロップ'}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · クリックして変更` : 'またはクリックしてファイルを選択'}</span></div><small>WAV, MP3, M4A, FLAC · 最大 100 MB · 全体を解析</small></div></div>
          <div className="segment-options"><label className="segment-toggle"><input type="checkbox" checked={segmentEnabled} onChange={event => setSegmentEnabled(event.target.checked)}/>指定した区間だけ生成</label>{segmentEnabled && <div className="segment-range"><label>開始（秒）<input type="number" min="0" step="0.1" value={start} onChange={event => setStart(Number(event.target.value))}/></label><span>—</span><label>終了（秒）<input type="number" min="0.1" step="0.1" value={end} onChange={event => setEnd(Number(event.target.value))}/></label></div>}</div>
          <div className="setup-row"><div className="field"><label>GUITAR PART</label><div className="select-wrap"><Guitar size={17}/><select value={part} onChange={event => setPart(event.target.value)}><option>Lead guitar</option><option>Rhythm guitar</option><option>Single guitar</option></select><ChevronDown size={15}/></div></div><div className="field"><label>TUNING</label><div className="select-wrap"><Settings2 size={17}/><select value={tuningName} onChange={event => setTuningName(event.target.value)}>{Object.keys(TUNINGS).map(name => <option key={name}>{name}</option>)}</select><ChevronDown size={15}/></div></div><button className="generate-button" onClick={startJob} disabled={submitting || isWorking}>{submitting || isWorking ? <LoaderCircle className="spin" size={18}/> : <Sparkles size={18}/>} {isWorking ? '解析中...' : 'Generate TAB'} <ArrowRight size={17}/></button></div>
        </section>

        {message && <div className="message-bar"><span>{message}</span><button onClick={() => setMessage(null)} aria-label="閉じる"><X size={16}/></button></div>}

        <div className="section-title"><div><span className="tiny-spark">✦</span><h2>Studio session</h2><span className="session-count">01</span></div><button className="text-button" onClick={resetDemo}><RotateCcw size={15}/> Demo を開く</button></div>

        <section className="session-card"><div className="session-top"><div className="album-art"><div className="album-wave"><AudioLines size={34}/></div></div><div className="session-meta"><div className="session-overline">{isDemo ? 'DEMO SESSION' : 'YOUR TRANSCRIPTION'} <span className={`status-chip ${isWorking ? 'working' : job.status === 'failed' ? 'failed' : ''}`}>{job.status === 'completed' ? <Check size={11}/> : isWorking ? <LoaderCircle size={11} className="spin"/> : <X size={11}/>} {job.status === 'completed' ? 'READY TO EDIT' : job.status === 'failed' ? 'FAILED' : 'PROCESSING'}</span></div><h3>{job.title}</h3><div className="session-details"><span><Clock3 size={14}/> {formatTime(duration)}</span><i/><span><Guitar size={14}/> {isDemo ? 'Lead guitar' : job.part || part}</span><i/><span>{jobTuningName}</span></div></div><div className="session-actions"><button className="ghost-button" onClick={() => exportFile('musicxml')} disabled={job.status !== 'completed'}><ArrowDownToLine size={16}/> MusicXML</button><button className="square-button" onClick={() => exportFile('midi')} disabled={job.status !== 'completed'} title="MIDI をダウンロード"><MoreHorizontal size={20}/></button></div></div>
          {job.status === 'failed' && <div className="error-state">{job.error || '解析できませんでした。'}</div>}
          {isWorking && <div className="progress-panel"><div className="progress-copy"><span><LoaderCircle size={16} className="spin"/> {job.stage}</span><strong>{job.progress}%</strong></div><div className="progress-track"><span style={{width: `${job.progress}%`}}/></div><div className="stage-list">{stages.map((stage, i) => <span key={stage} className={job.progress >= [8, 25, 50, 78, 88, 95][i] ? 'done' : ''}>{stage}</span>)}</div></div>}
          {job.status === 'completed' && <><div className="waveform-panel"><div className="waveform-top"><div><Waves size={16}/> AUDIO WAVEFORM <span>·</span> {audioMode === 'original' ? 'ORIGINAL' : 'GUITAR STEM'}</div><div className="audio-toggle"><button className={audioMode === 'original' ? 'selected' : ''} onClick={() => setAudioMode('original')}>Original</button><button className={audioMode === 'guitar' ? 'selected' : ''} onClick={() => setAudioMode('guitar')} disabled={!job.stem_url}>Guitar stem</button></div></div><div className="waveform" onClick={event => { const rect = event.currentTarget.getBoundingClientRect(); const next = Math.max(0, Math.min(duration, (event.clientX - rect.left) / rect.width * duration)); setPlayhead(next); if (audioRef.current) audioRef.current.currentTime = next }} role="slider" aria-label="再生位置" aria-valuemin={0} aria-valuemax={duration} aria-valuenow={playhead} tabIndex={0} onKeyDown={event => { if (event.key === 'ArrowRight') setPlayhead(v => Math.min(duration, v + .5)); if (event.key === 'ArrowLeft') setPlayhead(v => Math.max(0, v - .5)) }}><div className="waveform-bars">{bars.map((height, i) => <span key={i} className={i / bars.length <= playhead / duration ? 'passed' : ''} style={{height}}/>)}</div><div className="wave-playhead" style={{left: `${Math.min(100, playhead / duration * 100)}%`}}><span/></div></div><div className="waveform-times"><span>00:00</span><span>{formatTime(duration / 4)}</span><span>{formatTime(duration / 2)}</span><span>{formatTime(duration * .75)}</span><span>{formatTime(duration)}</span></div></div>
            <div className="transport"><button className="play-button" onClick={togglePlay} aria-label={playing ? '一時停止' : '再生'}>{playing ? <Pause size={18} fill="currentColor"/> : <Play size={18} fill="currentColor"/>}</button><div className="time-display">{formatTime(playhead)} <span>/ {formatTime(duration)}</span></div><div className="transport-divider"/><span className="transport-hint"><Headphones size={15}/> {isDemo ? 'デモ音を再生' : '音源と TAB を聴き比べ'}</span><div className="transport-spacer"/><span className="bpm">♩ 120 BPM</span><span className="meter">4 / 4</span></div></>}
        </section>

        {job.status === 'completed' && <div className="editor-grid"><section className="tab-card"><div className="card-top"><div><h3>Tab editor</h3><p>音を選択して弦・フレットを調整</p></div><div className="editor-actions"><button onClick={addNote} title="再生位置に音を追加"><Plus size={17}/> Add note</button><button onClick={() => setShowScore(true)} title="alphaTab で譜面表示"><FileMusic size={17}/> Score view</button></div></div><div className="tab-toolbar"><div className="view-switch"><button className={activeTab === 'tab' ? 'active' : ''} onClick={() => setActiveTab('tab')}>Tablature</button><button className={activeTab === 'notes' ? 'active' : ''} onClick={() => setActiveTab('notes')}>Note events</button><button className={activeTab === 'chart' ? 'active' : ''} onClick={() => setActiveTab('chart')}>歌詞・コード</button></div><span>MEASURE 01 — {String(measureCount).padStart(2, '0')} <SlidersHorizontal size={15}/></span></div>
          {activeTab === 'tab' ? <div className="tab-scroll"><div className="tab-sheet" style={{minWidth: `${measureCount * 105}px`}}><div className="measure-ruler">{Array.from({length: measureCount}, (_, i) => <span key={i} style={{width: `${100 / measureCount}%`}}>{String(i + 1).padStart(2, '0')}</span>)}</div><div className="tab-lines">{Array.from({length: 6}, (_, row) => <div className="tab-line" key={row}><span className="string-label">{(TUNING_LABELS[jobTuningName] || TUNING_LABELS['Standard E'])[row]}</span><div className="string-track"><div className="line-rule"/><div className="measure-lines">{Array.from({length: measureCount + 1}, (_, n) => <i key={n}/>)}</div>{notes.filter(note => note.string === row + 1 && note.onset_seconds <= tabLength).map(note => <button key={note.id} className={`fret-note ${selectedId === note.id ? 'selected' : ''} ${playhead >= note.onset_seconds && playhead < note.offset_seconds ? 'sounding' : ''}`} style={{left: `${note.onset_seconds / tabLength * 100}%`}} onClick={() => { setSelectedId(note.id); setPlayhead(note.onset_seconds); if (audioRef.current) audioRef.current.currentTime = note.onset_seconds }} title={`${pitchName(note.pitch)} · ${Math.round(note.confidence * 100)}% confidence`}>{note.fret}</button>)}</div></div>)}</div><div className="beat-ruler">{Array.from({length: measureCount * 4}, (_, i) => <span key={i}>{i % 4 + 1}</span>)}</div></div></div> : activeTab === 'chart' ? <ChartEditor key={`${job.id}-${chartRevision}`} events={job.chart_events || []} title={job.title} playhead={playhead} duration={duration} onSave={saveChart}/> : <div className="note-list"><div className="note-list-head"><span>TIME</span><span>NOTE</span><span>STRING</span><span>FRET</span><span>CONFIDENCE</span></div>{notes.map(note => <button key={note.id} className={`note-row ${selectedId === note.id ? 'selected' : ''}`} onClick={() => { setSelectedId(note.id); setPlayhead(note.onset_seconds) }}><span>{formatTime(note.onset_seconds)}.{Math.round(note.onset_seconds % 1 * 10)}</span><span>{pitchName(note.pitch)}</span><span>{note.string}</span><span>{note.fret}</span><span className="confidence"><i style={{width: `${note.confidence * 100}%`}}/> {Math.round(note.confidence * 100)}%</span></button>)}</div>}
          <div className="editor-footer"><span><span className="legend-dot"/> SELECTED NOTE</span><span>{notes.length} NOTES DETECTED</span></div></section>

          <aside className="inspector"><div className="inspector-head"><div className="inspector-icon"><Settings2 size={18}/></div><div><h3>Note inspector</h3><p>選択中の音を編集</p></div></div>{selected ? <><div className="pitch-card"><div><span>SELECTED NOTE</span><strong>{pitchName(selected.pitch)}</strong><small>{formatTime(selected.onset_seconds)} – {formatTime(selected.offset_seconds)}</small></div><div className="pitch-glyph"><Music2 size={30}/></div></div><div className="inspector-field"><label>STRING <span>{selected.string} / 6</span></label><div className="string-options">{Array.from({length: 6}, (_, i) => { const fret = selected.pitch - job.tuning[i]; return <button key={i} className={selected.string === i + 1 ? 'active' : ''} disabled={fret < 0 || fret > 24} onClick={() => updateNote({string: i + 1, fret})}>{i + 1}</button> })}</div></div><div className="inspector-field"><label>FRET <span>0 – 24</span></label><div className="fret-control"><button onClick={() => { if (selected.fret > 0) updateNote({fret: selected.fret - 1, pitch: selected.pitch - 1}) }}>−</button><strong>{selected.fret.toString().padStart(2, '0')}</strong><button onClick={() => { if (selected.fret < 24) updateNote({fret: selected.fret + 1, pitch: selected.pitch + 1}) }}>+</button></div></div><div className="inspector-field"><label>TECHNIQUE</label><div className="select-wrap technique-select"><select value={selected.technique} onChange={event => updateNote({technique: event.target.value})}><option value="">Normal</option><option value="bend">Bend</option><option value="slide">Slide</option><option value="hammer-on">Hammer-on</option><option value="pull-off">Pull-off</option><option value="mute">Mute</option></select><ChevronDown size={15}/></div></div><div className="confidence-box"><span>MODEL CONFIDENCE</span><strong>{Math.round(selected.confidence * 100)}%</strong><div><i style={{width: `${selected.confidence * 100}%`}}/></div><small>{selected.source_model === 'demo' ? 'デモ用のサンプル値' : selected.source_model}</small></div><button className="delete-note" onClick={deleteNote}><Trash2 size={15}/> この音を削除</button></> : <div className="empty-inspector">TAB 上の音を選択すると、ここで弦・フレットを調整できます。</div>}</aside></div>}

        <div className="bottom-note"><div><span>✳</span> Made for the moments between listening and playing.</div><span>FRETLAB / 2026</span></div>
      </div>
    </main>
    <audio ref={audioRef} src={isDemo ? undefined : audioMode === 'guitar' ? job.stem_url || undefined : job.audio_url || localAudio || undefined} onLoadedMetadata={event => { if (!job.audio_url && Number.isFinite(event.currentTarget.duration)) setSourceDuration(event.currentTarget.duration) }} onEnded={() => { setPlaying(false); setPlayhead(0) }}/>
    {showScore && <ScoreModal notes={notes} tuning={job.tuning} title={job.title} chartEvents={job.chart_events || []} onClose={() => setShowScore(false)}/>}
  </div>
}

function ScoreModal({notes, tuning, title, chartEvents, onClose}: {notes: Note[], tuning: number[], title: string, chartEvents: ChartEvent[], onClose: () => void}) {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let api: {destroy: () => void} | null = null
    let cancelled = false
    import('@coderline/alphatab').then(alphaTab => {
      if (cancelled || !container.current) return
      const settings = new alphaTab.Settings()
      settings.core.fontDirectory = '/alphatab/font/'
      settings.core.useWorkers = false
      settings.display.scale = .9
      const instance = new alphaTab.AlphaTabApi(container.current, settings)
      api = instance
      const sorted = [...notes].filter(n => n.string > 0 && n.fret >= 0).sort((a, b) => a.onset_seconds - b.onset_seconds).slice(0, 64)
      const body = sorted.map(n => `${n.fret}.${n.string}.8`).join(' ')
      const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
      const tuningText = tuning.map(midi => `${names[midi % 12]}${Math.floor(midi / 12) - 1}`).join(' ')
      instance.tex(`\\title "${title.replace(/["\\]/g, '')}" \\track "Guitar" \\staff {tabs} \\tuning (${tuningText}) ${body || 'r.4'}`)
    }).catch(() => setError('譜面ビューを読み込めませんでした。'))
    return () => { cancelled = true; api?.destroy() }
  }, [notes, tuning, title])
  return <div className="modal-backdrop" onClick={onClose}><div className="score-modal" onClick={event => event.stopPropagation()}><div className="modal-head"><div><span>ALPHATAB PREVIEW</span><h2>TAB 譜を確認</h2></div><button onClick={onClose} aria-label="閉じる"><X size={20}/></button></div><p>編集した音の弦・フレットを譜面で確認できます。音価はプレビュー用に均等配置しています。</p><ChordSheet events={chartEvents} title={title}/>{error ? <div className="error-state">{error}</div> : <div className="score-render" ref={container}/>}</div></div>
}

function createMusicXml(notes: Note[], tuning: number[], title: string) {
  const escape = (s: string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c] || c))
  const sorted = [...notes].sort((a,b) => a.onset_seconds - b.onset_seconds)
  const pitch = (midi: number) => { const names = ['C','C','D','D','E','F','F','G','G','A','A','B']; const alters = [0,1,0,1,0,0,1,0,1,0,1,0]; return `<step>${names[midi % 12]}</step>${alters[midi % 12] ? '<alter>1</alter>' : ''}<octave>${Math.floor(midi / 12) - 1}</octave>` }
  const measures = Array.from({length: Math.max(1, Math.ceil((sorted.at(-1)?.onset_seconds || 0) / 2) + 1)}, (_, index) => {
    const entries = sorted.filter(n => Math.floor(n.onset_seconds / 2) === index)
    return `<measure number="${index+1}">${index === 0 ? `<attributes><divisions>480</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>TAB</sign><line>5</line></clef><staff-details><staff-lines>6</staff-lines>${tuning.map((m,i) => `<staff-tuning line="${6-i}"><tuning-step>${['C','C','D','D','E','F','F','G','G','A','A','B'][m%12]}</tuning-step><tuning-octave>${Math.floor(m/12)-1}</tuning-octave></staff-tuning>`).join('')}</staff-details></attributes>` : ''}${entries.map(n => `<note><pitch>${pitch(n.pitch)}</pitch><duration>${Math.max(1, Math.round((n.offset_seconds-n.onset_seconds)*960))}</duration><type>eighth</type><notations><technical><string>${n.string}</string><fret>${n.fret}</fret></technical></notations></note>`).join('')}</measure>`
  }).join('')
  return `<?xml version="1.0" encoding="utf-8"?><!DOCTYPE score-partwise  PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd"><score-partwise version="4.0"><work><work-title>${escape(title)}</work-title></work><movement-title>${escape(title)}</movement-title><defaults><scaling><millimeters>7</millimeters><tenths>40</tenths></scaling></defaults><part-list><score-part id="P1"><part-name>Guitar</part-name><part-abbreviation>Gtr</part-abbreviation><score-instrument id="I1"><instrument-name>Guitar</instrument-name></score-instrument><midi-instrument id="I1"><midi-channel>1</midi-channel><midi-program>25</midi-program></midi-instrument></score-part></part-list><part id="P1">${measures}</part></score-partwise>`
}

function createMidi(notes: Note[]) {
  const variable = (n: number) => { const bytes = [n & 127]; while ((n >>= 7)) bytes.unshift((n & 127) | 128); return bytes }
  const events = notes.flatMap(n => [{tick: Math.round(n.onset_seconds * 960), data: [0x90, n.pitch, 80]}, {tick: Math.round(n.offset_seconds * 960), data: [0x80, n.pitch, 0]}]).sort((a,b) => a.tick - b.tick || a.data[0] - b.data[0])
  const track: number[] = [0, 0xff, 0x51, 3, 0x07, 0xa1, 0x20]
  let last = 0
  for (const event of events) { track.push(...variable(Math.max(0, event.tick-last)), ...event.data); last = event.tick }
  track.push(0, 0xff, 0x2f, 0)
  const size = track.length
  return new Uint8Array([77,84,104,100,0,0,0,6,0,0,0,1,1,224,77,84,114,107,(size>>>24)&255,(size>>>16)&255,(size>>>8)&255,size&255,...track])
}

export default App

