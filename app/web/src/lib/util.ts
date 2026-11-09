// Formatting helpers and small shared lookups.

export const SPORT: Record<string, [string, string]> = {
  run: ['Run', 'var(--run)'], ride: ['Ride', 'var(--ride)'], swim: ['Swim', 'var(--swim)'], row: ['Row', 'var(--row)'],
  str: ['Strength', 'var(--str)'], other: ['Other', 'var(--other)'], rest: ['Rest', '#666'],
}
export const ZONE_COLORS = ['var(--z1)', 'var(--z2)', 'var(--z3)', 'var(--z4)', 'var(--z5)', 'var(--z6)', 'var(--z7)']
/** Fallback names; intervals.icu sends its own per sport. */
export const DEFAULT_ZONE_NAMES = ['Recovery', 'Aerobic', 'Tempo', 'SubThreshold', 'SuperThreshold', 'Aerobic Capacity', 'Anaerobic']

export const pace = (p?: number | null) => {
  if (!p) return '–'
  const m = Math.floor(p), s = Math.round((p - m) * 60)
  return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, '0')}`
}

export const dur = (min: number) => {
  const m = Math.round(min)
  return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}` : `${m}′`
}

export const fd = (d: string, o: Intl.DateTimeFormatOptions = { weekday: 'short' }) =>
  new Date(d + 'T12:00').toLocaleDateString('en-GB', o)

export const addDays = (d: string, n: number) => {
  const x = new Date(d + 'T12:00'); x.setDate(x.getDate() + n); return x.toISOString().slice(0, 10)
}

export const isoWeekNo = (d: string) => {
  const x = new Date(d + 'T12:00'); x.setDate(x.getDate() + 3 - ((x.getDay() + 6) % 7))
  const w1 = new Date(x.getFullYear(), 0, 4)
  return 1 + Math.round(((x.getTime() - w1.getTime()) / 864e5 - 3 + ((w1.getDay() + 6) % 7)) / 7)
}

/** Render **bold** markers from backend text as <b>. */
export const md = (s: string) => s.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? { b: part } : part))

export const rolling = (v: (number | null)[], n: number) => v.map((_, i) => {
  const w = v.slice(Math.max(0, i - n + 1), i + 1).filter((x): x is number => x != null)
  return w.length ? w.reduce((a, b) => a + b, 0) / w.length : null
})

export const glowFor = (score?: number | null) => (score == null ? 158 : score >= 60 ? 158 : score >= 40 ? 42 : 8)

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api' + path, init)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}
