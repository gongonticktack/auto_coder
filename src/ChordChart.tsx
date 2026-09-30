import { useEffect, useRef, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import type { ChartEvent, LyricPhrase } from './types'
import './timeline.css'

const SHAPES: Record<string, number[]> = {
  C: [-1, 3, 2, 0, 1, 0], D: [-1, -1, 0, 2, 3, 2], E: [0, 2, 2, 1, 0, 0],
  F: [1, 3, 3, 2, 1, 1], G: [3, 2, 0, 0, 0, 3], A: [-1, 0, 2, 2, 2, 0],
  B: [-1, 2, 4, 4, 4, 2], Em: [0, 2, 2, 0, 0, 0], Am: [-1, 0, 2, 2, 1, 0],
  Dm: [-1, -1, 0, 2, 3, 1], A7: [-1, 0, 2, 0, 2, 0], D7: [-1, -1, 0, 2, 1, 2],
  Dsus4: [-1, -1, 0, 2, 3, 3], 'G/B': [-1, 2, 0, 0, 0, 3],
  'A/C#': [-1, 4, 2, 2, 2, 0], 'C/E': [0, 3, 2, 0, 1, 0],
  'B/E♭': [-1, 2, 1, 4, 4, 2], 'N.C.': [-1, -1, -1, -1, -1, -1],
}

export function shapeFor(chord: string): number[] {
  return [...(SHAPES[chord.trim()] || [-1, -1, -1, -1, -1, -1])]
}

export function alignLyrics(events: ChartEvent[], phrases: LyricPhrase[] = []): ChartEvent[] {
  if (!phrases.length || events.some(event => !event.chord && event.lyric)) return events
  const oldText = events.map(event => event.lyric).join('').replace(/\s+/g, '')
  const recognizedText = phrases.map(phrase => phrase.text).join('').replace(/\s+/g, '')
  if (oldText && oldText !== recognizedText) return events
  const chords = events.map(event => ({ ...event, lyric: '' }))
  const lyrics = phrases.filter(phrase => phrase.text.trim()).map((phrase, index) => ({
    id: `lyric-${index}-${phrase.start_seconds}`, time_seconds: phrase.start_seconds,
    chord: '', lyric: phrase.text.trim(), frets: [-1, -1, -1, -1, -1, -1],
  }))
  return [...chords, ...lyrics].sort((a, b) => a.time_seconds - b.time_seconds)
}

export function ChordDiagram({ chord, frets }: { chord: string, frets: number[] }) {
  const positive = frets.filter(fret => fret > 0)
  const base = positive.length && Math.max(...positive) > 5 ? Math.min(...positive) : 1
  const xs = [19, 30, 41, 52, 63, 74]
  return <svg className="chord-diagram" viewBox="0 0 94 116" role="img" aria-label={`${chord || 'コードなし'} のコード図`}>
    <text x="47" y="14" textAnchor="middle" className="chord-diagram-name">{chord || 'N.C.'}</text>
    {base > 1 && <text x="3" y="43" className="chord-diagram-base">{base}fr</text>}
    {xs.map((x, index) => <line key={`s${index}`} x1={x} y1="34" x2={x} y2="104" className="chord-string"/>)}
    {[34, 48, 62, 76, 90, 104].map((y, index) => <line key={`f${index}`} x1="19" y1={y} x2="74" y2={y} className={index === 0 && base === 1 ? 'chord-nut' : 'chord-fret'}/>)}
    {frets.map((fret, index) => fret === -1
      ? <text key={index} x={xs[index]} y="30" textAnchor="middle" className="chord-muted">×</text>
      : fret === 0
        ? <circle key={index} cx={xs[index]} cy="26" r="3.2" className="chord-open"/>
        : fret >= base && fret < base + 5
          ? <circle key={index} cx={xs[index]} cy={34 + (fret - base + .5) * 14} r="4" className="chord-dot"/>
          : null)}
  </svg>
}

export function ChordSheet({ events, title, playhead, duration, playing = false }: {
  events: ChartEvent[], title: string, playhead?: number, duration?: number, playing?: boolean,
}) {
  const sorted = [...events].sort((a, b) => a.time_seconds - b.time_seconds)
  const seconds = Math.max(1, duration ?? (sorted.at(-1)?.time_seconds || 0) + 2)
  const pixelsPerSecond = 108
  const width = Math.max(620, seconds * pixelsPerSecond + 130)
  const xFor = (time: number) => 35 + Math.max(0, Math.min(seconds, time)) * pixelsPerSecond
  const viewport = useRef<HTMLDivElement>(null)
  const chordLanes = [-Infinity, -Infinity, -Infinity]
  const lyricLanes = [-Infinity, -Infinity]
  const chordItems = sorted.filter(event => event.chord.trim()).map(event => {
    const x = xFor(event.time_seconds)
    let lane = chordLanes.findIndex(last => x - last >= 104)
    if (lane < 0) lane = chordLanes.indexOf(Math.min(...chordLanes))
    chordLanes[lane] = x
    return { event, x, lane }
  })
  const lyricItems = sorted.filter(event => event.lyric.trim()).map(event => {
    const x = xFor(event.time_seconds)
    const span = Math.max(155, Math.min(320, event.lyric.length * 13))
    let lane = lyricLanes.findIndex(last => x - last >= 10)
    if (lane < 0) lane = lyricLanes.indexOf(Math.min(...lyricLanes))
    lyricLanes[lane] = x + span
    return { event, x, lane, span }
  })
  useEffect(() => {
    if (!playing || playhead === undefined || !viewport.current) return
    const view = viewport.current
    const x = xFor(playhead)
    if (x > view.scrollLeft + view.clientWidth * .8 || x < view.scrollLeft + view.clientWidth * .2) {
      view.scrollLeft = Math.max(0, x - view.clientWidth * .35)
    }
  }, [playhead, playing, seconds])
  return <div className="chord-sheet">
    <div className="chord-sheet-heading"><span>CHORD &amp; LYRIC SHEET</span><h4>{title}</h4><p>時間に沿ってコードと歌詞を表示</p></div>
    {sorted.length ? <div className="chord-timeline-scroll" ref={viewport}><div className="chord-timeline" style={{ width }}>
      <div className="chord-time-ruler">{Array.from({ length: Math.ceil(seconds / 2) + 1 }, (_, index) => <span key={index} style={{ left: xFor(index * 2) }}>{Math.floor(index * 2 / 60)}:{String(index * 2 % 60).padStart(2, '0')}</span>)}</div>
      <div className="chord-timeline-track"><span className="timeline-track-label">コード</span>{chordItems.map(({ event, x, lane }) => <div key={event.id} className="timeline-chord" style={{ left: x, top: lane * 138 }} title={`${event.chord} · ${event.time_seconds.toFixed(1)}秒`}>{event.chord === 'N.C.' ? <div className="timeline-rest"><strong>N.C.</strong><span>休</span></div> : <ChordDiagram chord={event.chord} frets={event.frets}/>}</div>)}</div>
      <div className="chord-lyric-track"><span className="timeline-track-label">歌詞</span>{lyricItems.map(({ event, x, lane, span }) => <div key={event.id} className="timeline-lyric" style={{ left: x, top: lane * 50, width: span }} title={`${event.time_seconds.toFixed(1)}秒`}>{event.lyric}</div>)}</div>
      {playhead !== undefined && (playing || playhead > 0) && <div className="chord-timeline-playhead" style={{ left: xFor(playhead) }} aria-label={`再生位置 ${playhead.toFixed(1)}秒`}/>}
    </div></div> : <div className="chord-sheet-empty">コードと歌詞を追加すると、ここに譜面として並びます。</div>}
  </div>
}

export function ChartEditor({ events, lyrics = [], title, playhead, duration, playing, onSave }: {
  events: ChartEvent[], lyrics?: LyricPhrase[], title: string, playhead: number, duration: number, playing: boolean,
  onSave: (events: ChartEvent[]) => Promise<void>,
}) {
  const [draft, setDraft] = useState<ChartEvent[]>(() => alignLyrics(events, lyrics))
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(() => alignLyrics(events, lyrics) !== events)
  const [error, setError] = useState('')
  function change(id: string, patch: Partial<ChartEvent>) {
    setDraft(current => current.map(event => event.id === id ? { ...event, ...patch } : event))
    setDirty(true)
  }
  function add() {
    const time = Math.min(duration, Math.max(0, Math.round(playhead * 10) / 10))
    setDraft(current => [...current, { id: crypto.randomUUID(), time_seconds: time, chord: 'G', lyric: '', frets: shapeFor('G') }])
    setDirty(true)
  }
  async function save() {
    setSaving(true); setError('')
    try { await onSave([...draft].sort((a, b) => a.time_seconds - b.time_seconds)); setDirty(false) }
    catch (reason) { setError((reason as Error).message) }
    finally { setSaving(false) }
  }
  return <div className="chart-editor">
    <div className="chart-editor-intro"><strong>歌詞とコード進行</strong><p>和声パートから推定したコードと歌詞の候補です。コード名・時刻・押さえ方を修正して保存すると、伴奏 TAB と試聴音声にも反映されます。フレットは低音弦から高音弦の順です。</p></div>
    <ChordSheet events={draft} title={title} playhead={playhead} duration={duration} playing={playing}/>
    <div className="chart-controls"><button onClick={add}><Plus size={15}/> 再生位置に追加</button><button className="chart-save" onClick={save} disabled={!dirty || saving}><Save size={15}/> {saving ? '保存中...' : '変更を保存'}</button></div>
    {error && <div className="chart-error">{error}</div>}
    <div className="chart-event-list">{draft.map(event => <div className="chart-event-row" key={event.id}>
      <label>秒<input aria-label="配置時刻" type="number" min="0" max={duration} step="0.1" value={event.time_seconds} onChange={e => change(event.id, { time_seconds: Number(e.target.value) })}/></label>
      <label>コード<input aria-label="コード名" value={event.chord} maxLength={40} onChange={e => change(event.id, { chord: e.target.value, frets: Object.hasOwn(SHAPES, e.target.value.trim()) ? shapeFor(e.target.value) : event.frets })}/></label>
      <label className="chart-lyric-field">歌詞<input aria-label="歌詞" value={event.lyric} maxLength={240} onChange={e => change(event.id, { lyric: e.target.value })}/></label>
      <div className="chart-fret-field"><span>フレット <small>6→1弦 · ×はミュート</small></span><div className="chart-fret-inputs">{event.frets.map((fret, index) => <select key={index} aria-label={`${6 - index}弦のフレット`} value={fret} onChange={e => change(event.id, { frets: event.frets.map((value, i) => i === index ? Number(e.target.value) : value) })}>{Array.from({ length: 26 }, (_, value) => <option key={value} value={value - 1}>{value === 0 ? '×' : value - 1}</option>)}</select>)}</div></div>
      <button className="chart-remove" aria-label="コードを削除" title="コードを削除" onClick={() => { setDraft(current => current.filter(item => item.id !== event.id)); setDirty(true) }}><Trash2 size={16}/></button>
    </div>)}</div>
  </div>
}
