import { useEffect, useState, type ReactNode } from 'react'
import { api, md, ZONE_COLORS } from '../lib/util'

// Responses kept in memory: revisiting a page renders instantly from here while it refreshes.
const cache = new Map<string, unknown>()
const inflight = new Map<string, Promise<unknown>>()

function load<T>(path: string): Promise<T> {
  if (!inflight.has(path)) {
    inflight.set(path, api<T>(path).then(d => { cache.set(path, d); return d }).finally(() => inflight.delete(path)))
  }
  return inflight.get(path) as Promise<T>
}

/** Warm the cache in the background (e.g. all pages right after the app opens). */
export function prefetch(...paths: string[]) {
  paths.forEach(p => { if (!cache.has(p)) load(p).catch(() => {}) })
}

/** Fetch JSON from the API; shows cached data at once and re-fetches when `key` changes. */
export function useApi<T = any>(path: string | null, key: unknown = path) {
  const [data, setState] = useState<T | null>(() => (path ? (cache.get(path) as T) ?? null : null))
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!path) return
    let live = true
    setError(null)
    if (cache.has(path)) setState(cache.get(path) as T)
    load<T>(path).then(d => live && setState(d)).catch(e => live && setError(String(e)))
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  // local updates (e.g. an optimistic move) also go into the cache
  const setData = (d: T | null) => { if (path && d) cache.set(path, d); setState(d) }
  return { data, error, setData }
}

export function Loading({ error }: { error?: string | null }) {
  return <div className="loading">{error ? `Couldn't load: ${error}` : 'Loading…'}</div>
}

export function Card({ title, right, span, className = '', onClick, children }:
  { title?: ReactNode; right?: ReactNode; span?: number; className?: string; onClick?: () => void; children: ReactNode }) {
  return (
    <div className={`card ${span ? 's' + span : ''} ${onClick ? 'click' : ''} ${className}`} onClick={onClick}>
      {(title || right) && <h3><span>{title}</span>{right && <span>{right}</span>}</h3>}
      {children}
    </div>
  )
}

export function ZBar({ zones, height }: { zones: number[]; height?: number }) {
  const t = zones.reduce((a, b) => a + b, 0)
  return (
    <div className="zbar" style={height ? { height } : undefined}>
      {t ? zones.map((m, i) => m ? <div key={i} style={{ flex: m / t, background: ZONE_COLORS[i] }} /> : null)
        : <div style={{ flex: 1, background: 'rgba(255,255,255,.08)' }} />}
    </div>
  )
}

export function Md({ text }: { text: string }) {
  return <>{md(text).map((p, i) => typeof p === 'string' ? p : <b key={i} style={{ color: '#fff' }}>{p.b}</b>)}</>
}

export function Draft({ show, label = 'draft' }: { show?: boolean; label?: string }) {
  return show ? <span className="draft">{label}</span> : null
}

export function Seg<T extends string>({ value, options, onChange, small }:
  { value: T; options: [T, string][]; onChange: (v: T) => void; small?: boolean }) {
  return (
    <div className={`seg ${small ? 'small' : ''}`}>
      {options.map(([v, label]) => <button key={v} className={v === value ? 'on' : ''} onClick={() => onChange(v)}>{label}</button>)}
    </div>
  )
}

/** Planned-workout structure as rising blocks (used on Today and in Library). */
export function Blocks({ steps, height = 92 }: { steps: [number, string][]; height?: number }) {
  const total = steps.reduce((a, s) => a + s[0], 0) || 1
  const h: Record<string, number> = { hard: 92, moderate: 66, easy: 42, rest: 30 }
  const bg: Record<string, string> = {
    hard: 'linear-gradient(#ffb86b,#ff7a59)', moderate: 'linear-gradient(#f7d77a,#e0a948)',
    easy: 'linear-gradient(#7de8c8,#3fbf99)', rest: 'rgba(255,255,255,.16)',
  }
  return (
    <div className="blocks" style={{ height }}>
      {steps.map(([m, k], i) => <div key={i} style={{ flex: m / total, height: `${h[k] ?? 40}%`, background: bg[k] }} />)}
    </div>
  )
}

export const RATING: Record<string, [string, string]> = {
  on_target: ['On target', '#5ef2c4'], easier: ['Easier than planned', '#8aa8ff'], harder: ['Harder than planned', '#ff9f6b'],
  missed: ['Missed the mark', '#ff7a7a'], test: ['Test', '#c79bff'], unplanned: ['Unplanned', '#8b8b97'],
}

/** A coach report from reports/workouts: verdict, rating, flags and its short markdown body. */
export function Analysis({ a }: { a: any }) {
  const [label, color] = RATING[a.rating] ?? ['', '#8b8b97']
  return <>
    <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 14, marginBottom: 12 }}>
      <div style={{ fontSize: 19, fontWeight: 500, letterSpacing: '-.015em', lineHeight: 1.3 }}>{a.title}</div>
      <div className="chips" style={{ flex: 'none' }}>
        {label && <span className="chip" style={{ color, background: color + '1f' }}><span className="dot" style={{ background: color }} />{label}</span>}
        {a.flags?.map((f: string) => <span key={f} className="chip" style={{ color: '#f7c76a' }}>{f.replace(/_/g, ' ')}</span>)}
      </div>
    </div>
    <div className="report">{a.body.split(/\n\s*\n|\n(?=\s*- )/).map((p: string, i: number) => {
      const m = p.trim().match(/^-\s*(✓|→|!)?\s*(.*)$/s)
      if (!m) return <p key={i}><Md text={p.trim()} /></p>
      const kind = m[1] === '✓' ? 'ok' : m[1] === '!' ? 'warn' : m[1] === '→' ? 'next' : ''
      return <div key={i} className={`bullet ${kind}`}><span className="ic">{m[1] ?? '•'}</span><span><Md text={m[2]} /></span></div>
    })}</div>
  </>
}
