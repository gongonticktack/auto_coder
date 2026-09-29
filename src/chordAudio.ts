import type { ChartEvent } from './types'

const SAMPLE_RATE = 22050
const SAMPLE_ROOT = '/samples/acoustic-guitar'
const sampleCache = new Map<number, Promise<Float32Array>>()
let manifestCache: Promise<number[]> | null = null

function readSamples(buffer: ArrayBuffer): Float32Array {
  const view = new DataView(buffer)
  const text = (offset: number) => String.fromCharCode(...new Uint8Array(buffer, offset, 4))
  if (text(0) !== 'RIFF' || text(8) !== 'WAVE') throw new Error('ギター音源の形式が正しくありません。')
  let dataOffset = -1
  let dataLength = 0
  let format = 0
  let channels = 0
  let rate = 0
  for (let offset = 12; offset + 8 <= buffer.byteLength;) {
    const size = view.getUint32(offset + 4, true)
    if (text(offset) === 'fmt ') {
      format = view.getUint16(offset + 8, true)
      channels = view.getUint16(offset + 10, true)
      rate = view.getUint32(offset + 12, true)
    } else if (text(offset) === 'data') {
      dataOffset = offset + 8
      dataLength = size
      break
    }
    offset += 8 + size + (size & 1)
  }
  if (format !== 1 || channels !== 1 || rate !== SAMPLE_RATE || dataOffset < 0) {
    throw new Error('ギター音源を読み込めませんでした。')
  }
  const count = Math.min(Math.floor(dataLength / 2), Math.floor((buffer.byteLength - dataOffset) / 2))
  const samples = new Float32Array(count)
  for (let i = 0; i < count; i++) samples[i] = view.getInt16(dataOffset + i * 2, true) / 32768
  return samples
}

async function availableSamples(): Promise<number[]> {
  manifestCache ??= fetch(`${SAMPLE_ROOT}/manifest.json`).then(async response => {
    if (!response.ok) throw new Error('ギター音源一覧を読み込めませんでした。')
    return await response.json() as number[]
  })
  return manifestCache
}

function sampleFor(pitch: number, available: number[]): number {
  return available.reduce((nearest, candidate) =>
    Math.abs(candidate - pitch) < Math.abs(nearest - pitch) ? candidate : nearest, available[0])
}

function loadSample(pitch: number): Promise<Float32Array> {
  let pending = sampleCache.get(pitch)
  if (!pending) {
    pending = fetch(`${SAMPLE_ROOT}/${pitch}.wav`).then(async response => {
      if (!response.ok) throw new Error(`ギター音源 ${pitch} を読み込めませんでした。`)
      return readSamples(await response.arrayBuffer())
    })
    sampleCache.set(pitch, pending)
  }
  return pending
}

function writeWav(left: Float32Array, right: Float32Array): Blob {
  const length = left.length
  const bytes = new ArrayBuffer(44 + length * 4)
  const view = new DataView(bytes)
  const label = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)) }
  label(0, 'RIFF'); view.setUint32(4, 36 + length * 4, true); label(8, 'WAVE')
  label(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true)
  view.setUint16(22, 2, true); view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE * 4, true); view.setUint16(32, 4, true); view.setUint16(34, 16, true)
  label(36, 'data'); view.setUint32(40, length * 4, true)
  let peak = 0
  for (let i = 0; i < length; i++) peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]))
  const scale = peak ? .9 / peak : 1
  for (let i = 0; i < length; i++) {
    view.setInt16(44 + i * 4, Math.round(Math.max(-1, Math.min(1, left[i] * scale)) * 32767), true)
    view.setInt16(46 + i * 4, Math.round(Math.max(-1, Math.min(1, right[i] * scale)) * 32767), true)
  }
  return new Blob([bytes], { type: 'audio/wav' })
}

/** Use recorded CC0 nylon-guitar notes to play each saved fret shape. */
export async function renderChordAudio(events: ChartEvent[], tuning: number[], duration: number): Promise<Blob> {
  const available = await availableSamples()
  if (!available.length) throw new Error('ギター音源がありません。')
  const chords = events.filter(event => event.chord.trim() && event.chord !== 'N.C.' && event.frets.some(fret => fret >= 0))
  const pitches = new Set<number>()
  for (const event of chords) for (let string = 0; string < 6; string++) {
    if (event.frets[string] >= 0) pitches.add(sampleFor(tuning[5 - string] + event.frets[string], available))
  }
  await Promise.all([...pitches].map(loadSample))
  const length = Math.max(1, Math.ceil(duration * SAMPLE_RATE))
  const left = new Float32Array(length)
  const right = new Float32Array(length)
  for (const event of chords) {
    if (!Number.isFinite(event.time_seconds) || event.time_seconds < 0 || event.time_seconds >= duration) continue
    let played = 0
    for (let string = 0; string < 6; string++) {
      const fret = event.frets[string]
      if (!Number.isInteger(fret) || fret < 0 || fret > 24) continue
      const pitch = tuning[5 - string] + fret
      const recordedPitch = sampleFor(pitch, available)
      const sample = await loadSample(recordedPitch)
      const rate = Math.pow(2, (pitch - recordedPitch) / 12)
      const start = Math.round((event.time_seconds + played * .025) * SAMPLE_RATE)
      const count = Math.min(Math.ceil(sample.length / rate), Math.round(SAMPLE_RATE * 3.5), length - start)
      const pan = (string - 2.5) * .075
      const gainLeft = .27 * Math.sqrt((1 - pan) / 2)
      const gainRight = .27 * Math.sqrt((1 + pan) / 2)
      for (let i = 0; i < count; i++) {
        const position = i * rate
        const at = Math.floor(position)
        const value = (sample[at] || 0) * (1 - (position - at)) + (sample[at + 1] || 0) * (position - at)
        const fade = Math.min(1, i / (SAMPLE_RATE * .007)) * Math.min(1, (count - i) / (SAMPLE_RATE * .08))
        left[start + i] += value * fade * gainLeft
        right[start + i] += value * fade * gainRight
      }
      played++
    }
  }
  // A short, quiet room reflection gives the recorded notes a shared space.
  for (const [delay, gain] of [[.043, .075], [.081, .045], [.137, .025]]) {
    const offset = Math.round(delay * SAMPLE_RATE)
    for (let i = length - 1; i >= offset; i--) {
      left[i] += right[i - offset] * gain
      right[i] += left[i - offset] * gain
    }
  }
  return writeWav(left, right)
}
