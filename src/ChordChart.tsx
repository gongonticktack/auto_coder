import { useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import type { ChartEvent } from './types'

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

export function ChordSheet({ events, title }: { events: ChartEvent[], title: string }) {
  const sorted = [...events].sort((a, b) => a.time_seconds - b.time_seconds)
  return <div className="chord-sheet">
    <div className="chord-sheet-heading"><span>CHORD &amp; LYRIC SHEET</span><h4>{title}</h4><p>コード図の下に歌詞を配置 · 音符と同じ時間軸</p></div>
    {sorted.length ? <div className="chord-sheet-grid">{sorted.map(event => <div className="chord-sheet-cell" key={event.id}>
      <ChordDiagram chord={event.chord} frets={event.frets}/><div className="chord-lyric">{event.lyric || '\u00a0'}</div>
    </div>)}</div> : <div className="chord-sheet-empty">コードと歌詞を追加すると、ここに譜面として並びます。</div>}
  </div>
}

export function ChartEditor({ events, title, playhead, duration, onSave }: {
  events: ChartEvent[], title: string, playhead: number, duration: number,
  onSave: (events: ChartEvent[]) => Promise<void>,
}) {
  const [draft, setDraft] = useState<ChartEvent[]>(events)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
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
    <div className="chart-editor-intro"><strong>歌詞とコード図</strong><p>音源から推定した歌詞と基本コードの候補です。聴き比べて修正できます。フレットは低音弦から高音弦の順です。タブを切り替える前に変更を保存してください。</p></div>
    <ChordSheet events={draft} title={title}/>
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
