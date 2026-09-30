export type Note = {
  id: string
  pitch: number
  onset_seconds: number
  offset_seconds: number
  confidence: number
  string: number
  fret: number
  technique: string
  source_model: string
}

export type ChartEvent = {
  id: string
  time_seconds: number
  chord: string
  lyric: string
  frets: number[]
}

export type LyricPhrase = { start_seconds: number, end_seconds: number, text: string }

export type Job = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  error: string | null
  title: string
  part?: string
  duration_seconds: number | null
  start_seconds: number
  end_seconds: number | null
  tuning: number[]
  bpm?: number | null
  beat_times?: number[]
  notes: Note[]
  chart_events?: ChartEvent[]
  lyrics?: LyricPhrase[]
  lyrics_error?: string | null
  audio_url: string | null
  stem_url: string | null
  harmony_url?: string | null
  vocal_url?: string | null
  backing_url?: string | null
}

export const TUNINGS: Record<string, number[]> = {
  'Standard E': [64, 59, 55, 50, 45, 40],
  'Drop D': [64, 59, 55, 50, 45, 38],
  'Half step down': [63, 58, 54, 49, 44, 39],
  'Open G': [62, 59, 55, 50, 43, 38],
}

export const TUNING_LABELS: Record<string, string[]> = {
  'Standard E': ['e', 'B', 'G', 'D', 'A', 'E'],
  'Drop D': ['e', 'B', 'G', 'D', 'A', 'D'],
  'Half step down': ['e♭', 'B♭', 'G♭', 'D♭', 'A♭', 'E♭'],
  'Open G': ['D', 'B', 'G', 'D', 'G', 'D'],
}

export function pitchName(pitch: number) {
  const names = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B']
  return `${names[pitch % 12]}${Math.floor(pitch / 12) - 1}`
}
