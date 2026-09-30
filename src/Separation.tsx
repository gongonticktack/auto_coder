import { useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, AudioLines, Check, CloudUpload, FileAudio, LoaderCircle, Music2, Sparkles } from 'lucide-react'
import './separation.css'

type Stem = 'vocals' | 'bass' | 'drums' | 'guitar' | 'piano' | 'other'
type SeparationJob = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  error: string | null
  title: string
  stems: Partial<Record<Stem, string>>
}

const stems: { key: Stem, label: string, detail: string }[] = [
  { key: 'vocals', label: 'ボーカル', detail: '歌声' },
  { key: 'bass', label: 'ベース', detail: 'ベースギターなどの低音' },
  { key: 'drums', label: 'ドラム', detail: 'ドラム・打楽器' },
  { key: 'guitar', label: 'ギター', detail: 'ギター' },
  { key: 'piano', label: 'ピアノ', detail: 'ピアノ・鍵盤' },
  { key: 'other', label: 'その他', detail: '上記以外の楽器が混ざるパート' },
]

export function Separation() {
  const [file, setFile] = useState<File | null>(null)
  const [job, setJob] = useState<SeparationJob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const busy = uploading || job?.status === 'queued' || job?.status === 'running'

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return
    let cancelled = false
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/separations/${job.id}`)
        if (!response.ok) throw new Error('分離の状態を取得できませんでした。')
        const updated = await response.json() as SeparationJob
        if (!cancelled) { setJob(updated); setError(null) }
      } catch (cause) {
        if (!cancelled) setError((cause as Error).message)
      }
    }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [job?.id, job?.status])

  function chooseFile(chosen: File | null) {
    if (!chosen) return
    if (!/\.(wav|mp3|m4a|flac|ogg|aac)$/i.test(chosen.name)) {
      setError('WAV、MP3、M4A、FLAC、OGG、AAC の音声ファイルを選んでください。')
      return
    }
    if (chosen.size > 100 * 1024 * 1024) {
      setError('音源は 100 MB 以下にしてください。')
      return
    }
    setFile(chosen)
    setError(null)
  }

  async function start() {
    if (!file) { input.current?.click(); return }
    const form = new FormData()
    form.append('file', file)
    setUploading(true)
    setError(null)
    try {
      const response = await fetch('/api/separations', { method: 'POST', body: form })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || '分離を開始できませんでした。')
      setJob(body as SeparationJob)
    } catch (cause) {
      setError(`音源を送信できませんでした。${(cause as Error).message}`)
    } finally { setUploading(false) }
  }

  return <div className="separation-page">
    <div className="page-intro separation-intro"><div><div className="eyebrow"><span className="eyebrow-line"/> AUDIO TO STEMS</div><h1>音源を、<em>パートごとに。</em></h1><p>音源を6つのパートに分離して、各パートを MP3 で保存できます。</p></div><div className="separation-art" aria-hidden="true"><AudioLines size={74} strokeWidth={1.2}/></div></div>
    <section className="create-panel separation-upload"><div className="panel-heading"><div className="heading-icon"><Music2 size={18}/></div><div><h2>音源を分離</h2><p>分離したい音声ファイルを選択してください</p></div><span className="step-pill">01 / UPLOAD</span></div>
      <div className={`upload-zone separation-drop ${file ? 'has-file' : ''}`} role="button" tabIndex={0} onClick={() => input.current?.click()} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.current?.click() } }} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]) }}><input ref={input} type="file" accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg,.aac" hidden onChange={event => chooseFile(event.target.files?.[0] || null)}/><span className="upload-icon">{file ? <FileAudio size={23}/> : <CloudUpload size={23}/>}</span><div><strong>{file?.name || '音源ファイルをドロップ'}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · クリックして変更` : 'またはクリックしてファイルを選択'}</span></div><small>WAV, MP3, M4A, FLAC, OGG, AAC · 最大 100 MB</small></div>
      <div className="separation-submit"><p>ボーカル、ベース、ドラム、ギター、ピアノ、その他に分離します。</p><button className="generate-button" onClick={start} disabled={busy}>{busy ? <LoaderCircle className="spin" size={18}/> : <Sparkles size={18}/>} {busy ? '分離中...' : '分離を開始'}</button></div>
      {error && <div className="separation-error" role="alert">{error}</div>}
    </section>
    {job && <section className="session-card separation-result"><div className="separation-result-head"><div><span className="eyebrow">02 / STEMS</span><h2>{job.title}</h2><p>{job.status === 'completed' ? '各パートを試聴して MP3 をダウンロードできます。' : job.status === 'failed' ? '分離に失敗しました。' : job.stage}</p></div><span className={`status-chip ${job.status === 'failed' ? 'failed' : job.status === 'completed' ? '' : 'working'}`}>{job.status === 'completed' ? <Check size={11}/> : job.status === 'failed' ? 'FAILED' : <LoaderCircle size={11} className="spin"/>}{job.status === 'completed' ? ' READY' : job.status === 'failed' ? '' : ` ${job.progress}%`}</span></div>
      {job.status === 'failed' && <div className="error-state">{job.error || '音源を分離できませんでした。'}</div>}
      {(job.status === 'queued' || job.status === 'running') && <div className="separation-progress"><div className="progress-track"><span style={{ width: `${job.progress}%` }}/></div><small>長い音源や CPU での処理には時間がかかります。</small></div>}
      {job.status === 'completed' && <div className="stem-grid">{stems.map(({ key, label, detail }) => <div className="stem-card" key={key}><div className="stem-card-title"><span className="stem-icon"><AudioLines size={17}/></span><div><strong>{label}</strong><small>{detail}</small></div></div><audio controls preload="none" src={job.stems[key]} aria-label={`${label}を試聴`}/><a className="stem-download" href={job.stems[key]} download={`${job.title}-${key}.mp3`}><ArrowDownToLine size={15}/> MP3 をダウンロード</a></div>)}</div>}
    </section>}
    <p className="separation-note">「その他」は複数の楽器が混ざる場合があります。分離結果は音源によって異なります。</p>
  </div>
}
